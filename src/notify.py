from __future__ import annotations

import argparse
import base64
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import load_config
from .models import DailyReport, RunMetadata
from .report import split_sections
from .utils import ensure_relative_url_base


ROOT = Path(__file__).resolve().parents[1]


class NotificationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify the user about a generated report")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--metadata", default=str(ROOT / "run_metadata.json"))
    parser.add_argument("--page-url", default=os.getenv("PAGE_URL", ""))
    return parser.parse_args()


def _github_request(
    method: str,
    endpoint: str,
    token: str,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    response = requests.request(
        method,
        f"https://api.github.com{endpoint}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "daily-math-ds-digest",
        },
        json=payload,
        params=params,
        timeout=45,
    )
    if response.status_code >= 400:
        raise NotificationError(
            f"GitHub API {method} {endpoint} failed: {response.status_code} {response.text[:500]}"
        )
    if not response.content:
        return None
    return response.json()


def _find_or_create_notification_issue(
    repository: str,
    owner: str,
    token: str,
    title: str,
) -> int:
    issues = _github_request(
        "GET",
        f"/repos/{repository}/issues",
        token,
        params={"state": "open", "per_page": 100},
    )
    for issue in issues:
        if "pull_request" not in issue and issue.get("title") == title:
            return int(issue["number"])

    body = (
        f"@{owner}\n\n"
        "This persistent issue is the notification channel for the automated daily math.DS digest. "
        "A new comment is added for each generated report. Keep this issue subscribed and make sure "
        "GitHub email notifications are enabled."
    )
    payload: dict[str, Any] = {"title": title, "body": body}
    if owner:
        payload["assignees"] = [owner]
    try:
        created = _github_request(
            "POST", f"/repos/{repository}/issues", token, payload=payload
        )
    except NotificationError:
        # Organization repositories may not allow assigning the owner account.
        payload.pop("assignees", None)
        created = _github_request(
            "POST", f"/repos/{repository}/issues", token, payload=payload
        )
    return int(created["number"])


def _github_comment_exists(
    repository: str,
    issue_number: int,
    token: str,
    marker: str,
) -> bool:
    comments = _github_request(
        "GET",
        f"/repos/{repository}/issues/{issue_number}/comments",
        token,
        params={"per_page": 100, "page": 1},
    )
    return any(marker in (comment.get("body") or "") for comment in comments)


def send_github_issue_notification(
    report: DailyReport,
    config: dict[str, Any],
    report_url: str,
    pdf_url: str,
) -> bool:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    owner = os.getenv("GITHUB_REPOSITORY_OWNER", "").strip()
    if not token or not repository:
        print("GitHub issue notification skipped: GITHUB_TOKEN or GITHUB_REPOSITORY is absent.")
        return False

    issue_title = str(
        config["notifications"].get(
            "github_issue_title", "Daily math.DS Digest notifications"
        )
    )
    issue_number = _find_or_create_notification_issue(
        repository=repository,
        owner=owner,
        token=token,
        title=issue_title,
    )
    marker = f"<!-- math-ds-digest:{report.report_date} -->"
    if _github_comment_exists(repository, issue_number, token, marker):
        print(f"GitHub notification already exists for {report.report_date}; skipping duplicate.")
        return True

    sections = split_sections(report)
    top = (sections["high"] + sections["related"])[:5]
    lines = [
        marker,
        f"## math.DS digest - {report.report_date}",
        "",
        f"**{report.counts.get('HIGH PRIORITY', 0)} high priority** · "
        f"**{report.counts.get('RELATED / POSSIBLY INTERESTING', 0)} related** · "
        f"**{report.counts.get('LOW PRIORITY', 0)} low priority**",
        "",
        report.overview,
        "",
    ]
    if top:
        lines.append("### Top matches")
        for item in top:
            lines.append(f"- [{item.paper.title}]({item.paper.abstract_url})")
        lines.append("")
    lines.extend(
        [
            f"[Read the HTML report]({report_url}) · [Download the PDF]({pdf_url})",
        ]
    )
    _github_request(
        "POST",
        f"/repos/{repository}/issues/{issue_number}/comments",
        token,
        payload={"body": "\n".join(lines)},
    )
    print(f"Posted GitHub issue notification in #{issue_number}.")
    return True


def _email_recipients() -> list[str]:
    raw = os.getenv("EMAIL_TO", "")
    normalized = raw.replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _render_email(
    report: DailyReport,
    report_url: str,
    pdf_url: str,
) -> str:
    environment = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
    )
    sections = split_sections(report)
    counts = {
        "high": report.counts.get("HIGH PRIORITY", 0),
        "related": report.counts.get("RELATED / POSSIBLY INTERESTING", 0),
        "low": report.counts.get("LOW PRIORITY", 0),
    }
    return environment.get_template("email.html.j2").render(
        report=report,
        counts=counts,
        top_papers=(sections["high"] + sections["related"])[:5],
        report_url=report_url,
        pdf_url=pdf_url,
    )


def _plain_email_text(report: DailyReport, report_url: str, pdf_url: str) -> str:
    return (
        f"Daily math.DS Digest - {report.report_date}\n\n"
        f"{report.overview}\n\n"
        f"High priority: {report.counts.get('HIGH PRIORITY', 0)}\n"
        f"Related: {report.counts.get('RELATED / POSSIBLY INTERESTING', 0)}\n"
        f"Low priority: {report.counts.get('LOW PRIORITY', 0)}\n\n"
        f"HTML report: {report_url}\n"
        f"PDF: {pdf_url}\n"
    )


def send_resend_email(
    report: DailyReport,
    pdf_path: Path,
    report_url: str,
    pdf_url: str,
) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return False

    recipients = _email_recipients()
    sender = os.getenv("EMAIL_FROM", "").strip()
    if not recipients or not sender:
        raise NotificationError(
            "RESEND_API_KEY is set, but EMAIL_TO or EMAIL_FROM is missing."
        )

    html_body = _render_email(report, report_url, pdf_url)
    encoded_pdf = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    payload = {
        "from": sender,
        "to": recipients,
        "subject": f"math.DS digest - {report.report_date}",
        "html": html_body,
        "text": _plain_email_text(report, report_url, pdf_url),
        "attachments": [
            {
                "filename": pdf_path.name,
                "content": encoded_pdf,
            }
        ],
    }
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"math-ds-digest-{report.report_date}",
        },
        data=json.dumps(payload),
        timeout=60,
    )
    if response.status_code >= 400:
        raise NotificationError(
            f"Resend failed: {response.status_code} {response.text[:500]}"
        )
    print(f"Sent PDF email via Resend to {', '.join(recipients)}.")
    return True


def send_smtp_email(
    report: DailyReport,
    pdf_path: Path,
    report_url: str,
    pdf_url: str,
) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return False

    recipients = _email_recipients()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("EMAIL_FROM", "").strip() or username
    if not recipients or not sender:
        raise NotificationError("SMTP_HOST is set, but EMAIL_TO or EMAIL_FROM is missing.")

    security = os.getenv("SMTP_SECURITY", "starttls").strip().lower()
    default_port = 465 if security == "ssl" else 587
    port = int(os.getenv("SMTP_PORT", str(default_port)))

    message = EmailMessage()
    message["Subject"] = f"math.DS digest - {report.report_date}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(_plain_email_text(report, report_url, pdf_url))
    message.add_alternative(_render_email(report, report_url, pdf_url), subtype="html")
    message.add_attachment(
        pdf_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )

    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=60) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.ehlo()
            if security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)

    print(f"Sent PDF email via SMTP to {', '.join(recipients)}.")
    return True


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    metadata = RunMetadata.model_validate_json(Path(args.metadata).read_text(encoding="utf-8"))
    report = DailyReport.model_validate_json(Path(metadata.report_json).read_text(encoding="utf-8"))

    if not metadata.report_changed:
        print("Report is unchanged; no notification will be sent.")
        return 0
    if not report.papers and not bool(config["notifications"].get("send_on_no_papers", True)):
        print("No papers and send_on_no_papers is disabled; no notification will be sent.")
        return 0

    page_url = args.page_url.strip()
    if not page_url:
        raise NotificationError("The GitHub Pages deployment URL is missing.")
    page_url = ensure_relative_url_base(page_url)
    report_url = urljoin(page_url, f"reports/{report.report_date}/")
    pdf_url = urljoin(report_url, Path(metadata.report_pdf).name)
    pdf_path = Path(metadata.report_pdf)
    if not pdf_path.exists():
        raise NotificationError(f"Generated PDF not found: {pdf_path}")

    successes: list[str] = []
    errors: list[str] = []

    if bool(config["notifications"].get("github_issue", True)):
        try:
            if send_github_issue_notification(report, config, report_url, pdf_url):
                successes.append("github")
        except Exception as exc:
            errors.append(f"GitHub notification: {exc}")

    if bool(config["notifications"].get("email_enabled", True)):
        try:
            if send_resend_email(report, pdf_path, report_url, pdf_url):
                successes.append("resend")
            elif send_smtp_email(report, pdf_path, report_url, pdf_url):
                successes.append("smtp")
            else:
                print("Direct email is not configured; relying on GitHub issue notifications.")
        except Exception as exc:
            errors.append(f"Email notification: {exc}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        # Mark the workflow failed when an explicitly configured channel fails.
        raise NotificationError("; ".join(errors))
    if not successes:
        raise NotificationError(
            "No notification channel succeeded. Enable GitHub issue notifications or configure email."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

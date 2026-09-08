"""Read committed reports and post/update the persistent GitHub Issue notification."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin

import requests

from .config import load_config
from .models import DailyReport
from .utils import ensure_relative_url_base

ROOT = Path(__file__).resolve().parents[1]


class NotificationError(RuntimeError):
    pass


def latest_report(data_dir: Path, site_dir: Path) -> DailyReport | None:
    paths = sorted((data_dir / "reports").glob("*.json"), reverse=True)
    if not paths:
        return None
    path = paths[0]
    report = DailyReport.model_validate_json(path.read_text(encoding="utf-8"))
    if path.stem != report.report_date:
        raise NotificationError("Committed report filename and report_date differ")
    folder = site_dir / "reports" / report.report_date
    required = (folder / "index.html", folder / "report.json", site_dir / "index.html")
    if not all(item.is_file() and item.stat().st_size > 0 for item in required):
        raise NotificationError(f"Latest committed report is incomplete: {folder}")
    published = DailyReport.model_validate_json((folder / "report.json").read_text(encoding="utf-8"))
    if published != report:
        raise NotificationError("Published JSON does not match the committed report")
    return report


def _github_request(method: str, endpoint: str, token: str,
                    payload: dict[str, Any] | None = None,
                    params: dict[str, Any] | None = None) -> Any:
    response = requests.request(
        method, f"https://api.github.com{endpoint}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "daily-math-ds-digest"},
        json=payload, params=params, timeout=45,
    )
    if response.status_code >= 400:
        raise NotificationError(f"GitHub {method} {endpoint} failed: HTTP {response.status_code}")
    return response.json() if response.content else None


def _pages(endpoint: str, token: str, **params: Any) -> Iterator[dict[str, Any]]:
    page = 1
    while True:
        items = _github_request("GET", endpoint, token,
                                params={**params, "per_page": 100, "page": page})
        yield from items
        if len(items) < 100:
            return
        page += 1


def notification_body(report: DailyReport, page_url: str) -> str:
    archive_url = ensure_relative_url_base(page_url)
    report_url = urljoin(archive_url, f"reports/{report.report_date}/")
    return "\n".join([
        f"<!-- math-ds-digest:{report.report_date} -->",
        f"## math.DS digest - {report.report_date}", "",
        f"**{report.counts.get('HIGH PRIORITY', 0)} high priority** · "
        f"**{report.counts.get('RELATED / POSSIBLY INTERESTING', 0)} related** · "
        f"**{report.counts.get('LOW PRIORITY', 0)} low priority**", "",
        report.overview, "",
        f"[Read the HTML report]({report_url}) · [Browse all report dates]({archive_url})",
    ])


def send_github_issue_notification(report: DailyReport, config: dict[str, Any], body: str) -> None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not token or not repository:
        raise NotificationError("GitHub Actions token and repository are required for notification")
    title = config["notifications"].get("github_issue_title", "Daily math.DS Digest notifications")
    endpoint = f"/repos/{repository}/issues"
    issue = next((item for item in _pages(endpoint, token, state="all")
                  if "pull_request" not in item and item.get("title") == title), None)
    if issue is None:
        issue = _github_request("POST", endpoint, token, payload={
            "title": title,
            "body": "Subscribe to this persistent issue for daily math.DS digest links. "
                    "Each report has one comment, updated when its committed content changes.",
        })
    elif issue.get("state") == "closed":
        _github_request("PATCH", f"{endpoint}/{issue['number']}", token, payload={"state": "open"})
    comments_endpoint = f"{endpoint}/{issue['number']}/comments"
    marker = f"<!-- math-ds-digest:{report.report_date} -->"
    comment = next((item for item in _pages(comments_endpoint, token)
                    if marker in (item.get("body") or "")), None)
    if comment is None:
        _github_request("POST", comments_endpoint, token, payload={"body": body})
    elif comment["body"] != body:
        _github_request("PATCH", f"{endpoint}/comments/{comment['id']}", token, payload={"body": body})
    print(f"GitHub notification is current in issue #{issue['number']}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--site-dir", type=Path, default=ROOT / "site")
    parser.add_argument("--page-url", default=os.getenv("PAGE_URL", ""))
    parser.add_argument("--dry-run", action="store_true", help="Print notification without sending")
    parser.add_argument("--check-only", action="store_true", help="Check committed artifacts without sending")
    args = parser.parse_args()
    config = load_config(args.config)
    latest = latest_report(args.data_dir, args.site_dir)
    if latest is None:
        print("No committed reports yet; notification skipped.")
        return 0
    report = latest
    if args.check_only:
        print(f"Committed report {report.report_date} is complete.")
        return 0
    notifications = config["notifications"]
    if not notifications.get("github_issue", True):
        return 0
    if not report.papers and not notifications.get("send_on_no_papers", True):
        return 0
    if not args.page_url.strip():
        raise NotificationError("The GitHub Pages deployment URL is missing")
    body = notification_body(report, args.page_url.strip())
    if args.dry_run:
        print(body)
    else:
        send_github_issue_notification(report, config, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

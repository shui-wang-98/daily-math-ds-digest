from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .ai import analyze_papers, generate_overview
from .config import load_config
from .fetch_arxiv import fetch_feed
from .models import AnalyzedPaper, DailyReport, RunMetadata
from .report import render_report_files, render_site_index, report_filenames
from .utils import atomic_write_json, read_json, utc_now


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "state.json"
REPORTS_DIR = ROOT / "data" / "reports"
SITE_DIR = ROOT / "site"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
PAPER_PROMPT = ROOT / "prompts" / "paper_analysis.txt"
OVERVIEW_PROMPT = ROOT / "prompts" / "daily_overview.txt"
RUN_METADATA_PATH = ROOT / "run_metadata.json"


PRIORITIES = (
    "HIGH PRIORITY",
    "RELATED / POSSIBLY INTERESTING",
    "LOW PRIORITY",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the daily personalized math.DS digest")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument(
        "--local-feed",
        help="Read RSS XML from a local file instead of fetching arXiv (for tests/demo).",
    )
    parser.add_argument(
        "--mock-ai",
        action="store_true",
        help="Use deterministic fallback analysis instead of calling OpenAI.",
    )
    return parser.parse_args()


def _report_date(_feed_build_at, papers, timezone_name: str) -> str:
    zone = ZoneInfo(timezone_name)
    if papers:
        return papers[0].announced_at.astimezone(zone).date().isoformat()
    # An empty or stale feed should still produce a no-papers report for the
    # local run date, rather than reusing an older feed build date.
    return utc_now().astimezone(zone).date().isoformat()


def _count_priorities(papers: list[AnalyzedPaper]) -> dict[str, int]:
    return {
        priority: sum(item.analysis.priority == priority for item in papers)
        for priority in PRIORITIES
    }


def _load_report(path: Path) -> DailyReport | None:
    if not path.exists():
        return None
    return DailyReport.model_validate_json(path.read_text(encoding="utf-8"))


def _load_all_reports(directory: Path) -> list[DailyReport]:
    reports: list[DailyReport] = []
    for path in sorted(directory.glob("*.json")):
        try:
            reports.append(DailyReport.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"WARNING: skipping invalid report {path}: {exc}")
    return reports


def _write_metadata(
    report: DailyReport,
    created: bool,
    changed: bool,
    config: dict[str, Any],
) -> RunMetadata:
    pdf_name, markdown_name = report_filenames(report.report_date, config)
    metadata = RunMetadata(
        report_date=report.report_date,
        report_created=created,
        report_changed=changed,
        total_new_papers=len(report.papers),
        counts=report.counts,
        report_json=str(REPORTS_DIR / f"{report.report_date}.json"),
        report_html=str(SITE_DIR / "reports" / report.report_date / "index.html"),
        report_pdf=str(SITE_DIR / "reports" / report.report_date / pdf_name),
        report_markdown=str(SITE_DIR / "reports" / report.report_date / markdown_name),
    )
    atomic_write_json(RUN_METADATA_PATH, metadata)
    return metadata


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    arxiv_config = config["arxiv"]

    feed = fetch_feed(
        feed_url=str(arxiv_config["feed_url"]),
        include_types=arxiv_config["include_announce_types"],
        timeout_seconds=int(arxiv_config.get("request_timeout_seconds", 45)),
        user_agent=str(arxiv_config.get("user_agent", "daily-math-ds-digest/1.0")),
        local_xml=args.local_feed,
    )

    date = _report_date(
        feed.build_at,
        feed.papers,
        str(config["project"]["timezone"]),
    )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{date}.json"
    existing_report = _load_report(report_path)
    report_existed = existing_report is not None

    state = read_json(
        STATE_PATH,
        {
            "schema_version": 1,
            "seen": {},
            "last_feed_build": None,
            "updated_at": None,
        },
    )
    seen: dict[str, Any] = state.setdefault("seen", {})
    existing_ids = {
        item.paper.arxiv_id for item in (existing_report.papers if existing_report else [])
    }
    new_papers = [
        paper
        for paper in feed.papers
        if paper.arxiv_id not in seen and paper.arxiv_id not in existing_ids
    ]

    if existing_report is not None and not new_papers:
        # Idempotent rerun: keep generated_at and AI output unchanged.
        report = existing_report
        created = False
        changed = False
        print(f"No unseen papers for {date}; existing report is unchanged.")
    else:
        analyzed_new = analyze_papers(
            new_papers,
            config=config,
            prompt_path=PAPER_PROMPT,
            mock=args.mock_ai,
        )
        combined = list(existing_report.papers) if existing_report else []
        combined.extend(analyzed_new)
        counts = _count_priorities(combined)
        overview = generate_overview(
            combined,
            config=config,
            prompt_path=OVERVIEW_PROMPT,
            mock=args.mock_ai,
        )
        report = DailyReport(
            report_date=date,
            generated_at=utc_now(),
            feed_build_at=feed.build_at,
            category=str(config["project"]["category"]),
            model=str(config["openai"]["model"]),
            overview=overview,
            papers=combined,
            counts=counts,
        )
        previous_serialized = (
            existing_report.model_dump_json(indent=2) if existing_report is not None else None
        )
        current_serialized = report.model_dump_json(indent=2)
        created = not report_existed
        changed = previous_serialized != current_serialized
        atomic_write_json(report_path, report)

        for analyzed in analyzed_new:
            paper = analyzed.paper
            seen[paper.arxiv_id] = {
                "first_seen_report": date,
                "versioned_id": paper.versioned_id,
                "announce_type": paper.announce_type,
                "analysis_status": analyzed.analysis_status,
            }

    state["last_feed_build"] = feed.build_at.isoformat() if feed.build_at else None
    state["updated_at"] = utc_now().isoformat()
    atomic_write_json(STATE_PATH, state)

    pdf_name, markdown_name = report_filenames(report.report_date, config)
    expected_files = [
        SITE_DIR / "reports" / report.report_date / "index.html",
        SITE_DIR / "reports" / report.report_date / pdf_name,
        SITE_DIR / "reports" / report.report_date / markdown_name,
    ]
    if changed or any(not path.exists() for path in expected_files):
        render_report_files(
            report=report,
            config=config,
            template_dir=TEMPLATE_DIR,
            site_dir=SITE_DIR,
        )
    else:
        print("Report files already exist and the report is unchanged; skipping PDF regeneration.")

    all_reports = _load_all_reports(REPORTS_DIR)
    render_site_index(
        reports=all_reports,
        config=config,
        template_dir=TEMPLATE_DIR,
        static_dir=STATIC_DIR,
        site_dir=SITE_DIR,
    )
    metadata = _write_metadata(report, created, changed, config)

    print(
        json.dumps(
            {
                "report_date": metadata.report_date,
                "report_created": metadata.report_created,
                "report_changed": metadata.report_changed,
                "feed_items_included": len(feed.papers),
                "new_papers_analyzed": len(new_papers),
                "counts": metadata.counts,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

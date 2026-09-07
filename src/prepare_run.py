"""Fetch metadata for Codex to analyze, without changing the seen-paper state."""
from __future__ import annotations

import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config
from .fetch_arxiv import fetch_feed
from .models import PendingRun
from .utils import atomic_write_json, base_arxiv_id, read_json, utc_now

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_TYPES = ("new", "cross", "replace-cross")


def prepare_run(
    *, config_path: str | Path = ROOT / "config.yaml",
    data_dir: str | Path = ROOT / "data",
    local_feed: str | Path | None = None,
    report_date: str | None = None,
) -> PendingRun:
    config = load_config(config_path)
    data_dir = Path(data_dir)
    arxiv = config["arxiv"]
    feed = fetch_feed(
        feed_url=arxiv["feed_url"], include_types=INCLUDE_TYPES,
        timeout_seconds=int(arxiv.get("request_timeout_seconds", 45)),
        user_agent=arxiv.get("user_agent", "daily-math-ds-digest/1.0"),
        local_xml=local_feed,
    )
    state = read_json(data_dir / "state.json", {"seen": {}})
    seen = {base_arxiv_id(key) for key in state["seen"]}
    # Collapse repeated announcements of the same base ID in feed order.
    unseen = {}
    for paper in feed.papers:
        if paper.arxiv_id not in seen:
            unseen.setdefault(paper.arxiv_id, paper)
    now = utc_now()
    pending = PendingRun(
        report_date=report_date or now.astimezone(ZoneInfo(config["project"]["timezone"])).date().isoformat(),
        prepared_at=now, feed_build_at=feed.build_at,
        category=config["project"]["category"],
        research_profile=config["research_profile"], papers=list(unseen.values()),
    )
    atomic_write_json(data_dir / "pending_run.json", pending)
    return pending


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--local-feed", help="Offline RSS XML fixture")
    parser.add_argument("--report-date", help="Explicit YYYY-MM-DD (default: local run date)")
    args = parser.parse_args()
    pending = prepare_run(config_path=args.config, data_dir=args.data_dir,
                          local_feed=args.local_feed, report_date=args.report_date)
    print(f"Prepared {pending.report_date}: {len(pending.papers)} unseen papers; state unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

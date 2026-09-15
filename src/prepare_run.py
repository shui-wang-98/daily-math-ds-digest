"""Prepare the oldest unfinished local inbox input; never fetch over the network."""
from __future__ import annotations

import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config
from .fetch_arxiv import fetch_feed
from .inbox import INCLUDE_TYPES, InboxUpToDate, InputNotReady, expected_feed_date, read_inbox
from .models import PendingRun
from .utils import atomic_write_json, base_arxiv_id, read_json, utc_now

ROOT = Path(__file__).resolve().parents[1]


def prepare_run(
    *, config_path: str | Path = ROOT / "config.yaml",
    data_dir: str | Path = ROOT / "data",
    local_feed: str | Path | None = None,
    report_date: str | None = None,
    inbox_dir: str | Path | None = None,
) -> PendingRun:
    config = load_config(config_path)
    data_dir = Path(data_dir)
    state = read_json(data_dir / "state.json", {"seen": {}})
    now = utc_now()
    source = None
    if local_feed is not None:
        if data_dir.resolve() == (ROOT / "data").resolve():
            raise ValueError("--local-feed requires an isolated --data-dir; never use fixtures in production")
        feed = fetch_feed(feed_url=config["arxiv"]["feed_url"], include_types=INCLUDE_TYPES,
                          local_xml=local_feed)
    else:
        if report_date is not None:
            raise ValueError("--report-date is only supported with --local-feed; inbox dates come from RSS")
        inputs = read_inbox(Path(inbox_dir) if inbox_dir is not None else data_dir / "inbox")
        processed = state.get("processed_inputs", {})
        pending_path = data_dir / "pending_run.json"
        if pending_path.exists():
            previous = PendingRun.model_validate_json(pending_path.read_bytes())
            if previous.source_input is None:
                raise InputNotReady("Unfinished legacy/fixture pending run: recover or inspect it before inbox preparation")
            if previous.source_input.input_id not in processed:
                if not any(item == previous.source_input for item, _ in inputs):
                    raise InputNotReady("Unfinished pending input is missing or changed; preserve pending and analysis")
                return previous
        remaining = [(item, parsed) for item, parsed in inputs if item.input_id not in processed]
        if not remaining:
            if not inputs or inputs[-1][0].feed_date != expected_feed_date(now):
                raise InputNotReady(f"Input not ready: no unprocessed input; expected announcement date {expected_feed_date(now)}")
            raise InboxUpToDate("All available current inputs are already finalized; no files changed")
        source, feed = remaining[0]
        report_date = source.feed_date
    seen = {base_arxiv_id(key) for key in state["seen"]}
    # Collapse repeated announcements of the same base ID in feed order.
    unseen = {}
    for paper in feed.papers:
        if paper.arxiv_id not in seen:
            unseen.setdefault(paper.arxiv_id, paper)
    pending = PendingRun(
        report_date=report_date or now.astimezone(ZoneInfo(config["project"]["timezone"])).date().isoformat(),
        prepared_at=now, feed_build_at=feed.build_at,
        category=config["project"]["category"],
        research_profile=config["research_profile"], papers=list(unseen.values()),
        source_input=source,
    )
    atomic_write_json(data_dir / "pending_run.json", pending)
    return pending


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--local-feed", help="Offline RSS XML fixture")
    parser.add_argument("--report-date", help="Fixture date only; inbox reports use the RSS announcement date")
    parser.add_argument("--inbox-dir", help="Synced inbox path (default: DATA_DIR/inbox)")
    args = parser.parse_args()
    try:
        pending = prepare_run(config_path=args.config, data_dir=args.data_dir, inbox_dir=args.inbox_dir,
                              local_feed=args.local_feed, report_date=args.report_date)
    except InputNotReady as exc:
        print(f"INPUT NOT READY: {exc}")
        return 2
    except InboxUpToDate as exc:
        print(str(exc))
        return 3
    print(f"Prepared {pending.report_date}: {len(pending.papers)} unseen papers; state unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

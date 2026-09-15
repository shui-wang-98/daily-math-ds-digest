"""Cloud-only official RSS capture; no state, analysis, reports, or notifications."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import load_config
from .author_watch import download_author_feeds, load_watchlist
from .fetch_arxiv import download_feed
from .inbox import SOURCE_URL, persist_input, validate_rss
from .utils import utc_now

ROOT = Path(__file__).resolve().parents[1]


def capture_feed(*, config_path: Path = ROOT / "config.yaml",
                 inbox_dir: Path = ROOT / "data/inbox",
                 watchlist_path: Path = ROOT / "author_watchlist.yaml"):
    config = load_config(config_path)
    arxiv = config["arxiv"]
    if arxiv["feed_url"] != SOURCE_URL or config["project"]["category"] != "math.DS":
        raise ValueError("Capture only supports the configured official math.DS RSS endpoint")
    raw = download_feed(SOURCE_URL, int(arxiv.get("request_timeout_seconds", 45)),
                        arxiv.get("user_agent", "daily-math-ds-digest/1.0"))
    fetched_at = utc_now()
    _, _, feed_date = validate_rss(raw, fetched_at)
    watchlist = load_watchlist(watchlist_path)
    author_feed, author_pages = None, None
    if watchlist.scope == "all" and watchlist.authors and feed_date >= watchlist.start_date:
        author_feed, author_pages = download_author_feeds(
            watchlist, fetched_at=fetched_at,
            timeout=int(arxiv.get("request_timeout_seconds", 45)),
            user_agent=arxiv.get("user_agent", "daily-math-ds-digest/1.0"))
    run_url = None
    if os.getenv("GITHUB_RUN_ID") and os.getenv("GITHUB_REPOSITORY"):
        run_url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return persist_input(raw, inbox_dir=inbox_dir, fetched_at=fetched_at, capture_run_url=run_url,
                         author_feed=author_feed, author_pages=author_pages)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--inbox-dir", type=Path, default=ROOT / "data/inbox")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--watchlist", type=Path, default=ROOT / "author_watchlist.yaml")
    args = parser.parse_args()
    source, folder = capture_feed(config_path=args.config, inbox_dir=args.inbox_dir,
                                  watchlist_path=args.watchlist)
    print(f"Validated math.DS input {source.input_id}; fetched {source.fetched_at.isoformat()}; {source.byte_length} bytes.")
    if args.github_output:
        relative = folder.resolve().relative_to(ROOT).as_posix()
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"input_dir={relative}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

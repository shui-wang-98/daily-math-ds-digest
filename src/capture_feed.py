"""Cloud-only official RSS capture; no state, analysis, reports, or notifications."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import load_config
from .fetch_arxiv import download_feed
from .inbox import SOURCE_URL, InputNotReady, expected_feed_date, persist_input, read_input
from .utils import utc_now

ROOT = Path(__file__).resolve().parents[1]


def capture_feed(*, config_path: Path = ROOT / "config.yaml",
                 inbox_dir: Path = ROOT / "data/inbox", if_missing: bool = False):
    config = load_config(config_path)
    arxiv = config["arxiv"]
    if arxiv["feed_url"] != SOURCE_URL or config["project"]["category"] != "math.DS":
        raise ValueError("Capture only supports the configured official math.DS RSS endpoint")
    if if_missing:
        current_day = inbox_dir / expected_feed_date(utc_now())
        if current_day.exists():
            if not current_day.is_dir():
                raise InputNotReady(f"Input date path is not a directory: {current_day}")
            # Validate every pair before reusing any of them: a healthy capture
            # must not conceal another incomplete or damaged capture that day.
            sources = [read_input(folder)[0] for folder in sorted(current_day.iterdir())]
            if sources:
                source = max(sources, key=lambda item: (item.feed_build_at, item.fetched_at, item.sha256))
                return source, inbox_dir / source.input_id
    raw = download_feed(SOURCE_URL, int(arxiv.get("request_timeout_seconds", 45)),
                        arxiv.get("user_agent", "daily-math-ds-digest/1.0"))
    run_url = None
    if os.getenv("GITHUB_RUN_ID") and os.getenv("GITHUB_REPOSITORY"):
        run_url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return persist_input(raw, inbox_dir=inbox_dir, fetched_at=utc_now(), capture_run_url=run_url)


def capture_summary(folder: Path, *, inbox_dir: Path) -> dict:
    """Describe the validated pair without exposing the execution host's paths."""
    source, feed = read_input(folder)
    try:
        relative = folder.resolve().relative_to(ROOT.resolve())
        path_base = "repository"
    except ValueError:
        relative = folder.resolve().relative_to(inbox_dir.resolve())
        path_base = "inbox"
    return {
        "source": source.model_dump(mode="json"),
        "input_id": source.input_id,
        "path_base": path_base,
        "files": [(relative / name).as_posix() for name in ("feed.xml", "manifest.json")],
        "paper_count": len(feed.papers),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--inbox-dir", type=Path, default=ROOT / "data/inbox")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--json", action="store_true",
                        help="Print a validated JSON summary with relative archive paths")
    parser.add_argument("--if-missing", action="store_true",
                        help="Reuse validated current-day input without downloading again")
    args = parser.parse_args()
    source, folder = capture_feed(config_path=args.config, inbox_dir=args.inbox_dir,
                                 if_missing=args.if_missing)
    if args.json:
        print(json.dumps(capture_summary(folder, inbox_dir=args.inbox_dir), sort_keys=True))
    else:
        print(f"Validated math.DS input {source.input_id}; fetched {source.fetched_at.isoformat()}; {source.byte_length} bytes.")
    if args.github_output:
        relative = folder.resolve().relative_to(ROOT).as_posix()
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"input_dir={relative}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

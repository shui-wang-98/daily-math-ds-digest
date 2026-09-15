"""Cloud-only official RSS capture; no state, analysis, reports, or notifications."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import load_config
from .fetch_arxiv import download_feed
from .inbox import SOURCE_URL, persist_input
from .utils import utc_now

ROOT = Path(__file__).resolve().parents[1]


def capture_feed(*, config_path: Path = ROOT / "config.yaml",
                 inbox_dir: Path = ROOT / "data/inbox"):
    config = load_config(config_path)
    arxiv = config["arxiv"]
    if arxiv["feed_url"] != SOURCE_URL or config["project"]["category"] != "math.DS":
        raise ValueError("Capture only supports the configured official math.DS RSS endpoint")
    raw = download_feed(SOURCE_URL, int(arxiv.get("request_timeout_seconds", 45)),
                        arxiv.get("user_agent", "daily-math-ds-digest/1.0"))
    run_url = None
    if os.getenv("GITHUB_RUN_ID") and os.getenv("GITHUB_REPOSITORY"):
        run_url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return persist_input(raw, inbox_dir=inbox_dir, fetched_at=utc_now(), capture_run_url=run_url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--inbox-dir", type=Path, default=ROOT / "data/inbox")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    source, folder = capture_feed(config_path=args.config, inbox_dir=args.inbox_dir)
    print(f"Validated math.DS input {source.input_id}; fetched {source.fetched_at.isoformat()}; {source.byte_length} bytes.")
    if args.github_output:
        relative = folder.resolve().relative_to(ROOT).as_posix()
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"input_dir={relative}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

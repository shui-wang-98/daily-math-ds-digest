"""Rebuild HTML and site assets from archived reports without touching state."""
from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from .config import load_config
from .models import DailyReport
from .prepare_run import ROOT
from .report import render_report_html, render_site_index
from .utils import atomic_write_bytes


def rebuild_site(*, data_dir: str | Path = ROOT / "data", site_dir: str | Path = ROOT / "site",
                 config_path: str | Path = ROOT / "config.yaml") -> list[DailyReport]:
    data_dir, site_dir = Path(data_dir), Path(site_dir)
    config = load_config(config_path)
    reports = []
    for path in sorted((data_dir / "reports").glob("*.json")):
        report = DailyReport.model_validate_json(path.read_text(encoding="utf-8"))
        if path.stem != report.report_date:
            raise ValueError(f"Report date does not match archive filename: {path}")
        reports.append(report)
    # Reuse the daily rendering pipeline, but promote only HTML and shared assets.
    # A rendering error must not leave a partly restyled archive.
    with TemporaryDirectory(prefix=".rebuild-site-", dir=site_dir.parent) as temporary:
        staging = Path(temporary)
        for report in reports:
            render_report_html(report, config, ROOT / "templates", staging)
        render_site_index(reports, config, ROOT / "templates", ROOT / "static", staging)
        for source in sorted(staging.rglob("*")):
            if source.is_file():
                atomic_write_bytes(site_dir / source.relative_to(staging), source.read_bytes())
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--site-dir", default=str(ROOT / "site"))
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = parser.parse_args()
    reports = rebuild_site(data_dir=args.data_dir, site_dir=args.site_dir, config_path=args.config)
    print(f"Rebuilt {len(reports)} HTML reports and the archive homepage; state, JSON, PDF and Markdown untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

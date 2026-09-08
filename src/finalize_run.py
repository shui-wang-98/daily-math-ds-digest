"""Validate Codex analysis, render locally, then record successfully reported IDs."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from .config import load_config
from .models import AnalysisRun, AnalyzedPaper, DailyReport, PaperAnalysis, PendingRun
from .prepare_run import ROOT
from .report import render_report_files, render_site_index
from .utils import atomic_write_bytes, atomic_write_json, base_arxiv_id, read_json, utc_now

PRIORITIES = ("HIGH PRIORITY", "RELATED / POSSIBLY INTERESTING", "LOW PRIORITY")


def validate_analysis(pending: PendingRun, analysis: AnalysisRun) -> None:
    if pending.report_date != analysis.report_date:
        raise ValueError("Mismatched report date between pending run and analysis")
    expected = {paper.arxiv_id for paper in pending.papers}
    actual = {paper.arxiv_id for paper in analysis.papers}
    if expected != actual:
        raise ValueError(f"Paper IDs do not match: missing={sorted(expected - actual)}, "
                         f"unexpected={sorted(actual - expected)}")


def finalize_run(
    analysis_path: str | Path, *, config_path: str | Path = ROOT / "config.yaml",
    data_dir: str | Path = ROOT / "data", site_dir: str | Path = ROOT / "site",
) -> DailyReport:
    config = load_config(config_path)
    data_dir, site_dir = Path(data_dir), Path(site_dir)
    pending = PendingRun.model_validate_json((data_dir / "pending_run.json").read_text(encoding="utf-8"))
    analysis = AnalysisRun.model_validate_json(Path(analysis_path).read_text(encoding="utf-8"))
    validate_analysis(pending, analysis)
    reports_dir = data_dir / "reports"
    reports = [DailyReport.model_validate_json(path.read_text(encoding="utf-8"))
               for path in sorted(reports_dir.glob("*.json"))]
    existing = next((item for item in reports if item.report_date == pending.report_date), None)
    state = read_json(data_dir / "state.json", {
        "schema_version": 1, "seen": {}, "last_feed_build": None, "updated_at": None,
    })
    normalized_seen = {base_arxiv_id(key): value for key, value in state["seen"].items()}
    for paper in pending.papers:
        previous = normalized_seen.get(paper.arxiv_id)
        if previous and previous.get("first_seen_report") != pending.report_date:
            raise ValueError(f"Stale pending paper already reported on another date: {paper.arxiv_id}")

    by_id = {item.arxiv_id: item for item in analysis.papers}
    combined = {item.paper.arxiv_id: item for item in existing.papers} if existing else {}
    for paper in pending.papers:
        combined[paper.arxiv_id] = AnalyzedPaper(
            paper=paper,
            analysis=PaperAnalysis.model_validate(by_id[paper.arxiv_id].model_dump(exclude={"arxiv_id"})),
        )
    papers = list(combined.values())
    report = DailyReport(
        report_date=pending.report_date, generated_at=utc_now(),
        feed_build_at=pending.feed_build_at, category=pending.category,
        overview=analysis.overview, papers=papers,
        counts={priority: sum(item.analysis.priority == priority for item in papers)
                for priority in PRIORITIES},
    )
    # A fresh preparation on the same day must never erase an existing digest.
    if existing and not pending.papers:
        report = existing
    elif existing and report.model_dump(exclude={"generated_at"}) == existing.model_dump(exclude={"generated_at"}):
        report = existing

    # Render everything in staging first. Rendering or index failures leave both
    # the published archive and state untouched. Each promoted file is atomic;
    # a disk error during promotion is recoverable by rerunning this finalizer.
    with TemporaryDirectory(prefix=".finalize-", dir=data_dir) as temporary:
        staging = Path(temporary)
        staged_site = staging / "site"
        # Discover legacy downloads in the published tree, not the empty staging
        # tree. They are linked only; promotion never includes those files.
        render_report_files(report, config, ROOT / "templates", staged_site, legacy_site_dir=site_dir)
        all_reports = [item for item in reports if item.report_date != report.report_date] + [report]
        render_site_index(all_reports, config, ROOT / "templates", ROOT / "static", staged_site,
                          legacy_site_dir=site_dir)
        atomic_write_json(staging / "report.json", report)
        for source in sorted(staged_site.rglob("*")):
            if source.is_file():
                atomic_write_bytes(site_dir / source.relative_to(staged_site), source.read_bytes())
        atomic_write_bytes(reports_dir / f"{report.report_date}.json", (staging / "report.json").read_bytes())

    new_state = {**state, "seen": dict(state["seen"])}
    for paper in pending.papers:
        if paper.arxiv_id not in normalized_seen:
            new_state["seen"][paper.arxiv_id] = {
                "first_seen_report": report.report_date, "versioned_id": paper.versioned_id,
                "announce_type": paper.announce_type, "analysis_status": "ok",
            }
    # Do not rewind feed progress when repairing an older report.
    feed_build = pending.feed_build_at.isoformat() if pending.feed_build_at else None
    if feed_build and (not state.get("last_feed_build") or
                       pending.feed_build_at > datetime.fromisoformat(state["last_feed_build"])):
        new_state["last_feed_build"] = feed_build
    if new_state != state or not (data_dir / "state.json").exists():
        new_state["updated_at"] = utc_now().isoformat()
        atomic_write_json(data_dir / "state.json", new_state)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--site-dir", default=str(ROOT / "site"))
    args = parser.parse_args()
    report = finalize_run(args.analysis, config_path=args.config,
                          data_dir=args.data_dir, site_dir=args.site_dir)
    print(f"Finalized {report.report_date}: {len(report.papers)} papers; HTML, JSON and archive homepage ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

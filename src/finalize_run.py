"""Validate Codex analysis, render locally, then record successfully reported IDs."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from .config import load_config
from .author_watch import matched_authors
from .inbox import InputNotReady, read_input, validate_paper_links
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
    followed = {paper.arxiv_id: names for paper in pending.papers
                if pending.author_watchlist and (names := matched_authors(paper, pending.author_watchlist))}
    if followed != pending.followed_authors:
        raise ValueError("Pending followed-author matches differ from the supplied author names")
    for entry in analysis.papers:
        if entry.arxiv_id in followed and entry.priority != "HIGH PRIORITY":
            raise ValueError("Followed-author papers require HIGH PRIORITY and a complete digest")


def finalize_run(
    analysis_path: str | Path, *, config_path: str | Path = ROOT / "config.yaml",
    data_dir: str | Path = ROOT / "data", site_dir: str | Path = ROOT / "site",
    inbox_dir: str | Path | None = None,
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
    source = pending.source_input
    if source is None and (data_dir.resolve() == (ROOT / "data").resolve()
                           or site_dir.resolve() == (ROOT / "site").resolve()):
        raise InputNotReady("Production finalization requires a validated inbox input; fixture data and site must both be isolated")
    if source is not None:
        folder = (Path(inbox_dir) if inbox_dir is not None else data_dir / "inbox") / source.input_id
        original, feed = read_input(folder)
        if (source != original or pending.report_date != source.feed_date
                or pending.feed_build_at != source.feed_build_at or pending.category != source.category):
            raise InputNotReady("Pending run does not match its immutable inbox input")
        original_by_id = {}
        for paper in feed.papers:
            original_by_id.setdefault(paper.arxiv_id, paper)
        if any(original_by_id.get(paper.arxiv_id) != paper for paper in pending.papers):
            raise InputNotReady("Pending paper metadata differs from the original RSS")
        if source.input_id not in state.get("processed_inputs", {}):
            expected = set(original_by_id) - set(normalized_seen)
            if expected != {paper.arxiv_id for paper in pending.papers}:
                raise InputNotReady("Pending papers do not cover every unseen input ID")
    for paper in pending.papers:
        validate_paper_links(paper)
        previous = normalized_seen.get(paper.arxiv_id)
        if previous and previous.get("first_seen_report") != pending.report_date:
            raise ValueError(f"Stale pending paper already reported on another date: {paper.arxiv_id}")

    by_id = {item.arxiv_id: item for item in analysis.papers}
    combined = {item.paper.arxiv_id: item for item in existing.papers} if existing else {}
    for paper in pending.papers:
        combined[paper.arxiv_id] = AnalyzedPaper(
            paper=paper,
            analysis=PaperAnalysis.model_validate(by_id[paper.arxiv_id].model_dump(exclude={"arxiv_id"})),
            followed_authors=pending.followed_authors.get(paper.arxiv_id, []),
        )
    papers = list(combined.values())
    sources = list(existing.source_inputs) if existing else []
    if source is not None and source not in sources:
        sources.append(source)
    report = DailyReport(
        report_date=pending.report_date, generated_at=utc_now(),
        feed_build_at=pending.feed_build_at, category=pending.category,
        overview=analysis.overview, papers=papers,
        counts={priority: sum(item.analysis.priority == priority for item in papers)
                for priority in PRIORITIES},
        source_inputs=sources,
    )
    # A fresh preparation on the same day must never erase an existing digest.
    if existing and not pending.papers:
        report = existing.model_copy(update={"source_inputs": sources})
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
        for artifact in sorted(staged_site.rglob("*")):
            if artifact.is_file():
                atomic_write_bytes(site_dir / artifact.relative_to(staged_site), artifact.read_bytes())
        atomic_write_bytes(reports_dir / f"{report.report_date}.json", (staging / "report.json").read_bytes())

    new_state = {**state, "seen": dict(state["seen"])}
    if source is not None:
        new_state["schema_version"] = 2
        new_state["processed_inputs"] = dict(state.get("processed_inputs", {}))
        new_state["processed_inputs"][source.input_id] = {
            "report_date": report.report_date, "sha256": source.sha256,
        }
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
    parser.add_argument("--inbox-dir", help="Synced inbox path (default: DATA_DIR/inbox)")
    args = parser.parse_args()
    report = finalize_run(args.analysis, config_path=args.config,
                          data_dir=args.data_dir, site_dir=args.site_dir, inbox_dir=args.inbox_dir)
    print(f"Finalized {report.report_date}: {len(report.papers)} papers; HTML, JSON and archive homepage ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

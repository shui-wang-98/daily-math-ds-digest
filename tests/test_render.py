from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config
from src.models import AnalysisRun, AnalyzedPaper, DailyReport, PaperAnalysis
from src.fetch_arxiv import parse_feed
from src.report import render_report_files, render_site_index

ROOT = Path(__file__).resolve().parents[1]


def test_render_html_and_json_only(tmp_path: Path) -> None:
    feed = parse_feed((ROOT / "tests/fixtures/math_ds.xml").read_text(encoding="utf-8"),
                      include_types=["new", "cross", "replace-cross"])
    analysis = AnalysisRun.model_validate_json((ROOT / "tests/fixtures/analysis_run.json").read_text(encoding="utf-8"))
    analyzed = [AnalyzedPaper(paper=paper, analysis=PaperAnalysis.model_validate(entry.model_dump(exclude={"arxiv_id"})))
                for paper, entry in zip(feed.papers, analysis.papers, strict=True)]
    report = DailyReport(report_date=analysis.report_date, generated_at=datetime.now(timezone.utc),
                         feed_build_at=feed.build_at, category="math.DS", overview=analysis.overview,
                         papers=analyzed, counts={entry.priority: 1 for entry in analysis.papers})
    config = load_config(ROOT / "config.yaml")
    site = tmp_path / "site"
    paths = render_report_files(report, config, ROOT / "templates", site)
    render_site_index([report], config, ROOT / "templates", ROOT / "static", site)
    html = Path(paths["html"]).read_text(encoding="utf-8")
    assert set(paths) == {"html", "json"}
    assert DailyReport.model_validate_json(Path(paths["json"]).read_text(encoding="utf-8")) == report
    assert not list(site.rglob("*.pdf")) and not list(site.rglob("*.md"))
    assert "Entropy and symbolic extensions" in html
    assert "Related / Possibly Interesting" in html
    assert "Low Priority" in html
    assert "arXiv:2609.00002" in html
    assert "Main result" in html
    assert (site / "index.html").exists()

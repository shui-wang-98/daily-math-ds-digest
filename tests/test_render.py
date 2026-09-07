from datetime import datetime, timezone
from pathlib import Path

from src.models import AnalyzedPaper, DailyReport, PaperAnalysis
from src.fetch_arxiv import parse_feed
from src.report import render_report_files, render_site_index


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "math_ds.xml"


def test_render_html_markdown_and_pdf(tmp_path: Path) -> None:
    feed = parse_feed(
        FIXTURE.read_text(encoding="utf-8"),
        include_types=["new", "cross", "replace-cross"],
    )
    analyses = [
        PaperAnalysis(
            priority="HIGH PRIORITY",
            confidence="high",
            relevance_note="Directly concerns entropy, symbolic dynamics, and amenable group actions.",
            tldr="The paper studies entropy and symbolic extensions for amenable group actions.",
            problem="Understand symbolic extensions and a pressure-type invariant.",
            main_result="Under an explicit hypothesis, a variational principle is proved.",
            methods=["symbolic dynamics"],
            context="Topological dynamics and entropy theory.",
            prerequisites=["topological dynamics", "amenable groups"],
            keywords=["entropy", "symbolic extensions", "amenable actions"],
        ),
        PaperAnalysis(
            priority="LOW PRIORITY",
            confidence="high",
            relevance_note="Primarily numerical PDE modeling.",
            tldr="",
            problem="",
            main_result="",
            methods=[],
            context="",
            prerequisites=[],
            keywords=[],
        ),
    ]
    analyzed = [
        AnalyzedPaper(paper=paper, analysis=analysis)
        for paper, analysis in zip(feed.papers, analyses, strict=True)
    ]
    report = DailyReport(
        report_date="2026-09-04",
        generated_at=datetime.now(timezone.utc),
        feed_build_at=feed.build_at,
        category="math.DS",
        model="test-model",
        overview="Two papers were newly announced. One is directly relevant to entropy and group actions; the other is primarily numerical PDE work. The digest uses only the supplied abstracts.",
        papers=analyzed,
        counts={
            "HIGH PRIORITY": 1,
            "RELATED / POSSIBLY INTERESTING": 0,
            "LOW PRIORITY": 1,
        },
    )
    config = {
        "report": {
            "include_original_abstract_for_full_entries": True,
            "pdf_filename_pattern": "math-DS-digest-{date}.pdf",
            "markdown_filename_pattern": "math-DS-digest-{date}.md",
        },
        "site": {"title": "Daily math.DS Digest", "subtitle": "Test"},
    }
    site = tmp_path / "site"
    paths = render_report_files(
        report,
        config,
        ROOT / "templates",
        site,
    )
    render_site_index(
        [report],
        config,
        ROOT / "templates",
        ROOT / "static",
        site,
    )

    html = Path(paths["html"]).read_text(encoding="utf-8")
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    pdf = Path(paths["pdf"]).read_bytes()

    assert "Entropy and symbolic extensions" in html
    assert "Low Priority" in html
    assert "arXiv:2609.00002" not in html
    assert "Main result" in markdown
    assert "arXiv:2609.00002" not in markdown
    assert pdf.startswith(b"%PDF")
    assert (site / "index.html").exists()

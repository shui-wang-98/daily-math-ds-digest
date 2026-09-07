from pathlib import Path

from src.fetch_arxiv import parse_feed


FIXTURE = Path(__file__).parent / "fixtures" / "math_ds.xml"


def test_parse_feed_filters_replacements() -> None:
    result = parse_feed(
        FIXTURE.read_text(encoding="utf-8"),
        include_types=["new", "cross", "replace-cross"],
    )

    assert result.title == "math.DS updates on arXiv.org"
    assert [paper.arxiv_id for paper in result.papers] == ["2609.00001", "2609.00002"]
    assert result.papers[0].announce_type == "new"
    assert result.papers[1].announce_type == "cross"
    assert result.papers[0].authors == ["Ada Author", "Bernhard Researcher"]
    assert "variational principle" in result.papers[0].abstract
    assert result.papers[0].pdf_url == "https://arxiv.org/pdf/2609.00001"

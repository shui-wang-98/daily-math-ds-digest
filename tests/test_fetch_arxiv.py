from pathlib import Path

import pytest

from src.fetch_arxiv import parse_feed
from src.fetch_arxiv import ArxivFeedError
from src.utils import base_arxiv_id, clean_xml_text


FIXTURE = Path(__file__).parent / "fixtures" / "math_ds.xml"


def test_parse_feed_filters_replacements() -> None:
    result = parse_feed(
        FIXTURE.read_text(encoding="utf-8"),
        include_types=["new", "cross", "replace-cross"],
    )

    assert result.title == "math.DS updates on arXiv.org"
    assert [paper.arxiv_id for paper in result.papers] == ["2609.00001", "2609.00002", "2608.00003"]
    assert result.papers[0].announce_type == "new"
    assert result.papers[1].announce_type == "cross"
    assert result.papers[2].announce_type == "replace-cross"
    assert result.papers[2].versioned_id == "2608.00003v2"
    assert "2501.12345" not in {paper.arxiv_id for paper in result.papers}
    assert result.papers[0].authors == ["Ada Author", "Bernhard Researcher"]
    assert "variational principle" in result.papers[0].abstract
    assert result.papers[0].pdf_url == "https://arxiv.org/pdf/2609.00001"


@pytest.mark.parametrize("value,expected", [
    ("2609.00001v12", "2609.00001"),
    ("arXiv:2609.00001", "2609.00001"),
    ("https://arxiv.org/pdf/2609.00001v2.pdf", "2609.00001"),
    ("math/0301234v2", "math/0301234"),
])
def test_normalize_ids(value, expected):
    assert base_arxiv_id(value) == expected


def test_xml_cleanup_preserves_inequalities():
    assert clean_xml_text(r"<p>Assume \(a &lt; b\) and \(c &gt; d\).</p>") == r"Assume \(a < b\) and \(c > d\)."


def test_bad_item_is_not_silently_dropped():
    text = FIXTURE.read_text(encoding="utf-8").replace("2609.00001v1", "invalid")
    with pytest.raises(ArxivFeedError, match="Invalid arXiv"):
        parse_feed(text, ["new", "cross", "replace-cross"])


def test_invalid_rss_fails():
    with pytest.raises(ArxivFeedError, match="Invalid arXiv RSS XML"):
        parse_feed("<broken", ["new"])

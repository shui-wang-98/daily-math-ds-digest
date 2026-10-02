from pathlib import Path
import xml.etree.ElementTree as ET

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


@pytest.mark.parametrize("formula", [
    "$a<b$ and $c>d$", "$a<p>b$", "$$a<p>b$$",
    r"\(a<p>b\)", r"\[a<p>b\]",
    r"\begin{equation}a<p>b\end{equation}",
    r"\(\begin{matrix}a<p>b\end{matrix}\)",
])
def test_xml_cleanup_preserves_tag_shaped_math_and_removes_real_wrappers(formula):
    assert clean_xml_text(f'<p class="abstract"><b>Result:</b> {formula}<br /></p>') == f"Result: {formula}"


def test_xml_cleanup_respects_escaped_delimiters():
    assert clean_xml_text(r"<p>A \$5 cost. <b>Result:</b> \(a<p>b\).</p>") == r"A \$5 cost. Result: \(a<p>b\)."


@pytest.mark.parametrize("source,expected", [
    (r"\begin{aligned}a&not\end{aligned}", r"\begin{aligned}a&not\end{aligned}"),
    ("$a&notit;b$", "$a&notit;b$"),
    ("$a&lt;b$ and &#945; &amp; &#x3B2;", "$a<b$ and \u03b1 & \u03b2"),
])
def test_xml_cleanup_only_decodes_complete_known_entities(source, expected):
    assert clean_xml_text(source) == expected


@pytest.mark.parametrize("encoded,expected", [
    ("$a&lt;b$ and $c&gt;d$", "$a<b$ and $c>d$"),
    ("$a&amp;lt;b$", "$a&lt;b$"),
    ("$a<p>b$", "$a<p>b$"),
    ("$1<p<m$ and $\\sigma>0$", "$1<p<m$ and $\\sigma>0$"),
    ("$0<a_j<b_j<b<1$. If $b_j^m<a_j$ for all $j>0$",
     "$0<a_j<b_j<b<1$. If $b_j^m<a_j$ for all $j>0$"),
])
@pytest.mark.parametrize("cdata", [False, True])
def test_feed_abstract_is_cleaned_once_without_losing_math(encoded, expected, cdata):
    root = ET.fromstring(FIXTURE.read_bytes())
    item = root.find("channel/item")
    item.find("description").text = (
        "<p>arXiv:2609.00001v1 Announce Type: new<br/>"
        f"Abstract: We prove {encoded}.</p>"
    )
    raw = ET.tostring(root, encoding="unicode")
    if cdata:
        # ElementTree normally escapes the HTML layer; CDATA is an equivalent
        # RSS representation and must preserve the same mathematical source.
        first = raw.index("<description>") + len("<description>")
        last = raw.index("</description>", first)
        raw = raw[:first] + "<![CDATA[" + item.findtext("description") + "]]>" + raw[last:]
    paper = parse_feed(raw, ["new"]).papers[0]
    assert paper.abstract == f"We prove {expected}."


def test_bad_item_is_not_silently_dropped():
    text = FIXTURE.read_text(encoding="utf-8").replace("2609.00001v1", "invalid")
    with pytest.raises(ArxivFeedError, match="Invalid arXiv"):
        parse_feed(text, ["new", "cross", "replace-cross"])


def test_invalid_rss_fails():
    with pytest.raises(ArxivFeedError, match="Invalid arXiv RSS XML"):
        parse_feed("<broken", ["new"])

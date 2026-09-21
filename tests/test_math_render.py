import base64
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from src.finalize_run import finalize_run
from src.math_render import _formula, _svg_formula, _segments, html_text
from src.models import AnalysisRun
from src.prepare_run import prepare_run
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
SVG_NS = "{http://www.w3.org/2000/svg}"


def _svg_tree(encoded):
    return ET.fromstring(base64.b64decode(encoded))


def _visible_svg(encoded):
    """Ignore source annotations, preserving actual paths and their positions."""
    tree = _svg_tree(encoded)
    for node in tree.iter():
        for attribute in list(node.attrib):
            if attribute == "data-latex":
                del node.attrib[attribute]
    return ET.tostring(tree)


class _Images(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.images = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.images.append(dict(attrs))


def _image_svg(attrs):
    prefix = "data:image/svg+xml;base64,"
    assert attrs["src"].startswith(prefix)
    return attrs["src"][len(prefix):]


def _assert_same_math(source, reference, *, display=False):
    preserved, unknown = _formula(source, display=display)
    assert preserved == source
    assert not unknown
    svg, width, depth = _svg_formula(source, display=display)
    reference_svg, reference_width, reference_depth = _svg_formula(reference, display=display)
    assert (width, depth) == (reference_width, reference_depth)
    assert _visible_svg(svg) == _visible_svg(reference_svg)
    rendered = str(html_text(r"\(" + source + r"\)"))
    images = _Images(rendered).images
    assert len(images) == 1
    assert images[0]["alt"] == source
    assert "unrecognized commands" not in rendered


@pytest.mark.parametrize(("source", "reference"), [
    (r"\#P_f=4", r"\# P_f=4"),
    (r"\#A+\#B", r"\# A+\# B"),
    (r"x=\#O_k", r"x=\# O_k"),
    (r"\text{\#P}", r"\text{\#P}"),
    (r"\#P=\text{\#P}", r"\# P=\text{\#P}"),
])
def test_cardinality_before_letters_keeps_glyph_and_original_source(source, reference):
    _assert_same_math(source, reference)


@pytest.mark.parametrize(("source", "reference"), [
    (r"\frac12", r"\frac{1}{2}"),
    (r"\tfrac12", r"\tfrac{1}{2}"),
    (r"\dfrac12", r"\dfrac{1}{2}"),
])
def test_standard_fraction_spellings(source, reference):
    _assert_same_math(source, reference)


def test_fraction_style_commands_keep_their_distinct_display_sizes():
    inline, inline_width, _ = _svg_formula(r"\tfrac{1}{2}")
    display, display_width, _ = _svg_formula(r"\dfrac{1}{2}")
    assert display_width > inline_width
    assert _visible_svg(inline) != _visible_svg(display)


@pytest.mark.parametrize(("source", "reference"), [
    (r"(1+\sqrt5)/2", r"(1+\sqrt{5})/2"),
    (r"\sqrt12", r"\sqrt{1}2"),
    (r"\sqrt x^2", r"\sqrt{x}^2"),
    (r"\sqrt[3]5", r"\sqrt[3]{5}"),
    (r"\sqrt[n+1] xy", r"\sqrt[n+1]{x}y"),
    (r"\sqrt{\sqrt5}", r"\sqrt{\sqrt{5}}"),
    (r"\sqrt{12}+\sqrt[3]{x+1}", r"\sqrt{12}+\sqrt[3]{x+1}"),
    (r"\text{sqrt5}", r"\text{sqrt5}"),
    (r"\sqrt5+\text{sqrt5}", r"\sqrt{5}+\text{sqrt5}"),
])
def test_unbraced_roots_keep_glyphs_and_original_source(source, reference):
    _assert_same_math(source, reference)


def test_single_token_root_does_not_swallow_following_digits_or_superscripts():
    short, _, _ = _svg_formula(r"\sqrt12")
    whole_number, _, _ = _svg_formula(r"\sqrt{12}")
    outside_power, _, _ = _svg_formula(r"\sqrt x^2")
    inside_power, _, _ = _svg_formula(r"\sqrt{x^2}")
    assert _visible_svg(short) != _visible_svg(whole_number)
    assert _visible_svg(outside_power) != _visible_svg(inside_power)


def test_empty_root_and_longer_control_word_follow_tex_semantics():
    source, unknown = _formula(r"\sqrt{}")
    assert source == r"\sqrt{}"
    assert not unknown
    assert _svg_formula(source)[0]
    source, unknown = _formula(r"\sqrtx")
    assert source == r"\sqrtx"
    assert unknown == ("sqrtx",)
    assert "unrecognized commands sqrtx" in html_text(r"\(\sqrtx\)")


def test_unbraced_bold_greek_is_typeset_without_unrecognized_macro_note():
    source = r"{\boldsymbol \Pi}^0_4"
    preserved, unknown = _formula(source)
    assert preserved == source
    assert not unknown
    rendered = html_text(r"\(" + source + r"\)")
    assert "data:image/svg+xml;base64," in rendered
    assert "unrecognized commands" not in rendered


@pytest.mark.parametrize("source", [
    r"Q\Big(\sum_{p\in I}p\Big)\in U\pmod 1",
    r"\bigl(x+\tfrac12\bigr)\Bigl[y+\dfrac12\Bigr]",
    r"a\equiv b\pmod{n},\qquad T_bx=bx\bmod1",
    r"\lim\limits_{n\to\infty}a_n,\quad\sum\nolimits_{n=1}^{N}a_n",
    r"\mathscr F\subset\mathcal P(\mathbb R),\quad\boldsymbol\Pi",
    r"\begin{matrix}a&b\\c&d\end{matrix}",
    r"\begin{pmatrix}1&0\\0&1\end{pmatrix}",
    r"f(x)=\begin{cases}x^2&x\ge0\\-x&x<0\end{cases}",
    r"\begin{aligned}a&=b+c\\&=d\end{aligned}",
    r"\binom{n}{k}=\frac{n!}{k!(n-k)!}",
    r"\operatorname*{arg\,max}_{x\in X}f(x)",
])
def test_standard_tex_families_render_without_false_author_macro_notes(source):
    preserved, unknown = _formula(source, display=True)
    assert preserved == source
    assert not unknown
    svg, width, depth = _svg_formula(source, display=True)
    tree = _svg_tree(svg)
    assert tree.tag == SVG_NS + "svg"
    assert width > 0 and depth >= 0
    assert tree.findall(".//" + SVG_NS + "path")
    assert not any(node.attrib.get("data-mml-node") == "merror" for node in tree.iter())
    # None of these formulas contains a literal backslash. The former fallback
    # inserted one before each unsupported standard command.
    assert not any(node.attrib.get("data-c") == "5C" for node in tree.iter())
    rendered = html_text(r"\[" + source + r"\]")
    assert "unrecognized commands" not in rendered
    assert "does not define the macros" not in rendered


def test_equation_environment_keeps_complete_formula_together():
    formula = r"\lim_{N\to\infty}\frac{1}{N}\sum_{n=1}^N x_n=0"
    source = "Before " + r"\begin{equation*}" + formula + r"\end{equation*}" + " after."
    assert list(_segments(source)) == [(False, "Before "), (True, formula), (False, " after.")]
    images = _Images(str(html_text(source))).images
    assert len(images) == 1
    assert images[0]["alt"] == formula
    assert _image_svg(images[0]) == _svg_formula(formula, display=True)[0]


def test_display_delimiters_use_display_layout_without_changing_source():
    formula = r"\sum_{n=1}^{\infty}\frac{1}{n^2}"
    inline_svg, inline_width, inline_depth = _svg_formula(formula)
    display_svg, display_width, display_depth = _svg_formula(formula, display=True)
    assert (inline_width, inline_depth) != (display_width, display_depth)
    assert _visible_svg(inline_svg) != _visible_svg(display_svg)
    for before, after, expected in [
        (r"\(", r"\)", inline_svg),
        ("$", "$", inline_svg),
        (r"\[", r"\]", display_svg),
        ("$$", "$$", display_svg),
    ]:
        images = _Images(str(html_text(before + formula + after))).images
        assert len(images) == 1
        assert images[0]["alt"] == formula
        assert _image_svg(images[0]) == expected


def test_text_block_with_nested_inline_math_preserves_complete_source():
    formula = r"\text{$a=\frac12$ if and only if $b>2$},"
    source = "$$" + formula + "$$"
    assert list(_segments(source)) == [(True, formula)]
    images = _Images(str(html_text(source))).images
    assert len(images) == 1
    assert images[0]["alt"] == formula
    svg = _image_svg(images[0])
    assert svg == _svg_formula(formula, display=True)[0]
    glyphs = {node.attrib.get("data-c") for node in _svg_tree(svg).iter()}
    assert {"3D", "3E", "2C"}.issubset(glyphs)  # Both relations and final comma.


@pytest.mark.parametrize(("source", "glyphs"), [
    (r"\mathrm{L}<\mathrm{R}+\mathrm{Z}", {"4C", "3C", "52", "2B", "5A"}),
    (r"\mathrm{A}\leq\mathrm{B}", {"41", "2264", "42"}),
])
def test_inline_relations_do_not_drop_glyphs_after_a_possible_linebreak(source, glyphs):
    svg, _, _ = _svg_formula(source)
    rendered_glyphs = {node.attrib.get("data-c") for node in _svg_tree(svg).iter()}
    assert glyphs.issubset(rendered_glyphs)
    images = _Images(str(html_text(r"\(" + source + r"\)"))).images
    assert len(images) == 1
    assert _image_svg(images[0]) == svg


def test_escaped_dollar_in_prose_does_not_open_a_math_span():
    source = r"Cost \$5; formula \(x+1\) remains separate."
    assert [text for is_math, text in _segments(source) if is_math] == ["x+1"]
    rendered = html_text(source)
    assert "Cost $5;" in rendered
    assert rendered.count('class="math-formula"') == 1
    assert rendered.endswith(" remains separate.")


def test_fraction_and_symbols_are_typeset_instead_of_flattened():
    source = r"1-\frac{1}{d+1}\quad\mathbb{R}^{d}\quad\Pi_1^0"
    preserved, unknown = _formula(source)
    svg, width, depth = _svg_formula(source)
    assert preserved == source
    assert not unknown
    assert svg
    assert width > 0 and depth >= 0
    paragraph = html_text(r"Bound: \(" + source + r"\).")
    assert 'src="data:image/svg+xml;base64,' in paragraph
    assert "1-1/d+1" not in paragraph


def test_unrecognized_macros_are_retained_without_inventing_definitions():
    source = r"\Hau^{s_d}(p_\theta(\mathcal{C}(d)))=0,\quad\theta\in\IP(d)"
    preserved, unknown = _formula(source)
    assert preserved == source
    assert set(unknown) == {"Hau", "IP"}
    text = html_text("Original: $" + source + "$.")
    assert "unrecognized commands Hau, IP" in text
    assert "their literal command names are retained" in text
    assert "no definitions are inferred" in text
    assert "does not define the macros" not in text
    assert _Images(str(text)).images[0]["alt"] == source


def test_unknown_prose_macro_cannot_silently_delete_the_named_property():
    result = html_text(r"It does not have \STRP. A \blue{group} appears.")
    assert r"\STRP" in result
    assert r"\blue" in result and "group" in result
    assert "unrecognized commands STRP, blue" in result
    assert "no definitions are inferred" in result


def test_formula_local_macro_definition_does_not_leak_to_another_formula():
    defined = r"\newcommand{\DigestLocalAlias}{x}\DigestLocalAlias"
    preserved, unknown = _formula(defined)
    assert preserved == defined
    assert not unknown
    # The subsequent formula was never cached: its unrecognized result must
    # come from isolation, rather than a pre-definition cached result.
    preserved, unknown = _formula(r"\DigestLocalAlias+1")
    assert preserved == r"\DigestLocalAlias+1"
    assert unknown == ("DigestLocalAlias",)
    assert _formula(defined)[1] == ()


def test_author_accents_and_undelimited_rss_math():
    assert html_text(r"Sebasti\\'an Barbieri") == "Sebasti\u00e1n Barbieri"
    assert html_text(r"Pawe\l{} D\l{}otko \and B") == "Pawe\u0142 D\u0142otko  and  B"
    tau = html_text(r"Robustness of {\tau}-tipping")
    assert 'class="math-formula"' in tau and "unrecognized commands" not in tau
    result = html_text(r"space SL_n\mathbb{R}/\Gamma, n\ge 5, under the assumption")
    assert r'alt="SL_n\mathbb{R}/\Gamma,"' in result
    assert r'alt="n\ge 5,"' in result
    assert "unrecognized commands" not in result
    assert result.endswith("under the assumption")


@pytest.mark.parametrize(("source", "reference"), [
    (r"s\ge4", r"s\geq4"),
    (r"s\le2", r"s\leq2"),
    (r"s\ne0", r"s\neq0"),
])
def test_standard_aliases_immediately_before_numbers(source, reference):
    _assert_same_math(source, reference)


@pytest.mark.parametrize("source", [
    r"\sqrt",
    r"\frac{1}",
    r"\left(x",
    r"x^{2",
    r"\begin{matrix}a&b\end{cases}",
])
def test_malformed_math_is_rejected_instead_of_printing_an_error_node(source):
    with pytest.raises(ValueError, match="Cannot faithfully render math"):
        _formula(source)


@pytest.mark.parametrize("source", [
    r"\require{html}",
    r"\input{private.tex}",
    r"\includegraphics{https://example.invalid/picture.svg}",
    r"\href{https://example.invalid/}{x}",
    r"\htmlClass{untrusted}{x}",
    r"\def\DigestRecursive{\DigestRecursive}\DigestRecursive",
    "x" * 20000,
])
def test_external_commands_and_excessive_expansion_are_rejected(source):
    with pytest.raises(ValueError, match="Cannot faithfully render math"):
        _formula(source)


def test_svg_is_self_contained_and_repeatable_after_other_formula_rendering():
    source = r"\begin{aligned}a&=\frac12\\b&=\sqrt[3]5\end{aligned}"
    first, _, _ = _svg_formula(source, display=True)
    tree = _svg_tree(first)
    assert tree.findall(".//" + SVG_NS + "path")
    for node in tree.iter():
        assert node.tag not in {SVG_NS + "script", SVG_NS + "foreignObject", SVG_NS + "image"}
        for name, value in node.attrib.items():
            if name.rsplit("}", 1)[-1] == "href":
                assert value.startswith("#")
    _svg_formula(r"\sum_{k=1}^{n}k", display=True)
    _svg_formula.cache_clear()
    second, _, _ = _svg_formula(source, display=True)
    assert second == first


def test_vector_output_is_repeatable_in_fresh_python_processes():
    code = (
        "import hashlib; from src.math_render import _svg_formula; "
        "svg, width, depth = _svg_formula(r'\\sum_{k=1}^{n}\\frac1{k^2}', display=True); "
        "print(hashlib.sha256(svg.encode('ascii')).hexdigest(), width, depth)"
    )
    results = [
        subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=30).stdout.strip()
        for _ in range(2)
    ]
    assert results[0] == results[1]
    assert len(results[0].split()[0]) == 64


def test_math_render_failure_keeps_state_and_archive_unchanged(tmp_path):
    data, site = tmp_path / "data", tmp_path / "site"
    prepare_run(data_dir=data, local_feed=ROOT / "tests/fixtures/math_ds.xml", report_date="2026-09-04")
    payload = AnalysisRun.model_validate_json((ROOT / "tests/fixtures/analysis_run.json").read_text(encoding="utf-8"))
    payload.papers[0].main_result = r"Malformed source: \(\frac{1}\)."
    atomic_write_json(data / "analysis_run.json", payload)
    atomic_write_json(data / "state.json", {"seen": {}})
    before = (data / "state.json").read_bytes()
    with pytest.raises(ValueError, match="Cannot faithfully render math"):
        finalize_run(data / "analysis_run.json", data_dir=data, site_dir=site)
    assert (data / "state.json").read_bytes() == before
    assert not site.exists()
    assert not (data / "reports").exists()


def test_html_math_images_keep_metadata_and_are_repeatable(tmp_path):
    data, site = tmp_path / "data", tmp_path / "site"
    pending = prepare_run(data_dir=data, local_feed=ROOT / "tests/fixtures/math_ds.xml", report_date="2026-09-04")
    payload = AnalysisRun.model_validate_json((ROOT / "tests/fixtures/analysis_run.json").read_text(encoding="utf-8"))
    payload.papers[0].main_result = r"Test notation: \(\Pi_1^0\) and \(1-\frac{1}{d+1}\)."
    pending.papers[0].abstract += r" Cardinality notation: \(\#P_f=4\)."
    pending.papers[0].abstract += r" Root notation: \((1+\sqrt5)/2\)."
    pending.papers[0].abstract += (
        r" Standard notation: \(Q\Big(\sum_{p\in I}p\Big)\in U\pmod1\)."
        r" Limit notation: \(\lim\limits_{n\to\infty}a_n=0\)."
    )
    pending.papers[0].abstract += (
        r" Equation \eqref{fixture} follows. "
        r"\begin{equation}\label{fixture}x=1\tag{$\ast$}\end{equation}"
        r" This answers \cite[Question 8.2 (iii)]{Kl}."
    )
    atomic_write_json(data / "pending_run.json", pending)
    atomic_write_json(data / "analysis_run.json", payload)
    report = finalize_run(data / "analysis_run.json", data_dir=data, site_dir=site)
    assert report.papers[0].paper == pending.papers[0]
    html = site / "reports/2026-09-04/index.html"
    original = html.read_bytes()
    assert original.count(b"data:image/svg+xml;base64,") >= 5
    assert b"unrecognized commands" not in original
    assert b'[Kl, Question 8.2 (iii)]' in original
    assert b'&lt;ref&gt;' not in original and b'&lt;cit.' not in original
    assert b'no equation numbers' not in original
    assert json.loads((html.parent / 'report.json').read_text(encoding='utf-8'))['papers'][0]['paper']['abstract'] == pending.papers[0].abstract
    finalize_run(data / "analysis_run.json", data_dir=data, site_dir=site)
    assert html.read_bytes() == original

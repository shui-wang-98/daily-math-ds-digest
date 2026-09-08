from pathlib import Path

import pytest

from src.finalize_run import finalize_run
from src.math_render import _formula, _svg_formula, html_text
from src.models import AnalysisRun
from src.prepare_run import prepare_run
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]


def test_fraction_and_symbols_are_typeset_instead_of_flattened():
    source = r"1-\frac{1}{d+1}\quad\mathbb{R}^{d}\quad\Pi_1^0"
    normalized, unknown = _formula(source)
    svg, width, depth = _svg_formula(normalized)
    assert normalized == source
    assert not unknown
    assert svg
    assert width > 0 and depth >= 0
    paragraph = html_text(r"Bound: \(" + source + r"\).")
    assert 'src="data:image/svg+xml;base64,' in paragraph
    assert "1-1/d+1" not in paragraph


def test_undefined_macros_are_retained_with_explicit_source_note():
    source = r"\Hau^{s_d}(p_\theta(\mathcal{C}(d)))=0,\quad\theta\in\IP(d)"
    normalized, unknown, *_ = _formula(source)
    assert set(unknown) == {"Hau", "IP"}
    assert r"\backslash\mathrm{Hau}" in normalized
    assert r"\backslash\mathrm{IP}" in normalized
    text = html_text("Original: $" + source + "$.")
    assert "does not define the macros Hau, IP" in text


def test_author_accents_and_undelimited_rss_math():
    assert html_text(r"Sebasti\\'an Barbieri") == "Sebastián Barbieri"
    result = html_text(r"space SL_n\mathbb{R}/\Gamma, n\ge 5, under the assumption")
    assert r'alt="SL_n\mathbb{R}/\Gamma,"' in result
    assert r'alt="n\ge 5,"' in result
    assert "Source notation" not in result
    assert result.endswith("under the assumption")


@pytest.mark.parametrize(("source", "expected"), [(r"s\ge4", r"s\geq4"), (r"s\le2", r"s\leq2"), (r"s\ne0", r"s\neq0")])
def test_standard_aliases_immediately_before_numbers(source, expected):
    normalized, unknown, *_ = _formula(source)
    assert normalized == expected
    assert not unknown


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
    atomic_write_json(data / "analysis_run.json", payload)
    report = finalize_run(data / "analysis_run.json", data_dir=data, site_dir=site)
    assert report.papers[0].paper == pending.papers[0]
    html = site / "reports/2026-09-04/index.html"
    original = html.read_bytes()
    assert original.count(b"data:image/svg+xml;base64,") >= 2
    finalize_run(data / "analysis_run.json", data_dir=data, site_dir=site)
    assert html.read_bytes() == original

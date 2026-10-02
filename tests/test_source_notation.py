"""RSS notation is rendered without editing metadata or relaxing authored math."""
import base64
import json
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from src.finalize_run import finalize_run
from src.math_render import html_source_text, html_text
from src.math_spans import MAX_NESTING, spans
from src.models import AnalysisRun
from src.prepare_run import prepare_run
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]


class Visible(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.text, self.images, self.tags = [], [], []
        self.feed(str(source))

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'img':
            self.images.append(dict(attrs))


def test_href_keeps_complete_url_label_math_and_following_prose():
    source = (r'Before \href{https://example.invalid/a%20b_$x?key=a\&dl=0}'
              r' {Lean~4 certification and $x_2$} after.')
    visible = Visible(html_text(source))
    assert ''.join(visible.text) == (
        'Before Lean\u00a04 certification and '
        ' (https://example.invalid/a%20b_$x?key=a&dl=0) after.')
    assert [i['alt'] for i in visible.images] == ['x_2']
    assert 'a' not in visible.tags
    assert r'title="Before' not in str(html_text(source))


@pytest.mark.parametrize('command', ['url', 'nolinkurl'])
def test_literal_url_never_opens_math_or_drops_fragments(command):
    source = '\\' + command + r'{https://example.invalid/$x%20y?a=1\&b=2#p}'
    visible = Visible(html_text(source))
    assert ''.join(visible.text) == 'https://example.invalid/$x%20y?a=1&b=2#p'
    assert not visible.images and visible.tags == ['span']


def test_link_inside_formatting_supports_optional_arguments_and_nested_citations():
    source = r'\textbf{\href[option={value}]{https://example.invalid}{See \cite{A} and \(x\)}}.'
    visible = Visible(html_text(source))
    assert ''.join(visible.text) == 'See [A] and  (https://example.invalid).'
    assert [i['alt'] for i in visible.images] == ['x']


def test_links_cannot_inject_active_html_or_internal_tokens():
    source = ('\ue000Digest{}Reference0\ue001 '
              r'\href{javascript:alert(1)}{<img src=x onerror=alert(1)>}')
    visible = Visible(html_text(source))
    assert visible.tags == ['span']
    assert ''.join(visible.text) == ('\ue000DigestReference0\ue001 '
                                    '<img src=x onerror=alert(1)> (javascript:alert(1))')


@pytest.mark.parametrize('source', [r'\href{url}', r'\href{url}{open', r'\url{open',
                                     r'\href[open{url}{text}'])
def test_malformed_links_raise_a_useful_error(source):
    with pytest.raises(ValueError, match='Malformed source link'):
        html_text(source)


def test_link_arguments_have_a_nesting_limit():
    with pytest.raises(ValueError, match='nesting limit'):
        html_text(r'\url{' + '{' * MAX_NESTING + 'x' + '}' * (MAX_NESTING + 1))


@pytest.mark.parametrize('opening,closing', [('$', '$'), ('$$', '$$'),
                                            (r'\(', r'\)'), (r'\[', r'\]')])
@pytest.mark.parametrize('formula', ['82.4%', 'p=82.4 % '])
def test_source_numeric_percent_keeps_glyph_and_original_formula(opening, closing, formula):
    source = 'Value ' + opening + formula + closing + ' afterwards.'
    assert list(spans(source, rss_percentages=True))[1][1] == formula
    visible = Visible(html_source_text(source))
    assert len(visible.images) == 1
    assert visible.images[0]['alt'] == formula
    svg = ET.fromstring(base64.b64decode(visible.images[0]['src'].split(',', 1)[1]))
    assert '25' in {node.attrib.get('data-c') for node in svg.iter()}
    assert ' afterwards.' in ''.join(visible.text)
    assert 'numeric percent is displayed literally' in ''.join(visible.text)
    with pytest.raises(ValueError, match='Invalid math span'):
        html_text(source)


def test_source_percent_rule_does_not_reinterpret_comments_or_variable_macros():
    formula = 'x% ignore $ and \\)\n+y'
    for renderer in (html_text, html_source_text):
        assert Visible(renderer('$' + formula + '$')).images[0]['alt'] == formula
        with pytest.raises(ValueError, match='Invalid math span'):
            renderer(r'\(x% commented out \)')
    assert 'numeric percent' not in str(html_source_text(r'\(50\%\)'))
    with pytest.raises(ValueError):
        html_source_text(r'\(\frac{1}\)')


@pytest.mark.parametrize('command', ['textit', 'textbf'])
def test_prose_formatting_can_span_explicit_math(command):
    visible = Visible(html_source_text('\\' + command + r'{fully inhomogeneous $p$-adic conjecture}.'))
    assert ''.join(visible.text) == 'fully inhomogeneous -adic conjecture.'
    assert [i['alt'] for i in visible.images] == ['p']


def test_source_policies_reach_report_and_homepage_without_changing_metadata(tmp_path):
    data, site = tmp_path / 'data', tmp_path / 'site'
    pending = prepare_run(data_dir=data, local_feed=ROOT / 'tests/fixtures/math_ds.xml',
                          report_date='2026-09-04')
    analysis = AnalysisRun.model_validate_json(
        (ROOT / 'tests/fixtures/analysis_run.json').read_text(encoding='utf-8'))
    pending.papers[0].title = r'Teichm\"uller curves in \Omega\mathcal M_g(2g-2)^{\mathrm{hyp}}'
    pending.papers[0].abstract = (r'A value of $82.4%$ with '
                                  r'\href{https://example.invalid/a%20b}{source $x$}.')
    atomic_write_json(data / 'pending_run.json', pending)
    atomic_write_json(data / 'analysis_run.json', analysis)
    result = finalize_run(data / 'analysis_run.json', data_dir=data, site_dir=site)
    assert result.papers[0].paper == pending.papers[0]
    date = site / 'reports/2026-09-04'
    published = json.loads((date / 'report.json').read_text(encoding='utf-8'))
    assert published['papers'][0]['paper'] == pending.papers[0].model_dump(mode='json')
    for page in [date / 'index.html', site / 'index.html']:
        alts = [i['alt'] for i in Visible(page.read_text(encoding='utf-8')).images]
        assert r'\Omega\mathcal M_g(2g-2)^{\mathrm{hyp}}' in alts
    assert 'numeric percent is displayed literally' in (date / 'index.html').read_text(encoding='utf-8')
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
              for folder in (data, site) for p in folder.rglob('*') if p.is_file()}
    finalize_run(data / 'analysis_run.json', data_dir=data, site_dir=site)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns)
                      for folder in (data, site) for p in folder.rglob('*') if p.is_file()}

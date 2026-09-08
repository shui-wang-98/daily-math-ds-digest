import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import pytest

from src.config import load_config
from src.fetch_arxiv import parse_feed
from src.finalize_run import finalize_run
from src.math_render import html_text
from src.models import AnalysisRun, AnalyzedPaper, DailyReport, PaperAnalysis
from src.prepare_run import prepare_run
from src.rebuild_site import rebuild_site
from src.report import render_report_files, render_site_index
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Element:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def find(self, tag, class_name=None):
        found = []
        for child in self.children:
            if isinstance(child, Element):
                if child.tag == tag and (class_name is None or class_name in child.attrs.get('class', '').split()):
                    found.append(child)
                found.extend(child.find(tag, class_name))
        return found

    def text(self):
        return ''.join(c.text() if isinstance(c, Element) else c for c in self.children).strip()


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.root = Element('document')
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {'meta', 'link', 'img', 'br', 'hr', 'input'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        assert self.stack[-1].tag == tag, f'Unbalanced HTML element: {tag}'
        self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].children.append(data)


@pytest.fixture
def report():
    feed = parse_feed((ROOT/'tests/fixtures/math_ds.xml').read_text(encoding='utf-8'),
                      ['new', 'cross', 'replace-cross'])
    analysis = AnalysisRun.model_validate_json((ROOT/'tests/fixtures/analysis_run.json').read_text(encoding='utf-8'))
    return DailyReport(report_date=analysis.report_date, generated_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
                       feed_build_at=feed.build_at, category='math.DS', overview=analysis.overview,
                       papers=[AnalyzedPaper(paper=p, analysis=PaperAnalysis.model_validate(a.model_dump(exclude={'arxiv_id'})))
                               for p, a in zip(feed.papers, analysis.papers, strict=True)],
                       counts={a.priority: 1 for a in analysis.papers})


def document(path):
    return Document(path.read_text(encoding='utf-8')).root


def test_archive_all_dates_counts_no_new_and_future_links(tmp_path, report):
    config = load_config(ROOT/'config.yaml')
    empty = report.model_copy(update={'report_date': '2026-09-05', 'papers': [],
                                     'overview': 'No new papers.', 'counts': {key: 0 for key in report.counts}})
    future = report.model_copy(update={'report_date': '2099-01-12'})
    reports = [report, future, empty]
    for item in reports:
        render_report_files(item, config, ROOT/'templates', tmp_path)
    render_site_index(reports, config, ROOT/'templates', ROOT/'static', tmp_path)
    home = document(tmp_path/'index.html')
    assert home.find('h1')[0].text() == 'Daily math.DS Digest'
    rows = home.find('li', 'archive-row')
    assert [r.find('time')[0].attrs['datetime'] for r in rows] == ['2099-01-12', '2026-09-05', '2026-09-04']
    assert [r.find('dl')[0].find('dd')[-1].text() for r in rows] == ['3', '0', '3']
    assert [[n.text() for n in r.find('dl')[0].find('dd')] for r in rows] == [['1', '1', '1', '3'], ['0']*4, ['1', '1', '1', '3']]
    assert rows[1].find('p', 'no-papers')[0].text() == 'No new papers.'
    for row in rows:
        date = row.find('time')[0].text()
        assert row.find('a', 'open-report')[0].attrs['href'] == f'reports/{date}/'
    for page in tmp_path.rglob('*.html'):
        doc = document(page)
        for link in doc.find('a'):
            url = urlsplit(link.attrs['href'])
            if url.scheme or not url.path:
                continue
            target = page.parent/url.path
            assert (target/'index.html').is_file() if target.is_dir() else target.is_file()
    assert 'No new papers.' in document(tmp_path/'reports/2026-09-05/index.html').text()


def test_daily_native_details_full_fields_and_compact_low(tmp_path, report):
    render_report_files(report, load_config(ROOT/'config.yaml'), ROOT/'templates', tmp_path)
    doc = document(tmp_path/f'reports/{report.report_date}/index.html')
    assert not doc.find('script')
    assert [h.text() for h in doc.find('h2')] == ['High Priority', 'Related / Possibly Interesting', 'Low Priority']
    assert all(a.attrs['href'] == '../../' for a in doc.find('a', 'archive-home'))
    assert len(doc.find('a', 'archive-home')) == 2
    cards = doc.find('article')
    assert len(cards) == 2
    for card, item in zip(cards, [p for p in report.papers if p.analysis.priority != 'LOW PRIORITY'], strict=True):
        assert [dt.text() for dt in card.find('dt')] == ['Relevance', 'TL;DR', 'Problem', 'Main result', 'Methods / framework', 'Context', 'Prerequisites', 'Keywords']
        assert item.analysis.main_result in card.text()
        details = card.find('details')
        assert len(details) == 1
        assert details[0].find('summary')[0].text() == 'Original abstract'
        assert details[0].find('p', 'abstract')[0].text() == item.paper.abstract
        assert item.paper.abstract_url in [a.attrs['href'] for a in card.find('a')]
        assert item.paper.pdf_url in [a.attrs['href'] for a in card.find('a')]
    low = doc.find('ol', 'compact-paper-list')[0].find('li')
    assert len(low) == 1
    assert [c.tag for c in low[0].children if isinstance(c, Element)] == ['a', 'span', 'span']
    low_item = next(p for p in report.papers if p.analysis.priority == 'LOW PRIORITY')
    assert low[0].find('a')[0].text() == low_item.paper.title
    assert low[0].find('span', 'authors')[0].text() == ', '.join(low_item.paper.authors)
    assert low_item.paper.abstract not in doc.text()
    assert low_item.analysis.relevance_note not in doc.text()


def test_math_is_safe_embedded_vector_and_repeatable():
    source = r'Unicode: θ, ℝ. Source <script> & \(1-\frac{1}{d+1}\) and \(\Hau^s\).'
    output = str(html_text(source))
    doc = Document(output).root
    assert not doc.find('script')
    assert 'Unicode: θ, ℝ. Source <script> &' in doc.text()
    assert 'literal command names are retained' in doc.text()
    images = doc.find('img')
    assert len(images) == 2
    assert images[0].attrs['alt'] == r'1-\frac{1}{d+1}'
    for img in images:
        assert img.attrs['src'].startswith('data:image/svg+xml;base64,')
        svg = ET.fromstring(base64.b64decode(img.attrs['src'].split(',', 1)[1]))
        assert svg.tag == '{http://www.w3.org/2000/svg}svg'
        assert svg.findall('.//{http://www.w3.org/2000/svg}path')
    from src.math_render import _svg_formula
    _svg_formula.cache_clear()
    assert str(html_text(source)) == output


def test_rebuild_preserves_state_metadata_and_downloads(tmp_path):
    data, site = tmp_path/'data', tmp_path/'site'
    prepare_run(data_dir=data, local_feed=ROOT/'tests/fixtures/math_ds.xml', report_date='2026-09-04')
    analysis = AnalysisRun.model_validate_json((ROOT/'tests/fixtures/analysis_run.json').read_text(encoding='utf-8'))
    atomic_write_json(data/'analysis_run.json', analysis)
    finalized = finalize_run(data/'analysis_run.json', data_dir=data, site_dir=site)
    protected = [*data.rglob('*.json'), *site.rglob('*.pdf'), *site.rglob('*.md'), *site.rglob('*.json')]
    snapshot = lambda: {p:(p.read_bytes(), p.stat().st_mtime_ns) for p in protected}
    before = snapshot()
    (site/'reports/2026-09-04/index.html').write_text('outdated presentation', encoding='utf-8')
    assert rebuild_site(data_dir=data, site_dir=site) == [finalized]
    assert snapshot() == before
    assert 'Original abstract' in (site/'reports/2026-09-04/index.html').read_text(encoding='utf-8')
    html_before = (site/'reports/2026-09-04/index.html').read_bytes()
    rebuild_site(data_dir=data, site_dir=site)
    assert (site/'reports/2026-09-04/index.html').read_bytes() == html_before


def test_rebuild_failure_does_not_promote_partial_html(tmp_path, report, monkeypatch):
    import importlib
    module = importlib.import_module('src.rebuild_site')
    data, site = tmp_path/'data', tmp_path/'site'
    atomic_write_json(data/'reports/2026-09-04.json', report)
    site.mkdir()
    (site/'index.html').write_text('old homepage', encoding='utf-8')
    def fail(*args, **kwargs):
        raise ValueError('render failure')
    monkeypatch.setattr(module, 'render_site_index', fail)
    with pytest.raises(ValueError, match='render failure'):
        rebuild_site(data_dir=data, site_dir=site)
    assert (site/'index.html').read_text(encoding='utf-8') == 'old homepage'
    assert not (site/'reports').exists()


def test_rebuild_empty_archive_and_date_mismatch(tmp_path, report):
    data, site = tmp_path/'data', tmp_path/'site'
    rebuild_site(data_dir=data, site_dir=site)
    assert 'No reports have been generated yet.' in document(site/'index.html').text()
    before = (site/'index.html').read_bytes()
    atomic_write_json(data/'reports/2026-09-05.json', report)
    with pytest.raises(ValueError, match='Report date does not match'):
        rebuild_site(data_dir=data, site_dir=site)
    assert (site/'index.html').read_bytes() == before

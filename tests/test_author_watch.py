"""Synthetic Atom metadata derived from the existing RSS fixture; no live requests."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

import pytest
import requests

import src.author_watch as watch
import src.capture_feed as capture
import src.inbox as inbox
import src.prepare_run as preparer
from src.finalize_run import finalize_run
from src.models import AnalysisRun, AuthorFeedInput, AuthorFeedPage, AuthorWatchlist, DailyReport
from src.notify import notification_body
from src.rebuild_site import rebuild_site
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / 'tests/fixtures/math_ds.xml').read_bytes()
NOW = datetime(2026, 9, 4, 9, 15, tzinfo=timezone.utc)
WATCH = AuthorWatchlist(start_date='2026-09-04', authors=['Ruxi Shi', 'Masaki Tsukamoto'])
ANALYSIS = json.loads((ROOT / 'tests/fixtures/analysis_run.json').read_text(encoding='utf-8'))


def atom(*, ids=('2609.00001v1',), names=('Ruxi Shi',), total=None, start=0):
    source = ET.fromstring(RAW).find('channel/item')
    root = ET.Element(watch.ATOM + 'feed')
    ET.SubElement(root, watch.ATOM + 'updated').text = '2026-09-04T00:00:00-04:00'
    for tag, value in [('totalResults', len(ids) if total is None else total),
                       ('startIndex', start), ('itemsPerPage', watch.PAGE_SIZE)]:
        ET.SubElement(root, watch.OPEN + tag).text = str(value)
    for paper_id in ids:
        entry = ET.SubElement(root, watch.ATOM + 'entry')
        for tag, value in [('id', 'http://arxiv.org/abs/' + paper_id),
                           ('title', source.findtext('title')),
                           ('summary', 'Synthetic author search fixture. ' + source.findtext('description').split('Abstract:')[-1]),
                           ('published', '2026-09-04T01:00:00Z'),
                           ('updated', '2026-09-04T01:00:00Z')]:
            ET.SubElement(entry, watch.ATOM + tag).text = value
        for name in names:
            ET.SubElement(ET.SubElement(entry, watch.ATOM + 'author'), watch.ATOM + 'name').text = name
        ET.SubElement(entry, watch.ATOM + 'category', term='math.FA')
        ET.SubElement(entry, watch.ATOM + 'link', title='pdf', href='http://arxiv.org/pdf/' + paper_id)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def manifest(raw, config=WATCH, now=NOW):
    page = AuthorFeedPage(start=0, source_url=watch.query_url(config, '2026-09-04', 0),
                          sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw))
    return AuthorFeedInput(watchlist=config, fetched_at=now,
                           query_end_date='2026-09-04', pages=[page])


def config_file(tmp_path, config=WATCH):
    path = tmp_path / 'watchlist.yaml'
    atomic_write_json(path, config)
    return path


def archive(tmp_path, raw=None, rss=RAW, now=NOW):
    raw = atom(ids=('2609.99999v1',)) if raw is None else raw
    return inbox.persist_input(rss, inbox_dir=tmp_path/'inbox', fetched_at=now,
                                author_feed=manifest(raw, now=now), author_pages={'authors-00000.xml': raw})


def analysis_file(data, pending):
    full = {k: v for k, v in ANALYSIS['papers'][0].items() if k != 'prerequisites'}
    payload = AnalysisRun(report_date=pending.report_date, overview='Synthetic author-watch demonstration.',
                          papers=[{**full, 'arxiv_id': p.arxiv_id} for p in pending.papers])
    path = data/'analysis_run.json'
    atomic_write_json(path, payload)
    return path


def test_names_are_exact_normalized_not_fuzzy_or_subject_inferred():
    papers, total, _ = watch.parse_author_page(atom(names=('  ruxi   SHI ', 'Masaki Tsukamoto')),
                                                watchlist=WATCH, fetched_at=NOW, start=0)
    assert total == 1
    assert watch.matched_authors(papers[0], WATCH) == ['Ruxi Shi', 'Masaki Tsukamoto']
    assert watch.parse_author_page(atom(names=('R. Shi', 'Masaki Tsukamoto Jr.')),
                                    watchlist=WATCH, fetched_at=NOW, start=0)[0] == []
    with pytest.raises(ValueError, match='Duplicate'):
        AuthorWatchlist(start_date='2026-09-04', authors=['Ruxi Shi', 'ruxi shi'])
    with pytest.raises(ValueError, match='query operators'):
        AuthorWatchlist(start_date='2026-09-04', authors=['Ruxi Shi" OR all:physics'])


@pytest.mark.parametrize('raw', [b'<broken', b'<html>error</html>',
    atom().replace(b'math.FA', b''), atom().replace(b'arxiv.org/abs/', b'localhost/abs/'),
    atom().replace(b'arxiv.org/pdf/2609.00001v1', b'arxiv.org/pdf/2609.88888v1'),
    atom().replace(b'2026-09-04T00:00:00-04:00', b'2026-09-03T00:00:00-04:00'),
    atom().replace(b'2026-09-04T01:00:00Z', b'2026-09-03T01:00:00Z'),
    atom(total=2), atom(start=10),
])
def test_invalid_or_incomplete_author_input_never_persists(tmp_path, raw):
    with pytest.raises(ValueError):
        archive(tmp_path, raw)
    assert not (tmp_path/'inbox').exists()


def test_capture_validates_all_sources_before_persisting_and_keeps_original_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(watch.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(capture, 'utc_now', lambda: NOW)
    monkeypatch.setattr(capture, 'download_feed', lambda *args: RAW)
    path = config_file(tmp_path)
    def fail(*args):
        raise ValueError('author endpoint HTTP 503')
    monkeypatch.setattr(watch, 'download_feed', fail)
    with pytest.raises(ValueError, match='503'):
        capture.capture_feed(inbox_dir=tmp_path/'inbox', watchlist_path=path)
    assert not (tmp_path/'inbox').exists()
    raw = atom(ids=())
    monkeypatch.setattr(watch, 'download_feed', lambda *args: raw)
    source, folder = capture.capture_feed(inbox_dir=tmp_path/'inbox', watchlist_path=path)
    assert (folder/'feed.xml').read_bytes() == RAW
    assert (folder/'authors-00000.xml').read_bytes() == raw
    assert source.author_feed.watchlist == WATCH
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    assert capture.capture_feed(inbox_dir=tmp_path/'inbox', watchlist_path=path) == (source, folder)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    assert not (tmp_path/'state.json').exists()


def test_pagination_is_serial_complete_and_hash_checked(monkeypatch):
    monkeypatch.setattr(watch, 'PAGE_SIZE', 1)
    pages = [atom(ids=('2609.00001v1',), total=2), atom(ids=('2609.00002v1',), total=2, start=1)]
    calls, waits = [], []
    def download(url, *args):
        calls.append(url)
        return pages[len(calls)-1]
    monkeypatch.setattr(watch, 'download_feed', download)
    monkeypatch.setattr(watch.time, 'sleep', waits.append)
    source, files = watch.download_author_feeds(WATCH, fetched_at=NOW, timeout=45, user_agent='test')
    assert waits == [3, 3] and len(calls) == 2
    assert [p.arxiv_id for p in watch.validate_author_bundle(source, files)] == ['2609.00001', '2609.00002']
    files['authors-00001.xml'] += b' '
    with pytest.raises(ValueError, match='SHA-256'):
        watch.validate_author_bundle(source, files)


def test_offline_bundle_dedup_priority_render_notification_and_retry(tmp_path, monkeypatch):
    rss = RAW.replace(b'A. Researcher', b'Ruxi Shi')
    source, folder = archive(tmp_path, atom(ids=('2609.00001v1', '2609.99999v1')), rss=rss)
    path = config_file(tmp_path)
    def blocked(*args, **kwargs):
        raise AssertionError('Local author preparation or finalization attempted HTTP')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(preparer, 'utc_now', lambda: NOW)
    pending = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert len(pending.papers) == 4
    assert pending.followed_authors['2609.99999'] == ['Ruxi Shi']
    assert [p.arxiv_id for p in pending.papers].count('2609.00001') == 1
    assert pending.papers[-1].categories == ['math.FA']
    analysis = analysis_file(tmp_path, pending)
    report = finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path/'site')
    assert len(report.papers) == 4
    html = (tmp_path/'site/reports/2026-09-04/index.html').read_text(encoding='utf-8')
    assert 'IMPORTANT · Followed author: Ruxi Shi' in html and '<dt>Subjects</dt>' in html
    assert html.index('id="paper-2609.99999"') < html.index('id="paper-2609.00001"')
    assert 'math.FA' in html and 'First submitted: 2026-09-04' in html
    assert 'Prerequisites' not in html
    assert 'prerequisites' not in (tmp_path/'reports/2026-09-04.json').read_text(encoding='utf-8')
    body = notification_body(report, 'https://example.github.io/digest/')
    assert '**IMPORTANT' in body and 'arXiv:2609.99999' in body and 'Ruxi Shi' in body
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob('*') if p.is_file()}
    assert finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path/'site') == report
    with pytest.raises(inbox.InboxUpToDate):
        preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
    assert source.input_id in json.loads((tmp_path/'state.json').read_text())['processed_inputs']
    (folder/'authors-00000.xml').write_bytes(b'corrupt')
    with pytest.raises(inbox.InputNotReady, match='SHA-256'):
        preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)


def test_followed_author_cannot_be_downgraded_or_silently_marked_seen(tmp_path):
    archive(tmp_path)
    pending = preparer.prepare_run(data_dir=tmp_path, watchlist_path=config_file(tmp_path))
    path = analysis_file(tmp_path, pending)
    payload = json.loads(path.read_text())
    payload['papers'][-1]['priority'] = 'LOW PRIORITY'
    atomic_write_json(path, payload)
    with pytest.raises(ValueError, match='Followed-author'):
        finalize_run(path, data_dir=tmp_path, site_dir=tmp_path/'site')
    assert not (tmp_path/'state.json').exists() and not (tmp_path/'reports').exists()
    assert preparer.prepare_run(data_dir=tmp_path, watchlist_path=config_file(tmp_path)) == pending
    finalize_run(analysis_file(tmp_path, pending), data_dir=tmp_path, site_dir=tmp_path/'site')


def test_missing_author_capture_is_not_empty_and_older_rss_backlog_recovers(tmp_path, monkeypatch):
    inbox.persist_input(RAW, inbox_dir=tmp_path/'inbox', fetched_at=NOW)
    path = config_file(tmp_path)
    monkeypatch.setattr(preparer, 'utc_now', lambda: NOW)
    with pytest.raises(inbox.InputNotReady, match='author metadata is missing'):
        preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert not (tmp_path/'pending_run.json').exists()
    archive(tmp_path, now=NOW + timedelta(hours=1))
    first = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert first.source_input.author_feed is None
    finalize_run(analysis_file(tmp_path, first), data_dir=tmp_path, site_dir=tmp_path/'site')
    second = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert [p.arxiv_id for p in second.papers] == ['2609.99999']
    report = finalize_run(analysis_file(tmp_path, second), data_dir=tmp_path, site_dir=tmp_path/'site')
    assert len(report.papers) == 4
    assert len(report.source_inputs) == 2


def test_legacy_report_and_analysis_remain_readable_without_prerequisites(tmp_path):
    pending = preparer.prepare_run(data_dir=tmp_path, local_feed=ROOT/'tests/fixtures/math_ds.xml',
                                   report_date='2026-09-04')
    report = finalize_run(ROOT/'tests/fixtures/analysis_run.json', data_dir=tmp_path, site_dir=tmp_path/'site')
    legacy = report.model_dump(mode='json')
    legacy['papers'][0]['analysis']['prerequisites'] = ['Historical content']
    archive_path = tmp_path/'reports/2026-09-04.json'
    atomic_write_json(archive_path, legacy)
    before = archive_path.read_bytes()
    assert DailyReport.model_validate_json(before) == report
    rebuild_site(data_dir=tmp_path, site_dir=tmp_path/'site')
    assert archive_path.read_bytes() == before
    assert 'Prerequisites' not in (tmp_path/'site/reports/2026-09-04/index.html').read_text(encoding='utf-8')
    schema = AnalysisRun.model_json_schema()['$defs']['PaperAnalysisInput']
    assert 'prerequisites' not in schema['properties']


def test_empty_author_feed_is_valid_but_cannot_erase_same_day_report(tmp_path, monkeypatch):
    archive(tmp_path)
    path = config_file(tmp_path)
    monkeypatch.setattr(preparer, 'utc_now', lambda: NOW)
    first = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    report = finalize_run(analysis_file(tmp_path, first), data_dir=tmp_path, site_dir=tmp_path/'site')
    archive(tmp_path, atom(ids=()), now=NOW+timedelta(hours=1))
    second = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert not second.papers
    repeated = finalize_run(analysis_file(tmp_path, second), data_dir=tmp_path, site_dir=tmp_path/'site')
    assert repeated.papers == report.papers and repeated.overview == report.overview


def test_http_retries_respect_server_wait_and_shared_minimum_interval(monkeypatch):
    from urllib3.response import HTTPResponse
    from src.fetch_arxiv import ArxivRetry
    waits = []
    monkeypatch.setattr(watch.time, 'sleep', waits.append)
    retry = ArxivRetry(total=4, backoff_factor=1.5)
    retry.sleep(HTTPResponse(status=429))
    retry.sleep(HTTPResponse(status=429, headers={'Retry-After': '20'}))
    retry.sleep(HTTPResponse(status=429, headers={'Retry-After': '1'}))
    assert waits == [3, 20, 3]


def test_exhausted_http_limit_reports_actual_status_and_retry_after(monkeypatch):
    from src.fetch_arxiv import ArxivFeedError, download_feed
    response = requests.Response()
    response.status_code = 429
    response.headers['Retry-After'] = '30'
    response.url = watch.API_URL
    monkeypatch.setattr(requests.Session, 'get', lambda *args, **kwargs: response)
    with pytest.raises(ArxivFeedError, match='HTTP 429; Retry-After=30'):
        download_feed(watch.API_URL)

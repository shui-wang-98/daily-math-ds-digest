"""Author preference on the existing math.DS fixture, with local HTTP blocked."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import time
import xml.etree.ElementTree as ET

import pytest
import requests

import src.author_watch as watch
import src.capture_feed as capture
import src.inbox as inbox
import src.prepare_run as preparer
from src.fetch_arxiv import parse_feed
from src.finalize_run import finalize_run
from src.models import AnalysisRun, AuthorWatchlist, DailyReport
from src.notify import notification_body
from src.rebuild_site import rebuild_site
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / 'tests/fixtures/math_ds.xml').read_bytes()
NOW = datetime(2026, 9, 4, 9, 15, tzinfo=timezone.utc)
WATCH = AuthorWatchlist(authors=['Ruxi Shi', 'Masaki Tsukamoto'])
ANALYSIS = json.loads((ROOT / 'tests/fixtures/analysis_run.json').read_text(encoding='utf-8'))


def watched_rss():
    return (RAW.replace(b'Ada Author', b'Ruxi Shi')
            .replace(b'Clara Applied', b'Masaki Tsukamoto')
            .replace(b'Dora Corrector', b'Ruxi Shi'))


def config_file(tmp_path, config=WATCH):
    path = tmp_path / 'watchlist.yaml'
    atomic_write_json(path, config)
    return path


def analysis_file(data, pending):
    full = {k: v for k, v in ANALYSIS['papers'][0].items() if k != 'prerequisites'}
    payload = AnalysisRun(report_date=pending.report_date, overview='Synthetic author-watch demonstration.',
                          papers=[{**full, 'arxiv_id': p.arxiv_id} for p in pending.papers])
    path = data/'analysis_run.json'
    atomic_write_json(path, payload)
    return path


def archive(tmp_path, raw=None, now=NOW):
    return inbox.persist_input(watched_rss() if raw is None else raw,
                               inbox_dir=tmp_path/'inbox', fetched_at=now)


def test_names_are_exact_normalized_and_limited_to_math_ds():
    paper = parse_feed(RAW, inbox.INCLUDE_TYPES).papers[0]
    paper.authors = ['  ruxi   SHI ', 'Ｍasaki Tsukamoto']
    assert watch.matched_authors(paper, WATCH) == WATCH.authors
    paper.categories = ['math.FA']
    assert watch.matched_authors(paper, WATCH) == []
    paper.categories = ['math.AP', 'math.DS']
    paper.authors = ['R. Shi', 'Masaki Tsukamoto Jr.']
    assert watch.matched_authors(paper, WATCH) == []
    with pytest.raises(ValueError, match='Duplicate'):
        AuthorWatchlist(authors=['Ruxi Shi', 'ruxi shi'])
    with pytest.raises(ValueError, match='scope'):
        AuthorWatchlist(scope='all', authors=WATCH.authors)
    assert watch.load_watchlist() == WATCH


def test_cloud_capture_requests_only_existing_math_ds_rss(tmp_path, monkeypatch):
    calls = []
    def get(self, url, **kwargs):
        calls.append(url)
        response = requests.Response()
        response.status_code, response._content = 200, RAW
        return response
    monkeypatch.setattr(requests.Session, 'get', get)
    monkeypatch.setattr(capture, 'utc_now', lambda: NOW)
    source, folder = capture.capture_feed(inbox_dir=tmp_path/'inbox')
    assert calls == [inbox.SOURCE_URL]
    assert {p.name for p in folder.iterdir()} == {'feed.xml', 'manifest.json'}
    assert (folder/'feed.xml').read_bytes() == RAW
    assert source.input_id == f'{source.feed_date}/{source.sha256}'


def test_offline_matching_filters_render_notification_and_retry(tmp_path, monkeypatch):
    source, _ = archive(tmp_path)
    path = config_file(tmp_path)
    def blocked(*args, **kwargs):
        raise AssertionError('Local preparation or finalization attempted HTTP')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(preparer, 'utc_now', lambda: NOW)
    pending = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert [p.announce_type for p in pending.papers] == ['new', 'cross', 'replace-cross']
    assert pending.followed_authors == {'2609.00001': ['Ruxi Shi'], '2609.00002': ['Masaki Tsukamoto']}
    assert '2501.12345' not in {p.arxiv_id for p in pending.papers}
    assert not (tmp_path/'state.json').exists()
    analysis = analysis_file(tmp_path, pending)
    report = finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path/'site')
    html = (tmp_path/'site/reports/2026-09-04/index.html').read_text(encoding='utf-8')
    assert len(report.papers) == 3
    assert all(f'IMPORTANT · Followed author: {name}' in html for name in WATCH.authors)
    assert html.count('<dt>Subjects</dt>') == 3 and 'math.AP · math.DS' in html
    assert 'Prerequisites' not in html and 'author search' not in html
    for paper in pending.papers:
        assert html.count(f'id="paper-{paper.arxiv_id}"') == 1
        assert paper.abstract in html
    assert html.index('id="paper-2609.00002"') < html.index('id="paper-2608.00003"')
    backend = (tmp_path/'reports/2026-09-04.json').read_bytes()
    assert b'prerequisites' not in backend
    assert backend == (tmp_path/'site/reports/2026-09-04/report.json').read_bytes()
    body = notification_body(report, 'https://example.github.io/digest/')
    assert '**IMPORTANT' in body and 'arXiv:2609.00002' in body
    assert all(name in body for name in WATCH.authors)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob('*') if p.is_file()}
    assert finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path/'site') == report
    with pytest.raises(inbox.InboxUpToDate):
        preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
    assert source.input_id in json.loads((tmp_path/'state.json').read_text())['processed_inputs']


@pytest.mark.parametrize('paper_index', [0, 1])
def test_followed_author_cannot_be_downgraded_or_silently_marked_seen(tmp_path, paper_index):
    archive(tmp_path)
    pending = preparer.prepare_run(data_dir=tmp_path, watchlist_path=config_file(tmp_path))
    path = analysis_file(tmp_path, pending)
    payload = json.loads(path.read_text())
    payload['papers'][paper_index]['priority'] = 'LOW PRIORITY'
    atomic_write_json(path, payload)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='Followed-author'):
        finalize_run(path, data_dir=tmp_path, site_dir=tmp_path/'site')
    assert not (tmp_path/'state.json').exists() and not (tmp_path/'reports').exists()
    assert preparer.prepare_run(data_dir=tmp_path, watchlist_path=config_file(tmp_path)) == pending
    assert path.read_bytes() == before
    finalize_run(analysis_file(tmp_path, pending), data_dir=tmp_path, site_dir=tmp_path/'site')


def test_resume_keeps_watchlist_snapshot_and_rejects_tampered_matches(tmp_path):
    archive(tmp_path)
    path = config_file(tmp_path)
    pending = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    analysis = analysis_file(tmp_path, pending)
    config_file(tmp_path, AuthorWatchlist(authors=[]))
    assert preparer.prepare_run(data_dir=tmp_path, watchlist_path=path) == pending
    atomic_write_json(tmp_path/'pending_run.json', pending.model_copy(update={'followed_authors': {}}))
    with pytest.raises(ValueError, match='matches differ'):
        finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path/'site')
    assert not (tmp_path/'state.json').exists()


def test_legacy_report_and_analysis_remain_readable_without_prerequisites(tmp_path):
    preparer.prepare_run(data_dir=tmp_path, local_feed=ROOT/'tests/fixtures/math_ds.xml', report_date='2026-09-04')
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
    assert 'prerequisites' not in AnalysisRun.model_json_schema()['$defs']['PaperAnalysisInput']['properties']


def test_successful_empty_feed_cannot_erase_same_day_followed_report(tmp_path, monkeypatch):
    archive(tmp_path)
    path = config_file(tmp_path)
    monkeypatch.setattr(preparer, 'utc_now', lambda: NOW)
    first = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    report = finalize_run(analysis_file(tmp_path, first), data_dir=tmp_path, site_dir=tmp_path/'site')
    root = ET.fromstring(RAW)
    channel = root.find('channel')
    for item in list(channel.findall('item')):
        channel.remove(item)
    archive(tmp_path, ET.tostring(root), now=NOW+timedelta(hours=1))
    second = preparer.prepare_run(data_dir=tmp_path, watchlist_path=path)
    assert not second.papers and not second.followed_authors
    repeated = finalize_run(analysis_file(tmp_path, second), data_dir=tmp_path, site_dir=tmp_path/'site')
    assert repeated.papers == report.papers and repeated.overview == report.overview


def test_http_retries_respect_server_wait_and_minimum_interval(monkeypatch):
    from urllib3.response import HTTPResponse
    from src.fetch_arxiv import ArxivRetry
    waits = []
    monkeypatch.setattr(time, 'sleep', waits.append)
    retry = ArxivRetry(total=4, backoff_factor=1.5)
    for headers in [{}, {'Retry-After': '20'}, {'Retry-After': '1'}]:
        retry.sleep(HTTPResponse(status=429, headers=headers))
    assert waits == [3, 20, 3]


def test_exhausted_http_limit_reports_actual_status_and_retry_after(monkeypatch):
    from src.fetch_arxiv import ArxivFeedError, download_feed
    response = requests.Response()
    response.status_code = 429
    response.headers['Retry-After'] = '30'
    response.url = inbox.SOURCE_URL
    monkeypatch.setattr(requests.Session, 'get', lambda *args, **kwargs: response)
    with pytest.raises(ArxivFeedError, match='HTTP 429; Retry-After=30'):
        download_feed(inbox.SOURCE_URL)

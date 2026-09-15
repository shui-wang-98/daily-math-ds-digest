import hashlib
import json
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
import requests

import src.capture_feed as capture
import src.finalize_run as finalizer
import src.inbox as inbox
import src.prepare_run as preparer
from src.fetch_arxiv import ArxivFeedError
from src.models import AnalysisRun
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / 'tests/fixtures/math_ds.xml').read_bytes()
ANALYSIS = json.loads((ROOT / 'tests/fixtures/analysis_run.json').read_text(encoding='utf-8'))
NOW = datetime(2026, 9, 4, 9, 15, tzinfo=timezone.utc)


def rss(day='2026-09-04', *, empty=False, replacement_only=False):
    root = ET.fromstring(RAW)
    channel = root.find('channel')
    published = datetime.fromisoformat(day + 'T04:00:00+00:00')
    for node in root.iter('pubDate'):
        node.text = format_datetime(published)
    channel.find('lastBuildDate').text = format_datetime(published + timedelta(hours=1))
    for item in list(channel.findall('item')):
        kind = item.find('{http://arxiv.org/schemas/atom}announce_type').text
        if empty or (replacement_only and kind != 'replace'):
            channel.remove(item)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def archive(data, raw=RAW, now=NOW):
    return inbox.persist_input(raw, inbox_dir=data / 'inbox', fetched_at=now)


def write_analysis(data, pending):
    by_title = {paper.title: entry for paper, entry in zip(
        inbox.validate_rss(RAW, NOW)[0].papers, ANALYSIS['papers'], strict=True)}
    payload = AnalysisRun(report_date=pending.report_date,
                          overview=ANALYSIS['overview'] if pending.papers else 'No new papers.',
                          papers=[{**by_title[p.title], 'arxiv_id': p.arxiv_id} for p in pending.papers])
    path = data / 'analysis_run.json'
    atomic_write_json(path, payload)
    return path


def test_raw_capture_is_validated_immutable_and_retraceable(tmp_path):
    source, folder = archive(tmp_path)
    assert (folder / 'feed.xml').read_bytes() == RAW
    assert source.sha256 == hashlib.sha256(RAW).hexdigest()
    assert source.byte_length == len(RAW)
    assert source.feed_date == '2026-09-04'
    assert source.fetched_at == NOW
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    assert archive(tmp_path, now=NOW + timedelta(hours=1)) == (source, folder)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    assert not (tmp_path / 'state.json').exists()
    assert inbox.read_input(folder)[0] == source


@pytest.mark.parametrize('raw', [
    b'<broken', b'<html>Service unavailable</html>',
    RAW.replace(b'math.DS', b'math.AP'),
    RAW.replace(b'<pubDate>', b'<missingDate>').replace(b'</pubDate>', b'</missingDate>'),
    RAW.replace(b'<arxiv:announce_type>new', b'<arxiv:announce_type>unknown'),
    RAW.replace(b'https://arxiv.org/abs/2609.00001', b'https://arxiv.org/abs/2609.99999'),
])
def test_invalid_capture_never_persists(tmp_path, raw):
    with pytest.raises(inbox.InputNotReady):
        archive(tmp_path, raw)
    assert not (tmp_path / 'inbox').exists()


def test_stale_and_future_inputs_fail_instead_of_becoming_empty(tmp_path):
    with pytest.raises(inbox.InputNotReady, match='Stale RSS'):
        archive(tmp_path, now=NOW + timedelta(days=3))
    with pytest.raises(inbox.InputNotReady, match='future RSS'):
        archive(tmp_path, now=NOW.replace(hour=3))
    assert not (tmp_path / 'inbox').exists()


def test_capture_download_failure_and_success(tmp_path, monkeypatch):
    def fail(*args):
        raise ArxivFeedError('simulated HTTP 503')
    monkeypatch.setattr(capture, 'download_feed', fail)
    with pytest.raises(ArxivFeedError, match='503'):
        capture.capture_feed(inbox_dir=tmp_path / 'inbox')
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(capture, 'download_feed', lambda *args: RAW)
    monkeypatch.setattr(capture, 'utc_now', lambda: NOW)
    source, folder = capture.capture_feed(inbox_dir=tmp_path / 'inbox')
    assert source.source_url == inbox.SOURCE_URL
    assert (folder / 'feed.xml').read_bytes() == RAW


def test_partial_capture_write_failure_does_not_publish_pair(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError('manifest disk failure')
    monkeypatch.setattr(inbox, 'atomic_write_json', fail)
    with pytest.raises(OSError, match='manifest disk failure'):
        archive(tmp_path)
    assert inbox.read_inbox(tmp_path / 'inbox') == []
    assert not list(tmp_path.rglob('feed.xml'))


def test_missing_and_corrupt_inbox_preserve_state(tmp_path):
    atomic_write_json(tmp_path / 'state.json', {'seen': {}})
    before = (tmp_path / 'state.json').read_bytes()
    with pytest.raises(inbox.InputNotReady, match='missing'):
        preparer.prepare_run(data_dir=tmp_path)
    _, folder = archive(tmp_path)
    (folder / 'feed.xml').write_bytes(b'corrupted')
    with pytest.raises(inbox.InputNotReady, match='SHA-256'):
        preparer.prepare_run(data_dir=tmp_path)
    (folder / 'manifest.json').unlink()
    with pytest.raises(inbox.InputNotReady):
        preparer.prepare_run(data_dir=tmp_path)
    assert (tmp_path / 'state.json').read_bytes() == before
    assert not (tmp_path / 'pending_run.json').exists()


def test_default_preparation_and_finalization_are_offline(tmp_path, monkeypatch):
    def block(*args, **kwargs):
        raise AssertionError('HTTP or socket access attempted')
    monkeypatch.setattr(requests.sessions.Session, 'request', block)
    monkeypatch.setattr(socket, 'create_connection', block)
    monkeypatch.setattr(preparer, 'fetch_feed', block)
    source, _ = archive(tmp_path)
    pending = preparer.prepare_run(data_dir=tmp_path)
    assert pending.source_input == source
    assert pending.report_date == '2026-09-04'
    assert [p.announce_type for p in pending.papers] == ['new', 'cross', 'replace-cross']
    path = write_analysis(tmp_path, pending)
    report = finalizer.finalize_run(path, data_dir=tmp_path, site_dir=tmp_path / 'site')
    assert report.source_inputs == [source]
    state = json.loads((tmp_path / 'state.json').read_text())
    assert set(state['seen']) == {p.arxiv_id for p in pending.papers}
    assert set(state['processed_inputs']) == {source.input_id}


@pytest.mark.parametrize('replacement_only', [False, True])
def test_valid_empty_input_generates_a_dated_no_papers_report(tmp_path, replacement_only):
    source, _ = archive(tmp_path, rss(empty=not replacement_only, replacement_only=replacement_only))
    pending = preparer.prepare_run(data_dir=tmp_path)
    assert not pending.papers
    report = finalizer.finalize_run(write_analysis(tmp_path, pending), data_dir=tmp_path, site_dir=tmp_path / 'site')
    assert report.report_date == source.feed_date
    assert not report.papers and sum(report.counts.values()) == 0
    folder = tmp_path / 'site/reports' / source.feed_date
    assert {p.name for p in folder.iterdir()} == {'index.html', 'report.json'}
    assert 'No new papers.' in (folder / 'index.html').read_text(encoding='utf-8')


def test_pending_and_analysis_survive_resume_before_processing_backlog(tmp_path):
    first, _ = archive(tmp_path)
    pending = preparer.prepare_run(data_dir=tmp_path)
    analysis = write_analysis(tmp_path, pending)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in [analysis, tmp_path / 'pending_run.json']}
    second, _ = archive(tmp_path, rss('2026-09-07').replace(b'2609.00001', b'2609.10001'), NOW + timedelta(days=3))
    assert preparer.prepare_run(data_dir=tmp_path) == pending
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
    finalizer.finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path / 'site')
    next_run = preparer.prepare_run(data_dir=tmp_path)
    assert next_run.source_input == second and next_run.report_date == '2026-09-07'
    assert [p.arxiv_id for p in next_run.papers] == ['2609.10001']
    finalizer.finalize_run(write_analysis(tmp_path, next_run), data_dir=tmp_path, site_dir=tmp_path / 'site')
    state = json.loads((tmp_path / 'state.json').read_text())
    assert set(state['processed_inputs']) == {first.input_id, second.input_id}
    assert len(state['seen']) == 4


def test_duplicate_feed_ids_and_repeated_runs_are_idempotent(tmp_path, monkeypatch):
    root = ET.fromstring(RAW)
    root.find('channel').append(ET.fromstring(ET.tostring(root.find('channel/item'))))
    archive(tmp_path, ET.tostring(root))
    monkeypatch.setattr(preparer, 'utc_now', lambda: NOW)
    pending = preparer.prepare_run(data_dir=tmp_path)
    assert len(pending.papers) == 3
    analysis = write_analysis(tmp_path, pending)
    finalizer.finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path / 'site')
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob('*') if p.is_file()}
    finalizer.finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path / 'site')
    with pytest.raises(inbox.InboxUpToDate):
        preparer.prepare_run(data_dir=tmp_path)
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
    monkeypatch.setattr(preparer, 'utc_now', lambda: NOW + timedelta(days=3))
    with pytest.raises(inbox.InputNotReady, match='Input not ready'):
        preparer.prepare_run(data_dir=tmp_path)
    assert not (tmp_path / 'site/reports/2026-09-07').exists()


def test_changed_same_day_input_cannot_erase_a_nonempty_report(tmp_path):
    archive(tmp_path)
    pending = preparer.prepare_run(data_dir=tmp_path)
    report = finalizer.finalize_run(write_analysis(tmp_path, pending), data_dir=tmp_path, site_dir=tmp_path / 'site')
    archive(tmp_path, RAW + b'\n', NOW + timedelta(hours=1))
    pending = preparer.prepare_run(data_dir=tmp_path)
    assert pending.papers == []
    updated = finalizer.finalize_run(write_analysis(tmp_path, pending), data_dir=tmp_path, site_dir=tmp_path / 'site')
    assert updated.papers == report.papers and updated.overview == report.overview
    assert len(updated.source_inputs) == 2


@pytest.mark.parametrize('failure', ['promotion', 'state'])
def test_failed_finalization_resumes_without_losing_analysis(tmp_path, monkeypatch, failure):
    source, _ = archive(tmp_path)
    pending = preparer.prepare_run(data_dir=tmp_path)
    analysis = write_analysis(tmp_path, pending)
    analysis_before = analysis.read_bytes()
    original = finalizer.atomic_write_json
    def fail(path, payload):
        if failure == 'promotion' or Path(path).name == 'state.json':
            raise OSError('simulated finalization failure')
        original(path, payload)
    with monkeypatch.context() as patch:
        patch.setattr(finalizer, 'atomic_write_bytes' if failure == 'promotion' else 'atomic_write_json', fail)
        with pytest.raises(OSError, match='simulated finalization failure'):
            finalizer.finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path / 'site')
    assert not (tmp_path / 'state.json').exists()
    assert preparer.prepare_run(data_dir=tmp_path) == pending
    assert analysis.read_bytes() == analysis_before
    finalizer.finalize_run(analysis, data_dir=tmp_path, site_dir=tmp_path / 'site')
    assert source.input_id in json.loads((tmp_path / 'state.json').read_text())['processed_inputs']


def test_tampered_pending_cannot_mark_input_completed(tmp_path):
    archive(tmp_path)
    pending = preparer.prepare_run(data_dir=tmp_path)
    pending.papers.pop()
    atomic_write_json(tmp_path / 'pending_run.json', pending)
    with pytest.raises(inbox.InputNotReady, match='every unseen'):
        finalizer.finalize_run(write_analysis(tmp_path, pending), data_dir=tmp_path, site_dir=tmp_path / 'site')
    assert not (tmp_path / 'state.json').exists()


def test_fixture_cannot_target_production_and_inbox_date_cannot_be_overridden(tmp_path):
    with pytest.raises(ValueError, match='isolated'):
        preparer.prepare_run(local_feed=ROOT / 'tests/fixtures/math_ds.xml')
    with pytest.raises(ValueError, match='only supported'):
        preparer.prepare_run(data_dir=tmp_path, report_date='2026-09-04')


def test_missing_input_cli_has_distinct_nonzero_result(tmp_path):
    proc = subprocess.run([sys.executable, '-m', 'src.prepare_run', '--data-dir', str(tmp_path)],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 2
    assert 'INPUT NOT READY' in proc.stdout
    assert not list(tmp_path.iterdir())

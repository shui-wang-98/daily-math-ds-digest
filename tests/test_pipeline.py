import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

import src.finalize_run as finalizer
import src.prepare_run as preparer
from src.models import AnalysisRun
from src.notify import latest_report
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/math_ds.xml"
ANALYSIS = ROOT / "tests/fixtures/analysis_run.json"
DATE = "2026-09-04"


@pytest.fixture
def run(tmp_path):
    data, site = tmp_path / "data", tmp_path / "site"
    pending = preparer.prepare_run(data_dir=data, local_feed=FIXTURE, report_date=DATE)
    payload = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    path = data / "analysis_run.json"
    atomic_write_json(path, payload)
    return data, site, pending, payload, path


def finish(run):
    data, site, _, _, path = run
    return finalizer.finalize_run(path, data_dir=data, site_dir=site)


def snapshot(*roots):
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
            for root in roots for p in root.rglob("*") if p.is_file()}


def test_preparation_preserves_state_and_normalizes_ids(tmp_path):
    data = tmp_path / "data"
    state = {"seen": {"https://arxiv.org/abs/2609.00001v4": {"first_seen_report": "2026-09-01"}}}
    atomic_write_json(data / "state.json", state)
    before = (data / "state.json").read_bytes()
    pending = preparer.prepare_run(data_dir=data, local_feed=FIXTURE, report_date=DATE)
    assert (data / "state.json").read_bytes() == before
    assert [p.arxiv_id for p in pending.papers] == ["2609.00002", "2608.00003"]
    assert pending.research_profile["high_priority"]
    assert (data / "pending_run.json").is_file()
    assert not list(data.glob(".pending_run.json.*"))


def test_preparation_does_not_create_state(run):
    assert not (run[0] / "state.json").exists()


def test_preparation_deduplicates_feed_ids(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8")
    first = text[text.index("    <item>"):text.index("    </item>") + len("    </item>")]
    fixture = tmp_path / "duplicate.xml"
    fixture.write_text(text.replace("  </channel>", first + "\n  </channel>"), encoding="utf-8")
    pending = preparer.prepare_run(data_dir=tmp_path / "data", local_feed=fixture)
    assert len(pending.papers) == 3


def test_report_date_uses_warsaw_run_day(tmp_path, monkeypatch):
    monkeypatch.setattr(preparer, "utc_now", lambda: datetime(2026, 9, 6, 22, 30, tzinfo=timezone.utc))
    pending = preparer.prepare_run(data_dir=tmp_path, local_feed=FIXTURE)
    assert pending.report_date == "2026-09-07"


@pytest.mark.parametrize("mutation,match", [
    (lambda p: p["papers"].pop(), "missing="),
    (lambda p: p["papers"].append(copy.deepcopy(p["papers"][0])), "Duplicate"),
    (lambda p: p["papers"][0].update(arxiv_id="2609.99999"), "unexpected="),
    (lambda p: p.update(report_date="2026-09-05"), "Mismatched report date"),
    (lambda p: p["papers"][0].update(priority="IMPORTANT"), "priority"),
    (lambda p: p["papers"][0].update(confidence="certain"), "confidence"),
    (lambda p: p["papers"][0].pop("methods"), "methods"),
    (lambda p: p["papers"][0].update(main_result=""), "main_result"),
    (lambda p: p["papers"][0].update(methods="inferred"), "methods"),
    (lambda p: p["papers"][0].update(title="Replaced metadata"), "title"),
    (lambda p: p.update(overview=" "), "overview"),
    (lambda p: p.update(report_date="../../invalid"), "report_date"),
])
def test_invalid_analysis_leaves_state_and_reports_untouched(run, mutation, match):
    data, site, _, payload, path = run
    atomic_write_json(data / "state.json", {"seen": {}})
    before = (data / "state.json").read_bytes()
    mutation(payload)
    atomic_write_json(path, payload)
    with pytest.raises((ValueError, ValidationError), match=match):
        finish(run)
    assert (data / "state.json").read_bytes() == before
    assert not site.exists()
    assert not (data / "reports").exists()


def test_versioned_duplicate_is_rejected(run):
    payload = run[3]
    payload["papers"].append({**payload["papers"][0], "arxiv_id": "arXiv:2609.00001v9"})
    with pytest.raises(ValidationError, match="Duplicate"):
        AnalysisRun.model_validate(payload)


def test_full_offline_outputs_and_idempotency(run):
    data, site, pending, _, _ = run
    report = finish(run)
    folder = site / "reports" / DATE
    assert (data / "reports" / f"{DATE}.json").is_file()
    assert (folder / "report.json").is_file()
    html = (folder / "index.html").read_text(encoding="utf-8")
    assert {p.name for p in folder.iterdir()} == {"index.html", "report.json"}
    text = " ".join(html.split())
    assert "2609.00002" in text
    assert pending.papers[1].abstract not in text
    assert pending.papers[0].abstract in text
    assert pending.papers[2].abstract in text
    assert "reports/2026-09-04/" in (site / "index.html").read_text(encoding="utf-8")
    assert (site / "assets/style.css").is_file()
    assert (site / ".nojekyll").is_file()
    state = json.loads((data / "state.json").read_text(encoding="utf-8"))
    assert set(state["seen"]) == {p.arxiv_id for p in pending.papers}
    assert latest_report(data, site) == report
    before = snapshot(data, site)
    assert finish(run) == report
    assert snapshot(data, site) == before


@pytest.mark.parametrize("failure", ["html", "json", "index", "promotion"])
def test_failure_does_not_mark_seen_and_retry_recovers(run, monkeypatch, failure):
    import src.report as renderer
    data, site = run[:2]
    atomic_write_json(data / "state.json", {"seen": {}})
    before = (data / "state.json").read_bytes()
    def fail(*args, **kwargs):
        raise OSError("simulated failure")
    with monkeypatch.context() as patch:
        if failure == "html":
            patch.setattr(renderer, "render_report_html", fail)
        elif failure == "json":
            patch.setattr(renderer, "atomic_write_json", fail)
        elif failure == "index":
            patch.setattr(finalizer, "render_site_index", fail)
        else:
            patch.setattr(finalizer, "atomic_write_bytes", fail)
        with pytest.raises(OSError, match="simulated failure"):
            finish(run)
    assert (data / "state.json").read_bytes() == before
    assert not (data / "reports").exists()
    assert not list(data.glob(".finalize-*"))
    finish(run)
    assert len(json.loads((data / "state.json").read_text(encoding="utf-8"))["seen"]) == 3


def test_failed_state_write_recovers_existing_report(run, monkeypatch):
    original = finalizer.atomic_write_json
    def fail_state(path, payload):
        if Path(path).name == "state.json":
            raise OSError("state failure")
        original(path, payload)
    with monkeypatch.context() as patch:
        patch.setattr(finalizer, "atomic_write_json", fail_state)
        with pytest.raises(OSError, match="state failure"):
            finish(run)
    assert not (run[0] / "state.json").exists()
    before = snapshot(run[1])
    finish(run)
    assert snapshot(run[1]) == before
    assert (run[0] / "state.json").exists()


def test_repair_damaged_artifact_is_idempotent(run):
    finish(run)
    html = run[1] / "reports" / DATE / "index.html"
    original = html.read_bytes()
    html.write_bytes(b"damaged")
    finish(run)
    assert html.read_bytes() == original


def test_stale_pending_cannot_duplicate_paper_on_another_day(run):
    finish(run)
    data, _, pending, payload, path = run
    atomic_write_json(data / "pending_run.json", pending.model_copy(update={"report_date": "2026-09-07"}))
    atomic_write_json(path, {**payload, "report_date": "2026-09-07"})
    before = snapshot(data, run[1])
    with pytest.raises(ValueError, match="Stale pending paper"):
        finish(run)
    assert snapshot(data, run[1]) == before


def test_no_new_papers_and_same_day_repreparation(run):
    data, site, _, _, path = run
    original = finish(run)
    pending = preparer.prepare_run(data_dir=data, local_feed=FIXTURE, report_date=DATE)
    assert not pending.papers
    atomic_write_json(path, {"report_date": DATE, "overview": "No new papers.", "papers": []})
    assert finish(run) == original
    pending = preparer.prepare_run(data_dir=data, local_feed=FIXTURE, report_date="2026-09-07")
    atomic_write_json(path, {"report_date": pending.report_date, "overview": "No new papers.", "papers": []})
    report = finish(run)
    assert not report.papers
    assert set(report.counts.values()) == {0}
    folder = site / "reports/2026-09-07"
    assert "No new papers." in (folder / "index.html").read_text(encoding="utf-8")
    assert {p.name for p in folder.iterdir()} == {"index.html", "report.json"}
    assert json.loads((folder / "report.json").read_text(encoding="utf-8"))["papers"] == []
    before = snapshot(data, site)
    finish(run)
    assert snapshot(data, site) == before
    assert latest_report(data, site).report_date == "2026-09-07"


def test_same_day_additions_are_merged(run):
    data, _, pending, payload, path = run
    first = pending.model_copy(update={"papers": pending.papers[:1]})
    atomic_write_json(data / "pending_run.json", first)
    atomic_write_json(path, {**payload, "papers": payload["papers"][:1]})
    finish(run)
    next_run = preparer.prepare_run(data_dir=data, local_feed=FIXTURE, report_date=DATE)
    assert len(next_run.papers) == 2
    atomic_write_json(path, {**payload, "papers": payload["papers"][1:]})
    assert len(finish(run).papers) == 3


def test_offline_cli(tmp_path):
    data, site = tmp_path / "data", tmp_path / "site"
    commands = [
        ["-m", "src.prepare_run", "--local-feed", str(FIXTURE), "--report-date", DATE, "--data-dir", str(data)],
        ["-m", "src.finalize_run", "--analysis", str(ANALYSIS), "--data-dir", str(data), "--site-dir", str(site)],
        ["-m", "src.notify", "--check-only", "--data-dir", str(data), "--site-dir", str(site)],
    ]
    for command in commands:
        result = subprocess.run([sys.executable, *command], cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

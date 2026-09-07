from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
import yaml

import src.notify as notifier
from src.config import load_config
from src.models import AnalysisRun, DailyReport
from src.utils import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def report():
    return DailyReport(report_date="2026-09-04", generated_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
                       feed_build_at=None, category="math.DS", overview="No new papers.", papers=[],
                       counts={"HIGH PRIORITY": 0, "RELATED / POSSIBLY INTERESTING": 0, "LOW PRIORITY": 0})


def test_notification_links_preserve_project_base(report):
    body = notifier.notification_body(report, "https://example.github.io/digest", "daily report.pdf")
    assert "https://example.github.io/digest/reports/2026-09-04/" in body
    assert "https://example.github.io/digest/reports/2026-09-04/daily%20report.pdf" in body


@pytest.mark.parametrize("existing_body,expected", [(None, "POST"), ("old", "PATCH"), ("same", None)])
def test_persistent_issue_paginates_and_upserts(report, monkeypatch, existing_body, expected):
    config = load_config(ROOT / "config.yaml")
    body = notifier.notification_body(report, "https://example.github.io/digest", "report.pdf")
    marker = "<!-- math-ds-digest:2026-09-04 -->"
    mutations = []
    pages = []
    def fake_request(method, endpoint, token, payload=None, params=None):
        if method != "GET":
            mutations.append((method, endpoint, payload))
            return {}
        page = params["page"]
        pages.append((endpoint, page))
        if endpoint.endswith("/issues"):
            if page == 1:
                return [{"title": "Unrelated", "number": n} for n in range(100)]
            return [{"title": config["notifications"]["github_issue_title"], "number": 123, "state": "open"}]
        if page == 1:
            return [{"body": "Unrelated", "id": n} for n in range(100)]
        if existing_body is None:
            return []
        return [{"id": 456, "body": body if existing_body == "same" else marker + " old"}]
    monkeypatch.setenv("GITHUB_TOKEN", "non-secret-test-placeholder")
    monkeypatch.setenv("GITHUB_REPOSITORY", "test/digest")
    monkeypatch.setattr(notifier, "_github_request", fake_request)
    notifier.send_github_issue_notification(report, config, body)
    assert len(pages) == 4
    assert [item[0] for item in mutations] == ([expected] if expected else [])
    if expected == "PATCH":
        assert mutations[0][1] == "/repos/test/digest/issues/comments/456"


def test_persistent_issue_creation(report, monkeypatch):
    config = load_config(ROOT / "config.yaml")
    mutations = []
    def fake_request(method, endpoint, token, payload=None, params=None):
        if method == "GET":
            return []
        mutations.append((endpoint, payload))
        return {"number": 12}
    monkeypatch.setenv("GITHUB_TOKEN", "non-secret-test-placeholder")
    monkeypatch.setenv("GITHUB_REPOSITORY", "test/digest")
    monkeypatch.setattr(notifier, "_github_request", fake_request)
    notifier.send_github_issue_notification(report, config, "test body")
    assert [p for p, _ in mutations] == ["/repos/test/digest/issues", "/repos/test/digest/issues/12/comments"]


def test_incomplete_committed_report_is_rejected(tmp_path, report):
    assert notifier.latest_report(tmp_path / "data", tmp_path / "site") is None
    atomic_write_json(tmp_path / "data/reports/2026-09-04.json", report)
    with pytest.raises(notifier.NotificationError, match="incomplete"):
        notifier.latest_report(tmp_path / "data", tmp_path / "site")


def test_schema_export_matches_pydantic():
    schema = json.loads((ROOT / "schemas/analysis_run.schema.json").read_text(encoding="utf-8"))
    assert schema == AnalysisRun.model_json_schema()


def test_workflow_only_publishes_committed_files():
    text = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"push", "workflow_dispatch"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["push"]["paths"] == ["data/reports/**", "site/**"]
    assert workflow["permissions"]["contents"] == "read"
    for forbidden in ("OPENAI", "src.prepare_run", "src.finalize_run", "src.main", "git push", "git commit", "run_metadata", "SMTP", "RESEND", "pytest"):
        assert forbidden not in text
    steps = workflow["jobs"]["deploy-notify"]["steps"]
    upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-pages-artifact@"))
    assert upload["with"]["path"] == "site"
    assert not any("openai" in path.read_text(encoding="utf-8").lower() for path in (ROOT / "src").glob("*.py"))
    assert "openai" not in (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    config = load_config(ROOT / "config.yaml")
    assert config["notifications"]["github_issue"] is True
    assert config["notifications"]["email_enabled"] is False

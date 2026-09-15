import pytest
import requests
from pathlib import Path


@pytest.fixture(scope="session", autouse=True)
def preserve_production_state():
    root = Path(__file__).resolve().parents[1]
    def snapshot():
        return {path: (path.read_bytes(), path.stat().st_mtime_ns)
                for folder in (root / 'data', root / 'site')
                for path in folder.rglob('*') if path.is_file()}
    before = snapshot()
    yield
    assert snapshot() == before, "Offline tests must not modify production state, inbox, reports, or site"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not access the network; use the RSS fixture")
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)

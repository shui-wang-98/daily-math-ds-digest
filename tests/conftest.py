import pytest
import requests
from pathlib import Path


@pytest.fixture(scope="session", autouse=True)
def preserve_production_state():
    path = Path(__file__).resolve().parents[1] / "data/state.json"
    before = (path.read_bytes(), path.stat().st_mtime_ns) if path.exists() else None
    yield
    after = (path.read_bytes(), path.stat().st_mtime_ns) if path.exists() else None
    assert after == before, "Offline tests must not modify production state"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not access the network; use the RSS fixture")
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)

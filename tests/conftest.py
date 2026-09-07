import pytest
import requests


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not access the network; use the RSS fixture")
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)

"""Phase 6.5: tests for AdminConsoleClient.fetch_thumbnails."""
import base64
import json
from unittest.mock import patch

import pytest

from je_auto_control.utils.admin.admin_client import AdminConsoleClient


_FAKE_PNG = b"\x89PNG\r\n\x1a\nFAKE-PAYLOAD-BYTES"


@pytest.fixture
def client(tmp_path):
    c = AdminConsoleClient(persist_path=tmp_path / "hosts.json", timeout_s=1.0)
    c.add_host("alpha", "http://a.example", "tok-a")  # NOSONAR python:S5332  # reason: test fixture, no real network
    c.add_host("beta", "http://b.example", "tok-b")  # NOSONAR python:S5332  # reason: test fixture, no real network
    return c


def test_fetch_thumbnails_returns_png_bytes_per_host(client):
    encoded = base64.b64encode(_FAKE_PNG).decode("ascii")
    body = {"format": "png", "encoding": "base64", "data": encoded}

    def fake_get(self, host, path):
        return body

    with patch.object(AdminConsoleClient, "_http_get", new=fake_get):
        out = client.fetch_thumbnails()
    assert set(out.keys()) == {"alpha", "beta"}
    assert out["alpha"] == _FAKE_PNG
    assert out["beta"] == _FAKE_PNG


def test_fetch_thumbnails_returns_none_on_http_error(client):
    def fake_get(self, host, path):
        raise OSError("connection refused")

    with patch.object(AdminConsoleClient, "_http_get", new=fake_get):
        out = client.fetch_thumbnails()
    assert out == {"alpha": None, "beta": None}


def test_fetch_thumbnails_returns_none_on_malformed_response(client):
    def fake_get(self, host, path):
        # Missing the expected "encoding": "base64".
        return {"format": "png", "data": "Zm9v"}

    with patch.object(AdminConsoleClient, "_http_get", new=fake_get):
        out = client.fetch_thumbnails()
    assert out == {"alpha": None, "beta": None}


def test_fetch_thumbnails_returns_none_for_bad_base64(client):
    def fake_get(self, host, path):
        return {"format": "png", "encoding": "base64", "data": "%%not-b64%%"}

    with patch.object(AdminConsoleClient, "_http_get", new=fake_get):
        out = client.fetch_thumbnails()
    # Both hosts produce None on decode failure (clean degradation).
    assert all(v is None for v in out.values())


def test_fetch_thumbnails_filters_by_label(client):
    encoded = base64.b64encode(_FAKE_PNG).decode("ascii")
    body = {"format": "png", "encoding": "base64", "data": encoded}

    def fake_get(self, host, path):
        return body

    with patch.object(AdminConsoleClient, "_http_get", new=fake_get):
        out = client.fetch_thumbnails(labels=["beta"])
    assert set(out.keys()) == {"beta"}


def test_fetch_thumbnails_returns_empty_when_no_hosts(tmp_path):
    client = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
    assert client.fetch_thumbnails() == {}
    assert client.fetch_thumbnails(labels=["nope"]) == {}

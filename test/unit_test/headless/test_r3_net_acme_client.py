"""Round-3 net audit: the ACME client retries a badNonce rejection.

RFC 8555 §6.5 requires retrying a badNonce rejection once with the fresh
nonce the server just supplied.
"""
from je_auto_control.utils.acme_v2 import client as acme


def _bare_client():
    """An AcmeClient with only the attributes the flow under test touches."""
    client = acme.AcmeClient.__new__(acme.AcmeClient)
    client._account_key = object()
    client._kid = "kid"
    client._nonce = None
    client._directory = {"newNonce": "https://example/nonce"}
    return client


# --- badNonce retry -------------------------------------------------------

def test_signed_post_retries_once_on_bad_nonce(monkeypatch):
    client = _bare_client()
    client._nonce = "nonce-1"
    monkeypatch.setattr(
        acme, "sign_compact",
        lambda **kwargs: {"protected": "p", "payload": "l", "signature": "s"})

    responses = [
        (400, {"type": "urn:ietf:params:acme:error:badNonce"},
         {"Replay-Nonce": "nonce-2"}),
        (200, {"status": "valid"}, {"Replay-Nonce": "nonce-3"}),
    ]
    calls: list = []

    def fake_http(method, url, *, body=None, content_type=None, accept=None):
        calls.append((method, url))
        return responses[len(calls) - 1]

    monkeypatch.setattr(client, "_http", fake_http)

    status, parsed, _headers = client._signed_post("https://acct", {"x": 1})

    assert status == 200
    assert parsed == {"status": "valid"}
    assert len(calls) == 2  # retried once with the fresh nonce

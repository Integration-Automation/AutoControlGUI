"""ACME v2 client driving the RFC 8555 state machine end-to-end."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from cryptography.hazmat.primitives.asymmetric import rsa

from je_auto_control.utils.acme_v2.jws import (
    JwsError, csr_to_b64url, key_authorization, sign_compact,
)


LETSENCRYPT_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
LETSENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"

_USER_AGENT = "autocontrol-acme/1.0"
_JOSE_CONTENT_TYPE = "application/jose+json"


class AcmeError(RuntimeError):
    """Raised on protocol-level failures (HTTP errors, bad responses)."""


@dataclass
class AcmeChallenge:
    """One challenge offered for an authorization (HTTP-01 / DNS-01 / …)."""
    type: str
    url: str
    token: str
    status: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AcmeAuthorization:
    """One authorization (i.e. one domain) attached to an order."""
    url: str
    identifier: str
    status: str
    challenges: List[AcmeChallenge]
    raw: Dict[str, Any] = field(default_factory=dict)

    def http_challenge(self) -> AcmeChallenge:
        """Return the ``http-01`` challenge, or raise when none is offered."""
        for ch in self.challenges:
            if ch.type == "http-01":
                return ch
        raise AcmeError(
            f"authorization {self.identifier} has no http-01 challenge",
        )


@dataclass
class AcmeOrder:
    """An ACME order — identifiers + URLs the client polls."""
    url: str
    status: str
    authorizations: List[str]
    finalize: str
    certificate: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


HttpPublisher = Callable[[str, str], None]
"""HTTP-01 setup hook: ``(token, key_authorization) -> None``."""


class AcmeClient:
    """Stateful ACME client. Keep one instance per account key."""

    _POLL_INTERVAL_S = 1.0
    _POLL_TIMEOUT_S = 60.0

    def __init__(self, *, directory_url: str,
                 account_key: rsa.RSAPrivateKey,
                 contact_email: Optional[str] = None,
                 timeout_s: float = 10.0) -> None:
        if account_key is None:
            raise AcmeError("account_key is required")
        self._directory_url = directory_url.rstrip("/")
        self._account_key = account_key
        self._contact_email = contact_email
        self._timeout = float(timeout_s)
        self._directory: Optional[Dict[str, str]] = None
        self._kid: Optional[str] = None
        self._nonce: Optional[str] = None

    # ----- directory + nonce ------------------------------------------

    def directory(self) -> Dict[str, str]:
        """GET /directory once; subsequent calls return the cached body."""
        if self._directory is not None:
            return self._directory
        status, body, _headers = self._http("GET", self._directory_url)
        if status != 200 or not isinstance(body, dict):
            raise AcmeError(
                f"directory returned HTTP {status}: {body!r}",
            )
        self._directory = body
        return body

    def _fresh_nonce(self) -> str:
        """Fetch + cache a Replay-Nonce. Each POST consumes the cached one."""
        url = self.directory()["newNonce"]
        _status, _body, headers = self._http("HEAD", url)
        nonce = headers.get("Replay-Nonce") or headers.get("replay-nonce")
        if not nonce:
            raise AcmeError("server omitted Replay-Nonce header")
        return nonce

    # ----- account + order --------------------------------------------

    def new_account(self) -> str:
        """Register / look up the account; returns the kid URL."""
        directory = self.directory()
        payload: Dict[str, Any] = {"termsOfServiceAgreed": True}
        if self._contact_email:
            payload["contact"] = [f"mailto:{self._contact_email}"]
        status, body, headers = self._signed_post(
            directory["newAccount"], payload, use_jwk=True,
        )
        if status not in (200, 201):
            raise AcmeError(
                f"new-account returned HTTP {status}: {body!r}",
            )
        kid = headers.get("Location") or headers.get("location")
        if not kid:
            raise AcmeError("new-account omitted Location header")
        self._kid = kid
        return kid

    def new_order(self, domains: Sequence[str]) -> AcmeOrder:
        """Submit a new-order request for the given list of identifiers."""
        if not domains:
            raise AcmeError("at least one domain is required")
        self._require_kid()
        payload = {
            "identifiers": [{"type": "dns", "value": d} for d in domains],
        }
        status, body, headers = self._signed_post(
            self.directory()["newOrder"], payload,
        )
        if status not in (200, 201) or not isinstance(body, dict):
            raise AcmeError(f"new-order returned HTTP {status}: {body!r}")
        location = headers.get("Location") or headers.get("location")
        if not location:
            raise AcmeError("new-order omitted Location header")
        return _build_order(location, body)

    def fetch_authorization(self, url: str) -> AcmeAuthorization:
        """POST-as-GET an authorization URL."""
        self._require_kid()
        status, body, _ = self._signed_post(url, payload=None)
        if status != 200 or not isinstance(body, dict):
            raise AcmeError(
                f"authorization {url} returned HTTP {status}",
            )
        return _build_authorization(url, body)

    def respond_to_challenge(self, challenge_url: str) -> Dict[str, Any]:
        """Notify the CA we've published the challenge response — payload {}."""
        self._require_kid()
        status, body, _ = self._signed_post(challenge_url, payload={})
        if status not in (200, 202) or not isinstance(body, dict):
            raise AcmeError(
                f"challenge {challenge_url} returned HTTP {status}: {body!r}",
            )
        return body

    def finalize_order(self, order: AcmeOrder, csr_pem: bytes
                       ) -> AcmeOrder:
        """POST the CSR to ``order.finalize`` and re-fetch the order body."""
        self._require_kid()
        payload = {"csr": csr_to_b64url(csr_pem)}
        status, body, _ = self._signed_post(order.finalize, payload)
        if status not in (200, 201) or not isinstance(body, dict):
            raise AcmeError(
                f"finalize returned HTTP {status}: {body!r}",
            )
        return _build_order(order.url, body)

    def fetch_order(self, order_url: str) -> AcmeOrder:
        """POST-as-GET the order URL — used for polling status."""
        self._require_kid()
        status, body, _ = self._signed_post(order_url, payload=None)
        if status != 200 or not isinstance(body, dict):
            raise AcmeError(
                f"order {order_url} returned HTTP {status}",
            )
        return _build_order(order_url, body)

    def download_certificate(self, order: AcmeOrder) -> bytes:
        """POST-as-GET the ``certificate`` URL; returns the PEM chain."""
        if not order.certificate:
            raise AcmeError("order has no certificate URL yet")
        self._require_kid()
        status, body, _ = self._signed_post(
            order.certificate, payload=None,
            accept="application/pem-certificate-chain",
        )
        if status != 200 or not isinstance(body, (bytes, str)):
            raise AcmeError(
                f"certificate download returned HTTP {status}",
            )
        return body if isinstance(body, bytes) else body.encode("utf-8")

    # ----- high-level orchestration -----------------------------------

    def request_certificate(self, *, domains: Sequence[str],
                            csr_pem: bytes,
                            http_publisher: HttpPublisher,
                            ) -> bytes:
        """Drive the full flow; returns the issued PEM certificate chain."""
        self.new_account()
        order = self.new_order(domains)
        for auth_url in order.authorizations:
            auth = self.fetch_authorization(auth_url)
            challenge = auth.http_challenge()
            key_auth = key_authorization(challenge.token, self._account_key)
            http_publisher(challenge.token, key_auth)
            self.respond_to_challenge(challenge.url)
            self._poll_authorization(auth_url)
        order = self.finalize_order(order, csr_pem)
        order = self._poll_order(order.url)
        return self.download_certificate(order)

    # ----- polling helpers --------------------------------------------

    def _poll_authorization(self, url: str) -> AcmeAuthorization:
        deadline = time.monotonic() + self._POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            auth = self.fetch_authorization(url)
            if auth.status == "valid":
                return auth
            if auth.status in {"invalid", "deactivated", "revoked", "expired"}:
                raise AcmeError(
                    f"authorization {url} ended in status {auth.status!r}",
                )
            time.sleep(self._POLL_INTERVAL_S)
        raise AcmeError(f"authorization {url} did not become valid in time")

    def _poll_order(self, url: str) -> AcmeOrder:
        deadline = time.monotonic() + self._POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            order = self.fetch_order(url)
            if order.status == "valid":
                return order
            if order.status == "invalid":
                raise AcmeError(f"order {url} ended invalid")
            time.sleep(self._POLL_INTERVAL_S)
        raise AcmeError(f"order {url} did not finalise in time")

    # ----- low-level HTTP ---------------------------------------------

    def _require_kid(self) -> None:
        if self._kid is None:
            raise AcmeError("call new_account() before authenticated requests")

    def _signed_post(self, url: str,
                     payload: Optional[Mapping[str, Any]],
                     *, use_jwk: bool = False,
                     accept: Optional[str] = None,
                     ) -> tuple:
        nonce = self._nonce or self._fresh_nonce()
        self._nonce = None
        try:
            jws = sign_compact(
                key=self._account_key, url=url, nonce=nonce,
                payload=payload,
                kid=None if use_jwk else self._kid,
            )
        except JwsError as error:
            raise AcmeError(f"JWS signing failed: {error}") from error
        body = json.dumps(jws).encode("utf-8")
        status, parsed, headers = self._http(
            "POST", url, body=body,
            content_type=_JOSE_CONTENT_TYPE,
            accept=accept,
        )
        # Cache the next nonce the server offered us.
        next_nonce = headers.get("Replay-Nonce") or headers.get(
            "replay-nonce",
        )
        if next_nonce:
            self._nonce = next_nonce
        return status, parsed, headers

    def _http(self, method: str, url: str, *,
              body: Optional[bytes] = None,
              content_type: Optional[str] = None,
              accept: Optional[str] = None,
              ) -> tuple:
        headers = {"User-Agent": _USER_AGENT}
        if content_type:
            headers["Content-Type"] = content_type
        if accept:
            headers["Accept"] = accept
        request = urllib.request.Request(
            url, data=body, method=method, headers=headers,
        )
        try:
            with urllib.request.urlopen(  # nosec B310  # NOSONAR python:S5332  # reason: configured directory URL, https in production
                    request, timeout=self._timeout,
            ) as response:
                raw = response.read()
                ct = response.headers.get("Content-Type", "")
                resp_headers = dict(response.headers.items())
                status = response.status
        except urllib.error.HTTPError as error:
            raw = error.read() or b""
            ct = error.headers.get("Content-Type", "") if error.headers else ""
            resp_headers = (
                dict(error.headers.items()) if error.headers else {}
            )
            status = error.code
        body_value: Any = raw
        if "json" in ct.lower():
            try:
                body_value = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                body_value = raw
        return status, body_value, resp_headers


def _build_authorization(url: str, body: Mapping[str, Any]
                         ) -> AcmeAuthorization:
    challenges = [
        AcmeChallenge(
            type=str(ch.get("type", "")),
            url=str(ch.get("url", "")),
            token=str(ch.get("token", "")),
            status=str(ch.get("status", "")),
            raw=dict(ch),
        )
        for ch in body.get("challenges") or []
        if isinstance(ch, Mapping)
    ]
    identifier = body.get("identifier") or {}
    return AcmeAuthorization(
        url=url,
        identifier=str(identifier.get("value", "") if isinstance(identifier, Mapping) else ""),
        status=str(body.get("status", "")),
        challenges=challenges,
        raw=dict(body),
    )


def _build_order(url: str, body: Mapping[str, Any]) -> AcmeOrder:
    return AcmeOrder(
        url=url,
        status=str(body.get("status", "")),
        authorizations=[str(u) for u in (body.get("authorizations") or [])],
        finalize=str(body.get("finalize", "")),
        certificate=(
            str(body["certificate"]) if body.get("certificate") else None
        ),
        raw=dict(body),
    )


def request_certificate(*, directory_url: str,
                        account_key: rsa.RSAPrivateKey,
                        domains: Sequence[str], csr_pem: bytes,
                        http_publisher: HttpPublisher,
                        contact_email: Optional[str] = None,
                        ) -> bytes:
    """Convenience wrapper that handles the whole flow in one call."""
    client = AcmeClient(
        directory_url=directory_url, account_key=account_key,
        contact_email=contact_email,
    )
    return client.request_certificate(
        domains=domains, csr_pem=csr_pem,
        http_publisher=http_publisher,
    )


__all__ = [
    "AcmeAuthorization", "AcmeChallenge", "AcmeClient", "AcmeError",
    "AcmeOrder",
    "LETSENCRYPT_PRODUCTION", "LETSENCRYPT_STAGING",
    "request_certificate",
]

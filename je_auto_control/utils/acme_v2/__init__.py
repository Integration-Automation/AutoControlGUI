"""Phase 8.1: full ACME v2 client (RFC 8555) — no certbot.

The Phase 7.6 module delegated the actual ACME wire protocol to the
``certbot`` binary; this module replaces that delegation with a pure-
Python implementation. Operators can now request and renew Let's
Encrypt certificates from inside the AutoControl process without
spawning subprocesses.

The flow (RFC 8555 §7.4)::

    Directory  →  new-nonce  →  new-account  (JWK ID)
                                     ↓
                                new-order  →  authorization list
                                     ↓
                            challenge GET   (HTTP-01 token + key-auth)
                                     ↓
                            challenge POST  (notify server we're ready)
                                     ↓
                            poll authorization  until "valid"
                                     ↓
                            finalize (CSR)  →  poll order  until "valid"
                                     ↓
                            download certificate

The :class:`AcmeClient` exposes one high-level
:meth:`request_certificate` that drives that entire flow given a
domain name and a HTTP-01 publisher callable.

The bundled :class:`HttpChallengeServer` from
:mod:`tls_acme.challenge` plays the publisher role; for split-DNS
deployments where you can't bind port 80 directly, pass any callable
matching the signature ``(token: str, key_authorization: str) -> None``.
"""
from je_auto_control.utils.acme_v2.client import (
    AcmeAuthorization, AcmeChallenge, AcmeClient, AcmeError, AcmeOrder,
    LETSENCRYPT_PRODUCTION, LETSENCRYPT_STAGING, request_certificate,
)
from je_auto_control.utils.acme_v2.jws import (
    JwsError, build_jwk_thumbprint, key_authorization, sign_compact,
)

__all__ = [
    "AcmeAuthorization", "AcmeChallenge", "AcmeClient", "AcmeError",
    "AcmeOrder",
    "LETSENCRYPT_PRODUCTION", "LETSENCRYPT_STAGING",
    "request_certificate",
    "JwsError", "build_jwk_thumbprint", "key_authorization",
    "sign_compact",
]

"""Phase 7.6: TLS automation helpers (ACME / Let's Encrypt).

The Remote Desktop host already accepts an ``ssl.SSLContext`` and a
PEM cert + key pair (see :mod:`remote_desktop.host`). What it didn't
have was an answer to "how do I get a *real* cert in the first place,
and how do I rotate it before it expires?"

This module ships the operator-facing pieces:

  * :class:`KeyMaterial` — generate / load an RSA-2048 private key
    plus a CSR for one or more hostnames.
  * :class:`HttpChallengeServer` — single-purpose HTTPServer that
    answers the ACME HTTP-01 challenge on port 80. Run it for the
    duration of the cert request; tear it down once the certificate
    is in hand.
  * :class:`RenewalScheduler` — background thread that re-requests
    the certificate when ``not_after - now < threshold``.
  * :func:`run_certbot` — drive the standard ``certbot`` binary as a
    subprocess. The full ACME v2 wire protocol is delegated to
    certbot because reimplementing it well is a separate project.

For a *fully in-process* ACME client, install the ``acme`` library
(``pip install acme``) and plug it into the same :class:`RenewalScheduler`
hooks; see ``docs/tls_acme.rst`` for a worked example.
"""
from je_auto_control.utils.tls_acme.challenge import (
    HttpChallengeServer, run_certbot,
)
from je_auto_control.utils.tls_acme.keys import (
    KeyMaterial, generate_account_key, generate_certificate_key,
    parse_certificate_expiry,
)
from je_auto_control.utils.tls_acme.renewal import (
    RenewalScheduler, renewal_due,
)

__all__ = [
    "HttpChallengeServer", "run_certbot",
    "KeyMaterial", "generate_account_key", "generate_certificate_key",
    "parse_certificate_expiry",
    "RenewalScheduler", "renewal_due",
]

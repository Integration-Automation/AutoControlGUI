JSON Web Tokens (JWT)
=====================

RPA flows constantly need to mint or verify bearer tokens for the APIs they
drive, but the framework only had HMAC *file* signing (``action_signing``) and
an ACME-bound RS256 JWS (``acme_v2``) — neither produces or validates a compact
bearer JWT. This adds a focused, pure-stdlib JWT codec for the HMAC family with
full claim validation, designed to feed straight into ``http_request``'s bearer
auth.

Pure standard library (``hmac`` + ``hashlib`` + ``base64`` + ``json``); the
clock is injectable so ``exp`` / ``nbf`` checks are deterministic. Imports no
``PySide6``.

Security
--------

The decoder is safe by default:

* it **rejects ``alg: "none"``** and any algorithm the caller did not
  explicitly allow-list, defeating the classic algorithm-confusion / downgrade
  attack;
* it compares signatures with ``hmac.compare_digest`` (constant time);
* RSA/EC algorithms (RS256/ES256) are intentionally **out of scope** — they
  require a third-party crypto library.

Headless API
------------

.. code-block:: python

    from je_auto_control import encode_jwt, decode_jwt, ClaimsPolicy

    token = encode_jwt({"sub": "user1", "aud": "api", "exp": 1893456000}, secret)
    # -> "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...."

    # default policy: HS256 only, verify exp/nbf, no audience/issuer check
    claims = decode_jwt(token, secret)

    # tighten the policy for audience / issuer / leeway / algorithms
    policy = ClaimsPolicy(algorithms=("HS256",), audience="api",
                          issuer="my-service", leeway=30)
    claims = decode_jwt(token, secret, policy)

``encode_jwt`` signs a compact ``header.payload.signature`` token with
``HS256`` / ``HS384`` / ``HS512``. ``decode_jwt`` verifies the signature, then
validates the standard claims against a :class:`ClaimsPolicy` (``exp`` / ``nbf``
with ``leeway``, ``aud`` membership, ``iss`` match) using an injectable ``now``;
it raises ``ExpiredTokenError`` / ``InvalidSignatureError`` / ``JwtError`` on
failure. The minted token drops straight into the HTTP client:

.. code-block:: python

    from je_auto_control import http_request
    http_request("https://api.example.com/me",
                 auth={"type": "bearer", "token": token})

Executor commands
-----------------

``AC_jwt_encode`` takes ``claims`` (a dict or JSON string), ``key`` and an
optional ``alg``; it returns ``{token}``. ``AC_jwt_decode`` takes ``token``,
``key`` and optional ``algorithms`` / ``audience`` / ``leeway``; it returns
``{ok, claims}`` (or ``{ok: false, error}`` so a flow can branch without
raising). Both are exposed as the MCP tools ``ac_jwt_encode`` / ``ac_jwt_decode``
and as Script Builder commands under **Security**.

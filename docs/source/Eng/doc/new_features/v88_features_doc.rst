Secret Redaction for Config & Logs
==================================

``utils/redaction`` only blurs PIL screenshots, and ``secrets_scan`` only
*detects* and reports findings — neither returns a masked copy of a config dict
or string safe for logs, reports, or ``config_bundle`` export. This reuses the
``secrets_scan`` detector to produce a redacted copy.

Pure standard library (``re`` + reuse of ``secrets_scan``); imports no
``PySide6``. Every function is pure (data in, redacted copy out), so it is fully
deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import redact_config, redact_secret_text

    safe = redact_config({"db": {"password": secret}, "name": "alice"})
    # {"db": {"password": "***"}, "name": "alice"}

    line = redact_secret_text(f"auth failed for token {token}")
    # "auth failed for token ***"

``redact_config`` returns a deep copy of a nested structure with secret-looking
values masked, reusing ``secrets_scan`` (key-name patterns such as ``password``
/ ``api_key``, known value formats like AWS keys and bearer tokens, and
high-entropy strings); values already referencing the vault (``${secrets.*}``)
are left intact. ``redact_secret_text`` masks secret-looking tokens within a
free-text string (a log line) while preserving the surrounding words and
whitespace. Both accept a custom ``mask`` (default ``"***"``). The function is
named ``redact_secret_text`` to stay distinct from the prompt-injection
``guardrail.redact_text``.

Executor commands
-----------------

``AC_redact_config`` returns ``{redacted}`` for an ``obj`` (JSON accepted);
``AC_redact_secret_text`` returns ``{text}``. Both accept an optional ``mask``
and are exposed as MCP tools (``ac_redact_config`` / ``ac_redact_secret_text``)
and as Script Builder commands under **Security**.

Stable Failure Signatures
=========================

Two runs that failed the *same way* almost never have byte-identical error text —
paths, line numbers, memory addresses, ids and timestamps differ every time. That
defeats any attempt to ask "is this the same failure as yesterday?" or "which
tests fail *together*?". ``failure_signature`` strips the variable parts of an
error to a canonical form and hashes it (SHA-256), so the same *kind* of failure
gets the same short signature across runs — the join key the rest of the
test-robustness tools (run diffing, flake clustering) group on.

* :func:`normalize_error` — collapse paths / hex addresses / UUIDs / timestamps /
  line numbers / bare integers to placeholders,
* :func:`failure_signature` — a short stable SHA-256 of the normalised message,
* :func:`group_failures` — group a list of errors by signature, most frequent
  first.

Pure standard library (``re`` + ``hashlib``); no device, no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (normalize_error, failure_signature,
                                 group_failures)

    a = r"Timeout at C:\app\run.py line 42 (0x7ffab12c) at 2026-06-24 11:03:21"
    b = r"Timeout at C:\app\run.py line 88 (0x1234abcd) at 2026-06-25 09:15:00"
    normalize_error(a)          # "Timeout at <path> line <n> (0x<addr>) at <ts>"
    failure_signature(a) == failure_signature(b)        # True — same failure

    group_failures([a, b, "Connection refused to /tmp/x.sock"])
    # [{"signature": "...", "normalized": "...", "count": 2, "examples": [...]},
    #  {"signature": "...", "count": 1, ...}]

Windows and POSIX paths, ``0x`` addresses, UUIDs, ISO timestamps, ``line N`` and
any leftover integers become placeholders; whitespace is squeezed.
``group_failures`` keeps up to three distinct raw examples per group and skips
empty / ``None`` messages.

Executor commands
-----------------

``AC_failure_signature`` (``error`` / ``length``) returns ``{signature,
normalized}``; ``AC_group_failures`` (``errors``) returns the grouped list. They
are exposed as read-only ``ac_*`` MCP tools and as Script Builder commands under
**Testing**.

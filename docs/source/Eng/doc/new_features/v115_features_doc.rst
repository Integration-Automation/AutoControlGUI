Check-Digit Algorithms
======================

``pii_text`` detects credit-card and IBAN *shapes* by regex and ``data_quality``
does type / range / regex validation, but nothing actually computes or verifies a
*check digit*. This adds the shared arithmetic engine for the four schemes behind
most real-world identifiers — and the primitive that account-number, card, IBAN,
ISBN and EAN validation build on.

Pure standard library (integer arithmetic; the Verhoeff and Damm tables are small
embedded constants). Every function is pure (string in, bool / str out), so it is
fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        luhn_validate, luhn_check_digit,
        verhoeff_validate, verhoeff_check_digit,
        damm_validate, damm_check_digit,
        mod97_10_validate, mod97_10_check_digits,
    )

    luhn_validate("4111111111111111")    # True  (credit-card / IMEI)
    luhn_check_digit("7992739871")        # '3'   -> 79927398713
    verhoeff_validate("2363")             # True  (catches transpositions)
    damm_check_digit("572")               # '4'
    mod97_10_validate("3214282912345698765432161182")   # True  (IBAN engine)

- **Luhn** (mod 10): credit cards, IMEI, many national IDs — catches all
  single-digit errors and most adjacent transpositions.
- **Verhoeff** and **Damm**: decimal schemes that catch *all* single-digit and
  adjacent-transposition errors (stronger than Luhn).
- **ISO 7064 MOD 97-10**: the two-check-digit scheme behind IBAN and similar.

Each scheme exposes ``*_validate(number)`` (does the value incl. its check digit
verify?) and ``*_check_digit`` / ``*_check_digits`` (what digit(s) to append to a
bare payload?). Non-digit characters are ignored, so spaced/grouped input works.

Executor commands
-----------------

``AC_checksum_validate`` takes a ``scheme`` (``luhn`` / ``verhoeff`` / ``damm`` /
``mod97``) plus a ``number`` and returns ``{valid}``; ``AC_checksum_digit`` returns
``{check_digit}`` for a ``partial``. Both are exposed as MCP tools
(``ac_checksum_validate`` / ``ac_checksum_digit``) and as Script Builder commands
under **Data**.

"""Check-digit algorithms: Luhn, Verhoeff, Damm, ISO 7064 MOD 97-10.

``pii_text`` detects credit-card and IBAN *shapes* by regex and ``data_quality``
does type/range/regex validation, but nothing in the project actually computes or
verifies a *check digit*. This is the shared arithmetic engine that catches the
single-digit and adjacent-transposition typos those formats are designed to
detect, and the primitive that ``identifier_validate`` (IBAN / ISBN / EAN / card)
builds on.

Pure standard library (integer arithmetic only; the Verhoeff and Damm tables are
small embedded constants). Every function is pure (string in, bool/str out), so it
is fully deterministic in CI.
"""
from typing import List

# Verhoeff dihedral-group multiplication, permutation and inverse tables.
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6), (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4), (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2), (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

# Damm quasigroup table (totally anti-symmetric).
_DAMM = (
    (0, 3, 1, 7, 5, 9, 8, 6, 4, 2), (7, 0, 9, 2, 1, 5, 4, 8, 6, 3),
    (4, 2, 0, 6, 8, 7, 1, 3, 5, 9), (1, 7, 5, 0, 9, 8, 3, 4, 2, 6),
    (6, 1, 2, 3, 0, 4, 5, 9, 7, 8), (3, 6, 7, 4, 2, 0, 9, 5, 8, 1),
    (5, 8, 6, 9, 7, 2, 0, 1, 3, 4), (8, 9, 4, 5, 3, 6, 2, 0, 1, 7),
    (9, 4, 3, 8, 6, 1, 7, 2, 0, 5), (2, 5, 8, 1, 4, 3, 6, 7, 9, 0),
)


def _digits(value: object) -> List[int]:
    """Extract the decimal digits of a value as a list of ints."""
    return [int(ch) for ch in str(value) if ch.isdigit()]


# --- Luhn (mod 10) --------------------------------------------------------

def _luhn_sum(digits: List[int]) -> int:
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total


def luhn_validate(number: object) -> bool:
    """Whether ``number`` (incl. its trailing check digit) passes Luhn."""
    digits = _digits(number)
    return bool(digits) and _luhn_sum(digits) % 10 == 0


def luhn_check_digit(partial: object) -> str:
    """Return the Luhn check digit to append to ``partial`` (no check digit)."""
    total = _luhn_sum(_digits(partial) + [0])
    return str((10 - total % 10) % 10)


# --- Verhoeff -------------------------------------------------------------

def verhoeff_validate(number: object) -> bool:
    """Whether ``number`` (incl. check digit) passes the Verhoeff scheme."""
    check = 0
    for index, digit in enumerate(reversed(_digits(number))):
        check = _VERHOEFF_D[check][_VERHOEFF_P[index % 8][digit]]
    return check == 0


def verhoeff_check_digit(partial: object) -> str:
    """Return the Verhoeff check digit to append to ``partial``."""
    check = 0
    for index, digit in enumerate(reversed(_digits(partial))):
        check = _VERHOEFF_D[check][_VERHOEFF_P[(index + 1) % 8][digit]]
    return str(_VERHOEFF_INV[check])


# --- Damm -----------------------------------------------------------------

def damm_validate(number: object) -> bool:
    """Whether ``number`` (incl. check digit) passes the Damm scheme."""
    interim = 0
    for digit in _digits(number):
        interim = _DAMM[interim][digit]
    return interim == 0


def damm_check_digit(partial: object) -> str:
    """Return the Damm check digit to append to ``partial``."""
    interim = 0
    for digit in _digits(partial):
        interim = _DAMM[interim][digit]
    return str(interim)


# --- ISO 7064 MOD 97-10 (the IBAN engine) ---------------------------------

def mod97_10_validate(number: object) -> bool:
    """Whether the numeric string ``number`` satisfies ISO 7064 MOD 97-10."""
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    return bool(digits) and int(digits) % 97 == 1


def mod97_10_check_digits(partial: object) -> str:
    """Return the two MOD 97-10 check digits to append to ``partial``."""
    digits = "".join(ch for ch in str(partial) if ch.isdigit())
    value = int(digits) if digits else 0
    return f"{(1 - value * 100) % 97:02d}"

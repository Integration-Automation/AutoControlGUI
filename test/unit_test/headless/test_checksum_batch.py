"""Headless tests for check-digit algorithms. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.checksum import (
    damm_check_digit, damm_validate, luhn_check_digit, luhn_validate,
    mod97_10_check_digits, mod97_10_validate, verhoeff_check_digit,
    verhoeff_validate,
)


def test_luhn():
    assert luhn_validate("4111111111111111") is True
    assert luhn_validate("4111111111111112") is False
    assert luhn_check_digit("7992739871") == "3"          # 79927398713 is valid
    assert luhn_validate("79927398713") is True
    assert luhn_validate("") is False                     # no digits


def test_verhoeff():
    assert verhoeff_check_digit("236") == "3"
    assert verhoeff_validate("2363") is True
    assert verhoeff_validate("2364") is False             # wrong check digit
    assert verhoeff_validate("2633") is False             # transposition caught


def test_damm():
    assert damm_check_digit("572") == "4"
    assert damm_validate("5724") is True
    assert damm_validate("5720") is False
    assert damm_validate("7524") is False                 # transposition caught


def test_mod97_10():
    # GB82WEST12345698765432 rearranged + letters->numbers ends ...% 97 == 1
    rearranged = "3214282912345698765432161182"
    assert mod97_10_validate(rearranged) is True
    assert mod97_10_validate("3214282912345698765432161183") is False
    # appended check digits make the value satisfy MOD 97-10
    body = "123456789"
    check = mod97_10_check_digits(body)
    assert mod97_10_validate(body + check) is True
    assert len(check) == 2


def test_check_digit_round_trips():
    for scheme_validate, scheme_digit in [
            (luhn_validate, luhn_check_digit),
            (verhoeff_validate, verhoeff_check_digit),
            (damm_validate, damm_check_digit)]:
        base = "12345678"
        assert scheme_validate(base + scheme_digit(base)) is True


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_checksum_validate",
        {"scheme": "luhn", "number": "4111111111111111"}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["valid"] is True
    rec2 = ac.execute_action([[
        "AC_checksum_digit", {"scheme": "damm", "partial": "572"}]])
    assert next(v for v in rec2.values() if isinstance(v, dict))["check_digit"] == "4"


def test_executor_unknown_scheme_errors():
    rec = ac.execute_action([[
        "AC_checksum_validate", {"scheme": "nope", "number": "1"}]])
    # the executor records the failure rather than returning a {valid} dict
    assert not any(isinstance(v, dict) and v.get("valid") for v in rec.values())


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_checksum_validate", "AC_checksum_digit"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_checksum_validate", "ac_checksum_digit"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_checksum_validate", "AC_checksum_digit"} <= specs


def test_facade_exports():
    for attr in ("luhn_validate", "luhn_check_digit", "verhoeff_validate",
                 "verhoeff_check_digit", "damm_validate", "damm_check_digit",
                 "mod97_10_validate", "mod97_10_check_digits"):
        assert hasattr(ac, attr) and attr in ac.__all__

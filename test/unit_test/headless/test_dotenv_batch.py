"""Headless tests for .env parsing/serialisation. Pure stdlib, no Qt."""
import je_auto_control as ac
from je_auto_control.utils.dotenv import (
    dotenv_values, dump_dotenv, load_dotenv, parse_dotenv,
)

_TEXT = (
    "# a comment\n"
    "\n"
    "PLAIN=hello\n"
    "export TOKEN=secret\n"
    'QUOTED="line1\\nline2"\n'
    "LITERAL='no $expand #here'\n"
    "INLINE=value   # trailing comment\n"
    "SPACED = trimmed \n"
    "not a valid line\n"
    "123BAD=skip\n"
)


def test_parse_core_rules():
    values = parse_dotenv(_TEXT)
    assert values["PLAIN"] == "hello"
    assert values["TOKEN"] == "secret"            # export prefix stripped
    assert values["QUOTED"] == "line1\nline2"     # double-quote escapes
    assert values["LITERAL"] == "no $expand #here"  # single quote = literal
    assert values["INLINE"] == "value"            # inline comment stripped
    assert values["SPACED"] == "trimmed"


def test_parse_skips_invalid_lines():
    values = parse_dotenv(_TEXT)
    assert "not a valid line" not in values
    assert "123BAD" not in values                 # key must start with letter/_


def test_empty_and_blank():
    assert parse_dotenv("") == {}
    assert parse_dotenv("\n\n   \n# only comments\n") == {}


def test_load_dotenv_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(_TEXT, encoding="utf-8")
    env = {"PLAIN": "keep"}
    load_dotenv(str(path), env)
    assert env["PLAIN"] == "keep" and env["TOKEN"] == "secret"
    load_dotenv(str(path), env, override=True)
    assert env["PLAIN"] == "hello"                # override replaces
    assert dotenv_values(str(path))["TOKEN"] == "secret"


def test_dump_round_trip():
    mapping = {"A": "simple", "B": "needs # quote", "C": "two\nlines"}
    text = dump_dotenv(mapping)
    assert parse_dotenv(text) == mapping


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([["AC_parse_dotenv", {"text": "K=v\nexport T=1"}]])
    values = next(v for v in rec.values() if isinstance(v, dict))["values"]
    assert values == {"K": "v", "T": "1"}


def test_load_dotenv_executor(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\nB=2", encoding="utf-8")
    rec = ac.execute_action([["AC_load_dotenv", {"path": str(path)}]])
    values = next(v for v in rec.values() if isinstance(v, dict))["values"]
    assert values == {"A": "1", "B": "2"}


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_parse_dotenv", "AC_load_dotenv"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_parse_dotenv", "ac_load_dotenv"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_parse_dotenv", "AC_load_dotenv"} <= specs


def test_facade_exports():
    for attr in ("parse_dotenv", "load_dotenv", "dotenv_values", "dump_dotenv"):
        assert hasattr(ac, attr) and attr in ac.__all__

"""Code generation, the command-line tools and report writers at the edges the audit found.

No real input: the generated code is run only on actions that fail before
touching the screen, and the servers are not started.
"""
import importlib.util
import io
import json
import sys

import pytest

from je_auto_control.utils.codegen.codegen import generate_code
from je_auto_control.utils.exception.exceptions import AutoControlActionException, AutoControlException

_CJK = "中文 ✓"


def _cp950_stream(data: bytes = b"") -> io.TextIOWrapper:
    """A standard stream as Windows gives a piped process on a cp950 system."""
    return io.TextIOWrapper(io.BytesIO(data), encoding="cp950", newline=None)


# --- MCP entry point ---------------------------------------------------------------------------

def test_the_read_only_flag_reaches_the_server(monkeypatch):
    from je_auto_control.utils.mcp_server import server as server_mod
    served = []
    monkeypatch.setattr(server_mod.MCPServer, "serve_stdio", lambda self: served.append(self))
    server_mod.start_mcp_stdio_server(read_only=True)
    names = set(served[0]._tools)  # noqa: SLF001
    assert names and "ac_click_mouse" not in names and "ac_type_text" not in names


def test_mcp_stdio_speaks_utf8_whatever_the_code_page(monkeypatch):
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.tools import MCPTool
    tool = MCPTool(name="echo", description="echo",
                   input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                   handler=lambda text: text)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "echo", "arguments": {"text": _CJK}}}
    stdin = _cp950_stream((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
    stdout = _cp950_stream()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    MCPServer(tools=[tool]).serve_stdio()
    stdout.flush()
    raw = stdout.buffer.getvalue()
    reply = json.loads(raw.decode("utf-8"))
    assert reply["result"]["content"][0]["text"] == _CJK and b"\r\n" not in raw


def test_several_listings_are_one_json_document(monkeypatch, capsys):
    from je_auto_control.utils.mcp_server.__main__ import main
    main(["--list-resources", "--list-prompts"])
    document = json.loads(capsys.readouterr().out)
    assert set(document) == {"resources", "prompts"}
    main(["--list-prompts"])
    assert isinstance(json.loads(capsys.readouterr().out), list)


# --- the new CLI -------------------------------------------------------------------------------

def test_codegen_output_is_utf8_whatever_the_code_page(monkeypatch, tmp_path):
    from je_auto_control.cli import main
    flow = tmp_path / "flow.json"
    flow.write_text(json.dumps([["AC_write", {"write_string": _CJK}]], ensure_ascii=False),
                    encoding="utf-8")
    stdout = _cp950_stream()
    monkeypatch.setattr(sys, "stdout", stdout)
    assert main(["codegen", str(flow)]) == 0
    stdout.flush()
    source = stdout.buffer.getvalue().decode("utf-8")
    compile(source, "test_flow.py", "exec")
    assert _CJK in source


@pytest.mark.parametrize("port", ["70000", "-5", "http"])
def test_a_port_out_of_range_is_a_usage_error(port, capsys):
    from je_auto_control.cli import main
    with pytest.raises(SystemExit) as exit_info:
        main(["start-server", "--port", port])
    assert exit_info.value.code == 2 and "Traceback" not in capsys.readouterr().err


# --- codegen -----------------------------------------------------------------------------------

_FAILING = [["AC_execute_files", {"execute_files_list": ["does_not_exist.json"]}]]


@pytest.mark.parametrize("style", ["calls", "actions"])
def test_a_generated_test_fails_when_an_action_fails(style, tmp_path):
    script = tmp_path / "recorded_flow.py"
    script.write_text(generate_code(_FAILING, style=style), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("recorded_flow", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(AutoControlException):
        module.test_recorded_flow()


def test_placeholders_go_through_the_executor():
    code = generate_code([["AC_write", {"write_string": "${secrets.password}"}],
                          ["AC_write", {"write_string": "plain"}]])
    assert "ac.executor.execute_action([['AC_write', {'write_string': '${secrets.password}'}]]" in code
    assert "ac.write(write_string='plain')" in code


@pytest.mark.parametrize("actions", [[1], [[]], [["AC_click_mouse", {"x": 1}, "extra"]], [{"AC_screen_size": {}}]])
def test_action_shapes_the_executor_refuses_are_refused(actions):
    with pytest.raises(AutoControlActionException):
        generate_code(actions)


def test_a_function_name_does_not_shadow_the_modules_names():
    code = generate_code([["AC_screen_size"]], target="python", name="ac")
    assert "def flow_ac():" in code and "def ac(" not in code


def test_the_actions_style_keeps_key_order():
    code = generate_code([["AC_set_var", {"name": "x", "value": {"zeta": 1, "alpha": 2}}]], style="actions")
    assert code.index("'zeta'") < code.index("'alpha'")


def test_robot_output_takes_a_lone_surrogate_and_keeps_sigils_out_of_names():
    import base64
    import re
    code = generate_code([["AC_write", {"write_string": chr(0xD83D)}]], target="robot", name="$${HOME}")
    payload = re.search(r"b64decode\('([^']+)'\)", code).group(1)
    assert json.loads(base64.b64decode(payload))[0][1]["write_string"] == chr(0xD83D)
    test_name = code.split("*** Test Cases ***\n", 1)[1].splitlines()[0]
    assert not re.search(r"[$@&%]\{", test_name) and "raise_on_error=True" in code


# --- report writers ------------------------------------------------------------------------------

def test_sarif_takes_lone_surrogates_and_a_missing_message(tmp_path):
    from je_auto_control.utils.sarif.sarif import to_sarif, write_sarif
    findings = [{"rule_id": "R", "message": "bad " + chr(0xDC80)}, {"rule_id": "R", "message": None}]
    path = write_sarif(findings, str(tmp_path / "out" / "r.sarif"))
    document = json.loads(open(path, encoding="utf-8").read())
    assert len(document["runs"][0]["results"]) == 2
    assert to_sarif(findings[1:])["runs"][0]["results"][0]["message"]["text"] == ""


def test_an_sop_is_written_into_a_new_folder_and_survives_a_lone_surrogate(tmp_path):
    from je_auto_control.utils.process_doc.process_doc import write_sop
    path = write_sop([["AC_write", {"write_string": "x" + chr(0xDC80)}]], str(tmp_path / "new" / "sop.html"))
    assert "<html" in open(path, encoding="utf-8").read().lower()


def test_allure_results_carry_start_and_stop():
    from je_auto_control.utils.test_suite.reports import to_allure_results
    from je_auto_control.utils.test_suite.result import TestCaseResult, TestSuiteResult
    result = TestSuiteResult(name="s", started_at=1000.0, cases=[
        TestCaseResult(name="a", status="passed", duration_s=1.5),
        TestCaseResult(name="b", status="failed", duration_s=0.25)])
    spans = [(item["start"], item["stop"]) for item in to_allure_results(result)]
    assert spans == [(1_000_000, 1_001_500), (1_001_500, 1_001_750)]

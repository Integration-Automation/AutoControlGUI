"""MCP adapters for the QA surface: assertions, data-driven runs and reports.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit and this block was
already self-contained: it reads nothing from ``_handlers`` and ``_handlers``
reads nothing from it. Covers the assertion DSL, data sources, SQL / PDF /
e-mail / HTTP steps, code generation, visual regression, the state machine,
flaky detection and quarantine, the suite runner, accessibility audits, the
device matrix and media assertions.
"""
from typing import Any, Dict, List, Optional


# --- Assertion DSL ---------------------------------------------------------

def assert_text(text: str,
                region: Optional[List[int]] = None,
                lang: str = "eng",
                regex: bool = False,
                present: bool = True,
                ignore_case: bool = True,
                min_confidence: float = 60.0,
                raise_on_fail: bool = True,
                capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_text as _assert
    return _assert(
        text, region=region, lang=lang, regex=bool(regex),
        present=bool(present), ignore_case=bool(ignore_case),
        min_confidence=float(min_confidence),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_image(template_path: str,
                 threshold: float = 0.9,
                 present: bool = True,
                 raise_on_fail: bool = True,
                 capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_image as _assert
    return _assert(
        template_path, threshold=float(threshold), present=bool(present),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_pixel(x: int, y: int, rgb: List[int],
                 tolerance: int = 0,
                 match: bool = True,
                 raise_on_fail: bool = True,
                 capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_pixel as _assert
    return _assert(
        int(x), int(y), rgb, tolerance=int(tolerance), match=bool(match),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_window(title: str,
                  exists: bool = True,
                  ignore_case: bool = True,
                  raise_on_fail: bool = True,
                  capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_window as _assert
    return _assert(
        title, exists=bool(exists), ignore_case=bool(ignore_case),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_clipboard(text: str,
                     mode: str = "equals",
                     ignore_case: bool = False,
                     present: bool = True,
                     raise_on_fail: bool = True,
                     capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_clipboard as _assert
    return _assert(
        text, mode=mode, ignore_case=bool(ignore_case),
        present=bool(present), raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_process(name: str,
                   running: bool = True,
                   raise_on_fail: bool = True,
                   capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_process as _assert
    return _assert(
        name, running=bool(running), raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_file(path: str,
                exists: bool = True,
                contains: Optional[str] = None,
                sha256: Optional[str] = None,
                min_size: Optional[int] = None,
                raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_file as _assert
    return _assert(
        path, exists=bool(exists), contains=contains, sha256=sha256,
        min_size=None if min_size is None else int(min_size),
        raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def assert_http(url: str,
                status: int = 200,
                contains: Optional[str] = None,
                timeout: float = 10.0,
                method: str = "GET",
                raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_http as _assert
    return _assert(
        url, status=int(status), contains=contains, timeout=float(timeout),
        method=method, raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def assert_all(specs: List[Dict[str, Any]],
               raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_all as _assert
    return _assert(specs, raise_on_fail=bool(raise_on_fail)).to_dict()


def assert_any(specs: List[Dict[str, Any]],
               raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_any as _assert
    return _assert(specs, raise_on_fail=bool(raise_on_fail)).to_dict()


def assert_eventually(spec: Dict[str, Any],
                      timeout: float = 5.0,
                      interval: float = 0.25,
                      raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_eventually as _assert
    return _assert(
        spec, timeout=float(timeout), interval=float(interval),
        raise_on_fail=bool(raise_on_fail),
    ).to_dict()


# --- Data-driven execution -------------------------------------------------

def load_data(source: Dict[str, Any],
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
    from je_auto_control.utils.data_source import load_rows
    return load_rows(source, limit=limit if limit is None else int(limit))


# --- Ad-hoc SQL query + assertion ------------------------------------------

def sql_query(database: str, query: str,
              params: Any = None, fetch: str = "all") -> Any:
    from je_auto_control.utils.sql.sql_query import query_sqlite
    return query_sqlite(database, query, params=params, fetch=fetch)


def assert_db(database: str, query: str, params: Any = None,
              op: str = "eq", expected: Any = None,
              raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_variable
    from je_auto_control.utils.sql.sql_query import query_sqlite
    value = query_sqlite(database, query, params=params, fetch="scalar")
    return assert_variable(
        value, op=op, expected=expected, name="ac_assert_db",
        raise_on_fail=bool(raise_on_fail),
    ).to_dict()


# --- PDF text + assertion --------------------------------------------------

def extract_pdf_text(path: str, pages: Any = None) -> str:
    from je_auto_control.utils.pdf.pdf_reader import (
        extract_pdf_text as _extract,
    )
    return _extract(path, pages=pages)


def assert_pdf_text(path: str, text: str, present: bool = True,
                    page: Any = None, case_sensitive: bool = True,
                    raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.pdf.pdf_reader import (
        assert_pdf_text as _assert,
    )
    return _assert(path, text, present=bool(present), page=page,
                   case_sensitive=bool(case_sensitive),
                   raise_on_fail=bool(raise_on_fail))


# --- Send email (SMTP) -----------------------------------------------------

def send_email(message: Dict[str, Any],
               smtp: Dict[str, Any]) -> Dict[str, Any]:
    from je_auto_control.utils.email_send.email_sender import (
        send_email as _send,
    )
    return _send(message, smtp)


# --- HTTP / API request ----------------------------------------------------

def http_request(url: str, method: str = "GET",
                 headers: Optional[Dict[str, Any]] = None,
                 json_body: Any = None, data: Any = None,
                 auth: Optional[Dict[str, Any]] = None,
                 timeout: float = 30.0) -> Dict[str, Any]:
    from je_auto_control.utils.http_client.http_client import (
        http_request as _request,
    )
    return _request(url, method=method, headers=headers, json_body=json_body,
                    data=data, auth=auth, timeout=float(timeout))


# --- Codegen: action list -> source code -----------------------------------

def generate_code(source: Any, target: str = "pytest",
                  name: str = "recorded_flow", style: str = "calls",
                  output: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.codegen.codegen import (
        generate_code as _gen, generate_code_file,
    )
    from je_auto_control.utils.json.json_file import read_action_json
    if output:
        code = generate_code_file(source, output, target=target,
                                  name=name, style=style)
        return {"output": output, "code": code}
    actions = source if isinstance(source, list) else read_action_json(source)
    return {"code": _gen(actions, target=target, name=name, style=style)}


# --- Visual regression + state machine -------------------------------------

def take_golden(path: str, region: Optional[List[int]] = None) -> str:
    from je_auto_control.utils.visual_regression import (
        take_golden as _take,
    )
    return str(_take(path, region=region))


def assert_visual(golden_path: str, region: Optional[List[int]] = None,
                  tolerance: float = 0.0, per_pixel_threshold: int = 16,
                  diff_path: Optional[str] = None,
                  create_if_missing: bool = True,
                  raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _assert_visual
    return _assert_visual(
        golden_path, region=region, tolerance=tolerance,
        per_pixel_threshold=per_pixel_threshold, diff_path=diff_path,
        create_if_missing=create_if_missing, raise_on_fail=raise_on_fail)


def run_state_machine(spec: Dict[str, Any]) -> Dict[str, Any]:
    from je_auto_control.utils.state_machine import (
        run_state_machine as _run,
    )
    return _run(spec)


# --- Flaky-test detection --------------------------------------------------

def flaky_report(limit: int = 500,
                 min_runs: int = 2,
                 group_by: str = "script_path") -> Dict[str, Any]:
    from je_auto_control.utils.flakiness import analyze_flakiness
    return analyze_flakiness(
        limit=int(limit), min_runs=int(min_runs), group_by=group_by,
    ).to_dict()


# --- QA suite runner + CI reports ------------------------------------------

def run_suite(spec: Dict[str, Any],
              tags: Optional[List[str]] = None,
              respect_quarantine: bool = True,
              junit_path: Optional[str] = None,
              allure_dir: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.test_suite import (
        run_suite as _run, write_allure_results, write_junit_xml,
    )
    result = _run(
        spec, executor=executor, tags=tags,
        respect_quarantine=bool(respect_quarantine),
    )
    payload = result.to_dict()
    reports: Dict[str, Any] = {}
    if junit_path:
        reports["junit"] = write_junit_xml(result, junit_path)
    if allure_dir:
        reports["allure"] = write_allure_results(result, allure_dir)
    if reports:
        payload["reports"] = reports
    return payload


# --- Flaky quarantine ------------------------------------------------------

def quarantine_add(name: str, reason: str = "") -> Dict[str, Any]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return default_quarantine_store().add(name, reason=reason).to_dict()


def quarantine_remove(name: str) -> Dict[str, Any]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return {"name": name, "removed": default_quarantine_store().remove(name)}


def quarantine_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return [entry.to_dict() for entry in default_quarantine_store().list()]


def quarantine_auto(flip_rate_threshold: float = 0.5,
                    min_runs: int = 3,
                    limit: int = 500,
                    group_by: str = "script_path") -> List[Dict[str, Any]]:
    from je_auto_control.utils.quarantine import auto_quarantine_from_flakiness
    return [
        entry.to_dict()
        for entry in auto_quarantine_from_flakiness(
            flip_rate_threshold=float(flip_rate_threshold),
            min_runs=int(min_runs), limit=int(limit), group_by=group_by,
        )
    ]


# --- Accessibility / i18n audit --------------------------------------------

def audit_accessibility(app_name: Optional[str] = None,
                        contrast_pairs: Optional[List[Dict[str, Any]]] = None,
                        texts: Optional[List[str]] = None,
                        min_ratio: float = 4.5,
                        max_results: int = 500) -> Dict[str, Any]:
    from je_auto_control.utils.a11y_audit import run_audit
    return run_audit(
        app_name=app_name, contrast_pairs=contrast_pairs, texts=texts,
        min_ratio=float(min_ratio), max_results=int(max_results),
    ).to_dict()


def audit_contrast(foreground: List[int], background: List[int],
                   min_ratio: float = 4.5) -> Dict[str, Any]:
    from je_auto_control.utils.a11y_audit import contrast_ratio
    ratio = contrast_ratio(foreground, background)
    return {
        "ratio": round(ratio, 2),
        "passes_aa": ratio >= float(min_ratio),
        "foreground": list(foreground), "background": list(background),
    }


def wcag_audit(app_name: Optional[str] = None,
               contrast_pairs: Optional[List[Dict[str, Any]]] = None,
               texts: Optional[List[str]] = None, level: str = "AA",
               min_target_px: int = 24,
               max_results: int = 500) -> Dict[str, Any]:
    from je_auto_control.utils.a11y_audit import wcag_audit as _wcag
    return _wcag(
        app_name=app_name, contrast_pairs=contrast_pairs, texts=texts,
        level=str(level), min_target_px=int(min_target_px),
        max_results=int(max_results))


# --- Mobile device matrix --------------------------------------------------

def run_device_matrix(actions: List[Any], devices: List[Dict[str, Any]],
                      max_parallel: int = 4,
                      var_name: str = "device") -> Dict[str, Any]:
    from je_auto_control.utils.device_matrix import run_on_devices
    return run_on_devices(
        actions, devices, max_parallel=int(max_parallel), var_name=var_name,
    ).to_dict()


# --- Media assertions ------------------------------------------------------

def assert_audio(duration_s: float = 1.0,
                 threshold: float = 0.01,
                 expect_sound: bool = True,
                 samplerate: int = 44100,
                 channels: int = 1,
                 raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.media_assert import assert_audio_activity
    return assert_audio_activity(
        duration_s=float(duration_s), threshold=float(threshold),
        expect_sound=bool(expect_sound), samplerate=int(samplerate),
        channels=int(channels), raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def assert_video_changes(video_path: str,
                         start_s: float = 0.0,
                         end_s: Optional[float] = None,
                         threshold: float = 1.0,
                         expect_motion: bool = True,
                         region: Optional[List[int]] = None,
                         raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.media_assert import (
        assert_video_changes as _assert,
    )
    return _assert(
        video_path, start_s=float(start_s),
        end_s=None if end_s is None else float(end_s),
        threshold=float(threshold), expect_motion=bool(expect_motion),
        region=region, raise_on_fail=bool(raise_on_fail),
    ).to_dict()

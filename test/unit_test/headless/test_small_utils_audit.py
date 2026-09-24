"""Small-utility defects from the 2026-09-24 audit (fakes only; no network, no screen).

Implicit-SSL mail went to the STARTTLS port; the profiler's FPS kept falling
after stop(), was nonsense without start(), its speedscope export was not
recognised and spans on two threads left a stale tag; Content-Length took
"+5", "1_000" and non-ASCII digits and "xchunked" counted as chunked; a rect
drawn from its bottom-right corner crashed; multi-frame images leaked their
file; a project path with a quote broke the generated executors; a time
before the epoch raised OverflowError from TOTP.
"""
import ast
import gc
import threading
import warnings

import pytest
from PIL import Image

from je_auto_control.utils.annotate.annotate import annotate_screenshot
from je_auto_control.utils.email_send import email_sender
from je_auto_control.utils.http_headers import (
    INVALID_CONTENT_LENGTH, is_chunked, parse_content_length,
)
from je_auto_control.utils.profiler.resource_profiler import ResourceProfiler
from je_auto_control.utils.project.template.template_executor import executor_template_1
from je_auto_control.utils.qr.qr import read_qr_codes
from je_auto_control.utils.remote_desktop.totp import TOTPError, generate_code


def test_implicit_ssl_defaults_to_port_465(monkeypatch):
    ports = []

    class _Server:
        def __init__(self, _host, port, **_kw):
            ports.append(port)

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(email_sender.smtplib, "SMTP_SSL", _Server)
    monkeypatch.setattr(email_sender, "_login_send", lambda *_a: None)
    email_sender._deliver(object(), {"host": "smtp.example.com", "use_ssl": True})
    assert ports == [465]


def test_the_profiler_report_is_frozen_at_stop(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("je_auto_control.utils.profiler.resource_profiler.time.monotonic",
                        lambda: clock[0])
    profiler = ResourceProfiler()
    profiler._psutil = None   # FPS-only mode: no sampling thread
    assert profiler.report().duration_s == 0 and profiler.report().fps_avg == 0
    profiler.start()
    for _ in range(10):
        profiler.tick_frame()
    clock[0] += 2.0
    profiler.stop()
    clock[0] += 60.0
    report = profiler.report()
    assert report.duration_s == 2.0 and report.fps_avg == 5.0


def test_speedscope_recognises_the_export():
    payload = ResourceProfiler().speedscope_payload()
    assert payload["$schema"] == "https://www.speedscope.app/file-format-schema.json"


def test_interleaved_spans_on_two_threads_leave_no_tag():
    profiler = ResourceProfiler()
    a_in, b_in, a_out = threading.Event(), threading.Event(), threading.Event()

    def span_a():
        with profiler.span("A"):
            a_in.set()
            b_in.wait(2)
        a_out.set()

    def span_b():
        a_in.wait(2)
        with profiler.span("B"):
            b_in.set()
            a_out.wait(2)

    threads = [threading.Thread(target=span_a), threading.Thread(target=span_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)
    assert profiler._open_spans == []


class _Headers(dict):
    pass


@pytest.mark.parametrize("raw", ["+5", "1_000", chr(0x665), "-1", "5 5"])
def test_content_length_is_ascii_digits_only(raw):
    assert parse_content_length(_Headers({"Content-Length": raw})) == INVALID_CONTENT_LENGTH


def test_chunked_must_be_the_final_coding():
    assert is_chunked(_Headers({"Transfer-Encoding": "gzip, Chunked"}))
    assert not is_chunked(_Headers({"Transfer-Encoding": "xchunkedy"}))
    assert not is_chunked(_Headers({"Transfer-Encoding": "chunked, gzip"}))


def test_a_rect_given_from_its_bottom_right_corner_is_drawn(tmp_path):
    image = Image.new("RGB", (100, 100))
    annotate_screenshot(image, [{"type": "box", "rect": [80, 80, 10, 10]},
                                {"type": "highlight", "rect": [80, 80, 10, 10]}], tmp_path / "out.png")


def test_multi_frame_files_are_closed(tmp_path):
    path = tmp_path / "two.gif"
    frames = [Image.new("RGB", (20, 20), c) for c in ("red", "blue")]
    frames[0].save(path, save_all=True, append_images=frames[1:])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        read_qr_codes(str(path), decoder=lambda _img: [])
        annotate_screenshot(str(path), [], tmp_path / "out.png")
        gc.collect()
    assert not [w for w in caught if issubclass(w.category, ResourceWarning)]


def test_generated_executors_survive_a_quote_in_the_path():
    path = '/home/u/my"proj\\x/keyword1.json'
    source = executor_template_1.replace("{temp}", repr(path))
    call = ast.parse(source).body[1].value.args[0]
    assert call.args[0].value == path


def test_a_time_before_the_epoch_is_a_totp_error():
    with pytest.raises(TOTPError):
        generate_code("JBSWY3DPEHPK3PXP", at=-100)


def test_a_log_record_that_cannot_be_formatted_stays_in_the_handler(monkeypatch):
    import logging
    from je_auto_control.utils.watcher.watcher import LogTail
    monkeypatch.setattr(logging, "raiseExceptions", False)
    logger = logging.getLogger("small_utils_audit")
    tail = LogTail()
    logger.addHandler(tail)
    try:
        logger.warning("bad %s %s", "only-one")   # must not raise here
    finally:
        logger.removeHandler(tail)


def test_a_pixel_the_backend_cannot_read_is_none(monkeypatch):
    from je_auto_control.utils.exception.exceptions import AutoControlException
    from je_auto_control.utils.watcher.watcher import PixelWatcher
    from je_auto_control.wrapper import auto_control_screen

    def refuse(_x, _y):
        raise AutoControlException("GetPixel failed")

    monkeypatch.setattr(auto_control_screen, "get_pixel", refuse)
    assert PixelWatcher().sample(-99999, -99999) is None


def test_a_failing_notifier_is_not_shown(monkeypatch):
    import subprocess
    from je_auto_control.utils.notify import notifier
    monkeypatch.setattr(notifier.subprocess, "run",
                        lambda argv, **_kw: subprocess.CompletedProcess(argv, 1))
    assert notifier.notify("t", "m", system="Linux").shown is False
    _argv, env = notifier._notify_spec("Windows", "t", "m")
    assert env["AC_NOTIFY_APP_ID"].endswith("powershell.exe") and "WindowsPowerShell" in env["AC_NOTIFY_APP_ID"]


def test_a_region_past_the_edge_ignores_the_padding():
    from je_auto_control.utils.color_stats.color_stats import region_color_stats
    stats = region_color_stats(Image.new("RGB", (100, 100), (255, 0, 0)), region=(50, 50, 150, 150))
    assert stats.average_rgb == (255, 0, 0) and stats.dominant_fraction == 1.0


def test_an_unopenable_database_is_an_action_error(monkeypatch, tmp_path):
    import sqlite3
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    from je_auto_control.utils.sql import sql_query
    database = tmp_path / "x.db"
    database.write_bytes(b"")

    class _Driver:
        Row = sqlite3.Row

        @staticmethod
        def connect(*_a, **_kw):
            raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(sql_query, "require_sqlite3", lambda: _Driver)
    with pytest.raises(AutoControlActionException):
        sql_query.query_sqlite(str(database), "SELECT 1")

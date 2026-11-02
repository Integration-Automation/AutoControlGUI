"""The Python client and the committed C owner service agree, and the native suites pass.

The layout checks read the C header and run everywhere. The native suites compile and run
only on Linux with a compiler and glibc headers that know PIDFD_GET_INFO; anywhere else
they skip with the reason.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

from je_auto_control.utils.agent_runtime import owner_service_nested as nested
from je_auto_control.utils.agent_runtime import owner_service_wire as wire

ROOT = Path(__file__).resolve().parents[3] / "native" / "owner_service"
HEADER = (ROOT / "src" / "native_service.h").read_text(encoding="utf-8")


def _asserted(struct):
    sizes = re.findall(rf"sizeof\({struct}\) == (\d+)", HEADER)
    offsets = dict(re.findall(rf"offsetof\({struct}, (\w+)\) == (\d+)", HEADER))
    return int(sizes[0]), {name: int(value) for name, value in offsets.items()}


def _enum(first):
    body = re.search(rf"typedef enum \{{\s*({first}[^}}]*)\}}", HEADER).group(1)
    return [name.split("=")[0].strip() for name in body.split(",") if name.strip()]


def test_request_and_reply_layouts_match_the_header():
    size, offsets = _asserted("service_request")
    assert size == wire.REQUEST_SIZE
    assert offsets == {name: wire.REQUEST_OFFSETS[name] for name in offsets}
    size, offsets = _asserted("service_reply")
    assert size == wire.REPLY_SIZE
    assert offsets == {name: wire.REPLY_OFFSETS[name] for name in offsets}


def test_opcodes_and_statuses_match_the_header():
    opcodes = _enum("OP_OPEN_TOP")
    assert opcodes == ["OP_OPEN_TOP", "OP_OPEN_CHILD", "OP_START", "OP_CLOSE", "OP_WRITE", "OP_READ", "OP_OBSERVE",
                       "OP_RENEW"]
    assert [getattr(wire, name) for name in opcodes] == list(range(1, 9))
    statuses = _enum("STATUS_OK")
    assert [getattr(wire, name) for name in statuses] == list(range(len(statuses)))
    assert f"#define SERVICE_DATA_BYTES {wire.DATA_BYTES}" in HEADER
    assert f"#define SERVICE_MAGIC 0x{wire.MAGIC:08X}u".lower() in HEADER.lower()


def test_nested_bootstrap_frame_matches_the_core():
    internal = (ROOT / "src" / "owner_internal.h").read_text(encoding="utf-8")
    assert f"#define NO_BOOTSTRAP_MAGIC 0x{nested.BOOTSTRAP_MAGIC:08x}u".lower() in internal.lower()
    assert f"#define NO_BOOTSTRAP_FD {nested.BOOTSTRAP_FD}" in internal
    assert f"#define NO_CAPABILITY_BYTES {wire.CAPABILITY_BYTES}" in internal


def _toolchain_reason():
    if not sys.platform.startswith("linux"):
        return "the owner service is Linux-only"
    compiler = os.environ.get("CC", "cc")
    if shutil.which(compiler) is None:
        return f"no C compiler ({compiler})"
    probe = "#define _GNU_SOURCE\n#include <sys/pidfd.h>\nint main(void){return PIDFD_GET_INFO > 0 ? 0 : 1;}\n"
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "probe.c"
        source.write_text(probe, encoding="utf-8")
        result = subprocess.run([compiler, str(source), "-o", str(Path(directory) / "probe")],
                                capture_output=True, timeout=60, check=False)
    return None if result.returncode == 0 else "glibc headers without PIDFD_GET_INFO"


def test_native_suites_pass_where_the_toolchain_allows():
    reason = _toolchain_reason()
    if reason:
        pytest.skip(reason)
    result = subprocess.run([sys.executable, "-I", str(ROOT / "tests" / "run_checks.py")],
                            capture_output=True, text=True, timeout=1200, check=False)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]

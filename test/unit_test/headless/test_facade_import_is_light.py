"""``import je_auto_control`` must not need the image/crypto wheels.

The facade used to import OpenCV, NumPy, Pillow, ``je_open_cv`` and
``cryptography`` at module scope, so *any* import under ``je_auto_control``
pulled all five in. That is what kept the X11 backend off a FreeBSD desktop:
none of those five publishes a FreeBSD wheel, and moving a mouse needs none of
them. They are now imported by the functions that use them.

This is a property that regresses silently — one convenience import at the top
of one module puts the whole set back on the path, and every platform that has
wheels keeps passing. So the check is made the way a machine without them would
make it: the modules are blocked outright, in a subprocess, and the facade has
to import anyway.
"""
import os
import pathlib
import subprocess  # nosec B404  # reason: fixed argv, sys.executable, no shell
import sys

import pytest

#: Blocked wholesale. ``mss`` is in the list because screen capture is as
#: optional to input automation as OpenCV is; it was already lazy, and this
#: keeps it that way.
HEAVY = ("cv2", "numpy", "PIL", "cryptography", "je_open_cv", "mss")

#: The working tree, so the subprocess tests the checkout rather than whatever
#: version of the package happens to be installed in site-packages.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

_PROBE = '''
import sys


class _Blocker:
    """Refuse the heavy wheels the way an absent wheel would."""

    BLOCKED = {blocked!r}

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.BLOCKED:
            raise ImportError(
                "No module named %r (blocked by the probe)" % fullname)
        return None


sys.meta_path.insert(0, _Blocker())
import je_auto_control  # noqa: E402

leaked = sorted(name for name in sys.modules
                if name.split(".")[0] in _Blocker.BLOCKED)
if leaked:
    raise SystemExit("heavy modules reached sys.modules: %s" % leaked)
print("ok", len(je_auto_control.__all__))
'''


def test_facade_imports_without_the_heavy_wheels():
    """The facade imports with OpenCV / Pillow / cryptography absent."""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    result = subprocess.run(  # nosec B603  # reason: fixed argv, no shell
        [sys.executable, "-c", _PROBE.format(blocked=HEAVY)],
        capture_output=True, text=True, timeout=180, check=False, env=env)
    assert result.returncode == 0, (
        "import je_auto_control needs one of "
        f"{', '.join(HEAVY)}:\n{result.stdout}\n{result.stderr}")
    assert result.stdout.startswith("ok "), result.stdout


def test_the_lazy_modules_still_work_when_the_wheels_are_there():
    """Deferring an import must not have broken the function that uses it.

    The probe above proves the import path is clean; this proves the call path
    still is, so a local import placed in the wrong function cannot pass as a
    win.
    """
    pytest.importorskip("PIL")
    from PIL import Image

    from je_auto_control.utils.color_stats.color_stats import (
        region_color_stats,
    )

    image = Image.new("RGB", (8, 8), (10, 20, 30))
    stats = region_color_stats(image)
    assert stats.average_rgb == (10, 20, 30)
    assert stats.dominant_rgb == (10, 20, 30)

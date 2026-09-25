"""The package imports and writes SARIF URIs without deprecated APIs.

A test suite that turns warnings into errors could not import the package:
defusedxml 0.7.1's ``defuse_stdlib()`` warned about its own cElementTree.
SARIF file URIs came from ``PurePath.as_uri()``, deprecated in Python 3.14.
"""
import os
import subprocess  # nosec B404  # reason: runs the interpreter on a fixed import
import sys
import warnings
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from je_auto_control.utils.sarif.sarif import _artifact_uri, _file_uri

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_the_package_imports_with_warnings_as_errors():
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT))
    argv = [sys.executable, "-W", "error", "-c", "import je_auto_control"]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=180, env=env, cwd=str(_REPO_ROOT), check=False)  # nosec B603  # nosemgrep  # reason: fixed argv, this test's own import
    assert done.returncode == 0, done.stderr[-2000:]


def test_stdlib_xml_is_still_defused():
    import xml.etree.ElementTree as ElementTree  # nosec B405  # nosemgrep  # reason: asserts that parsing it is refused

    import je_auto_control.utils.xml  # noqa: F401  # reason: installs the defused parsers
    with pytest.raises(Exception, match="(?i)entit"):
        ElementTree.fromstring('<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')  # nosec B314  # reason: must be refused


@pytest.mark.parametrize("pure", [
    PureWindowsPath("C:/my dir/flow file.json"),
    PureWindowsPath("//server/share/a b.txt"),
    PureWindowsPath("D:/x/中 %.json"),
    PurePosixPath("/tmp/a b#c.json"),
    PurePosixPath("/x/中.json"),
])
def test_file_uris_match_what_the_stdlib_wrote(pure):
    if not hasattr(pure, "as_uri"):
        pytest.skip("PurePath.as_uri is gone")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        expected = pure.as_uri()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _file_uri(pure) == expected


def test_sarif_uris_raise_no_deprecation():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _artifact_uri("C:\\my dir\\flow file.json") == "file:///C:/my%20dir/flow%20file.json"
        assert _artifact_uri("rel/a b.json") == "rel/a%20b.json"

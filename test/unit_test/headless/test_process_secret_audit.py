"""Process / secret / file boundary defects from the 2026-09-24 audit.

Recycling a symlink recycled its target; a relative ``file://`` secret ref
ignored ``base_dir`` and a cross-drive one escaped ``SecretRefError``; a code
in non-ASCII digits crashed TOTP verification; a negative drop point could not
be packed; log redaction left quoted, ``pwd=`` and ``--password`` credentials
visible; dotenv ignored tabs; a batch file's arguments reached cmd.exe
unescaped; and ``start_exe`` launched whatever PATH found instead of the
checked file.
"""
import os
import sys

import pytest

from je_auto_control.utils.clipboard_files.clipboard_files import (
    build_dropfiles, parse_dropfiles,
)
from je_auto_control.utils.config_redaction.config_redaction import redact_secret_text
from je_auto_control.utils.dotenv.dotenv import parse_dotenv
from je_auto_control.utils.remote_desktop import totp
from je_auto_control.utils.secret_ref.secret_ref import SecretRefError, resolve_ref
from je_auto_control.utils.shell_process import shell_exec
from je_auto_control.utils.start_exe import start_another_process
from je_auto_control.utils.trash.trash import move_to_trash


def test_recycling_a_symlink_recycles_the_link_not_its_target(tmp_path):
    target = tmp_path / "important.db"
    target.write_text("data", encoding="utf-8")
    link = tmp_path / "link.db"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks needs a privilege on this machine")
    recycled = []
    assert move_to_trash(link, backend=recycled.append)
    assert recycled == [os.path.abspath(link)]
    target.unlink()
    recycled.clear()
    assert move_to_trash(link, backend=recycled.append)  # a dangling link exists too
    assert recycled == [os.path.abspath(link)]


def test_a_relative_file_ref_is_read_under_base_dir(tmp_path, monkeypatch):
    (tmp_path / "token.txt").write_text("s3cret", encoding="utf-8")
    monkeypatch.chdir(tmp_path.parent)
    assert resolve_ref("file://token.txt", base_dir=str(tmp_path)) == "s3cret"
    assert resolve_ref("file://./token.txt", base_dir=str(tmp_path)) == "s3cret"
    with pytest.raises(SecretRefError, match="escapes"):
        resolve_ref("file://../outside.txt", base_dir=str(tmp_path))


@pytest.mark.skipif(sys.platform != "win32", reason="drive letters are Windows paths")
def test_a_file_ref_on_another_drive_is_a_secret_ref_error(tmp_path):
    other = "D:/x.txt" if str(tmp_path).upper().startswith("C:") else "C:/x.txt"
    with pytest.raises(SecretRefError):
        resolve_ref(f"file://{other}", base_dir=str(tmp_path))
    with pytest.raises(SecretRefError):
        resolve_ref(f"file:///{other}", base_dir=str(tmp_path))


def test_a_file_url_with_a_drive_names_that_drive(tmp_path):
    if sys.platform != "win32":
        pytest.skip("drive letters are Windows paths")
    secret = tmp_path / "t.txt"
    secret.write_text("v", encoding="utf-8")
    url = "file:///" + str(secret).replace("\\", "/")
    assert resolve_ref(url, base_dir=str(tmp_path)) == "v"


def test_a_code_in_other_scripts_digits_does_not_verify():
    secret = totp.generate_secret()
    arabic_indic = "".join(chr(0x0660 + int(ch)) for ch in "123456")
    assert totp.verify_code(secret, arabic_indic) is False


def test_a_negative_drop_point_round_trips():
    blob = build_dropfiles(["C:/a.txt"], point=(-5, -7))
    assert parse_dropfiles(blob)["point"] == [-5, -7]


@pytest.mark.parametrize("text, leaked", [
    ('password="correct horse battery"', "horse"),
    ("pwd=hunter2", "hunter2"),
    ("--password hunter2 --verbose", "hunter2"),
    ("--db-password hunter2", "hunter2"),
])
def test_log_redaction_masks_quoted_short_key_and_cli_credentials(text, leaked):
    redacted = redact_secret_text(text)
    assert leaked not in redacted
    assert "***" in redacted or "*" in redacted


def test_log_redaction_leaves_ordinary_flags_alone():
    assert redact_secret_text("--token-file path.txt --verbose") == "--token-file path.txt --verbose"


def test_dotenv_treats_tabs_as_whitespace():
    parsed = parse_dotenv("A=b\t# comment\nexport\tB=1\n")
    assert parsed == {"A": "b", "B": "1"}


def test_batch_file_arguments_with_cmd_syntax_are_refused(monkeypatch):
    monkeypatch.setattr(shell_exec.sys, "platform", "win32")
    with pytest.raises(ValueError, match="metacharacters"):
        shell_exec.refuse_batch_metacharacters(["C:/tools/run.BAT", "x&calc"])
    shell_exec.refuse_batch_metacharacters(["C:/tools/run.bat", "plain", "C:/a b/c.txt"])
    shell_exec.refuse_batch_metacharacters(["C:/tools/app.exe", "x&y"])
    shell_exec.refuse_batch_metacharacters("run.bat x&calc")


def test_start_exe_launches_the_file_it_checked(tmp_path, monkeypatch):
    exe = tmp_path / "myapp"
    exe.write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    launched = []

    def fake_exec(self, command):
        launched.append(command)
        self.process = object()

    monkeypatch.setattr(start_another_process.ShellManager, "exec_shell", fake_exec)
    start_another_process.start_exe("myapp")
    assert launched == [[str(exe.resolve())]]

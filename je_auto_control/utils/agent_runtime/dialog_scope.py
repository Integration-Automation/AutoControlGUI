"""Pause managed desktop work at unsaved-content or unrecognized modal windows."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentHumanReview

_UNSAVED = ("don't save", "do not save", "unsaved", "discard changes", "save changes",
            "未儲存", "儲存變更", "不儲存", "未保存", "保存更改", "不保存", "保存しない", "変更を保存")
_FILE_TITLES = frozenset({"open", "save as", "select folder", "開啟", "另存新檔", "選取資料夾",
                          "打开", "另存为", "选择文件夹", "開く", "名前を付けて保存", "フォルダーの選択"})


def _dialog_library() -> Any:
    if sys.platform != "win32":
        raise AgentHumanReview("native dialog detection needs a trusted platform adapter")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindow.argtypes, user.GetWindow.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.restype = ctypes.c_int
    user.IsWindowEnabled.argtypes, user.IsWindowEnabled.restype = [wintypes.HWND], wintypes.BOOL
    return user


def _window_metadata(hwnd: int) -> dict:
    user = _dialog_library()
    owner = user.GetWindow(hwnd, 4)  # GW_OWNER; parent/owner is not an input authority grant.
    name = ctypes.create_unicode_buffer(256)
    if not user.GetClassNameW(hwnd, name, len(name)):
        raise AgentHumanReview("native dialog identity is unavailable")
    return {"class_name": name.value, "modal": bool(owner and not user.IsWindowEnabled(owner))}


def check_review(hwnd: int, title: str, elements: Sequence[Any], *, workspace: bool) -> None:
    """Refuse known unsaved prompts, unknown modals and marked dirty workspace documents."""
    metadata = _window_metadata(hwnd)
    if _dirty_workspace(title, workspace):
        raise AgentHumanReview("workspace contains unsaved content; explicit review is required")
    modal = metadata["modal"] or metadata["class_name"] == "#32770"
    if not modal:
        return
    text = " ".join([title, *(str(item.name) for item in elements)]).casefold().replace("’", "'")
    if any(phrase in text for phrase in _UNSAVED):
        raise AgentHumanReview("unsaved content dialog requires explicit human review")
    if metadata["class_name"] == "#32770" and title.strip().casefold() in _FILE_TITLES:
        return
    raise AgentHumanReview("unrecognized modal dialog requires explicit human review")


def _dirty_workspace(title: str, workspace: bool) -> bool:
    return workspace and (title.lstrip().startswith("*") or title.rstrip().endswith("*"))

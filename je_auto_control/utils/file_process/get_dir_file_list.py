import os
from os import getcwd, walk
from os.path import abspath, join, realpath
from typing import List, Optional


def get_dir_files_as_list(
    dir_path: Optional[str] = None,
    default_search_file_extension: str = ".json"
) -> List[str]:
    """
    Get all files in a directory that end with a specific extension.
    遍歷指定目錄，取得所有符合副檔名的檔案清單

    Sorted, so ``-d`` runs a directory in the same order on every machine
    (``os.walk`` follows the file system's own order: NTFS gave ``a, B, _x``,
    ext4 hash order). Nothing outside ``dir_path`` is listed: a directory
    junction or symlink pointing elsewhere used to put its files on the run
    list.

    :param dir_path: Directory path to search 要搜尋的目錄路徑 (預設為呼叫時的當前工作目錄)
    :param default_search_file_extension: File extension to filter 要搜尋的副檔名 (預設 ".json")
    :return: List of absolute file paths 符合條件的檔案絕對路徑清單
    """
    if dir_path is None:
        dir_path = getcwd()
    extension = default_search_file_extension.lower()
    top = realpath(dir_path)
    found: List[str] = []
    for current, dirs, files in walk(dir_path):
        dirs[:] = sorted(name for name in dirs if _inside(join(current, name), top))
        found.extend(abspath(join(current, name)) for name in sorted(files)
                     if name.lower().endswith(extension) and _inside(join(current, name), top))
    return found


def _inside(path: str, top: str) -> bool:
    """Whether ``path`` resolves to ``top`` or below it."""
    resolved = realpath(path)
    return resolved == top or resolved.startswith(top.rstrip(os.sep) + os.sep)

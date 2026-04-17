from os import getcwd, walk
from os.path import abspath, join
from typing import List, Optional


def get_dir_files_as_list(
    dir_path: Optional[str] = None,
    default_search_file_extension: str = ".json"
) -> List[str]:
    """
    Get all files in a directory that end with a specific extension.
    遍歷指定目錄，取得所有符合副檔名的檔案清單

    :param dir_path: Directory path to search 要搜尋的目錄路徑 (預設為呼叫時的當前工作目錄)
    :param default_search_file_extension: File extension to filter 要搜尋的副檔名 (預設 ".json")
    :return: List of absolute file paths 符合條件的檔案絕對路徑清單
    """
    if dir_path is None:
        dir_path = getcwd()
    extension = default_search_file_extension.lower()
    return [
        abspath(join(root, file))
        for root, dirs, files in walk(dir_path)
        for file in files
        if file.lower().endswith(extension)
    ]
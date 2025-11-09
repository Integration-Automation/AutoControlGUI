from os import getcwd, walk
from os.path import abspath, join
from typing import List


def get_dir_files_as_list(
    dir_path: str = getcwd(),
    default_search_file_extension: str = ".json"
) -> List[str]:
    """
    Get all files in a directory that end with a specific extension.
    遍歷指定目錄，取得所有符合副檔名的檔案清單

    :param dir_path: Directory path to search 要搜尋的目錄路徑
    :param default_search_file_extension: File extension to filter 要搜尋的副檔名 (預設 ".json")
    :return: List of absolute file paths 符合條件的檔案絕對路徑清單
    """
    extension = default_search_file_extension.lower()
    return [
        abspath(join(root, file))
        for root, dirs, files in walk(dir_path)
        for file in files
        if file.lower().endswith(extension)
    ]
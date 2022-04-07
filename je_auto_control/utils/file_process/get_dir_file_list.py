from os import walk
from os import getcwd
from os.path import abspath
from os.path import join


def get_dir_files_as_list(dir_path: str = getcwd(), default_search_file_extension: str = ".json"):
    """
    :param dir_path: which dir we want to walk and get file list
    :param default_search_file_extension: which extension we want to search
    :return: [] if nothing searched or [file1, file2.... files] file was searched
    """
    return [
        abspath(join(dir_path, file)) for root, dirs, files in walk(dir_path)
        for file in files
        if file.endswith(default_search_file_extension.lower())
    ]


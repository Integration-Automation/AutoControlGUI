AutoControlGUI File Process Doc
==========================


.. code-block:: python

    def get_dir_files_as_list(dir_path: str = getcwd(), default_search_file_extension: str = ".json"):
    """
    get dir file when end with default_search_file_extension
    :param dir_path: which dir we want to walk and get file list
    :param default_search_file_extension: which extension we want to search
    :return: [] if nothing searched or [file1, file2.... files] file was searched
    """
    return [
        abspath(join(dir_path, file)) for root, dirs, files in walk(dir_path)
        for file in files
        if file.endswith(default_search_file_extension.lower())
    ]
====================================================
AutoControl 檔案處理 文件
====================================================


.. code-block:: python

    def get_dir_files_as_list(dir_path: str = getcwd(), default_search_file_extension: str = ".json"):
    """
    取得指定資料夾路徑下的 所有 default_search_file_extension 附檔名的檔案的 list
    可以跟 執行器 模塊的 execute_files 一起使用
    get dir file when end with default_search_file_extension
    dir_path 是要搜尋檔案的資料夾路徑
    :param dir_path: which dir we want to walk and get file list
    default_search_file_extension 搜尋的附檔名
    :param default_search_file_extension: which extension we want to search
    :return: [] if nothing searched or [file1, file2.... files] file was searched
    """
    return [
        abspath(join(dir_path, file)) for root, dirs, files in walk(dir_path)
        for file in files
        if file.endswith(default_search_file_extension.lower())
    ]
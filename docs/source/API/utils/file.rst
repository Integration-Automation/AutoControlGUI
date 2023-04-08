File process API
----

.. code-block:: python

    def get_dir_files_as_list(
            dir_path: str = getcwd(),
            default_search_file_extension: str = ".json") -> List[str]:
        """
        get dir file when end with default_search_file_extension
        :param dir_path: which dir we want to walk and get file list
        :param default_search_file_extension: which extension we want to search
        :return: [] if nothing searched or [file1, file2.... files] file was searched
        """
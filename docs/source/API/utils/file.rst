====================
File Processing API
====================

Utility functions for working with action files.

----

get_dir_files_as_list
=====================

.. function:: get_dir_files_as_list(dir_path=os.getcwd(), default_search_file_extension=".json")

   Walks a directory and returns all files matching the given extension.

   :param str dir_path: Directory path to search. Defaults to the current working directory.
   :param str default_search_file_extension: File extension to filter by (e.g., ``".json"``).
   :returns: List of matching file paths. Empty list if no files found.
   :rtype: list[str]

   **Example:**

   .. code-block:: python

      from je_auto_control import get_dir_files_as_list

      # Get all JSON files in a directory
      files = get_dir_files_as_list("./actions/")
      print(files)  # ['./actions/step1.json', './actions/step2.json']

      # Search for Python files instead
      py_files = get_dir_files_as_list("./scripts/", ".py")

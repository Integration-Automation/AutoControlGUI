import os

from je_auto_control import execute_files
from je_auto_control import get_dir_files_as_list

files_list = get_dir_files_as_list(
    os.getcwd() +
    "/test/integrated_test/get_dir_file_and_execute"
)
print(files_list)
if files_list is not None:
    execute_files(files_list)

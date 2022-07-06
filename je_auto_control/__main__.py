# argparse
import argparse

from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.executor.action_executor import execute_files

if __name__ == "__main__":
    def preprocess_execute_action(file_path: str):
        execute_action(read_action_json(file_path))


    def preprocess_execute_files(file_path: str):
        execute_files(get_dir_files_as_list(file_path))


    argparse_event_dict = {
        "execute_file": preprocess_execute_action,
        "execute_dir": preprocess_execute_files
    }
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", "--execute_file", type=str, help="choose action file to execute")
    parser.add_argument("-d", "--execute_dir", type=str, help="choose dir include action file to execute")
    args = parser.parse_args()
    args = vars(args)
    for key, value in args.items():
        if value is not None:
            argparse_event_dict.get(key)(value)


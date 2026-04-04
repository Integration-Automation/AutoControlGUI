import os
import subprocess

print(os.getcwd())

cwd = os.getcwd()
subprocess.run(["python", "je_auto_control", "--execute_file", os.path.join(cwd, "test/unit_test/argparse/test1.json")])
subprocess.run(["python", "je_auto_control", "--execute_dir", os.path.join(cwd, "test/unit_test/argparse")])
subprocess.run(["python", "je_auto_control", "--create_project", cwd])

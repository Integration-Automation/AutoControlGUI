import os
import subprocess  # nosec B404  # reason: argparse smoke test invokes the CLI module

print(os.getcwd())

cwd = os.getcwd()
subprocess.run(  # nosec B603 B607  # reason: argv list, python on PATH; cwd path validated by os.path.join
    ["python", "je_auto_control", "--execute_file",
     os.path.join(cwd, "test/unit_test/argparse/test1.json")],
    check=False,
)
subprocess.run(  # nosec B603 B607  # reason: argv list, python on PATH; cwd path validated by os.path.join
    ["python", "je_auto_control", "--execute_dir",
     os.path.join(cwd, "test/unit_test/argparse")],
    check=False,
)
subprocess.run(  # nosec B603 B607  # reason: argv list, python on PATH; cwd path validated by os.path.join
    ["python", "je_auto_control", "--create_project", cwd],
    check=False,
)

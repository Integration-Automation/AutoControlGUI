import os

print(os.getcwd())

os.system("cd " + os.getcwd())
os.system("python je_auto_control " + os.getcwd() + r"/test/unit_test/argparse/test.json")



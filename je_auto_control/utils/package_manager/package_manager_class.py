from importlib import import_module
from importlib.util import find_spec
from inspect import getmembers, isfunction
from sys import stderr


class PackageManager(object):

    def __init__(self):
        self.installed_package_dict = {
        }
        self.executor = None

    def check_package(self, package: str):
        if self.installed_package_dict.get(package, None) is None:
            found_spec = find_spec(package)
            if found_spec is not None:
                try:
                    installed_package = import_module(found_spec.name)
                    self.installed_package_dict.update({found_spec.name: installed_package})
                except ModuleNotFoundError as error:
                    print(repr(error), file=stderr)
        return self.installed_package_dict.get(package, None)

    def add_package_to_executor(self, package):
        installed_package = self.check_package(package)
        if installed_package is not None and self.executor is not None:
            for function in getmembers(installed_package, isfunction):
                self.executor.event_dict.update({str(function): function})
        elif installed_package is None:
            print(repr(ModuleNotFoundError(f"Can't find package {package}")), file=stderr)
        else:
            print(f"Executor error {self.executor}", file=stderr)


package_manager = PackageManager()

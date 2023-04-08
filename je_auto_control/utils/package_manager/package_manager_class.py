from importlib import import_module
from importlib.util import find_spec
from inspect import getmembers, isfunction, isbuiltin, isclass
from sys import stderr


class PackageManager(object):

    def __init__(self):
        self.installed_package_dict = {
        }
        self.executor = None
        self.callback_executor = None

    def check_package(self, package: str):
        """
        :param package: package to check exists or not
        :return: package if find else None
        """
        if self.installed_package_dict.get(package, None) is None:
            found_spec = find_spec(package)
            if found_spec is not None:
                try:
                    installed_package = import_module(found_spec.name)
                    self.installed_package_dict.update(
                        {found_spec.name: installed_package})
                except ModuleNotFoundError as error:
                    print(repr(error), file=stderr)
        return self.installed_package_dict.get(package, None)

    def add_package_to_executor(self, package):
        """
        :param package: package's function will add to executor
        """
        self.add_package_to_target(
            package=package,
            target=self.executor
        )

    def add_package_to_callback_executor(self, package):
        """
        :param package: package's function will add to callback_executor
        """
        self.add_package_to_target(
            package=package,
            target=self.callback_executor
        )

    def get_member(self, package, predicate, target):
        """
        :param package: package we want to get member
        :param predicate: predicate
        :param target: which event_dict will be added
        """
        installed_package = self.check_package(package)
        if installed_package is not None and target is not None:
            for member in getmembers(installed_package, predicate):
                target.event_dict.update(
                    {str(package) + "_" + str(member[0]): member[1]})
        elif installed_package is None:
            print(repr(ModuleNotFoundError(f"Can't find package {package}")),
                  file=stderr)
        else:
            print(f"Executor error {self.executor}", file=stderr)

    def add_package_to_target(self, package, target):
        """
        :param package: package we want to get member
        :param target: which event_dict will be added
        """
        try:
            self.get_member(
                package=package,
                predicate=isfunction,
                target=target
            )
            self.get_member(
                package=package,
                predicate=isbuiltin,
                target=target
            )
            self.get_member(
                package=package,
                predicate=isfunction,
                target=target
            )
            self.get_member(
                package=package,
                predicate=isclass,
                target=target
            )
        except Exception as error:
            print(repr(error), file=stderr)


package_manager = PackageManager()

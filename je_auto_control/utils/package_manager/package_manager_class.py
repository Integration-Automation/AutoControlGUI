import importlib
from importlib.util import find_spec
from inspect import getmembers, isfunction, isbuiltin, isclass
from types import ModuleType
from sys import stderr
from typing import Optional

from je_auto_control.utils.logging.loggin_instance import autocontrol_logger


class PackageManager:
    """
    PackageManager
    套件管理器
    - 動態載入外部套件
    - 將套件中的函式/類別加入到 Executor 或 CallbackExecutor 的事件字典
    """

    def __init__(self):
        self.installed_package_dict: dict[str, ModuleType] = {}
        self.executor = None
        self.callback_executor = None

    def check_package(self, package: str) -> Optional[ModuleType]:
        """
        檢查並載入套件
        Check and import package

        :param package: 套件名稱 Package name
        :return: 套件模組 ModuleType 或 None
        """
        if package not in self.installed_package_dict:
            found_spec = find_spec(package)
            if found_spec is not None:
                try:
                    installed_package = importlib.import_module(found_spec.name)
                    self.installed_package_dict[found_spec.name] = installed_package
                except ModuleNotFoundError as error:
                    print(repr(error), file=stderr)
        return self.installed_package_dict.get(package)

    def add_package_to_executor(self, package: str) -> None:
        """
        將套件成員加入 Executor
        Add package members to Executor
        """
        autocontrol_logger.info(f"add_package_to_executor, package: {package}")
        self.add_package_to_target(package, self.executor)

    def add_package_to_callback_executor(self, package: str) -> None:
        """
        將套件成員加入 CallbackExecutor
        Add package members to CallbackExecutor
        """
        autocontrol_logger.info(f"add_package_to_callback_executor, package: {package}")
        self.add_package_to_target(package, self.callback_executor)

    def get_member(self, package: str, predicate, target) -> None:
        """
        取得套件成員並加入事件字典
        Get package members and add to event_dict

        :param package: 套件名稱 Package name
        :param predicate: 過濾條件 (isfunction, isbuiltin, isclass)
        :param target: 目標 Executor/CallbackExecutor
        """
        installed_package = self.check_package(package)
        if installed_package is not None and target is not None:
            for member in getmembers(installed_package, predicate):
                target.event_dict[f"{package}_{member[0]}"] = member[1]
        elif installed_package is None:
            print(repr(ModuleNotFoundError(f"Can't find package {package}")), file=stderr)
        else:
            print(f"Executor error {self.executor}", file=stderr)

    def add_package_to_target(self, package: str, target) -> None:
        """
        將套件所有成員加入目標事件字典
        Add all package members to target event_dict

        :param package: 套件名稱 Package name
        :param target: 目標 Executor/CallbackExecutor
        """
        try:
            for predicate in (isfunction, isbuiltin, isclass):
                self.get_member(package, predicate, target)
        except Exception as error:
            print(repr(error), file=stderr)


# 全域 PackageManager 實例 Global instance
package_manager = PackageManager()
import importlib
import re
import warnings
from importlib.util import find_spec
from inspect import getmembers, isfunction, isbuiltin, isclass
from types import ModuleType
from typing import Optional

from je_auto_control.utils.exception.exceptions import AutoControlExecuteActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")
# warnings.warn -> _check_allowed -> add_package_to_* -> the command's caller
_GATE_WARNING_STACKLEVEL = 3


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
        # Package gate (workspace X-12). None = not configured: any package still loads, with a
        # DeprecationWarning. False = only ``allowed_packages``; True = any package, silently.
        self.allow_arbitrary_packages: Optional[bool] = None
        self.allowed_packages: set[str] = set()

    def set_allow_arbitrary_packages(self, enabled: bool) -> None:
        """
        設定是否允許載入允許清單以外的套件
        Allow (True) or refuse (False) packages outside :attr:`allowed_packages`.
        Deliberately not an ``AC_*`` command: an action list must not open its own gate.
        """
        self.allow_arbitrary_packages = bool(enabled)

    def allow_packages(self, *packages: str) -> None:
        """
        把套件加入允許清單（連同其子模組）
        Add packages to the allowlist; a listed package also allows its submodules.
        """
        self.allowed_packages.update(packages)

    def _is_allowlisted(self, package: str) -> bool:
        return any(package == allowed or package.startswith(allowed + ".")
                   for allowed in self.allowed_packages)

    def _check_allowed(self, package: object) -> None:
        """Refuse ``package`` before it is imported, unless the gate lets it through."""
        if isinstance(package, str) and self._is_allowlisted(package):
            return
        if self.allow_arbitrary_packages is True:
            return
        if self.allow_arbitrary_packages is False:
            raise AutoControlExecuteActionException(
                f"package {package!r} is not allowed; the host must call "
                "executor.allow_packages(...) or executor.set_allow_arbitrary_packages(True)"
            )
        warnings.warn(
            f"loading package {package!r} that is not on the allowlist; a future release will refuse "
            "it by default. Call executor.allow_packages(...) for the packages you load, or "
            "executor.set_allow_arbitrary_packages(True) to keep loading any package.",
            DeprecationWarning,
            stacklevel=_GATE_WARNING_STACKLEVEL,
        )

    def check_package(self, package: str) -> Optional[ModuleType]:
        """
        檢查並載入套件
        Check and import package

        :param package: 套件名稱 Package name (must match a Python dotted identifier)
        :return: 套件模組 ModuleType 或 None
        """
        if not isinstance(package, str) or not _PACKAGE_NAME_RE.match(package):
            autocontrol_logger.error("rejected invalid package name: %r", package)
            return None
        if package not in self.installed_package_dict:
            try:
                # find_spec imports the parent package, so it raises too
                # ("no_such_parent.child"); and a module that fails to
                # compile raises SyntaxError, which is no ImportError.
                found_spec = find_spec(package)
                if found_spec is not None:
                    # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
                    installed_package = importlib.import_module(found_spec.name)
                    self.installed_package_dict[found_spec.name] = installed_package
            # A plugin's module body can raise anything ("missing config"), and
            # find_spec raises ValueError for "__main__"; all are "not loaded".
            except Exception as error:  # noqa: BLE001  # reason: third-party import code, reported and not raised
                autocontrol_logger.error("import %s failed: %r", package, error)
        return self.installed_package_dict.get(package)

    def add_package_to_executor(self, package: str) -> None:
        """
        將套件成員加入 Executor
        Add package members to Executor

        :raises AutoControlExecuteActionException: the package gate refused ``package`` (nothing is imported)
        """
        autocontrol_logger.info(f"add_package_to_executor, package: {package}")
        self._check_allowed(package)
        self.add_package_to_target(package, self.executor)

    def add_package_to_callback_executor(self, package: str) -> None:
        """
        將套件成員加入 CallbackExecutor
        Add package members to CallbackExecutor

        :raises AutoControlExecuteActionException: the package gate refused ``package`` (nothing is imported)
        """
        autocontrol_logger.info(f"add_package_to_callback_executor, package: {package}")
        self._check_allowed(package)
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
            autocontrol_logger.error("can't find package %s", package)
        else:
            autocontrol_logger.error("Executor error %r", self.executor)

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
        except Exception as error:  # noqa: BLE001  # reason: third-party members, reported and not raised
            autocontrol_logger.error("add_package_to_target failed: %r", error)


# 全域 PackageManager 實例 Global instance
package_manager = PackageManager()
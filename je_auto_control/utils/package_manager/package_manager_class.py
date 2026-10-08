import importlib
import os
import re
from importlib.util import find_spec
from inspect import getmembers, isfunction, isbuiltin, isclass
from types import ModuleType
from typing import Optional

from je_auto_control.utils.exception.exceptions import AutoControlExecuteActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")

#: Comma-separated package names the gate allows, for hosts with no Python of
#: their own to call ``executor.allow_packages``: the CLIs, the socket / REST /
#: MCP servers and the scheduler. Read once, when a manager is created.
ALLOWED_PACKAGES_ENV = "JE_AUTOCONTROL_ALLOWED_PACKAGES"


def is_package_name(name: object) -> bool:
    """Whether ``name`` is a dotted Python module name, the only thing the gate lists."""
    return isinstance(name, str) and bool(_PACKAGE_NAME_RE.match(name))


def _packages_from_environment() -> set[str]:
    """The names in ``JE_AUTOCONTROL_ALLOWED_PACKAGES``; what is not a module name is skipped."""
    allowed: set[str] = set()
    for raw in os.environ.get(ALLOWED_PACKAGES_ENV, "").split(","):
        name = raw.strip()
        if not name:
            continue
        if is_package_name(name):
            allowed.add(name)
        else:
            # Importing the package must not fail on a typo in the environment.
            autocontrol_logger.error("%s: ignored %r, not a package name", ALLOWED_PACKAGES_ENV, name)
    return allowed


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
        # Package gate (workspace X-12). False (the default) = only ``allowed_packages``;
        # True = any package. The allowlist starts from JE_AUTOCONTROL_ALLOWED_PACKAGES.
        self.allow_arbitrary_packages: bool = False
        self.allowed_packages: set[str] = _packages_from_environment()

    def set_allow_arbitrary_packages(self, enabled: bool) -> None:
        """
        設定是否允許載入允許清單以外的套件
        Allow (True) or refuse (False, the default) packages outside :attr:`allowed_packages`.
        Deliberately not an ``AC_*`` command: an action list must not open its own gate.
        """
        self.allow_arbitrary_packages = bool(enabled)

    def allow_packages(self, *packages: str) -> None:
        """
        把套件加入允許清單（連同其子模組）
        Add packages to the allowlist; a listed package also allows its submodules.

        :raises AutoControlExecuteActionException: a name is not a dotted module name (none is added)
        """
        for package in packages:
            if not is_package_name(package):
                raise AutoControlExecuteActionException(
                    f"cannot allow {package!r}: not a package name")
        self.allowed_packages.update(packages)

    def _is_allowlisted(self, package: str) -> bool:
        return any(package == allowed or package.startswith(allowed + ".")
                   for allowed in self.allowed_packages)

    def _check_allowed(self, package: object) -> None:
        """Refuse ``package`` before it is imported, unless the gate lets it through."""
        if isinstance(package, str) and self._is_allowlisted(package):
            return
        if self.allow_arbitrary_packages:
            return
        raise AutoControlExecuteActionException(
            f"package {package!r} is not allowed. To allow it: list it in the "
            f"{ALLOWED_PACKAGES_ENV} environment variable (comma-separated), pass "
            "--allow-package NAME to `je_auto_control run`, or call "
            "executor.allow_packages(...) from Python; "
            "executor.set_allow_arbitrary_packages(True) allows every package."
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
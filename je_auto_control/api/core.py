"""Stable, headless AutoControl API façade."""

from je_auto_control.utils.codegen.codegen import generate_code
from je_auto_control.utils.diagnostics import run_diagnostics
from je_auto_control.utils.executor.action_executor import (
    execute_action,
    execute_action_with_vars,
)
from je_auto_control.utils.failure_bundle import (
    FailureBundleOptions,
    create_failure_bundle,
    failure_bundle_on_error,
)

__all__ = [
    "FailureBundleOptions", "create_failure_bundle", "execute_action",
    "execute_action_with_vars", "failure_bundle_on_error", "generate_code",
    "run_diagnostics",
]

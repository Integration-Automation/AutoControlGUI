"""Small, versioned entry points for new integrations.

The historical top-level package remains compatible.  New consumers should
prefer this namespace so importing core automation does not eagerly import
hundreds of optional integrations.
"""

from je_auto_control.api.core import (
    FailureBundleOptions,
    create_failure_bundle,
    execute_action,
    execute_action_with_vars,
    generate_code,
    failure_bundle_on_error,
    run_diagnostics,
)

__all__ = [
    "FailureBundleOptions", "create_failure_bundle", "execute_action",
    "execute_action_with_vars", "failure_bundle_on_error", "generate_code",
    "run_diagnostics",
]

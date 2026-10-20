"""Small, versioned entry points for new integrations.

The historical top-level package remains compatible.  New consumers should
prefer this namespace so importing core automation does not eagerly import
hundreds of optional integrations.
"""

# pylint: disable-next=useless-import-alias  # reason: PEP 484 re-exports share core's public list without duplicating it
from je_auto_control.api.core import (
    CancellationToken as CancellationToken,
    TaskProgress as TaskProgress,
    cancellation_scope as cancellation_scope,
    BackendContext as BackendContext,
    CapabilitySnapshot as CapabilitySnapshot,
    CapabilityStatus as CapabilityStatus,
    probe_capabilities as probe_capabilities,
    FailureBundleOptions as FailureBundleOptions,
    create_failure_bundle as create_failure_bundle,
    execute_action as execute_action,
    execute_action_with_vars as execute_action_with_vars,
    generate_code as generate_code,
    failure_bundle_on_error as failure_bundle_on_error,
    run_diagnostics as run_diagnostics,
    __all__ as _CORE_PUBLIC,
)

__all__ = list(_CORE_PUBLIC)

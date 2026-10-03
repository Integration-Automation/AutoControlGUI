"""Retain request authorization and roots for deferred work, with fresh variables."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional, ParamSpec, TypeVar

from je_auto_control.utils.path_guard.policy import (
    PathPolicy, current_path_policy, path_policy_scope,
)
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope, current_authorization,
)
from je_auto_control.utils.script_vars.scope import current_execution_scope, execution_scope

_Params = ParamSpec('_Params')
_Result = TypeVar('_Result')


@dataclass(frozen=True)
class RequestBinding:
    """Server-owned identity and filesystem limits captured at registration."""
    authorization: Optional[AuthorizationContext]
    policy: Optional[PathPolicy]
    variables: Optional[Mapping[str, object]] = None

    @classmethod
    def capture(cls) -> RequestBinding:
        """Capture immutable identity and copy the current policy configuration."""
        policy = current_path_policy()
        copy = None if policy is None else PathPolicy(policy.roots, allowed_env=policy.allowed_env)
        scope = current_execution_scope()
        variables = None if scope is None else scope.fork().as_dict()
        return cls(current_authorization(), copy, variables)

    def run(self, function: Callable[_Params, _Result],
            *args: _Params.args, **kwargs: _Params.kwargs) -> _Result:
        """Run one deferred delivery under its registered limits and a fresh scope."""
        with authorization_scope(self.authorization), path_policy_scope(self.policy):
            with execution_scope(self.variables, isolated=True):
                return function(*args, **kwargs)

"""Bind filesystem resources to the same roots as tool calls per connection."""
from je_auto_control.utils.mcp_server.resources import (
    ChainProvider, FileSystemProvider, ResourceProvider,
)
from je_auto_control.utils.path_guard.policy import PathPolicy


def bounded_resources(provider: ResourceProvider, policy: PathPolicy) -> ResourceProvider:
    """Adapt filesystem providers without changing another client's workspace."""
    if policy.roots is None:
        return provider
    if isinstance(provider, ChainProvider):
        return ChainProvider([bounded_resources(child, policy) for child in provider.providers])
    if isinstance(provider, FileSystemProvider):
        return ChainProvider([FileSystemProvider(str(root), scheme=provider.scheme)
                              for root in policy.roots])
    return provider

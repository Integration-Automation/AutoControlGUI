"""Canonicalise and bound filesystem paths supplied on the command line."""
from je_auto_control.utils.path_guard.path_guard import (
    ALLOWED_ROOTS_ENV, PathNotAllowedError, default_allowed_roots,
    validate_path,
)
from je_auto_control.utils.path_guard.policy import (
    MCP_CLIENT_ROOTS_ENV, MCP_PATH_ROOTS_ENV, PathPolicy,
)

__all__ = [
    "ALLOWED_ROOTS_ENV", "MCP_CLIENT_ROOTS_ENV", "MCP_PATH_ROOTS_ENV",
    "PathNotAllowedError", "PathPolicy", "default_allowed_roots",
    "validate_path",
]

"""Plugin SDK: discover & load third-party AC_* commands via entry points."""
from je_auto_control.utils.plugin_sdk.plugin_sdk import (
    COMMANDS_GROUP, discover_plugins, load_plugins,
)

__all__ = ["COMMANDS_GROUP", "discover_plugins", "load_plugins"]

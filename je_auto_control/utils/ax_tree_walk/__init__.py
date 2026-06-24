"""Readable, addressable accessibility-tree post-processing (role names + node paths)."""
from je_auto_control.utils.ax_tree_walk.ax_tree_walk import (
    assign_node_paths, control_type_name, find_by_path, humanize_role,
    humanize_tree,
)

__all__ = [
    "control_type_name", "humanize_role", "humanize_tree",
    "assign_node_paths", "find_by_path",
]

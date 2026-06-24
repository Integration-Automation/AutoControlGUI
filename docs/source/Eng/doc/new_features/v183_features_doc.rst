Readable, Addressable Accessibility Tree (role names + node paths)
==================================================================

``dump_accessibility_tree`` emits nodes with the platform's *raw* role — on
Windows that is the bare UI Automation ControlType id, e.g. ``"ControlType_50000"``
for a button. That is unreadable, and a serialised dump carries no stable
per-node identity (UIA RuntimeId needs the live element, which the dump has
thrown away). ``ax_tree_walk`` adds the pure, platform-agnostic post-processing
the dump lacks, composable on top of any ``dump_accessibility_tree`` output:

* :func:`control_type_name` / :func:`humanize_role` — translate a ControlType id
  (or ``"ControlType_NNNNN"`` / ``"NNNNN"`` string) to a friendly name,
* :func:`humanize_tree` — a deep copy of the tree with every role humanised,
* :func:`assign_node_paths` — a deep copy stamping each node with a stable
  positional ``path`` (``"0.2.1"``) — a pure stand-in for RuntimeId identity,
* :func:`find_by_path` — resolve a node back from its path.

Pure-stdlib over ``AXTreeNode`` values; no device or backend access. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (dump_accessibility_tree, humanize_tree,
                                 assign_node_paths, find_by_path, humanize_role)

    humanize_role("ControlType_50000")          # "Button"
    humanize_role(50004)                         # "Edit"

    tree = assign_node_paths(humanize_tree(dump_accessibility_tree()))
    # every node now has a readable role and tree["attributes"]["path"]
    node = find_by_path(tree, "0.0.1")           # re-resolve a node by its path

Unknown ids and non-UIA roles (``"AXApplication"``) pass through unchanged, so
nothing is lost. The path is stable for a given tree shape, giving scripts /
agents a deterministic handle to a node across a dump → act round-trip.

Executor commands
-----------------

``AC_walk_tree`` (``app_name`` / ``max_results``) returns the humanised,
path-stamped tree as a nested dict — the readable counterpart to
``AC_a11y_dump``. ``AC_humanize_role`` (``role``) returns ``{"role": ...}``.
Both are exposed as read-only ``ac_*`` MCP tools and as Script Builder commands
under **Native UI**.

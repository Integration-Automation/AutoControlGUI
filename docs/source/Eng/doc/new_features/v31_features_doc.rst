==================================================
New Features (2026-06-19) — Plugin SDK
==================================================

A third-party pip package can now register new ``AC_*`` executor commands
declaratively via a setuptools **entry point** in the
``je_auto_control.commands`` group — turning the monolith into an ecosystem
(how pytest/Playwright grew). AutoControl discovers them at runtime;
discovered commands are immediately usable from JSON action files, the
socket server, the scheduler, and MCP. Pure standard library
(``importlib.metadata``); full stack.

.. contents::
   :local:
   :depth: 2


Authoring a plugin
=================

A plugin package exposes an entry point whose target is a factory returning
a ``{command_name: handler}`` mapping::

    # in the plugin's pyproject.toml
    [project.entry-points."je_auto_control.commands"]
    my_pack = "my_pack.commands:provide"

    # my_pack/commands.py
    def provide():
        return {"AC_my_command": lambda **kw: {"ok": True}}


Discovering & loading
====================

::

    from je_auto_control import discover_plugins, load_plugins

    discover_plugins()      # {command_name: handler} from all plugins
    load_plugins()          # discover + register into the executor

Broken plugins are skipped (logged), not fatal. Exposed as
``AC_list_plugins`` (discover names) / ``AC_load_plugins`` (discover +
register) and ``ac_list_plugins`` / ``ac_load_plugins``. The entry-point
source is injectable, so discovery is unit-testable without installing a
real plugin. This is the declarative, namespaced complement to the existing
runtime path loader.

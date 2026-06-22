====================================================
New Features (2026-06-19) — Authoring & Debugging
====================================================

Two authoring-time tools, pure standard library and wired through the
full stack (facade, ``AC_*`` executor commands, MCP tools, Script
Builder): a native-UI **element repository** (object repository) and a
**step debugger / tracer** for action lists.

.. contents::
   :local:
   :depth: 2


Element repository
=================

Save native-UI locators under friendly names once, reuse them everywhere
— the classic RPA *object repository*. A flow references
``"login.submit"`` instead of repeating ``name="Submit", role="button"``
at every call site, and a UI change is fixed in one place::

    from je_auto_control import ElementRepository

    repo = ElementRepository("app.objects.json")
    repo.save("login.submit", name="Submit", role="button")
    repo.save("login.user", role="edit", app_name="MyApp")

    repo.click("login.submit")          # resolve + click the live element
    info = repo.find_info("login.user")  # {found, name, role, center}

A locator is a small set of accessibility filters (``name`` / ``role`` /
``app_name``); resolving finds the live element through the accessibility
backend. Storage is a JSON file and works on any platform; resolution
needs a platform accessibility backend.

Executor / MCP commands: ``AC_element_save`` / ``AC_element_find`` /
``AC_element_click`` / ``AC_element_remove`` / ``AC_element_list`` (and
the matching ``ac_element_*`` MCP tools).


Step debugger and tracer
=======================

Run an action list one command at a time with breakpoints, single-step,
and live variable inspection. Stepping reuses one executor instance, so
script variables (``${name}`` interpolation, ``AC_set_var`` …) persist
across steps exactly as in a normal run::

    from je_auto_control import FlowDebugger

    dbg = FlowDebugger(actions, breakpoints=[3])
    dbg.continue_()          # run until the breakpoint
    dbg.variables()          # inspect live variables
    dbg.step()               # one command at a time
    dbg.run_to_end()

The stateless one-shot form, :func:`trace_actions`, runs a list (or
``dry_run`` to only plan it) and returns a per-step trace of
``{index, command, result}`` — exposed as ``AC_debug_trace`` /
``ac_debug_trace``::

    from je_auto_control import trace_actions

    plan = trace_actions(actions, dry_run=True)   # plan without running
    trace = trace_actions(actions)                # run and trace

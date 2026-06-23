Window Z-Order — Always-On-Top / Front / Back
=============================================

``windows_window_manage.set_window_position`` exists at the raw Win32 layer but is not
exported in the package facade, has no title-based wrapper, and no topmost / not-topmost
semantics — and there was no ``always_on_top`` anywhere outside GUI overlay code. This
adds the standard RPA z-order primitive: a pure ``plan_zorder`` that maps an action to
the ``SetWindowPos`` insert-after constant, plus title-based ``set_topmost`` /
``bring_to_front`` / ``send_to_back`` over an injectable driver (the same seam pattern
as ``snap_window``).

The planning is pure and headless-testable; only the default driver touches Win32
(returning ``False`` on other platforms). Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (set_topmost, bring_to_front, send_to_back,
                                 plan_zorder)

    set_topmost("Media Player")          # pin always-on-top
    set_topmost("Media Player", False)   # release
    bring_to_front("Editor")
    send_to_back("Background Monitor")

    plan_zorder("topmost")["insert_after"]   # -1 (HWND_TOPMOST), pure / testable

``plan_zorder(action)`` (``top`` / ``bottom`` / ``topmost`` / ``notopmost``) returns the
``SetWindowPos`` descriptor (``insert_after`` constant + ``SWP_NOMOVE`` / ``SWP_NOSIZE``
flags); unknown actions raise ``ValueError``. ``set_topmost`` / ``bring_to_front`` /
``send_to_back`` resolve the window by title and apply the action through the default
Win32 driver (or an injected one in tests), returning whether it was applied.

Executor commands
-----------------

``AC_set_topmost`` (``title`` / ``on`` → ``{applied}``), ``AC_bring_to_front`` and
``AC_send_to_back`` (``title`` → ``{applied}``). They are exposed as the MCP tools
``ac_set_topmost`` / ``ac_bring_to_front`` / ``ac_send_to_back`` and as Script Builder
commands under **Window**.

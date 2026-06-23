Canonical Computer-Use Action Schema
====================================

``tool_use_schema`` exports the AC_* command *signatures* as tool definitions and
``coordinate_space`` rescales a model grid — but neither *normalizes an inbound action
payload*. Anthropic's computer-use tool emits ``{action:"left_click",
coordinate:[x,y]}``, OpenAI's CUA emits ``{type:"click", x, y, button}`` — there was no
adapter mapping these heterogeneous shapes onto a canonical action and then onto a
runnable AC_* command, so integrators hand-wrote the glue.

Pure-stdlib dict mapping (an optional ``scale`` callable applies coordinate-space
rescaling), fully headless-testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (from_anthropic, from_openai_cua, to_ac_command,
                                 canonical_action)

    # Anthropic agent output -> canonical -> runnable AC action.
    canonical = from_anthropic({"action": "left_click", "coordinate": [120, 80]})
    command = to_ac_command(canonical)
    # -> ["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 120, "y": 80}]

    # OpenAI CUA, with model->physical coordinate rescaling.
    cmd = to_ac_command(from_openai_cua({"type": "scroll", "x": 5, "y": 6,
                                         "scroll_y": 120}),
                        scale=lambda x, y: (x * 2, y * 2))

``from_anthropic`` / ``from_openai_cua`` map each provider's payload to a canonical
``{type, x, y, text, …}`` (clicks, double/right/middle click, move, type, key, scroll,
screenshot). ``to_ac_command`` maps a canonical action to a ``[command_name, params]``
AC action (``AC_click_mouse`` / ``AC_set_mouse_position`` / ``AC_write`` / ``AC_hotkey``
/ ``AC_mouse_scroll`` / ``AC_screenshot``), applying ``scale`` to coordinates; an
unmapped type raises ``AutoControlActionException``. ``canonical_action`` builds a
canonical dict directly.

Executor command
----------------

``AC_cua_command`` normalizes a ``payload`` from ``source`` (``anthropic`` / ``openai``
/ ``canonical``) and returns ``{canonical, command}``. It is exposed as the MCP tool
``ac_cua_command`` and as a Script Builder command under **Native UI**.

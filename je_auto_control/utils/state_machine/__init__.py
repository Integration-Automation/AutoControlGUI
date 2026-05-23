"""Phase 7.2: declarative finite-state-machine driver for action JSON.

Existing flow control (``AC_loop``, ``AC_if_var``, ``AC_for_each``) is
imperative — fine for short scripts but awkward for longer flows with
many decision points (login → 2FA → success vs. retry → error popup
vs. captcha). This module adds a small FSM engine that consumes a
declarative spec::

    {"initial": "login",
     "states": {
         "login": {"on_enter": [...AC actions...],
                   "transitions": [
                       {"if_image_found": "welcome.png", "go_to": "done"},
                       {"if_image_found": "captcha.png", "go_to": "captcha"},
                       {"after": 5, "go_to": "retry_login"}
                   ]},
         "captcha": {...},
         "retry_login": {...},
         "done": {"final": true}
     },
     "max_steps": 50,
     "global_timeout_s": 120
    }

Each state has:
  * ``on_enter`` — list of AC actions to execute when the FSM enters
  * ``transitions`` — ordered list of guards; first match wins
  * ``final`` — when ``true``, the FSM stops with success
  * ``retry`` — ``{max: N, backoff_s: 2.0}`` retry on action failure

The engine is headless; the GUI script-builder wraps it via a new
``AC_state_machine`` command.
"""
from je_auto_control.utils.state_machine.engine import (
    StateMachine, StateMachineError, run_state_machine,
)

__all__ = ["StateMachine", "StateMachineError", "run_state_machine"]

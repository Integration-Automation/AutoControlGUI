"""Phase 7.7: bridge AutoControl action JSON over to WebRunner (``je_web_runner``).

The sister project at https://github.com/Integration-Automation/WebRunner
exposes its ``WR_*`` commands for Selenium / Playwright browser
automation. This bridge lets an AutoControl script call into those
commands from the same JSON file by issuing ``AC_web_run`` /
``AC_web_run_actions``::

    [
        ["AC_web_run", {"action": "WR_new_driver",
                        "params": {"webdriver_name": "chrome"}}],
        ["AC_web_run", {"action": "WR_to_url",
                        "params": {"url": "https://example.com"}}],
        ["AC_screenshot", {"file_path": "after-load.png"}],
        ["AC_web_run", {"action": "WR_quit"}]
    ]

Each command runs through WebRunner's ``execute_one`` (its command gates,
retry policy and failure screenshots) when the installed WebRunner has it.
A failing command raises :class:`WebRunnerBridgeError`, which the executor
records like any other failed action.

WebRunner is **optional**: :func:`is_webrunner_available` returns False
when the package isn't installed (it looks the package up without
importing it) and the AC_web_* commands raise a clear
``WebRunnerBridgeError`` instead of a confusing ImportError.
"""
from je_auto_control.utils.webrunner_bridge.bridge import (
    WebRunnerBridgeError, is_webrunner_available, list_webrunner_commands,
    run_webrunner_action, run_webrunner_actions, web_current_url,
    web_open, web_quit, web_screenshot,
)

__all__ = [
    "WebRunnerBridgeError", "is_webrunner_available",
    "list_webrunner_commands", "run_webrunner_action",
    "run_webrunner_actions", "web_current_url", "web_open",
    "web_quit", "web_screenshot",
]

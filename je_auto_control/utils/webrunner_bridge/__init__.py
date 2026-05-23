"""Phase 7.7: bridge AutoControl action JSON over to WebRunner (``je_web_runner``).

The sister project at https://github.com/Intergration-Automation-Testing/WebRunner
exposes ~440 ``WR_*`` commands for Selenium / Playwright browser
automation. This bridge lets an AutoControl script call into those
commands from the same JSON file by issuing ``AC_web_run`` /
``AC_web_run_actions``::

    [
        ["AC_web_run", {"action": "WR_new_driver",
                        "params": {"browser": "chrome"}}],
        ["AC_web_run", {"action": "WR_get_url",
                        "params": {"url": "https://example.com"}}],
        ["AC_screenshot", {"file_path": "after-load.png"}],
        ["AC_web_run", {"action": "WR_quit"}]
    ]

WebRunner is **optional**: :func:`is_webrunner_available` returns False
when the package isn't installed and the AC_web_* commands raise a
clear ``RuntimeError`` instead of a confusing ImportError.
"""
from je_auto_control.utils.webrunner_bridge.bridge import (
    WebRunnerBridgeError, is_webrunner_available, list_webrunner_commands,
    run_webrunner_action, run_webrunner_actions,
)

__all__ = [
    "WebRunnerBridgeError", "is_webrunner_available",
    "list_webrunner_commands", "run_webrunner_action",
    "run_webrunner_actions",
]

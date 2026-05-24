"""pytest plugin + BDD step library for AutoControl.

Two integration points::

    # 1. As a pytest plugin (automatic when je_auto_control is installed
    # via the [project.entry-points."pytest11"] entry in pyproject.toml,
    # or explicitly via conftest.py):
    pytest_plugins = ["je_auto_control.utils.pytest_plugin"]

    # 2. As Gherkin step definitions (pytest-bdd or behave):
    from je_auto_control.utils.pytest_plugin import bdd_steps
    bdd_steps.register_pytest_bdd_steps(__import__("pytest_bdd"))
"""
from je_auto_control.utils.pytest_plugin.keywords import (
    keyword_click_image, keyword_press_key, keyword_screen_size,
    keyword_screenshot, keyword_type_text, keyword_wait_for_image,
    keyword_wait_for_text,
)
from je_auto_control.utils.pytest_plugin.plugin import (
    autocontrol, autocontrol_executor, autocontrol_screenshot_dir,
    pytest_configure, pytest_runtest_makereport,
)
from je_auto_control.utils.pytest_plugin import bdd_steps


__all__ = [
    "autocontrol", "autocontrol_executor", "autocontrol_screenshot_dir",
    "bdd_steps", "keyword_click_image", "keyword_press_key",
    "keyword_screen_size", "keyword_screenshot", "keyword_type_text",
    "keyword_wait_for_image", "keyword_wait_for_text",
    "pytest_configure", "pytest_runtest_makereport",
]

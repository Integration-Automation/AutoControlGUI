"""Drive AutoControl from pytest + pytest-bdd.

The pytest plugin ships with the package — installing
``je_auto_control`` registers an entry-point so the plugin loads
automatically. The fixtures it provides::

    autocontrol                 # the je_auto_control module
    autocontrol_executor        # the executor singleton
    autocontrol_screenshot_dir  # per-test directory under tmp_path

Marking a test with ``@pytest.mark.autocontrol`` arms the
screenshot-on-failure hook — the plugin writes ``<nodeid>.png`` into
``autocontrol_screenshot_dir`` and attaches the path to the failure
report. Example::

    import pytest

    @pytest.mark.autocontrol
    def test_login_flow(autocontrol):
        autocontrol.write("admin")
        autocontrol.type_keyboard("tab")
        autocontrol.write("secret")
        autocontrol.type_keyboard("enter")

For Gherkin tests, register the bundled step definitions once and
write the .feature file:

    # conftest.py
    import pytest_bdd
    from je_auto_control.utils.pytest_plugin import bdd_steps
    bdd_steps.register_pytest_bdd_steps(pytest_bdd)

    # features/login.feature
    Feature: Sign in to the corporate dashboard
      Scenario: a valid user signs in
        Given AutoControl is ready
        When I click on image "username_field.png"
        And I type "admin"
        And I press "tab"
        And I type "secret"
        And I press "enter"
        Then I see image "dashboard_banner.png"

Run with pytest like any other suite. Failure artefacts land in the
per-test ``autocontrol_screenshot_dir``.

This script is a *demo of the demo* — it just prints the registered
keywords + step templates so you can confirm everything is wired
without actually launching a GUI test session.
"""
from je_auto_control.utils.pytest_plugin import bdd_steps, keywords


def main() -> None:
    print("Registered keyword helpers:")
    for name in (
        "keyword_click_image", "keyword_type_text", "keyword_press_key",
        "keyword_screenshot", "keyword_screen_size",
        "keyword_wait_for_image", "keyword_wait_for_text",
    ):
        function = getattr(keywords, name)
        print(f"  {name}{function.__doc__ and '  — ' + function.__doc__.splitlines()[0]}")

    print("\nGherkin step templates (pytest-bdd / behave):")
    print('  Given AutoControl is ready')
    print('  When  I type "<text>"')
    print('  When  I press "<keycode>"')
    print('  When  I click on image "<path>"')
    print('  When  I take a screenshot to "<path>"')
    print('  Then  I see image "<path>"')
    print('  Then  I see text "<text>"')
    print('  Then  the screen size is <width>x<height>')

    # No-op when behave is not installed.
    bdd_steps.register_behave_steps()


if __name__ == "__main__":
    main()

"""Drive WebRunner (browser automation) from an AutoControl script.

Requires ``pip install je_web_runner`` plus the matching browser
driver (chromedriver / geckodriver / msedgedriver).

Two ways to call:

1. Convenience helpers — one-shot login / screenshot flows::

       je_auto_control.web_open("https://example.com")
       je_auto_control.web_screenshot("loaded.png")
       je_auto_control.web_quit()

2. Bridge mode — any of WebRunner's ~440 ``WR_*`` commands by name,
   so JSON action files (and the scheduler / triggers / MCP) can
   compose browser actions with native UI automation::

       je_auto_control.execute_action([
           ["AC_web_open", {"url": "https://example.com"}],
           ["AC_web_run", {"action": "WR_left_click",
                             "params": {"element_name": "#submit"}}],
           ["AC_screenshot", {"file_path": "after-click.png"}],
           ["AC_web_quit", {}],
       ])
"""
import je_auto_control as ac


def main() -> None:
    if not ac.is_webrunner_available():
        print("je_web_runner is not installed — skipping.")
        return

    ac.web_open("https://example.com", browser="chrome")
    print("current URL:", ac.web_current_url())
    ac.web_screenshot("example.png")
    ac.web_quit()


if __name__ == "__main__":
    main()

"""Stand up a Slack chat-ops bot for AutoControl.

The router takes inbound chat lines and dispatches them through the
default command set::

    /help                    list every registered command
    /scripts                 list .json scripts under ``script_root``
    /run <script-name>       execute one of those scripts
    /screenshot [path]       capture the screen, reply with the saved path
    /status                  show the last 5 runs from the run-history store

Register your own commands by calling ``router.register("deploy", …)``
before starting the bot.

Required environment for the live demo:

* ``SLACK_BOT_TOKEN`` — bot token (``xoxb-…``) with
  ``channels:history``, ``chat:write``, and ``auth.test`` scopes.
* ``SLACK_CHANNEL_ID`` — channel the bot listens on.
* ``JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT`` — directory of .json scripts.

When the env vars are missing the script demonstrates the router
locally by dispatching a few canned messages.
"""
import os
from pathlib import Path

from je_auto_control import (
    CommandRouter, make_default_slack_bot,
    register_chatops_default_commands,
)


def _local_demo() -> None:
    print("Running the router locally — set SLACK_BOT_TOKEN to go live.")
    root = Path("./scripts")
    root.mkdir(exist_ok=True)
    (root / "demo.json").write_text("[]", encoding="utf-8")

    router = CommandRouter()
    register_chatops_default_commands(router)

    for message in ("/help", "/scripts", "/garbage"):
        result = router.dispatch(message, context={"script_root": str(root)})
        prefix = "✓" if result and result.succeeded else "✗"
        print(f"{prefix} {message!r} → {result.text if result else '(no match)'}")


def main() -> None:
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    script_root = os.environ.get("JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT")
    if not (token and channel):
        _local_demo()
        return
    bot = make_default_slack_bot(
        token=token, channel_id=channel, script_root=script_root,
    )
    print(f"Listening on {channel} — Ctrl-C to stop.")
    try:
        bot.run_forever()
    except KeyboardInterrupt:
        bot.stop()


if __name__ == "__main__":
    main()

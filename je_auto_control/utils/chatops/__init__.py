"""Chat-ops bot: receive slash commands from Slack / Discord / webhooks
and dispatch them through AutoControl's headless API.

Public surface::

    from je_auto_control import (
        CommandRouter, ChatOpsError, CommandResult,
        register_chatops_default_commands, SlackBot, make_default_slack_bot,
    )

Compose your own:

    router = CommandRouter()
    register_chatops_default_commands(router)
    bot = SlackBot(token=..., channel_id=..., router=router)
    bot.run_forever()
"""
from je_auto_control.utils.chatops.handlers import (
    cmd_run, cmd_screenshot, cmd_scripts, cmd_status,
    register_default_commands as register_chatops_default_commands,
)
from je_auto_control.utils.chatops.router import (
    ChatOpsError, CommandHandler, CommandResult, CommandRouter,
    CommandSpec,
)
from je_auto_control.utils.chatops.slack_bot import (
    SlackBot, SlackError, make_default_slack_bot,
)


__all__ = [
    "ChatOpsError", "CommandHandler", "CommandResult", "CommandRouter",
    "CommandSpec", "SlackBot", "SlackError",
    "cmd_run", "cmd_screenshot", "cmd_scripts", "cmd_status",
    "make_default_slack_bot", "register_chatops_default_commands",
]

Multi-Channel Webhook Notifications
===================================

The built-in ``notify`` is desktop-toast only, and ChatOps shipped Slack as the
only transport — but unattended runs want to alert Microsoft Teams, Discord, or a
generic incoming webhook too. Each is a simple JSON POST with a transport-shaped
payload (Slack and a Teams MessageCard use ``text``, Discord uses ``content``);
``notify_webhook`` builds the right body and POSTs it through the egress-guarded
HTTP client.

The transport is injectable (a ``poster`` callable or a module-level default),
so sending is unit-testable with no network. Pure standard library; imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import notify_webhook, WebhookChannel

    notify_webhook("https://hooks.slack.com/...", "Run finished", transport="slack")
    notify_webhook("https://discord.com/api/webhooks/...", "Build broke",
                   transport="discord", title="CI")
    notify_webhook("https://prod.webhook.office.com/...", "Deploy done",
                   transport="teams", title="Release")

    chan = WebhookChannel("https://hooks.example.com/x", transport="raw")
    result = chan.send("hello")          # -> WebhookResult(ok, status, transport)

``transport`` is ``slack`` / ``discord`` / ``teams`` / ``raw``; the result's
``ok`` reflects a 2xx status. Pass a ``poster(url, payload) -> status`` to
``WebhookChannel`` / ``notify_webhook`` (or install one with
``set_default_poster``) to route through a custom transport or a test fake.

Executor command
----------------

``AC_notify_webhook`` takes ``url``, ``text`` (+ optional ``transport`` /
``title``) and returns ``{ok, status, transport}``. The same operation is exposed
as the MCP tool ``ac_notify_webhook`` and as a Script Builder command under
**Tools**.

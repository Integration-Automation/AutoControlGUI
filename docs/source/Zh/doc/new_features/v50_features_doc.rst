多通道 Webhook 通知
===================

內建的 ``notify`` 僅限桌面快顯,而 ChatOps 只內建 Slack 一種傳輸 —— 但無人值守的執行也
想通知 Microsoft Teams、Discord 或一般的 incoming webhook。每一種都是簡單的 JSON POST,
搭配對應傳輸的酬載結構(Slack 與 Teams MessageCard 用 ``text``,Discord 用
``content``);``notify_webhook`` 會組出正確的本文,並透過受出口守衛保護的 HTTP 用戶端
POST 出去。

傳輸可注入(``poster`` 可呼叫物件或模組層級預設),因此發送在無網路下即可單元測試。純標
準函式庫;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import notify_webhook, WebhookChannel

    notify_webhook("https://hooks.slack.com/...", "Run finished", transport="slack")
    notify_webhook("https://discord.com/api/webhooks/...", "Build broke",
                   transport="discord", title="CI")
    notify_webhook("https://prod.webhook.office.com/...", "Deploy done",
                   transport="teams", title="Release")

    chan = WebhookChannel("https://hooks.example.com/x", transport="raw")
    result = chan.send("hello")          # -> WebhookResult(ok, status, transport)

``transport`` 為 ``slack`` / ``discord`` / ``teams`` / ``raw``;結果的 ``ok`` 反映 2xx 狀
態。可傳入 ``poster(url, payload) -> status`` 給 ``WebhookChannel`` / ``notify_webhook``
(或以 ``set_default_poster`` 安裝一個)以走自訂傳輸或測試假物件。

執行器指令
----------

``AC_notify_webhook`` 接受 ``url``、``text``(以及選用的 ``transport`` / ``title``),回傳
``{ok, status, transport}``。相同操作亦提供為 MCP 工具 ``ac_notify_webhook``,以及 Script
Builder 中 **Tools** 分類下的指令。

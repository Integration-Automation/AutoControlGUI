對外 CloudEvents 發送器
=======================

AutoControl 能*接收* webhook,但一直無法*對外發送*事件。CloudEvents 1.0(CNCF)是事件
酬載的互通標準 —— Knative、Azure Event Grid、iPaaS 與一般 webhook 消費端皆採用。本功能
將執行生命週期 / 斷言 / 失敗資料包進 CloudEvents 信封,並(選擇性地)透過 HTTP binding
POST 出去,重用框架的出口允許清單守衛。

傳輸可注入(``sink`` / ``poster`` 可呼叫物件),因此發送在無網路下即可單元測試。純標準函
式庫;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import to_cloudevent, post_cloudevent, EventEmitter

    event = to_cloudevent("com.example.run.finished", "/runs/42",
                          {"status": "passed"}, subject="run-42")
    # -> {specversion, id, source, type, time, datacontenttype, subject, data}

    post_cloudevent("https://hooks.example.com/ce", event)   # 受出口守衛保護的 POST

    emitter = EventEmitter(source="je_auto_control")
    emitter.emit("run.started", {"flow": "checkout"})
    emitter.events                                           #擷取到的信封

``to_cloudevent`` 會自動填入 ``specversion`` / ``id``(新的 UUID)/ ``time``(現在,
UTC);可傳 ``event_id`` / ``time`` 覆寫。``EventEmitter`` 綁定固定的 ``source`` 並將每個
信封派送到 ``sink``(預設為記憶體內日誌 —— 可注入自己的以轉發到匯流排)。
``post_cloudevent`` 接受 ``poster`` 以在測試中注入傳輸。

執行器指令
----------

``AC_emit_event`` 接受 ``event_type``(以及選用的 ``data`` / ``source`` / ``subject`` /
``url``);回傳 ``{event}``,當提供 ``url`` 時於 POST 後回傳 ``{event, status}``。相同操作
亦提供為 MCP 工具 ``ac_emit_event``,以及 Script Builder 中 **Tools** 分類下的指令。

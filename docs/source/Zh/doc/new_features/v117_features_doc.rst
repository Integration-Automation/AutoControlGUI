清空再輸入欄位
==============

可靠地設定欄位值,必須先*清空*既有內容再輸入新文字——否則自動化會附加到或破壞既有內容。框架分別有 ``write``
(可輸入,但對 emoji / CJK / 不在版面表內的字元會拋例外)與 ``set_clipboard`` / ``hotkey``,但沒有單一的
「聚焦 → 清空 → 設值」基本元件,也沒有可輸入 ``write`` 無法處理之文字的貼上策略。本功能加入 Playwright 的
``fill`` 慣用法。

:func:`plan_field_set` 建立決定性的操作計畫(純函式、可單元測試);:func:`set_field_text` 透過可注入的 ``sink``
派發,因此可在無真實輸入下測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import set_field_text, plan_field_set

    set_field_text("new value")                       # 全選、刪除、輸入
    set_field_text("café 🚀", paste=True)             # 透過剪貼簿(Unicode 安全)
    set_field_text("appended", clear="none")          # 不清空,直接輸入
    set_field_text("値", paste=True, modifier="command")   # macOS

    plan_field_set("hi")
    # [{'op': 'hotkey', 'keys': ['ctrl', 'a']},
    #  {'op': 'key', 'key': 'delete'},
    #  {'op': 'type', 'text': 'hi'}]

``clear`` 為 ``"select_all"``(``modifier``+A 再 Delete 的清空)或 ``"none"``。``paste=True`` 透過剪貼簿
(``modifier``+V)輸入文字——這是 ``write`` 無法輸入之 Unicode / emoji / CJK 的可靠途徑——而非逐鍵輸入。
``modifier`` 為平台指令鍵(``"ctrl"``;macOS 用 ``"command"``)。未知的 ``clear`` 模式會拋出 ``ValueError``。

執行器命令
----------

``AC_set_field_text`` 接受 ``text`` 以及 ``clear`` / ``paste`` / ``modifier``,並回傳 ``{ops, plan}``。它以
MCP 工具 ``ac_set_field_text`` 以及 Script Builder 中 **Keyboard** 分類下的命令提供。

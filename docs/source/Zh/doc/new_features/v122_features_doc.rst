Unicode 文字輸入(emoji / CJK)
==============================

``write`` 透過平台虛擬鍵表輸入,對任何不在表內的字元會*拋例外*——emoji、CJK、許多重音字母——因此無法以正常
途徑輸入非 ASCII 文字。可靠的跨平台輸入任意 Unicode 的方法,是將其放上剪貼簿再貼上。

:func:`plan_paste` 建立決定性操作計畫,:func:`unicode_code_units` 將文字拆成 UTF-16 碼元(供能做
``KEYEVENTF_UNICODE`` 的後端使用);兩者皆為純函式、可單元測試。:func:`type_unicode` 透過可注入的 ``sink``
派發貼上計畫,因此可在不觸碰真實剪貼簿下測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import type_unicode, plan_paste, unicode_code_units

    type_unicode("café 🚀 値")              # 設定剪貼簿 + Ctrl+V
    type_unicode("値", modifier="command")  # macOS

    unicode_code_units("🚀")               # [0xD83D, 0xDE80](代理對)
    plan_paste("hi")
    # [{'op': 'set_clipboard', 'text': 'hi'},
    #  {'op': 'hotkey', 'keys': ['ctrl', 'v']}]

``type_unicode`` 將剪貼簿設為該文字並送出貼上熱鍵(``modifier`` 預設 ``"ctrl"``;macOS 用 ``"command"``),
因此無論鍵盤配置都能輸入*任何*文字——emoji、CJK、RTL、重音。它回傳派發的計畫加上 UTF-16 碼元數。
``unicode_code_units`` 供想直接注入碼元的後端使用。

執行器命令
----------

``AC_type_unicode`` 接受 ``text`` 與選用的 ``modifier``,並回傳 ``{ops, plan, code_units}``。它以 MCP 工具
``ac_type_unicode`` 以及 Script Builder 中 **Keyboard** 分類下的命令提供。

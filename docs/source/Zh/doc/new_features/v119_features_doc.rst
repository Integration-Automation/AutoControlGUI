按住按鍵 / 自動重複
==================

``type_keyboard`` 是瞬間的按下+放開,``input_macro.run_sequence`` 雖可手動拼出按下 / 等待 / 放開,但先前沒有
「按住此鍵 N 秒」(遊戲移動、按住捲動)或「每秒送 R 次」(自動重複)的基本元件。

:func:`plan_key_hold` 建立決定性的操作計畫(純函式、可單元測試);:func:`hold_key` 透過可注入的 ``sink``
與 ``sleep`` 派發,因此可在無真實輸入、無真實等待下測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import hold_key, plan_key_hold

    hold_key("key_d", duration_s=1.5)              # 按下、按住 1.5 秒、放開
    hold_key("key_down", duration_s=2.0, rate_hz=20)   # 40 個按鍵事件 @ 50ms

    plan_key_hold("space", 1.0)
    # [{'op': 'press', 'key': 'space'},
    #  {'op': 'wait', 'seconds': 1.0},
    #  {'op': 'release', 'key': 'space'}]

未設定 ``rate_hz`` 時,鍵會被按下、按住 ``duration_s``、再放開。設定 ``rate_hz`` 時,會送出
``round(duration_s * rate_hz)`` 個相隔 ``1 / rate_hz`` 的離散按鍵事件——用於移動 / 捲動迴圈的模擬自動重複。
非正數的時長或頻率會拋出 ``ValueError``。``hold_key`` 將 ``wait`` 步驟導向 ``sleep``、按鍵步驟導向 ``sink``,
兩者皆可注入。

執行器命令
----------

``AC_hold_key`` 接受 ``key`` 以及 ``duration_s`` 與選用的 ``rate_hz``,並回傳 ``{ops, plan}``。它以 MCP 工具
``ac_hold_key`` 以及 Script Builder 中 **Keyboard** 分類下的命令提供。

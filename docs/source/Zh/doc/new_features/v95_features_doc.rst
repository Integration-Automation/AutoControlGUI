具型別的設定結構
==============

``assets._coerce`` 只轉換單一值,``json_schema`` 只驗證 JSON 結構,但沒有任何東西能把已解析的設定 dict
綁定成具型別的物件,並做必填欄位強制與選項約束。本功能依宣告的欄位驗證一個 mapping,轉換型別並回報可
據以行動的錯誤 —— 標準函式庫版的 pydantic-settings。

純標準函式庫(``dataclasses``);不匯入 ``PySide6``。驗證為純函式(輸入 mapping、輸出報告),因此在 CI
中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import ConfigSchema, ConfigField, validate_config

    schema = ConfigSchema({
        "port": ConfigField("int", required=True),
        "env": ConfigField("str", default="dev", choices=["dev", "prod"]),
        "debug": ConfigField("bool", default=False),
    })
    report = schema.validate({"port": "8080", "debug": "yes"})
    # {"ok": True, "config": {"port": 8080, "env": "dev", "debug": True}, "errors": []}

``ConfigField`` 宣告 ``type``(``str`` / ``int`` / ``float`` / ``bool``)、選用的 ``default``、``required``
旗標、``choices`` 與 ``env`` 提示。``ConfigSchema.validate`` 轉換每個存在的值、套用預設、強制必填與選項,
回傳 ``{ok, config, errors}``(錯誤為 ``{field, error}``)。``ConfigSchema.from_dict`` 從純 spec 建立結構,
``validate_config`` 一次完成 spec 加 mapping,``coerce`` 公開值轉換(布林接受 ``true``/``yes``/``on`` 等)。

執行器命令
----------

``AC_validate_config`` 依 ``schema`` spec 驗證 ``config`` mapping,回傳 ``{ok, config, errors}``。它以 MCP
工具 ``ac_validate_config`` 以及 Script Builder 中 **Data** 分類下的命令提供。

設定與日誌的機密遮蔽
==================

``utils/redaction`` 只會模糊 PIL 截圖,``secrets_scan`` 只會*偵測*並回報發現 —— 兩者都不會回傳一份對
日誌、報告或 ``config_bundle`` 匯出而言安全的、已遮蔽的設定 dict 或字串副本。本功能重用 ``secrets_scan``
偵測器來產生遮蔽後的副本。

純標準函式庫(``re`` + 重用 ``secrets_scan``);不匯入 ``PySide6``。每個函式皆為純函式(輸入資料、輸出
遮蔽副本),因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import redact_config, redact_secret_text

    safe = redact_config({"db": {"password": secret}, "name": "alice"})
    # {"db": {"password": "***"}, "name": "alice"}

    line = redact_secret_text(f"auth failed for token {token}")
    # "auth failed for token ***"

``redact_config`` 回傳巢狀結構的深層副本,並遮蔽看似機密的值,重用 ``secrets_scan``(鍵名模式如
``password`` / ``api_key``、已知值格式如 AWS 金鑰與 bearer token,以及高熵字串);已經參照 vault 的值
(``${secrets.*}``)保持不變。``redact_secret_text`` 遮蔽自由文字字串(日誌行)中看似機密的 token,同時
保留周圍的文字與空白。兩者皆接受自訂 ``mask``(預設 ``"***"``)。此函式命名為 ``redact_secret_text`` 以
與處理 prompt-injection 的 ``guardrail.redact_text`` 區分。

執行器命令
----------

``AC_redact_config`` 對 ``obj``(可為 JSON)回傳 ``{redacted}``;``AC_redact_secret_text`` 回傳
``{text}``。兩者皆接受選用的 ``mask``,並以 MCP 工具(``ac_redact_config`` / ``ac_redact_secret_text``)
以及 Script Builder 中 **Security** 分類下的命令提供。

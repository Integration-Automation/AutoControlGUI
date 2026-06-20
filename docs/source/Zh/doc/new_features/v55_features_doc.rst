文字 PII 偵測與遮蔽
==================

影像遮蔽模組會在螢幕截圖中模糊 PII,但從 UI、OCR、剪貼簿、LLM 提示/回應或日誌行擷取的
*文字*卻沒有字串層級的對應 —— 因此 PII 可能洩漏進動作紀錄、稽核日誌或一次模型呼叫。
``detect_pii`` / ``redact_pii_text`` 可在純文字上找出並遮蔽電子郵件、電話號碼、SSN、信
用卡號、IPv4 位址與 IBAN。

樣式刻意保持簡單(無巢狀量詞 → 無災難性回溯)。純標準函式庫(``re`` + ``hashlib``);不匯
入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import detect_pii, redact_pii_text

    detect_pii("mail a@b.com, ip 10.0.0.1")
    # -> [PIIFinding(kind='email', value='a@b.com', start=5, end=12), ...]

    redact_pii_text("contact a@b.com")                    # -> "contact [email]"
    redact_pii_text("a@b.com", mode="mask")               # -> "*******"
    redact_pii_text("4111111111111111", mode="partial")   # -> "************1111"
    redact_pii_text("a@b.com", mode="hash")               # -> "[email:fb98d44a]"

    detect_pii(text, kinds=["email", "phone"])            # 限定偵測器

``detect_pii`` 回傳依位置排序、互不重疊的結果(較前、再較長的匹配勝出 —— 因此信用卡號不
會同時被標記為電話)。``redact_pii_text`` 模式:``label``(``[email]``)、``mask``
(``****``)、``partial``(保留末 4 碼)、``hash``(``[email:<digest>]``)。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_detect_pii``                ``{findings}`` —— 文字中的 PII 區段。
``AC_redact_pii``                ``{text}`` —— 已遮蔽 PII 的文字。
================================ ===================================================

``kinds`` 接受清單或 JSON 字串清單。相同操作亦提供為 MCP 工具(``ac_detect_pii`` /
``ac_redact_pii``),以及 Script Builder 中 **Data** 分類下的指令。

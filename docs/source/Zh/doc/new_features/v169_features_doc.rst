宣告式動作後置條件
==================

動作之後,代理(或重播框架)通常有具體的預期:「應出現寫著『Saved』的對話框,且 Submit
按鈕應停用」。``expect_poll`` / ``assert_eventually`` 輪詢*單一條件*,卻沒有與動作綁定的
*後置條件規格*概念,也不對照 *before* 基準做差異(因此無法表達「一個*新*對話框出現了」
——只能表達「存在對話框」)。``trajectory_eval`` 的評分準則是整條軌跡層級,而非每步畫面
狀態。``postcondition`` 補上這個缺口:用一個小型 JSON 子句規格,對照 after 觀測(可選擇與
before 觀測做差異)評估,回傳逐子句的通過 / 失敗報告。

子句:``appears`` / ``disappears``(對照 ``before``)、``enabled`` / ``disabled``、
``text_present`` / ``text_absent``,以及 ``count``(``equals`` / ``min``)。純標準函式庫,
作用於元素字典;規格為純 JSON,可帶入 action 檔 / MCP / 排程器。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import check_postcondition, compile_postcondition

    spec = {"appears": {"role": "dialog", "name": "Saved"},
            "disabled": {"name": "Submit"}}
    report = check_postcondition(after_elements, spec, before=before_elements)
    if not report.ok:
        print("失敗子句:", report.failed)

    # 把規格轉成判定函式以驅動 expect_poll
    predicate = compile_postcondition({"text_present": "Saved"})

``check_postcondition`` 回傳 ``PostconditionReport``(``ok`` / ``clauses`` —
``[{type, ok, detail}]`` — / ``failed``)。``appears`` 只有在元素位於 ``after`` 且*不*在
``before``(確為新元素)時才成功;``disappears`` 需要 ``before`` 幀。``compile_postcondition``
回傳 ``after -> bool`` 判定函式,可與 ``expect_poll`` / ``assert_eventually`` 搭配。

執行器指令
----------

``AC_check_postcondition``(``after`` / ``spec`` / ``before`` → ``{ok, clauses, failed}``)
以 MCP 工具 ``ac_check_postcondition``(唯讀)及 Script Builder 指令 **Check Postcondition**
(位於 **Native UI** 分類下)形式提供。

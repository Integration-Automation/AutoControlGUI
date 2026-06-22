核准式測試(Golden-Master 基準)
================================

核准式測試(又稱 golden-master / snapshot 測試)把「這個輸出還正確嗎?」重新表述為
「它是否仍與人工核准過的版本相符?」。:func:`verify_artifact` 將產出的內容與儲存的
``<name>.approved.<ext>`` 基準比對:

* **相符** → 檢查通過;
* **不符或缺少基準** → 產出的位元組會被寫入 ``<name>.received.<ext>`` 且檢查失敗,讓
  審查者可比對兩者,若變更為預期,即以 :func:`approve_artifact` 晉升。

它適用於*任何*產物 —— 渲染後的文字、JSON、OCR 輸出、螢幕截圖位元組 —— 因此以一個受
審查把關、與測試一起提交的基準,補強逐像素比對。純標準函式庫,不匯入 ``PySide6``。
名稱會經過路徑穿越驗證。

無頭 API
--------

.. code-block:: python

    from je_auto_control import verify_artifact, approve_artifact

    result = verify_artifact("invoice_render", produced_text,
                             approvals_dir="tests/.approvals")
    if not result.match:
        # 首次執行為 "new",輸出變更為 "mismatch";審查 .received 檔後再核可:
        approve_artifact("invoice_render", approvals_dir="tests/.approvals")

``content`` 可為 ``str`` 或 ``bytes``(二進位快照請傳 ``extension="png"``)。相符的執
行會清除任何過期的 received 檔。``pending_artifacts(dir)`` 列出仍待核准的名稱。
``ApprovalResult`` 帶有 ``status``(``verified`` / ``mismatch`` / ``new``)、
``match`` 及兩個檔案路徑。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_verify_artifact``           將 ``content`` 與已核准基準比對。
``AC_approve_artifact``          將 received 產物晉升為基準。
``AC_pending_artifacts``         列出待核准的產物。
================================ ===================================================

相同操作亦提供為 MCP 工具(``ac_verify_artifact`` / ``ac_approve_artifact`` /
``ac_pending_artifacts``),以及 Script Builder 中 **Testing** 分類下的指令。

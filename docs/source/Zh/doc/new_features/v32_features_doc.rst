Maker-Checker 審批閘門
======================

有些自動化步驟後果太重大,不該由單一方說了算 —— 刪除正式環境資料、匯款、發布版
本。``ApprovalGate`` 提供**職責分離(segregation of duties)**控制:由 *maker*
提出請求並取得 token;*checker*(必須是**不同**的主體)核准或駁回;只有在 token
被核准後動作才會繼續。

狀態存於選用的 JSON 檔,因此 maker(例如 CI 派發器)與 checker(例如人工審批者)
可分屬不同程序執行。本模組為純標準函式庫,不匯入 ``PySide6``;token 使用
:mod:`secrets`。

無頭 API
--------

.. code-block:: python

    from je_auto_control import ApprovalGate

    gate = ApprovalGate("approvals.json")          # 跨程序共用
    token = gate.request("delete prod table", requester="alice")

    # 自我核准會被拒絕 —— checker 必須與 maker 不同。
    gate.approve(token, "alice")    # -> False
    gate.approve(token, "bob")      # -> True

    if gate.is_approved(token):
        run_high_risk_action()

``reject(token, approver)`` 會封鎖動作;已決議的請求無法再次決議。
``status(token)`` 回傳 ``pending`` / ``approved`` / ``rejected``(未知 token 為
``None``),``get(token)`` 回傳完整紀錄,``pending()`` 則列出所有仍待決議的請求。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_approval_request``          為 ``action`` 提出請求;回傳 ``{token}``。
``AC_approval_approve``          以 ``approver`` 核准 ``token``;``{approved}``。
``AC_approval_reject``           以 ``approver`` 駁回 ``token``;``{rejected}``。
``AC_approval_status``           回傳 ``{status, approved}`` 以閘控動作。
================================ ===================================================

每個指令都接受選用的 ``db`` 路徑,讓流程可將請求保存到共用 JSON 檔。相同操作亦提供
為 MCP 工具(``ac_approval_request`` / ``ac_approval_approve`` /
``ac_approval_reject`` / ``ac_approval_status``),以及 Script Builder 中 **Tools**
分類下的指令。

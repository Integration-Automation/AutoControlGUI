SARIF 2.1.0 發現項目匯出
========================

框架有多個發現項目產生器 —— action-lint、密鑰掃描、WCAG/a11y 稽核、guardrail —— 但缺乏
共通匯出,因此結果無法進入 GitHub / Azure DevOps 的**程式碼掃描**(持久、去重、定位到行
的警示儲存)。SARIF 2.1.0(OASIS)正是該交換格式。

``to_sarif`` 由一份正規化*發現項目*清單(``{rule_id, level, message, file?, line?}``)建
立 SARIF 文件,並為既有 lint / audit 形狀提供轉接器,加上穩定的 ``partialFingerprints``
讓同一問題能跨執行去重。純標準函式庫(``json`` + ``hashlib``);不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        make_finding, to_sarif, write_sarif, from_lint_issues,
        from_audit_findings)

    findings = [
        make_finding("AC_SHELL", "shell command not allow-listed",
                     level="error", file="flow.json", line=12),
        *from_lint_issues(lint_issues, file="flow.json"),
        *from_audit_findings(wcag_report["findings"]),
    ]
    write_sarif(findings, "results.sarif", tool_name="AutoControl")
    # 以 GitHub「upload-sarif」action 上傳 results.sarif

``make_finding`` 建立單一正規化發現項目;``from_lint_issues``(對映
``index/severity/code/message``)與 ``from_audit_findings``(對映
``sc/criterion/kind/severity``)轉接既有產生器;``to_sarif`` 自動衍生規則目錄並為每個結
果附上穩定指紋;``write_sarif`` 序列化成檔案。嚴重度字串對映為 SARIF 的 ``error`` /
``warning`` / ``note``。

執行器指令
----------

``AC_export_sarif`` 接受 ``findings``(清單或 JSON 字串)以及選用的 ``path`` 與
``tool_name``,回傳 ``{sarif, path?}``。相同操作亦提供為 MCP 工具 ``ac_export_sarif``,以
及 Script Builder 中 **Report** 分類下的指令。

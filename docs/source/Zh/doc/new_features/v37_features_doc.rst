合規控制報告(SOC2 / ISO 27001)
================================

AutoControl 已內建稽核員關注的*控制項* —— 網路出口允許清單、即時憑證租約、
maker-checker 審批、密鑰掃描器、稽核記錄、CycloneDX SBOM。
:func:`build_compliance_report` 把「這些控制項是否到位?」轉化為稽核員可讀的**控制證
據報告**:你提供一個扁平的 ``evidence`` 觀察事實對應表,每個編目控制項即被標記為
``satisfied`` / ``gap`` / ``not_assessed``。

它是報告*輔助工具*,非認證 —— 它記錄你所聲明的證據,並不自行驗證控制項。純標準函式
庫,不匯入 ``PySide6``。

對應的控制項
------------

================ ============= =================================================== ==============================
框架             控制項        標題                                                證據鍵
================ ============= =================================================== ==============================
SOC2             CC6.1         邏輯存取限制於授權主機                              ``egress_allowlist_enforced``
SOC2             CC6.3         最小權限、限時憑證                                  ``jit_credentials_used``
SOC2             CC6.8         密鑰不硬編碼且經掃描                                ``secrets_scanned``
SOC2             CC7.3         安全事件留存供審查                                  ``audit_logging_enabled``
SOC2             CC8.1         變更需職責分離(maker-checker)審批                ``change_approval_required``
ISO 27001        A.5.23        雲端/網路出口的資訊安全                            ``egress_allowlist_enforced``
ISO 27001        A.8.16        監控活動 / 稽核軌跡                                 ``audit_logging_enabled``
ISO 27001        A.8.30        維護軟體物料清單                                    ``sbom_generated``
================ ============= =================================================== ==============================

無頭 API
--------

.. code-block:: python

    from je_auto_control import build_compliance_report, write_compliance_report

    report = build_compliance_report({
        "egress_allowlist_enforced": True,
        "jit_credentials_used": True,
        "secrets_scanned": True,
        "audit_logging_enabled": True,
        "change_approval_required": True,
        "sbom_generated": True,
    }, frameworks=["SOC2"])          # frameworks 為選用

    print(report["summary"])         # {satisfied, gap, not_assessed, total}
    write_compliance_report(report, "build/compliance.html", fmt="html")

當控制項的證據鍵為真時為 ``satisfied``,明確為假時為 ``gap``,鍵不存在時為
``not_assessed`` —— 因此部分證據字典會產生誠實的缺口分析。``render_compliance_html``
回傳獨立的 HTML 表格;``write_compliance_report`` 寫出 ``json`` 或 ``html``。

執行器指令
----------

``AC_compliance_report`` 接受 ``evidence``(JSON 物件,或視覺化建構器傳入的 JSON 字
串)、選用的 ``frameworks`` 清單/逗號字串,以及選用的 ``path`` + ``fmt`` 以寫出檔案;
回傳 ``{summary, controls, path?}``。相同操作亦提供為 MCP 工具
``ac_compliance_report``,以及 Script Builder 中 **Report** 分類下的指令。

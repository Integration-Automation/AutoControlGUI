OpenVEX 漏洞分級
===============

``scan_components``(OSV 比對器)會產生漏洞發現項目,但之後每次執行每個已知 CVE 都會一直出現
—— 沒有辦法記錄「我們看過了,這個不影響我們」並把它捨棄。VEX(Vulnerability Exploitability
eXchange)正是這個分級訊號的標準。本功能撰寫 `OpenVEX <https://openvex.dev>`_ 0.2.0 陳述並
套用到掃描器的發現項目上。

``not_affected`` / ``fixed`` 陳述會**抑制**一項發現;``affected`` / ``under_investigation``
則以評估後的狀態**標註**它。陳述以漏洞 id *或*其任一別名與發現項目配對,並可選擇性地限定到某個
產品。純標準函式庫(``hashlib`` + ``json`` + ``datetime``);不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        scan_components, vex_statement, build_vex, apply_vex)

    findings = scan_components(sbom["components"], advisories)

    statements = [
        vex_statement("CVE-2024-1", "not_affected",
                      products=["pkg:pypi/foo"],
                      justification="vulnerable_code_not_present"),
        vex_statement("GHSA-bar", "under_investigation"),
    ]
    vex = build_vex(statements, author="security@example.com")

    triaged = apply_vex(findings, vex)
    # CVE-2024-1(not_affected)被捨棄;GHSA-bar 保留並設定 vex_status

``vex_statement`` 會驗證輸入:``status`` 必須是 ``VEX_STATUSES`` 之一(``not_affected`` /
``affected`` / ``fixed`` / ``under_investigation``);``not_affected`` 陳述必須帶有
``justification``(``VEX_JUSTIFICATIONS`` 其一)或 ``impact_statement``。``build_vex`` 把
陳述包成 OpenVEX 文件(傳入明確的 ``timestamp`` 可得到可重現的 ``@id``)。``apply_vex`` 回傳
存活的發現項目,每個未被抑制的配對都會標註 ``vex_status``。

執行器命令
----------

``AC_apply_vex`` 接受 ``findings`` 與一份 ``vex`` 文件(各為 list/object 或 JSON 字串),回傳
存活者的 ``{findings, count}``。同一操作亦以 MCP 工具 ``ac_apply_vex`` 以及 Script Builder
中 **Security** 分類下的命令提供。它可直接接在 ``AC_scan_vulns`` 之後。

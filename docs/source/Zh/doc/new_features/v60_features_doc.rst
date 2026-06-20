授權政策閘門
===========

``build_sbom`` 會記錄每個元件的授權*名稱*,但從未對它做判斷 —— copyleft 或其他不被允許的授權
可能在無人察覺下隨產品出貨。本功能補上政策閘門:把 SBOM 的授權字串正規化為 SPDX id,以
允許清單 / 拒絕清單(內建強 copyleft 集合)評估,並產生可橋接到既有 SARIF 匯出器的違規項目
—— 與 OSV 漏洞通道並列的授權合規通道。

純標準函式庫(``re``);完全離線;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        build_sbom, evaluate_sbom, evaluate_license,
        license_findings_to_sarif, write_sarif, DEFAULT_COPYLEFT)

    sbom = build_sbom("je_auto_control")

    # 允許清單模式:清單之外的一律視為違規。
    violations = evaluate_sbom(sbom["components"],
                               allow=["MIT", "Apache-2.0", "BSD-3-Clause"])

    # 或以內建強 copyleft 集合做拒絕清單模式。
    violations = evaluate_sbom(sbom["components"], deny=DEFAULT_COPYLEFT)

    write_sarif(license_findings_to_sarif(violations), "licenses.sarif",
                tool_name="AutoControl-License")

``normalize_spdx`` 把寬鬆的名稱(``"MIT License"`` → ``MIT``、``"Apache 2.0"`` →
``Apache-2.0``)對應到 SPDX id。``evaluate_license`` 回傳 ``allowed`` / ``denied`` /
``unknown``:``deny`` 優先;空的 ``allow`` 代表「不受限制」;缺少授權則為 ``unknown``。亦理解
SPDX **運算式** —— ``"MIT OR GPL-3.0-only"`` 是*擇一*(任一運算元被允許即允許),而
``"MIT AND GPL-3.0-only"`` 需要每個運算元都被允許。每個違規為
``{name, version, license, status}``;``denied`` 對應 SARIF ``error``,``unknown`` 對應
``warning``。

執行器命令
----------

``AC_check_licenses`` 接受 ``components``(元件清單、完整 SBOM dict 或 JSON 字串)與選用的
``allow`` / ``deny`` 清單;回傳 ``{violations, count}``。同一操作亦以 MCP 工具
``ac_check_licenses`` 以及 Script Builder 中 **Security** 分類下的命令提供。

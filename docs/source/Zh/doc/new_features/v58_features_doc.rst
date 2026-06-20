相依套件漏洞掃描(OSV)
======================

``build_sbom`` 會*盤點*相依套件,``to_sarif`` 會*匯出*發現項目,但兩者之間從未真正**產生**
漏洞發現項目 —— 完全沒有諮詢比對。本功能補上這個環節:給定 SBOM 的
``(ecosystem, name, version)`` 元件與一份 `OSV <https://osv.dev>`_ 諮詢資料庫,
``scan_components`` 會回報哪些套件受影響,而 ``findings_to_sarif`` 把結果直接橋接到既有的
SARIF 匯出器,供 GitHub / Azure DevOps 程式碼掃描使用。

諮詢資料庫以**純資料注入**(一份 OSV 紀錄清單),因此比對完全離線且具決定性;線上的
``osv.dev`` 查詢則是另一個選用的 ``fetcher`` 接縫。純標準函式庫(``re``);不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        build_sbom, scan_components, findings_to_sarif, write_sarif)

    advisories = [{
        "id": "GHSA-foo", "summary": "RCE in foo",
        "database_specific": {"severity": "HIGH"},
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "foo"},
            "ranges": [{"type": "ECOSYSTEM",
                        "events": [{"introduced": "0"}, {"fixed": "1.2.0"}]}],
        }],
    }]

    sbom = build_sbom("je_auto_control")
    findings = scan_components(sbom["components"], advisories)
    # findings: [{id, package, version, summary, severity, fixed, aliases}]
    write_sarif(findings_to_sarif(findings), "vulns.sarif",
                tool_name="AutoControl-VulnScan")

``is_affected(version, osv_range)`` 透過掃描 ``introduced`` / ``fixed`` /
``last_affected`` 事件來評估單一 OSV 範圍;``match_package`` 以資料庫比對單一套件(明確的
``versions`` **或**範圍);``scan_components`` 跑完整份 SBOM。套件名稱以 PEP-503 正規化後比較,
OSV 嚴重度字詞(``CRITICAL`` / ``HIGH`` / ``MODERATE`` / ``LOW``)對應到 SARIF 的
``error`` / ``warning`` / ``note`` 等級(預設為 ``warning``)。

版本排序採務實的數值比較:release 元件以整數比較,pre-release 後綴(``1.2.0-rc1``)排在最終
release 之前。Git 範圍與完整 CVSS 向量評分不在範圍內。

線上諮詢(選用)
----------------

傳入 ``fetcher`` callable 即可在掃描當下抓取諮詢(例如從 ``osv.dev`` API)。測試注入假的
fetcher,因此比對邏輯不需任何網路即可驗證:

.. code-block:: python

    findings = scan_components(sbom["components"], None,
                              fetcher=my_osv_fetcher)

執行器命令
----------

``AC_scan_vulns`` 接受 ``components``(元件清單、完整 SBOM dict 或 JSON 字串)與
``advisories``(清單或 JSON 字串),並可選用 ``sarif_path`` 寫出 SARIF 報告;回傳
``{findings, count}``(寫檔時另含 ``sarif_path``)。同一操作亦以 MCP 工具 ``ac_scan_vulns``
以及 Script Builder 中 **Security** 分類下的命令提供。

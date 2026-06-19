==============================================
新功能 (2026-06-19) — SBOM 與測試分片
==============================================

來自安全與規模研究角度的兩項純標準庫維運工具,走完整五層(facade、
``AC_*`` 執行器指令、MCP 工具、Script Builder):**CycloneDX SBOM 產生器**
與**時長感知的測試套件分片**(含分片結果合併)。

.. contents::
   :local:
   :depth: 2


CycloneDX SBOM
==============

供應鏈法規(歐盟網路韌性法 CRA、美國 EO 14028)日益要求可機讀的軟體物料
清單(SBOM)。``build_sbom`` 會走訪已安裝的 Python 發行套件並輸出
**CycloneDX 1.6** JSON 文件——不需任何第三方相依::

    from je_auto_control import build_sbom, write_sbom

    sbom = build_sbom("je_auto_control")        # 該套件的相依封閉集
    sbom = build_sbom(None)                      # 所有已安裝發行套件
    write_sbom("sbom.cdx.json", "je_auto_control",
               extra_components=[{"type": "file", "name": "login.json",
                                  "version": "1"}])

每個元件帶有 ``name`` / ``version`` / ``purl``(``pkg:pypi/...``),有提供時
也帶授權。``extra_components`` 讓你把 action 檔與程式碼一併納入清單。對應
``AC_generate_sbom`` / ``ac_generate_sbom``。


時長感知的套件分片
==================

把套件依*數量*分到 N 個 worker,在測試時長不均時會浪費時間——最慢的
worker 決定總時長。``shard_flows`` 以 run-history 中的**每個流程歷史時長**
用貪婪裝箱法平衡各分片::

    from je_auto_control import shard_flows, merge_results

    shards = shard_flows(all_flows, shards=4)    # 每片時間約略相等
    # ... 各 worker 跑自己的分片,產生一份報告 ...
    report = merge_results([shard_report_1, shard_report_2, ...])

沒有歷史的流程退回為已知流程的平均(讓新測試平均分散)。``merge_results``
會重新合併各分片報告 dict——加總 ``total`` / ``passed`` / ``failed`` /
``skipped`` / ``errors`` 並串接 ``results``。對應 ``AC_shard_suite`` /
``AC_merge_results``(以及 ``ac_shard_suite`` / ``ac_merge_results``)。

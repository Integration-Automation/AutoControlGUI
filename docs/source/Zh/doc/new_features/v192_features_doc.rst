執行軌跡比較(兩次執行之間改變了什麼)
======================================

執行歷史告訴你某次執行*失敗*了,卻不告訴你相較於通過的那次*改變了什麼*:哪個步驟被加入或移除、
哪個步驟由通過翻轉成失敗、哪個步驟變慢了。``run_diff`` 以最長共同子序列(LCS)走訪對齊兩個步驟
序列——這樣插入或移除一個步驟會把其餘步驟順移到位,而非整個錯位配對——並將差異分類:

* **added** / **removed** ——只存在於其中一次執行的步驟,
* **status_flips** ——某個已對齊步驟的狀態改變,若帶有 ``error`` 則附上新失敗的
  :func:`failure_signature`,
* **timing_regressions** ——某個已對齊步驟變慢了 ``regress_factor`` 倍。

步驟可為任何帶有名稱鍵(預設 ``"name"``)與選填 ``status`` / ``duration`` / ``error`` 的字典。
純標準庫;不涉及裝置,不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import diff_runs, summarize_run_diff

    before = [{"name": "login", "status": "ok", "duration": 1.0},
              {"name": "submit", "status": "ok", "duration": 1.0}]
    after = [{"name": "login", "status": "ok", "duration": 1.1},
             {"name": "accept_cookies", "status": "ok"},          # 插入
             {"name": "submit", "status": "error", "error": "Timeout ..."}]

    diff = diff_runs(before, after)
    # {"added": [accept_cookies], "removed": [],
    #  "status_flips": [{"name": "submit", "from": "ok", "to": "error",
    #                    "signature": "..."}],
    #  "timing_regressions": [], "aligned": 2, "identical": False}

    summarize_run_diff(diff)        # "+1 added, 1 status flip(s)"

``regress_factor``(預設 ``1.5``)是算作退化的變慢比率;``key`` 選擇步驟對齊所依據的欄位。
``summarize_run_diff`` 產生一行摘要(相同時為 ``"no change"``)。

執行器指令
----------

``AC_diff_runs``(``before`` / ``after`` / ``key`` / ``regress_factor``)回傳該差異並附帶
``summary`` 欄位。以唯讀 ``ac_diff_runs`` MCP 工具及 Script Builder 指令(位於 **Testing**
分類下)形式提供。

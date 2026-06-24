以預設程式開啟檔案 / URL
========================

框架原本能啟動字面執行檔(``start_exe`` / ``shell_process``),卻無法做最常見的「交接給另一個應用程式」
RPA 步驟:用註冊的應用程式開啟 ``report.pdf``、``print`` 一份文件,或在預設瀏覽器開啟 URL。
``shell_open`` 補上這點,依作業系統路由到 ``os.startfile`` / ``open`` / ``xdg-open`` /
``webbrowser``。

* :func:`plan_open` ——純 planner:分類目標(URL 或檔案路徑)、驗證(URL scheme 白名單;檔案用
  ``realpath``)並回傳分派描述子,
* :func:`open_path` ——透過可注入的 ``opener`` 接縫執行計畫(預設為真正的 OS 呼叫)。

純標準庫;透過可注入的 ``opener``,分派邏輯可在不真正開啟任何東西的情況下單元測試。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import open_path, plan_open

    open_path("report.pdf")                 # 預設 PDF 檢視器
    open_path("invoice.pdf", verb="print")  # 列印
    open_path("https://example.com")        # 預設瀏覽器

    plan_open("https://example.com")
    # {"kind": "url", "scheme": "https", "target": "...", "backend": "webbrowser",
    #  "verb": "open"}
    plan_open("report.pdf")
    # {"kind": "file", "target": "<realpath>", "backend": "startfile", ...}

``scheme://`` 目標(或 ``mailto:`` / ``tel:``)會以 URL 開啟——只接受白名單 scheme
(``http`` / ``https`` / ``ftp`` / ``file`` / ``mailto`` / ``tel``),其他則拋出 ``ValueError``。
其餘皆視為檔案路徑(Windows 磁碟代號如 ``C:\\…`` 會正確視為路徑而非 scheme)並以 ``realpath``
解析。``verb``(``open`` / ``print`` / ``edit``)在 Windows 上套用於檔案。

執行器指令
----------

``AC_open_path``(``target`` / ``verb`` → ``{opened}``)與 ``AC_plan_open``(``target`` /
``verb`` → 計畫)。皆以對應的 ``ac_*`` MCP 工具(``open_path`` 為僅副作用、``plan_open`` 為唯讀)
及 Script Builder 指令(位於 **Shell** 分類下)形式提供。

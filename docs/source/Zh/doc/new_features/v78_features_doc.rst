RFC 9457 Problem Details 解析
============================

``http_request`` 回傳的非 2xx 內文未經解析,因此流程 —— 或 ``assert_http`` —— 無法以結構化方式讀取
標準化的 API 錯誤。本功能解析 RFC 9457 ``application/problem+json`` 文件:已註冊的 ``type`` /
``title`` / ``status`` / ``detail`` / ``instance`` 成員,加上任何 vendor 擴充欄位。

純標準函式庫(``json``);不匯入 ``PySide6``。每個函式皆為純函式(輸入 response dict、輸出 dataclass),
因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import http_request, parse_problem, raise_for_problem

    response = http_request("https://api.example.com/orders/12")
    problem = parse_problem(response)        # 非 problem+json 時為 None
    if problem is not None:
        log(problem.status, problem.title, problem.detail)
        retry_after = problem.extensions.get("balance")

    # 或把 problem 回應轉成例外:
    raise_for_problem(response)              # 拋出 HttpProblemError

``is_problem`` 檢查 ``Content-Type``(不分大小寫)。``parse_problem`` 回傳 ``ProblemDetails``
(``type`` 預設 ``about:blank``,可轉換時 ``status`` 為整數,所有非註冊鍵收進 ``extensions``),
回應非 problem 文件時回傳 ``None``;當 ``json`` 缺席時會回退去解析 ``text``。``ProblemDetails.summary``
給出一行描述,``to_dict`` 把文件攤平並併回擴充欄位。``raise_for_problem`` 對 problem 回應拋出
``HttpProblemError``(帶著 ``ProblemDetails``),否則不做任何事。

執行器命令
----------

``AC_parse_problem`` 接受 ``http_request`` 的 ``response``,回傳 ``{problem}``(攤平的文件)或
``null``。它以 MCP 工具 ``ac_parse_problem`` 以及 Script Builder 中 **Data** 分類下的命令提供。

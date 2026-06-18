====================================
新功能 (2026-06-18) — CLI 與整合
====================================

八項 headless 能力,補齊腳本化、整合與 CI 使用情境:一個真正的命令列
介面、把錄製轉成程式碼,以及一級的 HTTP / SQL / Email / PDF / 等待步驟。
每項功能都提供 headless Python API、``AC_*`` 執行器指令、MCP 工具,以及
視覺化 Script Builder 項目,並有 headless 測試覆蓋——網路、SMTP、PDF
後端皆以注入方式測試,完全不會碰到外部系統。

.. contents::
   :local:
   :depth: 2


命令列介面
==========

套件現在會安裝 ``je_auto_control`` console script,可在 shell 或 CI 中
執行與檢查動作檔::

    je_auto_control run script.json --var user=alice --dry-run
    je_auto_control validate script.json      # 別名:lint
    je_auto_control list-commands --filter mouse --json
    je_auto_control fmt script.json --check
    je_auto_control record out.json --duration 5
    je_auto_control codegen script.json --target pytest -o test_flow.py
    je_auto_control version

``run`` 直接執行(``--dry-run`` 只驗證並列出步驟而不實際操作),
``validate`` / ``lint`` 檢查結構並拒絕未知指令,``fmt`` 標準化 JSON,
``record`` 錄製輸入,``codegen`` 產生程式碼(見下),``list-commands``
列出執行器即時的指令目錄。


程式碼產生
==========

把錄製或動作檔轉成可提交、可執行的程式碼::

    from je_auto_control import generate_code, generate_code_file

    code = generate_code(actions, target="pytest", style="calls")
    generate_code_file("flow.json", "test_flow.py", target="pytest")

``target`` 可為 ``pytest`` / ``python`` / ``robot``。預設的 ``calls``
風格會把每個 ``AC_*`` 指令對應到 facade 呼叫(``ac.click_mouse(...)``),
流程控制與私有 adapter 則退回 ``ac.execute_action([...])``;``actions``
風格則直接嵌入動作清單並透過執行器重播。

執行器指令:``AC_generate_code``。CLI:``je_auto_control codegen``。


HTTP / API
==========

不需額外相依的 HTTP(S) 客戶端,適合 UI + API 混合流程::

    from je_auto_control import http_request

    resp = http_request(
        "https://api.example/items", method="POST",
        json_body={"name": "Sam"},
        headers={"X-Trace": "1"},
        auth={"type": "bearer", "token": "..."},
        timeout=30.0)
    assert resp["status"] == 201

回傳 ``{status, ok, headers, text, json, url}``;非 2xx 回應會被回傳而非
丟出例外,因此可直接對狀態碼斷言。僅允許 ``http`` / ``https``。
``AC_http_to_var`` 現在共用同一個客戶端,因此也能送 body、headers 與認證。

執行器指令:``AC_http_request``。


SQL
===

唯讀、參數化的 SQLite 查詢::

    from je_auto_control import query_sqlite

    rows = query_sqlite("app.db", "SELECT id, name FROM users")
    count = query_sqlite("app.db",
                         "SELECT COUNT(*) FROM users WHERE active = ?",
                         params=[1], fetch="scalar")

查詢僅限單句唯讀的 ``SELECT`` / ``WITH``,以唯讀連線執行,且值一律以
參數綁定(絕不字串拼接)。

執行器指令:``AC_sql_to_var``(列 / 單列 / 純量存入變數)與
``AC_assert_db``(對純量查詢以 eq / ne / lt / gt / contains / ... 斷言)。


Email(SMTP)
============

透過標準庫寄信——例如流程的報告::

    from je_auto_control import send_email

    send_email(
        {"sender": "bot@x.com", "to": ["qa@x.com"],
         "subject": "Run passed", "body": "All green",
         "attachments": ["report.html"]},
        {"host": "smtp.x.com", "port": 587,
         "username": "bot@x.com", "password": "..."})

預設啟用 TLS(STARTTLS,或設定 ``use_ssl`` 時用隱式 SSL),使用已驗證
憑證的預設 context;支援多收件人、CC、HTML 內文與檔案附件。

執行器指令:``AC_send_email``。


PDF
===

從 PDF 文件抽取文字並斷言其內容(可選的 ``pypdf`` 後端——
``pip install je_auto_control[pdf]``)::

    from je_auto_control import extract_pdf_text, assert_pdf_text

    text = extract_pdf_text("invoice.pdf", pages=1)
    assert_pdf_text("invoice.pdf", "Total: $50.00")

執行器指令:``AC_pdf_to_var``(文字存入變數)與 ``AC_assert_pdf_text``
(文字存在 / 不存在,可指定頁碼)。


智慧等待
========

兩個用來取代不可靠 ``sleep`` 的等待::

    from je_auto_control import wait_until_file, wait_until_port

    wait_until_file("~/Downloads/report.pdf", stable_for_s=1.0)
    wait_until_port("127.0.0.1", 8080, timeout_s=30.0)

``wait_until_file`` 會在檔案存在、達到 ``min_size`` 位元組、且大小持續
``stable_for_s`` 秒不變(下載寫完)後回傳。``wait_until_port`` 會在
``host:port`` 可接受 TCP 連線後回傳——是啟動伺服器的最佳搭檔。兩者都
回傳 ``WaitOutcome`` 並有硬性 ``timeout_s`` 上限。

執行器指令:``AC_wait_for_file``、``AC_wait_for_port``。


安全性
======

HTTP 與 SMTP 強制 ``http`` / ``https`` 或使用已驗證憑證的 TLS,並設定明確
逾時;SQL 為唯讀且參數綁定;所有使用者提供的檔案路徑在 I/O 前都會以
``realpath`` 解析。

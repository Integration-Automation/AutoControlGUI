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
流程控制、私有 adapter 與任何含 ``${...}`` 佔位符的動作(只有執行器會解析)則交給執行器;
``actions`` 風格則直接嵌入動作清單並透過執行器重播。每次重播都是
``ac.executor.execute_action(..., raise_on_error=True)``,所以產生的測試會在第一個失敗的動作停下並失敗。
執行器會拒絕的動作清單(``[1]``、多了第三個元素的動作)這裡也會拒絕。

執行器指令:``AC_generate_code``。CLI:``je_auto_control codegen``。


動作日誌與候選腳本
==================

動作日誌是選用、僅附加的 JSON-lines 紀錄,記下執行器跑過的每一個動作——不論是從
Python、CLI、GUI、REST、socket 還是 MCP 進來的::

    from je_auto_control import (
        start_action_journal, stop_action_journal, read_events,
        generate_candidate_from_log,
    )

    run_id = start_action_journal("journal.jsonl")["run_id"]
    execute_action(actions)
    stop_action_journal()

    for event in read_events("journal.jsonl", run_id=run_id):
        print(event.sequence, event.command, event.status, event.parent_id)

沒有啟動日誌時,每個動作只多一次全域變數讀取,不配置任何物件。每筆事件
(``ActionEvent``,``schema_version`` 為 1)包含:

* ``run_id`` / ``step_id`` / ``parent_id`` / ``sequence``——巢狀在區塊內的步驟以該區塊
  為 parent;``AC_parallel`` 的分支保留區塊為 parent 並帶 ``branch`` 編號;``sequence``
  是步驟開始的順序(也是檔案中各行的順序);
* ``command`` 與 ``params``——參數依 *原樣* 記錄:``${var}`` 與 ``${secrets.NAME}`` 參照
  維持參照。秘密在該行 **寫入前** 就已遮罩(規則同執行器的 log,另含 tuple),JSON 無法
  表示的值改記為 ``{"$unserialisable": "<型別>"}``;
* ``unreplayable``——上述每個路徑(``params.password``、``params.body[0][1].token``)
  無法重播的原因;
* ``status``——``ok``、``error`` 或 ``incomplete``。步驟在開始時寫一行、結束時再寫一行,
  所以結束行沒寫進檔案的步驟(行程死掉、``Ctrl+C``)讀回來是 ``incomplete``,不會看起來
  像成功;
* ``outcome``——只記回傳值的型別與大小(數字與布林才記值);回傳的文字一律不存,而且
  outcome 永遠不會被當成輸入。

start 到 stop 之間記下的一切屬於同一個 ``run_id``(可用 ``run_id=`` 指定)。日誌檔寫不
進去時,日誌會停止而自動化繼續執行;``action_journal_status()`` 會回報錯誤。除了
``AC_parallel`` 以外,交給執行緒池執行的步驟(DAG runner、device matrix)記錄時沒有
parent。

``generate_candidate_from_log(path, run_id=..., target="pytest", style="actions")``
把一次執行轉成 ``CandidateScript``——``code``、``actions``、``manifest``、``warnings``
與 ``observed_path_only``:

* 頂層步驟依原樣輸出,所以記錄到的 ``AC_loop`` / ``AC_if_*`` / ``AC_parallel`` 保留其
  控制流程;
* 區塊無法還原時(日誌是在區塊內才啟動、參數無法儲存、呼叫了這次執行沒定義的巨集),
  改輸出實際在它底下跑過的步驟,manifest 中標為 ``observed``,且 ``observed_path_only``
  為 true——候選腳本重播的是那次執行走過的路徑,不會憑空產生沒執行的分支。已觀察的
  ``AC_retry`` 只保留最後一次嘗試(manifest 會記嘗試次數);
* 被遮罩的秘密會變成 ``${journal_redacted_N_M}`` 參照,在你替換掉之前會以未知變數
  失敗;
* 失敗與未完成的步驟會保留(它們是腳本的輸入),並列在 warnings;
* manifest 逐步記錄來源的日誌行號,以及做過的檢查:原始碼可解析、指令名稱已查表、
  動作清單通過執行器的 dry run。日誌中的任何內容都不會被執行或 eval。

執行器指令:``AC_journal_start`` / ``AC_journal_stop`` / ``AC_journal_status`` /
``AC_journal_read`` / ``AC_journal_runs`` 與 ``AC_generate_code_from_journal``。
MCP 工具:``ac_journal_start`` / ``ac_journal_stop`` / ``ac_journal_status`` /
``ac_journal_read`` / ``ac_journal_runs`` 與 ``ac_generate_code_from_log``。CLI::

    je_auto_control codegen --from-log journal.jsonl --run-id RUN \
        --target pytest -o test_flow.py --manifest test_flow.manifest.json

日誌只有一次執行時可省略 ``--run-id``;這裡 ``--style`` 預設為 ``actions``(動作檔則是
``calls``)。GUI:Run History 分頁 → Actions 選單(啟動/停止日誌、儲存候選腳本);
Recording Editor →「匯入日誌的執行…」;Script Builder →「匯入日誌」。


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

回傳 ``{status, ok, headers, set_cookie, text, json, url}``;非 2xx 回應會被回傳而非
丟出例外,因此可直接對狀態碼斷言。重複的標頭在 ``headers`` 裡以 ", " 串接,``set_cookie``
列出每一個 ``Set-Cookie`` 值。回應本文超過 64 MiB 會拋出 ``URLError``。僅允許 ``http`` / ``https``。
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

執行器指令:``AC_sql_to_var``\ (列 / 單列 / 純量存入變數)與
``AC_assert_db``\ (對純量查詢以 eq / ne / lt / gt / contains / ... 斷言)。


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

預設啟用 TLS(STARTTLS,或設定 ``use_ssl`` 時用隱式 SSL,埠號預設改為 465
而非 587),使用已驗證
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

    from je_auto_control import (
        wait_until_file, wait_until_port, wait_until_process)

    wait_until_file("~/Downloads/report.pdf", stable_for_s=1.0)
    wait_until_port("127.0.0.1", 8080, timeout_s=30.0)
    wait_until_process("myserver", present=True, timeout_s=30.0)

``wait_until_file`` 會在檔案存在、達到 ``min_size`` 位元組、且大小持續
``stable_for_s`` 秒不變(下載寫完)後回傳。``wait_until_port`` 會在
``host:port`` 可接受 TCP 連線後回傳——是啟動伺服器的最佳搭檔。兩者都
回傳 ``WaitOutcome`` 並有硬性 ``timeout_s`` 上限。

``wait_until_process`` 會在名稱含目標字串的行程出現(或 ``present=False``
時結束)後回傳——是 ``launch_process`` / ``kill_process`` 的搭檔(需
psutil)。

執行器指令:``AC_wait_for_file``、``AC_wait_for_port``、``AC_wait_for_process``。


安全性
======

HTTP 與 SMTP 強制 ``http`` / ``https`` 或使用已驗證憑證的 TLS,並設定明確
逾時;SQL 為唯讀且參數綁定;所有使用者提供的檔案路徑在 I/O 前都會以
``realpath`` 解析。

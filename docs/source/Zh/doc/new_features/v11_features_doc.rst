============================================
新功能 (2026-06-19) — 測試與工具三件套
============================================

三項提升生產力的工具,皆為純標準庫,並走完整五層(facade、``AC_*``
執行器指令、MCP 工具、Script Builder):有種子的合成測試資料、MCP
registry ``server.json`` 產生器,以及風險導向的測試選擇。

.. contents::
   :local:
   :depth: 2


合成測試資料
============

依一個極小的欄位 schema 產生**可重現**的假資料列——用來驅動資料驅動的
執行,而不必散布真實 PII。不需要 Faker;相同的 ``seed`` 永遠產生相同的
資料列::

    from je_auto_control import generate_rows, write_dataset

    rows = generate_rows({
        "name": "name",
        "email": {"type": "email", "domain": "acme.test"},
        "age": {"type": "int", "min": 18, "max": 65},
        "status": {"type": "choice", "choices": ["new", "vip"]},
    }, count=100, seed=7)

    write_dataset(rows, "people.csv")   # 或 .json

支援的欄位型別:``first_name``、``last_name``、``name``、``username``、
``email``、``phone``、``city``、``company``、``word``、``sentence``、
``uuid``、``bool``、``int``(min/max)、``float``(min/max/ndigits)、
``choice``(choices)、``date``(start/end)。

``AC_generate_data`` 指令會寫出檔案(再交給 ``AC_load_data``)或直接
回傳資料列。


MCP registry 清單
=================

產生描述此 AutoControl MCP 伺服器的 ``server.json``,讓支援 MCP 的
agent 與 IDE 能發現並安裝它。清單由即時套件中繼資料建構,因此不會與
實際能力脫節::

    from je_auto_control import write_server_manifest

    write_server_manifest("server.json", include_tools=True)

``include_tools`` 會把即時工具清單嵌入 ``_meta``(不更動 registry 規範
的核心欄位)。同時提供 ``AC_mcp_manifest`` 與 ``ac_mcp_manifest`` MCP
工具。


風險導向測試選擇
================

與其每次都跑整套測試,不如依據流程的**風險**排序——最近失敗、不穩定
(flaky)、太久沒跑、或從未跑過——用 run-history 紀錄計算,然後先跑最
高風險的(或只跑前 k 個)::

    from je_auto_control import select_flows, rank_flows

    ranked = rank_flows(["login", "checkout", "report"])
    risky = select_flows(["login", "checkout", "report"], k=2)

分數為 ``0.5*失敗率 + 0.2*上次失敗 + 0.2*不穩定度 + 0.1*陳舊度``;
從未跑過的流程得 ``0.8``(未測試即高風險)。提供 ``AC_rank_tests`` /
``AC_select_tests`` 以及 ``ac_rank_tests`` / ``ac_select_tests`` MCP
工具。

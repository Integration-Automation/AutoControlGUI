============================
新功能 (2026-05)
============================

新增 23 個功能，涵蓋更聰明的定位器、更深的 IDE / 維運工具、兩個新平台後端，
以及幾個新整合。每個功能都遵循框架既有模式：headless Python API、
``AC_*`` executor 命令、``ac_*`` MCP 工具，以及（適用時）Qt GUI 分頁。

.. contents::
   :local:
   :depth: 2


定位器與選擇器智慧化
====================

自我修復定位器
--------------

``影像樣板 → VLM 後備`` 並寫入 JSON-lines 稽核記錄，方便長期調校
不穩定的定位器::

    from je_auto_control import self_heal_click

    outcome = self_heal_click(
        template_path="submit.png",
        description="綠色的 Submit 按鈕",
    )

Executor：``AC_self_heal_locate / _click / _log_list / _log_clear``。
MCP：``ac_self_heal_*``。GUI：**Self-Healing** 分頁。

取消會原樣傳遞，中止後備定位、點擊與失敗紀錄。
稽核記錄在寫入與讀取時遮蔽本次執行已解析的秘密值。
定位結果保留原值；讀取時不會改寫既有紀錄檔。

兩條策略共用一次延遲邏輯截圖。``screen_region`` 均為 ``[左, 上, 右, 下]``，
裁切至實際桌面。未指定區域且有樣板時搜尋所有螢幕，只有 VLM 時保留主螢幕請求；
自行擷取整個版面的 backend 即使收到主螢幕請求，也會保留其發布的原點。
無效 bbox 在截圖前拒絕，擷取失敗也不會再為後備策略重截。

Schema 2 增加 run／step ID（沿用作用中的動作日誌）、定位器身份、解碼樣板／設定版本、
frame hash、實際原點／尺寸、邏輯縮放、各策略與擷取耗時，以及 backend 與實際 model。
未知資料與無法取得的美元成本維持 null，舊記錄仍以 schema 1 載入。
PNG 只暫存在範圍內，離開時釋放。首個策略耗時包含擷取；擷取時間是其中一部分，不能重複相加。
原有結果格式與 ``duration_ms`` 只計定位的語意不變。

點擊紀錄在送出後結算：``issued`` 只表示輸入已送出，``error`` 記錄一般失敗並原樣傳遞例外。
沒有明確操作後證據時，``verified`` 維持 null。取消不追加完成事件。
GUI 可輸入區域，查看操作狀態與所選記錄的 JSON 證據；即時控制項放在執行紀錄子分頁，
與固定影像比較分開。Script Builder 提供兩個即時命令，JSON 欄位可保留結構化區域。


明確的點擊後驗證
^^^^^^^^^^^^^^^^

實驗性不可變請求 API 預設只定位。驗證須明確指定 ``operation="click"``。
Python ``VerificationRequest`` 必須擇一提供回傳 bool 的 ``verifier`` callback，
或交由已設定 VLM 檢查的 ``description``。VLM 檢查可能產生 API 費用::

    from je_auto_control import SelfHealRequest, VerificationRequest, self_heal_run

    result = self_heal_run(SelfHealRequest(
        template_path="submit.png",
        operation="click",
        verification=VerificationRequest(description="確認訊息已顯示"),
    ))
    # result.verified 為 True、False 或 None；找到元素本身不是操作驗證。

在送出輸入前檢查 VLM 是否可用。只有點擊成功送出後才執行驗證，並重新取得邏輯 PNG。
驗證 bbox 獨立於定位 bbox；未指定驗證區域時請求主螢幕。驗證 model 未指定時沿用定位的
明確 model。Callback 在點擊前影像範圍之外執行，VLM 與其巢狀視覺助手只共用新影像。
驗證失敗、例外或取消均不會重試點擊。

``AC_self_heal_run`` 與 MCP ``ac_self_heal_run`` 接受巢狀 JSON ``request``::

    [["AC_self_heal_run", {"request": {
        "template_path": "submit.png", "operation": "click",
        "verification": {"description": "確認訊息已顯示"}
    }}]]

JSON 驗證支援 description、model、screen_region，不接受任意 Python callback／backend。
樣板受作用中路徑根目錄限制，進度通知前後也會重新檢查。明確 false 驗證使 AC／CLI 拋出
保留結果的 ``SelfHealVerificationError``（CLI exit 1），MCP 則回傳結構化結果與 ``isError``。
Python 請求 API 將 false 當成結果資料；例外與取消均原樣傳遞。

稽核區分 ``verified``、``verification_failed``、``verification_error`` 與 ``issued``／未知。
新增可選驗證描述、frame hash、backend／model、錯誤欄位及獨立的 verify 耗時；
``duration_ms`` 仍只計定位。Callback 不宣稱影像來源證據，舊記錄保持可讀。
GUI **Self-Healing** 提供選填的操作後條件，提示使用已設定 VLM 可能產生費用，並要求選擇點擊。
Script Builder 的新命令提供結構化 JSON 請求欄位。

獨立 VLM 擷取也改用記憶體邏輯影像及 Retina 正規化，保留裁切／非零原點。
``verify_description`` 會拒絕非 bool 後端回覆。Framework assertion 會在後備前中止定位復原。
上述行為有受控測試，真機與付費 API 驗收仍暫緩。


原始步驟追溯
^^^^^^^^^^^^

在已擷取的 executor 動作中，自癒紀錄會保存可選 ``journal_path`` 與 run／step ID。
直接呼叫、舊紀錄或沒有動作步驟綁定的 run scope 不會產生來源路徑。
正規路徑若含本次已解析的秘密文字，也不保存。明確查閱只會讀取資料::

    from je_auto_control import inspect_heal_source

    snapshots = inspect_heal_source(event.journal_path, event.run_id, event.step_id)

``AC_self_heal_source`` 與 MCP ``ac_self_heal_source`` 接受 ``path``（紀錄的 journal_path）、
``run_id``、``step_id`` 及可選 ``limit``。CLI 動作檔可使用相同指令，Script Builder 提供欄位。
MCP 的唯讀標記不會授予 viewer 讀取私有日誌的權限。

在 **Self-Healing → 執行紀錄** 選取紀錄後，使用 **動作 → 檢視原始步驟**。
原始步驟子分頁沿用共用背景讀取器；Run History 也能選填步驟 ID。
變更所選自癒紀錄會清除並取消舊來源檢視，關閉時取消讀取，舊結果不能覆蓋新目標。新目標會在舊讀取停止後啟動，保留請求者脈絡；
關閉也會取消待處理的讀取。
舊紀錄會顯示來源不可用，不捏造連結。檔案不存在或 ID 不符時回傳空快照；格式錯誤則驗證失敗。

``inspect_journal`` 新增可選 ``step_id``；run／step 篩選先於 1–10,000 的輸出上限，
整份檔案仍須驗證。進入、每次進度通知前後及回傳前都重查作用中路徑根目錄。
取消原樣傳遞且不回傳部分結果；開始／完成快照維持分開並經過清理。
來源查閱不會執行任何已記錄指令。


審閱候選模板
^^^^^^^^^^^^

實驗性候選流程只使用明確提供的檔案，不截圖、不輸入，也不呼叫模型。
新的不可變 schema-1 JSON 版本包保存精確原始位元組、依目標 PNG／JPEG／BMP
格式編碼的候選、雜湊、標準化目標路徑及比對閾值::

    from pathlib import Path
    from je_auto_control import (
        create_template_candidate, preview_template_candidate,
        verify_template_candidate, accept_template_candidate,
        revert_template_candidate, write_healing_report,
    )

    create_template_candidate("submit.png", Path("candidate.png").read_bytes(),
                              "candidate.json", threshold=0.9)
    reviewed = preview_template_candidate("candidate.json")
    checked = verify_template_candidate("candidate.json", "dataset.json")
    write_healing_report(checked.comparison, "comparison.html")
    if checked.eligible:
        accepted = accept_template_candidate("candidate.json", "dataset.json",
                                             reviewed.state.revision)
        reverted = revert_template_candidate("candidate.json", reviewed.state.revision)

預覽回傳每邊最多 512 像素的兩張 PNG 縮圖與完整尺寸資訊。
影像上限為 16 MiB／1,600 萬像素，版本包上限 48 MiB；建立時拒絕覆寫既有版本包，
也不更動目標。驗證沿用固定影像評估的 schema-1 樣本清單（清單 1 MiB、最多 500 樣本，
影像合計 64 MiB）。可省略 ``versions``；即使提供也會忽略，兩個固定版本均來自版本包::

    {"schema_version": 1, "samples": [
        {"id": "hit", "frame": "frame.png", "expected_box": [20, 16, 37, 29]},
        {"id": "miss", "frame": "absent.png", "expected_miss": true},
        {"id": "unknown", "frame": "unlabelled.png"}
    ]}

資格要求至少一個已標註目標、一個預期 miss，且全部已標註樣本正確。
未標註維持未知，原生操作是否成功另行驗證。JPEG 使用目標格式編碼後的實際像素驗證。
解碼／比對錯誤（包含正規化後的常數模板）會阻止接受。驗證使用記錄的閾值；啟用影像
不修改腳本的定位閾值，腳本應使用相符設定。

接受一定重新驗證資料集，並要求審閱時取得的 ``expected_revision``。
這是整份版本包位元組的 SHA-256，與執行時定位器版本雜湊不同。
取得目標鎖後，在最後進度檢查點之後再次檢查版本包雜湊、路徑與目前內容，才執行一次原子替換。
狀態依目前位元組判定為 original／candidate／conflict／missing，不代表核准歷史。
重複相同結果回傳 ``changed=False``；回復只在目前內容仍為此候選或原始版本時精確還原，
拒絕覆寫後續修改或缺失檔案。提交前取消會阻止替換；已完成替換不因後來取消而復原或改標失敗，
提交之後不再通知 observer。

Python 提供上述五個函式；JSON 動作／CLI 使用
``AC_template_candidate_create/preview/verify/accept/revert``，MCP 使用對應
``ac_template_candidate_*``。建立接受 ``template_path``、``candidate_path``（PNG）、
``bundle_path`` 與可選 ``threshold``；驗證／接受需要 ``dataset_path``，接受／回復需要
``expected_revision``。MCP 預覽另外回傳兩個影像區塊，JSON 入口回傳資訊。
所有操作均要求 drive 權限並遵守目前與外層路徑根目錄，包含版本包內的目標與已載入樣本。
Script Builder 提供五個命令；**Self-Healing → 候選模板** 以背景工作顯示縮圖、JSON 證據、
進度與取消，五項操作位於動作選單，四種介面語言均可使用。
``python -m examples.template_candidates`` 提供只使用合成影像和暫存檔案的範例。
真機與付費 API 驗收仍暫緩。


錨點定位器
----------

依「相對於錨點 A 的空間關係」找到元素 B。錨點與目標可以使用不同
backend — 每一部分挑成本最低、能唯一識別的方式::

    from je_auto_control import (
        anchor_locate, image_locator, ocr_locator,
    )

    outcome = anchor_locate(
        anchor=ocr_locator("Username"),
        target=image_locator("submit_green.png"),
        relation="below",
    )

關係：``above``、``below``、``left_of``、``right_of``、``near``。
Executor：``AC_anchor_locate / _click``。


結構化 OCR
----------

把 OCR 原始 match 聚合為 rows、tables（欄位對齊的 row 集合）以及
form-field ``label:value`` 對::

    from je_auto_control import ocr_read_structure
    result = ocr_read_structure(region=[0, 0, 1280, 800])
    for field in result.fields:
        print(field.label, "=", field.value)

Executor：``AC_ocr_read_structure``。


智慧等待
--------

用 frame-diff 取代 ``time.sleep``::

    from je_auto_control import wait_until_screen_stable
    wait_until_screen_stable(timeout_s=10.0, stable_for_s=0.5)

輔助函式：``wait_until_screen_stable``、``wait_until_pixel_changes``、
``wait_until_region_idle``。Executor：``AC_wait_screen_stable``、
``AC_wait_pixel_changes``、``AC_wait_region_idle``。


A/B 定位器框架
--------------

對同一目標並行跑 N 種策略，並推薦歷史上最佳的::

    from je_auto_control import ab_locate, ab_best_strategy

    outcome = ab_locate(
        target_id="submit_button",
        strategies={
            "image": image_locator("submit.png"),
            "ocr": ocr_locator("Submit"),
            "vlm": vlm_locator("綠色的 Submit 按鈕"),
        },
    )
    print("歷史最佳：", ab_best_strategy("submit_button"))

成績存放於 ``~/.je_auto_control/ab_locator_stats.json``。
Executor：``AC_ab_locate / _report / _best_strategy / _clear``。


維運與觀察性
============

成本遙測
--------

每次 LLM 呼叫的 token / USD 紀錄，並按天 / 模型 / 提供者彙總::

    from je_auto_control import record_llm_call, summarise_llm_costs

    record_llm_call(
        provider="anthropic", model="claude-opus-4-7",
        input_tokens=512, output_tokens=128, label="vlm_locate",
    )
    summary = summarise_llm_costs()
    print(summary.total_usd, summary.by_model)

``summarise_llm_costs()`` 不帶參數時彙總 ``default_cost_store`` 記錄的呼叫。內建價格表是 Anthropic
目前的 Claude 牌價(Fable 5.x、Opus 5.x / 4.x、Sonnet 5 / 4.x、Haiku 4.5 與較舊的系列;帶日期或
``anthropic.`` 前綴的 id 會以基本 id 查價)與 OpenAI；可單次呼叫覆寫。
Executor：``AC_costs_record / _summary / _list / _clear``。


追蹤重播 UI
-----------

在現有的 time-travel 錄影上建構可拖曳時間軸 — 讀取含
``manifest.json`` + ``actions.jsonl`` 的目錄，逐 frame 倒退並
旁列當時執行的動作。``TraceReplayController`` 提供純 Python 介面
供非 GUI 使用；**Trace Replay** 分頁則是其上的薄殼。


失敗 → 工單自動化
------------------

當排程任務、觸發器或 REST 工作失敗時，將失敗報告分送 Jira /
Linear / GitHub Issues::

    from je_auto_control import (
        FailureReport, GitHubBackend, default_failure_hook_manager,
    )
    default_failure_hook_manager.register(
        GitHubBackend(owner="acme", repo="ops",
                       token=os.environ["GH_TOKEN"]),
    )

錯誤文字、日誌尾端與 metadata 裡的憑證會在任何 backend 看到報告前先遮蔽;某個 backend 拋出例外時，
它會記成失敗的 ``TicketResult``,不影響其他 backend。

Executor：``AC_failure_hook_fire / _list / _clear``。


容器化 CI 模板
--------------

* ``.github/workflows/docker.yml`` — 在 Xvfb 容器內建置鏡像、跑
  headless pytest、smoke-test REST entrypoint。
* ``ci_templates/.gitlab-ci.yml`` — 透過 Docker-in-Docker 的同等
  GitLab pipeline。
* ``docker/Dockerfile.xfce`` — XFCE4 桌面 + x11vnc 變體，給需要
  真實 WM 的流程使用。

完整指南：``docs/source/getting_started/run_in_ci.rst``。


跨主機 DAG 編排
---------------

每個節點攜帶 ``(host, actions | action_file, depends_on)``。``local``
節點在本機 in-process 執行；其他節點透過 admin console REST client
分派。失敗會層層下游 cascade — 後續節點直接報告為 ``skipped``，
不會被嘗試::

    je_auto_control.run_dag({
        "nodes": [
            {"id": "step1", "host": "local", "actions": [...]},
            {"id": "step2", "host": "machine-a",
             "action_file": "x.json", "depends_on": ["step1"]},
        ],
    })

從別的執行緒設定 ``stop_event=``（``threading.Event``）即可停止：執行中的節點會跑完，
尚未開始的節點一律為 ``skipped``、錯誤為 ``"stopped"``。Executor：``AC_run_dag``。
GUI：**DAG Runner** 分頁，Actions 選單有 **停止 DAG**。


多 viewer 名單
--------------

為 multi-viewer 遠端桌面提供觀察者名單與「控制者 / 觀察者」角色。
純 Python 的 ``PresenceRegistry`` 獨立發佈，input dispatch 的角色
門禁可獨立單元測試（無需 aiortc）。

Executor：``AC_presence_register / _unregister / _update_cursor /
_set_role / _list / _clear``。GUI：**Viewer Roster** 分頁。


代理與整合
==========

Computer-use 高階 API
---------------------

封裝 :class:`ComputerUseAgentBackend` + :class:`AgentLoop`，一次呼叫
即可驅動 Anthropic 的 computer-use tool(預設是 ``claude-opus-5`` 上的 ``computer_20251124``,
以對應的 ``computer-use-2025-11-24`` beta 送出;``tool_type=`` 可換版本,``beta=`` 指定它的 beta)。
``model="claude-opus-5-5"`` 只接受 GA 的 ``computer_toolset_20260801``,backend 會改送這個形式:不帶 beta、
一回合可有多個動作,截圖先縮到模型的影像上限內(長邊 2576 px、4784 visual tokens,1080p 螢幕不必縮),
模型給的座標再換算回螢幕座標;``zoom`` 以該區域的全解析度裁切回覆::

    from je_auto_control import run_computer_use
    result = run_computer_use(
        "開啟計算機，計算 12 * 7，截圖結果",
        max_steps=15, wall_seconds=120.0,
    )

自動偵測螢幕大小。截圖會縮到模型的影像層級內(Claude 4.7 以後:2576 px／4784 visual tokens;較舊的模型:1568 px／1568 tokens),
beta 工具也一樣:它宣告縮放後的大小為螢幕大小,再把模型給的座標換算回螢幕。以 ``max_steps`` + ``wall_seconds`` 為預算上限，
避免失控的 loop 把 API 額度耗光；設定 ``stop_event=``（``threading.Event``）會在下一步之前結束，
``final_message`` 為 ``"stopped"``。Executor：``AC_computer_use``。
GUI：**Computer Use** 分頁，Actions 選單有 **停止**。關閉視窗時會請執行中的工作停止，最多等 10 秒。

Anthropic 的兩個 backend（這一個，以及 ``AC_run_agent`` 背後的 ``AnthropicAgentBackend``）不會改寫已送出的回合。
對話裡的截圖將超過三張（或合計超過 20 MB）時，下一個請求改開一段新的對話：只有一則訊息，內容是目標、
目前為止執行過的動作與各自的結果，再加上當下的截圖。較早的回合與其中的 thinking 區塊不會重播，
模型只憑這份摘要接續。OpenAI backend 仍是就地把較舊的截圖換成文字。


WebRunner 接入 executor + MCP
-----------------------------

在既有 ``je_web_runner`` 橋接之上提供新的便利命令::

    je_auto_control.web_open("https://example.com")
    je_auto_control.web_screenshot("loaded.png")
    je_auto_control.web_quit()

Executor：``AC_web_open / _quit / _screenshot / _current_url``
（加上既有的 ``AC_web_run``）。MCP 同步以 ``ac_web_*`` 暴露。
GUI：**WebRunner** 分頁；Script Builder：**Browser** 分類。

``["AC_web_run", {"action": "WR_to_url", "params": {"url": "..."}}]``
在安裝的 WebRunner 有 ``execute_one`` 時，經由它執行單一 ``WR_*`` 命令
（WebRunner 的命令閘門、重試策略與失敗截圖）。命令失敗時拋出
``WebRunnerBridgeError``，executor 會像其他失敗的動作一樣記下它，
腳本繼續執行。


Chat-ops 機器人
----------------

傳輸層中立的 ``CommandRouter`` 加上 Slack polling adapter，
``/run <script>`` 經 Slack 進入和 scheduler 相同的執行路徑。
內建命令：``/help``、``/scripts``、``/run``、``/screenshot``、
``/status``。``/screenshot [name]`` 寫進 context 的 ``screenshot_dir``
（預設為暫存目錄下的 ``je_auto_control_chatops``），給的名稱只保留檔名。
Slack adapter 走套件的 HTTP client，所以出站政策同樣適用。
RBAC 透過 ``required_role`` 參數。
GUI：**Chat-Ops** 試用分頁。


平台覆蓋
========

Wayland CLI backend
-------------------

直接可用的 Wayland 後端，分別呼叫 ``wtype``（鍵盤輸入）、
``ydotool``（按鍵 + 滑鼠）、``grim``（截圖）。import 時自動偵測
``XDG_SESSION_TYPE=wayland`` / ``WAYLAND_DISPLAY``，當 CLI 工具未
安裝時回退到 X11 (XWayland)。

覆寫::

   export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11      # 強制 XWayland
   export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=wayland  # 強制 Wayland
   export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=auto     # 預設


Wayland libei native backend
----------------------------

對 ``libei.so.*`` 的 ctypes 綁定，繞過 CLI shim 取得微秒級延遲。
以 ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei|cli|auto`` 啟用；
``auto`` （預設）只在選用原生後端缺席時改用 CLI。portal 拒絕／逾時、
握手失敗、裝置暫停或權限撤銷會停止原生按鍵／按鈕／指標輸入，不會自動改走 CLI。
重複失敗呼叫不重開同意對話框。``libei`` 強制原生輸入，``cli`` 明確選擇工具。
解決權限問題後，明確呼叫
``je_auto_control.linux_wayland.libei.reset_default_backend()`` 才允許重新請求。
組合鍵中斷會在同一後端嘗試釋放每個已按下的按鍵，並保留原始取消。
明確的 wtype 文字輸入路徑與螢幕擷取選擇不變。


Diagnostics 開啟時先顯示已翻譯的「尚未執行」狀態。選擇 **Actions → 執行診斷**
才會啟動既有主動檢查，可能擷取螢幕或要求 portal 同意。開啟或切換語系不啟動檢查。
明確的 headless／AC／MCP 診斷維持主動行為，無副作用的能力探測仍列於 ``Progress.md``。


未完成的 screenshot 請求會在原始 bus 上以獨立 0.25 秒 I/O 預算嘗試
``org.freedesktop.portal.Request.Close``，跟隨替代 handle，回覆不確定時使用預測 handle。
已完成的 Response 不重複關閉；原始取消與強制中斷物件穿過包裝及清理繼續傳播。
D-Bus 寫入與回覆共用預算，connect／驗證／Hello 中斷時，即使 ``__enter__`` 未完成
也會釋放描述元。原生合成器／對話框、restore 與重啟驗收仍列於 Progress.md。


repo 的 dev／main 無頭工作在原生失敗後仍保留合併測試輸出與執行環境版本。
Linux 經 GDB 擷取各執行緒原生堆疊，其他平台保留 Python faulthandler 輸出。
``native-<os>-<python>`` artifact 保留七天；子行程失敗仍使 CI 失敗。
Linux 先在完整套件的 debugger 外檢查工具，保留原始 argv 與已處理的 SIGINT。
重現方法見 :doc:`/getting_started/run_in_ci`。蒐集證據不代表完成尚缺的 portal／原生生命週期驗收。


macOS Accessibility：tree dump + recorder
-----------------------------------------

擴充 macOS AX backend，新增遞迴 tree dump
(``dump_accessibility_tree()``) 與 polling 事件 recorder
(``AccessibilityRecorder``) 來捕捉 focus / bounds 變化。

Executor：``AC_a11y_dump``、``AC_a11y_record_start / _stop /
_events``。


開發者體驗
==========

autocontrol-lsp 完整化
----------------------

language server 現在會追蹤文件（``didOpen`` / ``didChange`` /
``didClose``）、為無效 JSON 與未知 ``AC_*`` 命令發佈 diagnostics，
並由即時的 ``Executor.event_dict`` 產生 signature help。schema
驗證會在執行前抓出未知命令與格式錯誤的 action list。


``.pyi`` stub 產生器
--------------------

執行::

   python -m je_auto_control.utils.stubs.generator \
       je_auto_control/actions.pyi

即可更新 IDE 端的 stub 檔。IDE（PyCharm、VS Code 透過 Pylance、
Pyright）會透過標準的 ``actions.pyi`` 查找，使每一個 ``AC_*``
命令都能 autocomplete 並顯示參數提示。


VS Code 擴充
------------

``autocontrol-lsp/vscode/`` 的擴充新增三個命令::

   AutoControl: Run current script via REST API
   AutoControl: Take screenshot (REST API)
   AutoControl: Preview script as step tree

REST URL 與 bearer token 來自 VS Code settings
(``autocontrolLsp.rest.url`` / ``autocontrolLsp.rest.token``)，
若空則 fallback 到 ``$AC_TOKEN`` 環境變數。


瀏覽器擴充錄製器
----------------

``browser-extension/`` 是一個 Manifest V3 擴充，捕捉瀏覽器分頁裡
的點擊、輸入、導航與表單提交，匯出成可由 ``AC_web_*`` / ``WR_*``
驅動的 AutoControl JSON action 檔。CSS selector 會優先使用
``data-testid`` / ``data-cy`` / ``name`` / ``nth-of-type``
路徑，貼近實務寫法。


pytest plugin + Gherkin BDD
---------------------------

安裝 ``je_auto_control`` 會註冊 ``pytest11`` entry point，plugin
自動載入。Fixtures（``autocontrol``、``autocontrol_executor``、
``autocontrol_screenshot_dir``）與 ``@pytest.mark.autocontrol``
marker 會在失敗時自動截圖。
``bdd_steps.register_pytest_bdd_steps(pytest_bdd)`` 一次註冊
``Given / When / Then`` 步驟對應到每一個公開的 ``AC_*`` verb。


視覺流程編輯器
--------------

AC JSON 腳本的 node-based 視圖。與 list-based **Script Builder**
共用同一份 JSON 格式 — 兩個視圖完全相容。純 Python 的 layout
helper（``je_auto_control.gui.flow_editor.layout_steps``）可單元
測試（無需 Qt）。


通用 agent 迴圈（JSON + MCP）
-----------------------------

``AC_run_agent`` / ``ac_run_agent`` 把閉環 ``AgentLoop``
（規劃 → 執行 → 驗證 → 重試）開放給 JSON action 與 MCP。參數：

* ``goal`` — 自然語言目標。
* ``backend`` — ``"anthropic"`` 或 ``"openai"`` 。 ``AC_run_agent`` 預設只提供聚焦、低風險的
  computer-use allow-list，不再把完整的 ``AC_*`` 命令目錄交給模型。需要自訂工具集時，
  可直接用 ``export_anthropic_tools(only=[...])`` 或 ``export_openai_tools(only=[...])`` 建立 backend。
* ``max_steps`` （預設 25）、 ``wall_seconds`` （預設 300.0）。
* ``model`` / ``max_tokens`` — backend 專屬覆寫。

每次向模型發出的請求 120 秒逾時，對話裡只重送最新的三張截圖（較早的換成一行文字），
長時間執行也不會超過 API 的請求大小上限。``export_anthropic_tools(only=[...])``
只提供列出的指令——空清單就是一個都不提供。

Anthropic 原生 Computer-Use 路徑（``computer_20251124``）仍透過
``AC_computer_use`` / ``ac_computer_use`` 提供，適合需要由模型
直接看見桌面像素的場景。


截圖 PII 遮罩
-------------

新模組 ``je_auto_control.utils.redaction``：``RedactionEngine``
加上三個現成政策（``POLICY_OFF / MODERATE / STRICT``）。
內建偵測器：

* 對呼叫端提供的 OCR token 做 regex — email、信用卡、SSN、電話。
* Accessibility tree 的 secure-text 欄位（engine 讀
  ``context["accessibility"]`` 內 ``[{"is_password": True, "bbox":
  [x1, y1, x2, y2]}, ...]``）。
* 強制模糊區域，覆蓋規則看不到的疊加層。

預設政策由環境變數 ``JE_AUTOCONTROL_REDACTION``
（``off`` / ``moderate`` / ``strict``）決定。逐次呼叫：

.. code-block:: python

   from je_auto_control import redact_png_bytes, POLICY_STRICT
   redacted_bytes, result = redact_png_bytes(png_bytes, policy=POLICY_STRICT)

``AC_redact_screenshot`` 與 ``ac_redact_screenshot`` 從磁碟讀取
PNG、跑 engine、寫回 ``output_path`` （未指定時覆蓋原檔），並回傳
合併後的 bounding box list 供稽核。


Android backend（uiautomator2 widget tree）
-------------------------------------------

在既有 ``AC_android_tap / swipe / key / text / screenshot`` 的
adb-shell 路徑之上加上 widget-aware 自動化：

* ``AC_android_find_element`` — 以 ``text`` / ``resource_id`` /
  ``description`` / ``class_name`` 為 selector，回傳
  ``{x1, y1, x2, y2}``。
* ``AC_android_click_element`` — 同樣的 selector，點擊中心並
  回傳 ``{x, y}``。
* ``AC_android_dump_hierarchy`` — 即時 XML widget tree。

Python 入口為 ``je_auto_control.android.UIAutomatorDevice``，支援
``serial`` 指定多裝置。``uiautomator2`` 為可選相依、懶載入。


iOS backend（XCUITest via WebDriverAgent）
------------------------------------------

新增命名空間 ``je_auto_control.ios``：

* ``tap`` / ``long_press`` / ``swipe`` / ``type_text`` /
  ``press_key`` — 觸控與按鍵原語。
* ``screenshot`` / ``screen_size`` — 擷取與尺寸。
* ``find_element`` / ``click_element`` — selector：``name``
  （label / accessibility id）、``class_name``
  （``XCUIElementTypeButton`` …）或完整 ``predicate``
  （NSPredicate 字串）。
* ``dump_source`` — XCUITest 頁面 source XML。

新增 7 個 ``AC_ios_*`` executor 命令與對應 ``ac_ios_*`` MCP 工具。
``facebook-wda`` 為可選 pip 相依、懶載入，非 macOS 主機 import
``je_auto_control.ios`` 仍可成功。

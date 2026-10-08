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

``screen_region`` 是螢幕座標的 ``[x1, y1, x2, y2]``，\ **兩種**\ 策略都受它限制；
以前只有 VLM 收到它，樣板比對可能在區域之外回報命中。

**找到不等於驗證過。** ``HealOutcome.found`` 只表示某個策略回傳了一個點。
點擊有沒有達到目的是另一個欄位 ``action_verified``，由呼叫端傳入的檢查填入——
沒有檢查時是 ``None``，絕不從命中推論::

    outcome = self_heal_click(
        template_path="submit.png",
        description="綠色的 Submit 按鈕",
        verify=lambda result: dialog_is_open(),
    )
    outcome.found            # 回傳了一個點
    outcome.action_verified  # 檢查結果 True / False，沒有檢查則為 None

自愈記錄新增選用欄位（``schema_version``、``run_id``、``step_id``、``locator_id``、
``locator_version``、``backend``、``model``、``screen_region``、``image_ms``、
``vlm_ms``、``action``、``action_verified``）。這些欄位出現之前寫入的記錄仍可讀取，
缺少的欄位為 ``None``。識別資訊由呼叫端標註::

    from je_auto_control import heal_context

    with heal_context(run_id="nightly-42", locator_id="submit", locator_version="v2"):
        self_heal_click(template_path="submit.png")

從 JSON 動作或 MCP 呼叫時，把同樣的鍵放在 ``AC_self_heal_locate`` /
``AC_self_heal_click`` 的 ``context`` 參數。JSON 步驟無法攜帶檢查函式，所以它的
``action_verified`` 會維持 ``None``。``AC_heal_stats`` 另外回報
``action_verification``（``actions`` / ``verified`` / ``failed`` / ``unchecked``），
與只計算「有回傳座標」的 ``healed`` 分開。

量測定位器版本
~~~~~~~~~~~~~~

``evaluate_locators`` 讓每個策略版本跑同一批已標註的畫面——每個樣本只有一張
擷取畫面、一個區域、一組原點與縮放，所有版本收到同一個 request 物件——再替答案計分::

    from je_auto_control import (
        EvaluationSample, evaluate_locators, template_match_strategy,
    )

    samples = [
        EvaluationSample("submit", frame, expected_box=(100, 60, 156, 92),
                         template="submit.png"),
        EvaluationSample("left-monitor-150", hidpi_frame,
                         expected_box=(-1880, -180, -1824, -148),
                         origin=(-1920, -300), scale=1.5, template="submit.png"),
        EvaluationSample("dialog-closed", other_frame, expect_miss=True,
                         template="submit.png"),
    ]
    comparison = evaluate_locators(samples, {
        "v1": template_match_strategy(0.9),
        "v2": template_match_strategy(0.9, scales=(1.0, 1.25, 1.5, 2.0)),
    })
    report = comparison.report("v2")
    report.accuracy          # Ratio(分子, 分母)；分母為 0 時 .value 是 None
    report.recovery_rate     # v1 失敗而 v2 正確命中的目標
    report.p50_ms, report.p95_ms
    comparison.failures("v2")

計分方式：

* 命中點落在 ``expected_box`` 內才是 ``correct``；落在別處，或樣本標為
  ``expect_miss`` 卻命中，都是 ``false_positive``——有找到，但不算恢復；
* 既沒有 ``expected_box`` 也沒有 ``expect_miss`` 的樣本是 ``unknown``，
  只計入命中率，不計入任何宣稱正確的比率；
* 策略拋出例外記為 ``error``，即使該樣本預期 miss；
* 策略若修改了畫面，會以 ``HealingEvaluationError`` 拒絕：下一個版本量到的
  就不是同一張圖了。

座標一律是螢幕座標。``origin`` 是畫面左上角像素的螢幕位置（在主螢幕左方或上方的
螢幕為負值），``scale`` 是每一個螢幕單位對應的畫面像素數。

資料集也可以是一個 JSON 檔，畫面影像放在它旁邊；Executor 指令、MCP 工具與 GUI
評估的就是這種檔案::

    {"schema_version": 1,
     "samples": [{"id": "submit", "frame": "frames/submit.png",
                  "template": "submit.png",
                  "expected_box": [100, 60, 156, 92],
                  "origin": [0, 0], "scale": 1.0, "region": null}],
     "versions": {"v1": {"strategy": "template", "threshold": 0.9},
                  "v2": {"strategy": "template", "threshold": 0.9,
                         "scales": [1.0, 1.5]}},
     "thresholds": {"v2": {"min_correct": 1, "max_false_positive": 0}}}

    from je_auto_control import evaluate_healing_dataset
    payload = evaluate_healing_dataset("dataset.json")
    payload["passed"], payload["violations"]

影像路徑相對於資料集檔案，且不得離開它所在的目錄。JSON 裡只能指名 ``template``
策略；要評估 VLM，請把包裝它的 callable 傳給 ``evaluate_locators``。

``benchmarks/self_healing/run.py`` 是固定的回歸資料集：十張在記憶體中繪製的畫面
（一般、125%／150% 縮放、負原點螢幕、必須選中兩個相同目標中第二個的區域、
改版後的控制項、目標不存在、相似的鄰近控制項、一張未標註畫面）與三個版本。
它不擷取螢幕::

    python benchmarks/self_healing/run.py --check --json report.json

候選樣板修訂
~~~~~~~~~~~~

自愈得到的點絕不直接覆寫樣板。新影像只是候選，必須先預覽才能取代任何東西::

    from je_auto_control import (
        propose_template_revision, preview_template_revision,
        accept_template_revision, revert_template_revision,
    )

    revision = propose_template_revision("submit.png", "submit_new.png")
    preview = preview_template_revision(revision.revision_id,
                                        dataset_path="dataset.json")
    preview["revision"]["validated"]
    accept_template_revision(revision.revision_id)   # 保留備份
    revert_template_revision(revision.revision_id)   # 還原備份

``propose`` 與 ``preview`` 都不會動到樣板。給了資料集（或 ``samples=``）時，
preview 會讓現行樣板與候選樣板跑同一批畫面；候選必須至少正確一次、正確次數不少於
現行樣板、且沒有 false positive 或 error，才會標為 ``validated``。``accept`` 會拒絕
未驗證的候選，除非傳入 ``allow_unvalidated=True``；樣板檔在修訂之後被別人改過時，
``accept`` 與 ``revert`` 都會拒絕。修訂存放在 ``~/.je_auto_control/template_revisions``。

Executor：``AC_self_heal_evaluate``、``AC_self_heal_revision_propose /
_preview / _accept / _revert / _list``。MCP：``ac_self_heal_evaluate``、
``ac_self_heal_revision_*``。GUI：**Self-Healing** 分頁 → Actions 選單
（*評估資料集*、*提出／預覽／接受／回復修訂*）。


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
``auto``\ （預設）在 libei 可載入時用 libei，否則用 CLI，現有
部署不會中斷。


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
* ``backend`` — ``"anthropic"`` 或 ``"openai"``。``AC_run_agent`` 預設只提供聚焦、低風險的
  computer-use allow-list，不再把完整的 ``AC_*`` 命令目錄交給模型。需要自訂工具集時，
  可直接用 ``export_anthropic_tools(only=[...])`` 或 ``export_openai_tools(only=[...])`` 建立 backend。
* ``max_steps``\ （預設 25）、``wall_seconds``\ （預設 300.0）。
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
PNG、跑 engine、寫回 ``output_path``\ （未指定時覆蓋原檔），並回傳
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

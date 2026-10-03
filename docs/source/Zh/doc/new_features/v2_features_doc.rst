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

對 ``libei.so.*`` 的 ctypes 綁定，提供原生輸入。
以 ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei|cli|auto`` 啟用；
``auto``（預設）使用 libei；缺少相依回報型別化錯誤。
CLI 需明確選擇，拒絕授權不觸發替代輸入。


授權與能力診斷
~~~~~~~~~~~~~~

``probe_capabilities()``（Beta ``je_auto_control.api.capabilities``）、
``AC_probe_capabilities`` 與 MCP ``ac_probe_capabilities`` 分別回報輸入／擷取狀態，不請求授權、不送輸入、不截圖，
也不載入原生函式庫。XWayland 只涵蓋 X11 用戶端。原生授權取消、失敗或撤銷時停止輸入；
CLI 需明確設定 ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli``。診斷 Actions 選單可
停止原生輸入或允許下一次明確請求重新授權。現有綁定不支援 restore token，亦不保存 token。

GUI 與 ``AC_diagnose`` 預設被動檢查；``AC_diagnose include_active=true`` 才執行截圖／游標
檢查。Python 使用 ``run_diagnostics(include_active=False)`` 跳過上述主動檢查。
這些本機功能不需要付費 API 或 API key；找到工具不代表已有合成器實機驗證。



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
自動載入頂層 ``je_auto_control_pytest``，只匯入 pytest；使用 fixture
或失敗截圖時才匯入自動化核心。升級 editable 工作樹後須重新安裝以更新
入口 metadata；明確載入 ``je_auto_control.utils.pytest_plugin`` 仍相容。Fixtures（``autocontrol``、``autocontrol_executor``、
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
* ``backend`` — ``"anthropic"``（透過 ``export_anthropic_tools()``
  以 tool-use messages 驅動；每張截圖先縮到模型的影像層級內，工具呼叫的 ``x`` / ``y`` 再換算回螢幕）或 ``"openai"``（``export_openai_tools()``
  + Chat Completions function calling）。
* ``max_steps``（預設 25）、``wall_seconds``（預設 300.0）。
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
PNG、跑 engine、寫回 ``output_path``（未指定時覆蓋原檔），並回傳
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


舊版 CLI 失敗狀態
-----------------

``python -m je_auto_control -e/-d/--execute_str`` 的動作失敗會回傳結束碼 1，
與 ``je_auto_control run`` 一致；成功回傳 0。目錄執行累積所有檔案失敗，stderr 回報失敗數。


執行變數範圍
------------

每次公開呼叫建立獨立範圍；巢狀呼叫共用當次範圍，平行分支與 DAG 工作執行緒
深複製變數。REST／MCP 請求各自隔離。明確持有的 ``Executor`` 在公開範圍外保留狀態。
需要跨呼叫共用並讀取結果時::

    import je_auto_control as ac
    with ac.execution_scope({"seed": "hello"}) as scope:
        ac.execute_action([["AC_set_var", {"name": "result", "value": "${seed}"}]])
        assert scope["result"] == "hello"

平行變數中的自訂物件須支援深複製。``isolated=True`` 可建立獨立巢狀範圍，離開時還原父層。


USB 請求配對
------------

JSON 操作可攜帶最多 64 字元的 ``request_id``。新版 client 產生 ID，主機在
OPEN／RESUME、LIST、transfer、CLOSE、ERROR 與 CREDIT 回傳同一 ID；分片重組後才配對。
遲到回覆不能完成另一個請求。credit 必須符合請求與 claim，且只套用一次；
遲到 OPEN 產生的未使用 claim 會自動關閉。二進位框標頭不變，仍相容舊端點。

舊版或能力未確認的主機回覆逾時後，client 關閉並取消 pending，handle 的 ``closed`` 為真。
重試前須重連傳輸並建立新的 ``UsbPassthroughClient``。已確認 ID 配對能力的端點可繼續以新 ID 重試。

動作檔簽章的公鑰部署與遷移
---------------------------

Ed25519 第 2 版 JSON 側檔驗證原始檔案位元組、公鑰指紋及用途前綴。
金鑰接受 32 位元組原始格式或 Ed25519 PEM；建立時保留既有金鑰，拒絕不匹配組合。
新金鑰檔採 0600 模式；Windows 請使用主機 ACL 保護私鑰。

離線簽署端建立金鑰並簽署::

    je_auto_control signing-keygen --private-key private.pem --public-key public.pem
    je_auto_control sign flow.json --private-key private.pem

執行端只部署 flow.json、flow.json.sig、public.pem。將
JE_AUTOCONTROL_SIGNING_PUBLIC_KEY 設為公鑰的絕對路徑，並設定
JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS=1。執行端不設定
JE_AUTOCONTROL_SIGNING_PRIVATE_KEY；驗證不會建立金鑰::

    je_auto_control verify flow.json --public-key public.pem
    je_auto_control run flow.json

Python API 同樣分離私鑰與公鑰::

    from pathlib import Path
    import je_auto_control as ac
    ac.create_signing_keypair(Path('private.pem'), Path('public.pem'))
    ac.sign_action_file('flow.json', private_key_path='private.pem')
    assert ac.verify_action_file('flow.json', public_key_path='public.pem').verified

Script Builder 提供 AC_create_signing_keypair、AC_sign_action_file 與
AC_verify_action_file；MCP 使用對應 ac_ 名稱。產生與簽署會修改檔案，
唯讀 MCP 不會提供這兩個工具。

舊版十六進位 HMAC 與第 1 版側檔預設拒絕。遷移時先明確驗證，再離線重簽::

    je_auto_control verify old.json --allow-legacy-hmac --legacy-key-file old.key
    je_auto_control sign old.json --private-key private.pem

Python 驗證需 allow_legacy_hmac=True 與明確的舊金鑰內容；強制驗簽的載入器
另需 JE_AUTOCONTROL_ALLOW_LEGACY_HMAC=1 與指向既有金鑰檔的
JE_AUTOCONTROL_LEGACY_SIGNING_KEY。遷移完成後移除兩項設定。
舊版簽署需 legacy_hmac=True 及明確金鑰，不會自動建立個人金鑰或退回私鑰驗證。

強制驗簽檢查檔案載入器，內嵌動作清單不驗簽；這不會隔離脚本或阻止已授權
操作者改動主機。私鑰必須留在簽署端；使用者角色授權另行處理。

MCP 檔案與引用邊界
------------------

JE_AUTOCONTROL_MCP_ROOTS 使用 OS 路徑分隔符列出允許根目錄；client 的
roots/list 只會與部署設定取交集，不能擴權。多根目錄與 HTTP 連線各自獨立，
檔案資源也使用同一有效根目錄。明確空清單拒絕檔案參數；未配置、也沒有
client roots 時保留相容檔案存取。唯讀模式需另外設定，不會自動開啟。

真正的檔案欄位使用 format=path 與讀寫語意標記；巢狀附件、DAG action_file、
定位樣板與輸出路徑同樣檢查。圖片模式的 target 才是路徑；文字、JSONPath、
SBOM 套件名稱及 URL 保留原義。相對路徑從第一個有效根目錄解析；realpath
拒絕 symlink 越界，尚未建立的輸出路徑也會檢查。

MCP 預設拒絕 env://，需在 JE_AUTOCONTROL_MCP_ALLOWED_ENV 以逗號列出明確名稱。
巢狀 env:// 與 file:// 使用同一呼叫策略；記錄型入口繼續拒絕 secret://。
本機無頭 API 可明確套用限制::

    from pathlib import Path
    import je_auto_control as ac
    policy = ac.PathPolicy(roots=[Path('workspace')], allowed_env=['BUILD_ID'])
    value = ac.resolve_ref('file://settings.txt', policy=policy)

本機 Python 未指定策略時保留原行為；遠端呼叫經 executor 引用 adapter 仍受
同一策略限制。此檢查限制已標記參數及引用；任意腳本／程序工具與可信預設儲存
仍需使用者授權，並非防止本機檔案系統競態的 OS 沙箱。外掛須用同一 schema
metadata 標記自己的檔案欄位。

Viewer 收檔遷移
----------------

TCP／WebSocket viewer 收檔預設使用 ~/Downloads/AutoControl，本機可用
JE_AUTOCONTROL_DOWNLOAD_DIR 改變目錄。Host 使用相對目的地::

    host.send_file_to_viewers('local.bin', 'reports/from_host.bin')

絕對路徑、磁碟相對路徑、UNC、上層穿越、NUL、替代串流及 symlink 越界在
開啟 part 檔之前被拒絕，完成時在替換目的檔前再次檢查；不完整傳輸的既有
保護仍保留。Host 的 FileReceiver() 保留原行為。本機可指定其他受限目錄::

    from pathlib import Path
    from je_auto_control import FileReceiver
    viewer.set_file_receiver(FileReceiver(base_dir=Path('downloads')))

GUI 使用相同預設邊界；WebRTC 保留既有受限 inbox 與檔名協定。舊 host 絕對
目的地範例須改為相對檔名；本機仍可明確選擇自訂、不限制根目錄的 receiver。

Registry 發布名稱
-----------------

預設 manifest 名稱改為 io.github.integration-automation/autocontrol，專案網址為
https://github.com/Integration-Automation/AutoControlGUI。穩定 PyPI 套件仍為
je_auto_control，dev.toml 保留 je_auto_control_dev。發布前重新產生 server.json
以使用已核准命名空間；自訂 name／repository_url 參數繼續支援。

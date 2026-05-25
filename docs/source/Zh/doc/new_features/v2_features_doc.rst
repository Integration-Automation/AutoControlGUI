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

內建價格表涵蓋 Claude 4.x 與 OpenAI；可單次呼叫覆寫。
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

Executor：``AC_run_dag``。GUI：**DAG Runner** 分頁。


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
即可驅動 Anthropic 官方 ``computer_20250124`` tool::

    from je_auto_control import run_computer_use
    result = run_computer_use(
        "開啟計算機，計算 12 * 7，截圖結果",
        max_steps=15, wall_seconds=120.0,
    )

自動偵測螢幕大小；以 ``max_steps`` + ``wall_seconds`` 為預算上限，
避免失控的 loop 把 API 額度耗光。Executor：``AC_computer_use``。
GUI：**Computer Use** 分頁。


WebRunner 接入 executor + MCP
-----------------------------

在既有 ``je_web_runner`` 橋接之上提供新的便利命令::

    je_auto_control.web_open("https://example.com")
    je_auto_control.web_screenshot("loaded.png")
    je_auto_control.web_quit()

Executor：``AC_web_open / _quit / _screenshot / _current_url``
（加上既有的 ``AC_web_run``）。MCP 同步以 ``ac_web_*`` 暴露。
GUI：**WebRunner** 分頁。


Chat-ops 機器人
----------------

傳輸層中立的 ``CommandRouter`` 加上 Slack polling adapter，
``/run <script>`` 經 Slack 進入和 scheduler 相同的執行路徑。
內建命令：``/help``、``/scripts``、``/run``、``/screenshot``、
``/status``。RBAC 透過 ``required_role`` 參數。
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
``auto``（預設）在 libei 可載入時用 libei，否則用 CLI，現有
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
* ``backend`` — ``"anthropic"``（透過 ``export_anthropic_tools()``
  以 tool-use messages 驅動）或 ``"openai"``（``export_openai_tools()``
  + Chat Completions function calling）。
* ``max_steps``（預設 25）、``wall_seconds``（預設 300.0）。
* ``model`` / ``max_tokens`` — backend 專屬覆寫。

Anthropic 原生 Computer-Use 路徑（``computer_20250124``）仍透過
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

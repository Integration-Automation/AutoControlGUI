# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** 是一套開源、跨平台的 **computer-use 與 GUI 自動化框架**，面向 AI agent、Python 應用程式與自動化測試。它能驅動滑鼠與鍵盤、透過樣板比對、OCR、作業系統無障礙樹或視覺模型找到 UI 目標、錄製與重播流程，並以 JSON 動作檔執行——支援 Windows、macOS、Linux（X11 與 Wayland）、BSD、Android 與 iOS。

每項能力都以三種形式提供：**Python API**、可在 JSON 檔／CLI／伺服器使用的 **`AC_*` 動作指令**，
以及 **GUI 分頁**。沒有任何功能只存在於 GUI。

**[English](../README.md)** · **[简体中文](README_zh-CN.md)**

---

## 為什麼選擇 AutoControl

- **一套 API，七個平台。** `wrapper/platform_wrapper.py` 在匯入時挑選後端；同一份腳本在
  Windows、macOS、X11 與 Wayland 上都不需要改寫。
- **不寫 Python 也能腳本化。** 800 個 `AC_*` 指令涵蓋全部功能，因此一個 JSON 檔能做到函式庫
  能做的任何事——包含迴圈、分支、try/catch、巨集與變數。
- **預設無頭執行。** `import je_auto_control` 絕不會載入 Qt。GUI 是選用套件，包在同一個無頭核心之外。
- **四種定位方式。** 樣板比對、OCR、無障礙樹、視覺語言模型——可透過錨點定位器與自癒後備串接組合。
- **相依基線輕薄。** REST 伺服器、JSON Schema 驗證、JWT、TOTP、WebSocket 框架、ACME 用戶端、
  USB/IP 協定與 Prometheus 指標全部以標準庫實作；較重的相依都是選用。


## AI Agent 與 Computer Use

**AutoControl 是開源、跨平台的 computer-use 與 GUI 自動化框架。**

當 AI agent 需要操作真實桌面、原生應用程式、真正的瀏覽器視窗、遠端桌面或行動裝置，而不只是操作瀏覽器 DOM/API 時，使用 AutoControl。

### 何時選擇 AutoControl

- 真實滑鼠與鍵盤輸入
- 螢幕擷取與座標操作
- OCR 與原生無障礙樹
- 影像／樣板比對
- Vision-Language Model UI 定位
- Anchor 與 self-healing locator
- 跨平台桌面／行動裝置自動化
- JSON 動作檔
- MCP computer use

建議的 agent loop：

**observe → identify → act → wait → verify → recover**

完整的 [AI Agent 指南](../AI.md) 提供 MCP 設定、工具選擇、OpenAI 整合、安全性與 computer-use 關鍵字。

### AI-friendly MCP

```bash
pip install je_auto_control
je_auto_control_mcp
```

MCP 提供完整的 `ac_*` 工具，以及 `click`、`type`、`screenshot`、`find_text`、`click_text`、`drag`、`focus_window`、`wait_image` 等短名稱 alias。

只做檢查：

```bash
je_auto_control_mcp --read-only
```

只需要 canonical `ac_*` 名稱：

```bash
JE_AUTOCONTROL_MCP_ALIASES=0 je_auto_control_mcp
```

OpenAI agent 請使用 `export_openai_tools(only=[...])` 提供聚焦工具集，不要一次提供整個 AutoControl 命令目錄。

### 專案識別

**專案：** AutoControl  
**Repository：** `Integration-Automation/AutoControlGUI`  
**Python package / PyPI：** `je_auto_control`  
**MCP command：** `je_auto_control_mcp`


---


## 如何選擇自動化層

AutoControl 不需要取代所有自動化工具；應該選擇最符合介面的那一層：

| 需求 | 適合工具 |
|---|---|
| 穩定的瀏覽器 DOM／API 自動化 | Playwright／Selenium |
| 簡單的 Python 滑鼠鍵盤腳本 | PyAutoGUI 或 AutoControl |
| 原生桌面應用程式自動化 | **AutoControl** |
| 無障礙樹 GUI 自動化 | **AutoControl** |
| OCR GUI 自動化 | **AutoControl** |
| 截圖／視覺模型 GUI 定位 | **AutoControl** |
| Self-healing 跨平台 GUI locator | **AutoControl** |
| AI agent 操作真實桌面 | **AutoControl + MCP** |
| 確定性的 JSON GUI workflow | **AutoControl** |

AutoControl 的差異在於把 **真實電腦輸入 + 語意／視覺定位 + self-healing + agent/MCP 整合** 放在同一個跨平台自動化介面。


## 安裝

```bash
pip install je_auto_control            # 核心
pip install je_auto_control[gui]       # 加上 PySide6 桌面應用程式
```

需要時才安裝的選用套件：

| Extra | 啟用的功能 |
|---|---|
| `gui` | PySide6 桌面應用程式（48 個分頁）：左側可搜尋的導覽面板（`Ctrl+K`）依分類列出全部功能，分頁在第一次開啟時才建立，**View → Theme** 切換深色／淺色。窄視窗的內容可捲動；關閉視窗時，主題、字級、導覽面板顯示（`Ctrl+B`）與寬度會存入 `~/.je_auto_control/gui.ini`。主題直接使用 Qt，不需要 `qt-material`。 |
| `webrtc` | WebRTC 遠端桌面、USB 直通（`aiortc`、`av`） |
| `signaling` | 獨立的訊令／rendezvous 伺服器（`fastapi`、`uvicorn`） |
| `discovery` | mDNS / Zeroconf 區網主機探索 |
| `pdf` / `office` | PDF 與 Excel／Word／PowerPoint 讀取 |
| `fuzzy` / `locale` | `rapidfuzz` 模糊比對、`babel` 地區解析 |
| `s3` / `audio` | S3 產出物儲存、系統音量控制 |

以分頁關閉鈕關閉 factory 建立的功能面板時，下一次 Qt event loop 會釋放 widget、訂閱與計時器；重新開啟會建立新面板。**View → Tabs** 與嵌入用的 `hide_tab` 只隱藏並保留狀態。`tab_registry.open/close` 與 `close_tab` 提供明確的生命週期介面。既有的擁有者表單與 Remote Desktop 在生命週期遷移完成前，關閉後仍保留以供重用。

**Windows arm64** 裝得起來也跑得起來，少的是上游在那裡發不出來的那些：
`opencv-python` 與 `cryptography` 都沒發 `win_arm64` wheel。所以 `find_image*`、
`screenshot()`（OpenCV／BGR 那一支——Pillow 截圖仍可用）、秘密金庫、動作檔加密、
ACME／TLS 與加密錄影會拋出指名缺哪個 wheel 的錯誤，而不是難以追查的失敗。
滑鼠、鍵盤、螢幕尺寸、視窗管理、無障礙樹、動作執行器、MCP／REST／TCP 伺服器
與 GUI 都正常——這是實測的，不是推論的。其他平台不受影響。

**系統需求：** Python ≥ 3.10（Windows arm64≥ 3.11，CPython 官方建置從那裡開始）。
Linux 請先安裝建置前置套件：

```bash
sudo apt-get install cmake libssl-dev
```

OCR、VLM 與 LLM 後端（`pytesseract`、`easyocr`、`paddleocr`、`anthropic`、`openai`）
都是按需載入——只裝你實際會用到的。Tesseract 的部分，`find_tesseract_cmd()` 找出執行檔
（依序是 `$TESSERACT_CMD`、`PATH`、安裝程式的預設資料夾），`set_tessdata_dir()` 把它指到
語言資料夾，`ocr_status()`／`ocr_languages()` 在第一次 OCR 之前就說出缺了什麼。

**記錄檔：** 函式庫寫到 `~/.je_auto_control/logs/AutoControlGUI.log`，第一筆記錄時
才建立（只 import 不會寫任何檔），同一個帳號的所有行程共用（附加寫入、每行帶行程 ID，
超過 10 MB 就改名成 `.1`）。要寫到別處就設定
`JE_AUTOCONTROL_LOG_FILE`，設成 `os.devnull` 則不寫檔。

---

## 60 秒上手

**1. 當成 Python 函式庫**

```python
import je_auto_control as ac

ac.set_mouse_position(500, 300)
ac.click_mouse("mouse_left")
ac.write("Hello World")
ac.hotkey(["ctrl_l", "s"])

x, y = ac.locate_image_center("save_button.png", detect_threshold=0.9)
ac.click_text("Submit")                       # OCR
ac.click_accessibility_element(name="OK")     # 無障礙樹
ac.click_by_description("the green Submit button")   # 視覺模型
ac.screenshot("shot.png", screen_region=[0, 0, 800, 600])
```

**2. 當成 JSON 動作檔** — `flow.json`

```json
[
    ["AC_set_var", {"name": "user", "value": "alice"}],
    ["AC_locate_and_click", {"image": "login.png", "mouse_keycode": "mouse_left"}],
    ["AC_write", {"write_string": "${user}"}],
    ["AC_retry", {"max_attempts": 3, "body": [
        ["AC_wait_text", {"target": "Welcome", "timeout": 10}]
    ]}],
    ["AC_assert_text", {"text": "Welcome"}],
    ["AC_generate_html_report", {"html_name": "report"}]
]
```

```bash
je_auto_control run flow.json --var user=bob
je_auto_control run flow.json --dry-run     # 只列出步驟，不會真的動滑鼠
```

**3. 當成桌面應用程式**

```bash
pip install je_auto_control[gui]
python -c "import je_auto_control; je_auto_control.start_autocontrol_gui()"
```

錄製一段流程、在視覺化 Script Builder 裡編輯，然後存成 CLI 能直接執行的同一種 JSON 格式。
（`python -m je_auto_control` 是舊式的動作檔執行器——`-e`、`-d`、`-c`、`--execute_str`——不會開 GUI。）

---

## 能力總覽

每一列都能無頭執行。「GUI 分頁」是同一功能在桌面應用中的位置；分頁的指令都放在視窗的
**Actions** 選單裡。

| 能力 | Python API | `AC_*` 指令 | GUI 分頁 |
|---|---|---|---|
| 滑鼠 | `click_mouse`（`clicks=2` 就是雙擊）、`set_mouse_position`、`mouse_scroll`、`tween_drag`／`drag_path`（以 `step_delay_s`、`settle_s` 控制節奏） | `AC_click_mouse`、`AC_tween_drag`、`AC_drag_path` | Auto Click |
| 鍵盤 | `write`、`write_secret`、`hotkey`、`type_keyboard`、`keyboard_key_name`（鍵碼 → 標準鍵名；Windows 也收 `ctrl`、`esc`、`enter` 等別名） | `AC_write`、`AC_write_secret`、`AC_hotkey` | Auto Click |
| 螢幕與像素 | `screenshot`、`screen_size`、`get_pixel` | `AC_screenshot` | Screenshot |
| 影像比對 | `locate_image_center`、`locate_and_click` | `AC_locate_and_click` | Image Detect |
| OCR 文字 | `click_text`、`wait_for_text`、`read_text_in_region`、`ocr_status` | `AC_click_text`、`AC_wait_text`、`AC_ocr_status` | OCR Reader |
| 無障礙樹 | `find_accessibility_element`、`click_accessibility_element` | `AC_a11y_find`、`AC_a11y_click` | Accessibility |
| 視覺模型定位 | `locate_by_description`、`click_by_description` | `AC_vlm_locate`、`AC_vlm_click` | VLM |
| 錨點定位 | — | `AC_anchor_click`、`AC_anchor_locate` | — |
| 自癒定位器 | `self_heal_run`、`self_heal_locate`、`self_heal_click` | `AC_self_heal_click` | Self-Healing |
| 自然語言規劃 | `plan_actions`、`run_from_description` | `AC_llm_plan` | LLM Planner |
| Computer-use agent | `AgentLoop`、`run_agent` | `AC_run_agent` | Computer Use |
| 錄製與重播 | `record`、`stop_record` | `AC_record`、`AC_stop_record` | Record |
| JSON 腳本 | `execute_action`、`execute_files` | 全部 800 個指令 | Script、Script Builder |
| 變數與流程控制 | `execute_action_with_vars` | `AC_set_var`、`AC_loop`、`AC_for_each`、`AC_try`、`AC_retry` | Variables |
| 資料驅動執行 | — | `AC_for_each_row`（CSV／JSON／SQLite／Excel） | Data Sources |
| 斷言 | `assert_text`、`assert_image` | `AC_assert_text` 等 21 個 | Assertions |
| 測試套件 | `run_suite` | `AC_run_suite` | Test Suites |
| 排程（間隔 + cron） | `default_scheduler` | — | Scheduler |
| 全域熱鍵 | `default_hotkey_daemon` | — | Hotkeys |
| 事件觸發 | `default_trigger_engine` | `AC_email_trigger_add` | Triggers、Webhooks、Email |
| 視窗管理 *(Windows、macOS、X11)* | `list_windows`、`focus_window` | `AC_focus_window`、`AC_snap_window` | Window Manager |
| 剪貼簿（文字 + 影像） | `get_clipboard`、`set_clipboard`、`get_clipboard_image`、`set_clipboard_image` | `AC_clipboard_get`、`AC_clipboard_set`、`AC_clipboard_get_image`、`AC_clipboard_set_image` | — |
| 遠端桌面 | `RemoteDesktopHost`、`RemoteDesktopViewer` | `AC_start_remote_host`、`AC_remote_connect` | Remote Desktop |
| USB 列舉與直通 | `list_usb_devices`、`enable_usb_passthrough` | `AC_usb_*`（16 個指令） | USB Devices、USB Share |
| 機密保險庫 | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| 報表（HTML／JSON／XML） | `generate_html_report` | `AC_generate_html_report` | Report |
| 執行歷史 | `HistoryStore`、`manual_history_scope` | `AC_history_list`、`AC_history_capture` | Run History、Script Executor、Script Builder |
| 動作日誌 | `execute_journal_run`、`inspect_journal` | `AC_journal_capture`、`AC_journal_read` | Run History、Script Builder |
| 指標與追蹤 | `default_metric_registry`、`render_metrics_text` | — | — |
| 系統診斷 | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| 測試碼產生 | `generate_code` | — | — |

自癒定位器會在後備或點擊前原樣傳遞取消。稽核記錄在寫入或回傳記錄前遮蔽本次執行已解析的秘密值；回傳的定位結果保留原值，讀取時不改寫既有紀錄檔。

即時 image／VLM 自癒現在共用一次延遲邏輯截圖及實際裁切原點，兩條路徑的 `screen_region` 均為 `[左, 上, 右, 下]`。Schema-v2 記錄增加 run／step 身份、內容與設定版本、frame hash、策略／截圖耗時及實際 backend／model，仍相容舊記錄。未設定驗證的點擊僅記錄已送出或失敗，驗證維持未知。GUI 提供區域輸入與所選記錄證據，Script Builder 保留結構化區域 JSON。舊 `healed`／`heal_rate` 統計定位候選，獨立的操作指標需要明確驗證。

實驗性 `self_heal_run(SelfHealRequest(...))` 預設只定位。明確選擇 `operation="click"`，再透過 `VerificationRequest(verifier=...)`（Python bool callback）或 `VerificationRequest(description=...)`（已設定的 VLM）於輸入送出後驗證條件。VLM 驗證使用新擷取的邏輯影像，可能產生 API 費用。`verified` 分為真、假及未知；`found` 與 `issued` 本身不代表操作通過驗證。例外與取消原樣傳遞，不重試點擊。`AC_self_heal_run` 和 MCP `ac_self_heal_run` 接受巢狀 `request`；明確驗證失敗使指令／CLI 失敗，或回傳含結構化結果的 MCP `isError`。GUI **Self-Healing** 提供選填的操作後條件，Script Builder 可編輯 JSON 請求。獨立 VLM 擷取也改用相同的記憶體邏輯原點／Retina 正規化。Framework assertion 會中止定位後備。

已擷取的自癒紀錄新增可選的 `journal_path`，搭配 run／step ID。實驗性 `inspect_heal_source(path, run_id, step_id)`、`AC_self_heal_source` 與 MCP `ac_self_heal_source` 只讀取原始步驟經清理的生命週期快照。在 **Self-Healing** 選取紀錄後，使用 **動作 → 檢視原始步驟** 開啟背景讀取器；切換目標時會等待舊讀取停止並保留請求者脈絡，關閉則取消待處理工作；Run History 讀取器也可選填步驟 ID。先篩選 run／step 再套用輸出上限，整份日誌仍會驗證，進度通知前後重查路徑根目錄，取消不回傳部分結果。舊紀錄或未經動作日誌擷取的操作沒有來源連結；查閱不會重播指令。

實驗性因果同步提供 `CausalBucket`、`CausalConfigStore`、`SyncActor`、保留衝突的 entry 版本與持久化本機 `SyncOutbox`。獨立且經驗證的 `GET/PUT /config/{user_id}/causal` 第三版協定，在保存重送收據的同一個 CAS 交易內驗證裝置註冊、確認、退休／完整同步 epoch 與刪除回收。回收後保留永久的最小刪除憑證；舊版寫入不能覆蓋已升級帳號。私有 `AC_config_store_get`／`AC_config_store_commit` 與對應 MCP／Builder 命令可讀取及提交帶明確 `_actor` 的因果 JSON；純資料合併／peer 與私有 outbox 命令仍可使用。明確的 `CausalSyncClient` 與 `AC_config_causal_fetch`、`AC_config_causal_commit`、`AC_sync_outbox_flush`（含 MCP／Builder）已提供第三版 HTTP 投遞：結果不明時重送固定請求，只有明確的過期版本才在有界預算內重合併。`CausalReceipt` 在 outbox 原子確認原收據與最新完整快照；命令憑證使用即時的 `options.secret_env` 參照。自動 peer 控制／完整重同步協調仍待完成，`ConfigSyncClient` 保留時間戳合併。參閱[因果／outbox 指南](../docs/source/Zh/doc/causal_sync/causal_sync_doc.rst)與 `python -m examples.causal_sync`。

實驗性持久化設定使用 `ConfigStore.commit(..., base_revision=..., operation_id=...)` 與第二版 signaling PUT envelope。SQLite 交易讓 bucket 與重送收據在重啟後保留；過期版本或 ID 改配其他內容會衝突。`ConfigSyncClient` 預設條件寫入；舊版盲寫須在 client／server 明確開啟。`--config-store` 選取延後開啟的資料庫。私有 `AC_config_store_get`／`AC_config_store_commit` 與對應 MCP 工具共用 Script Builder 的明確 Data 命令。只儲存資料，不執行腳本或啟用觸發器；因果合併與離線 outbox 另行交付。參閱[持久化設定指南](../docs/source/Zh/doc/config_store/config_store_doc.rst)與 `python -m examples.config_store`。

實驗性日誌產碼候選支援 `generate_candidate_from_log(path, run_id=...)`、`AC_generate_candidate_from_log` 與 MCP `ac_generate_candidate_from_log`。它會整合開始／完成快照，保留已記錄的控制來源與重試證據，並將不完整重建標示為已觀察路徑。失敗／未完成呼叫、未知命令及遮罩輸入均列為排除項目，不捏造平行順序。Python／pytest／Robot 產物經靜態、命令及不發送輸入的乾跑檢查。`codegen --from-log run.jsonl --run-id selected` 輸出 JSON 審閱包；`-o review.zip` 或 `write_candidate_archive` 可將程式、動作與來源資訊一起原子匯出。Recording Editor 與 Script Builder 的 **動作 → 審閱日誌候選腳本** 提供程式／差異／來源／警告；Builder 匯入為獨立操作，拒絕覆蓋審閱期間的編輯變更。產生與匯入均不執行候選。參閱[候選指南](../docs/source/Zh/doc/journal_candidates/journal_candidates_doc.rst)與 `python -m examples.journal_candidates`。

實驗性候選樣板版本提供 `create_template_candidate`、`preview_template_candidate`、`verify_template_candidate`、`accept_template_candidate`、`revert_template_candidate`，以及對應 `AC_template_candidate_*`／`ac_template_candidate_*` 操作。新的不可變 JSON 版本包保存原始位元組及依目標 PNG／JPEG／BMP 格式編碼的候選；預覽回傳有界縮圖。驗證在本機資料集比較兩個固定版本；接受須有已標註命中、期望 miss、全部已標註案例正確，並提供已預覽版本的 SHA-256。接受時重驗資料集，只原子替換仍符合的原始內容；回復精確還原原始位元組，拒絕覆蓋後續修改。未知樣本與原生操作結果分開呈現。驗證使用記錄的門檻；啟用影像不修改腳本門檻。**Self-Healing → 候選樣板** 提供五個動作、背景工作、取消與 JSON 證據。執行 `python -m examples.template_candidates` 可跑只使用暫存檔的範例。

實驗性固定影像比較支援 `evaluate_locators`、`evaluate_healing_manifest`、`AC_self_heal_evaluate`、MCP `ac_self_heal_evaluate` 與 **Self-Healing → 版本比較**。報告分別呈現已標註正確率、誤判、未知與已驗證恢復，包含 p50／p95 及來源，可由 `write_healing_report` 或 GUI 動作匯出 JSON／HTML。本機資料集入口不會截圖、點擊或自行選擇網路 backend。參閱[資料集、統計母體與限制](../benchmarks/self_healing/README.md)。

除了這張表，`utils/` 底下還有 311 個無頭套件，涵蓋斷言、韌性、資料品質、i18n 稽核、遮蔽、
治理、可觀測性等等。完整的逐模組地圖在 **[architecture_explore.md](../architecture_explore.md)**。

---

實驗性的結構化日誌已從 `je_auto_control` 匯出（也可透過 `utils.action_journal` 使用）：`journal_scope` 記錄現有 executor 呼叫，`execute_action_with_journal` 隔離一次執行。本機 loop／parallel／DAG 步驟保留 parent ID，並區分失敗、取消與 dry-run。既有 history 擁有者會自動連結明確擷取，包含本機 parallel／DAG worker 開啟的 journal；`HistoryStore.journals_for_run` 可查詢非擁有式連結，清理 history 不會刪除日誌檔。CLI 支援 `run script.json --journal run.jsonl [--journal-run-id ID]` 與 `journal run.jsonl [--run-id ID] [--limit 100]`。查閱會按附加順序顯示遮罩後的生命週期快照，預設最多 100 筆，上限 10,000 筆。`AC_journal_capture` 接受具名參數，在擁有者 executor 上執行巢狀 `body`，保留原變數範圍；`AC_journal_read` 與 CLI、公開的 `inspect_journal` 共用遮罩後的有界查閱。兩個指令皆可在 Script Builder 編輯。擷取會在 history 連結、開檔及動作執行前拒絕含有當次執行已知秘密的識別碼或目的地。MCP 的 `ac_journal_capture` 與 `ac_journal_read` 提供結構化結果、進度與合作式取消。擷取的日誌根目錄限制與 observer 會保留至巢狀擷取及本機 workers；查閱可在逐筆驗證時取消。Python 可透過 `JournalRunOptions` 與 `execute_journal_run` 使用相同控制。

手動執行可透過 `manual_history_scope`、`AC_history_capture`、CLI 的 `run --history [--history-db PATH]`，或 Script Executor／Script Builder 的 **記錄至執行歷史** 選用紀錄。GUI 的選填日誌路徑也能獨立使用；GUI／CLI 保留原本的結果 JSON 與變數範圍，指令則回傳 `history_id`、`record`、`failed_actions`。既有與巢狀擷取都會連結到新的手動歷史列。CLI 預覽以 `cli.preview` 標示，一般執行使用 `cli.run`。

Run History 提供唯讀日誌檢視。使用 **操作 → 使用所選執行的日誌** 選擇來源連結，或用 **選擇日誌** 指定外部檔案；設定執行 ID 與快照上限後，使用 **讀取日誌**。起始／完成快照保持分離，選取後會顯示完整的遮罩資料。**取消讀取日誌** 與關閉檢視會在逐筆邊界提出取消要求；檔案解析在背景 worker 執行，單純選取連結不會開檔。

`${secrets.NAME}` 解析後的值會在 executor 執行期間的應用程式診斷中遮罩，包含巢狀動作及本機 parallel／DAG。CLI／REST／MCP 請求與排程、trigger、hotkey、email 執行會將遮罩保留到錯誤處理及 audit／history 寫入完成；報表紀錄保存遮罩後的快照。DAG 會將擁有者的遮罩保留到 node 診斷完成，包含獨立呼叫與自訂 local runner。watchdog、observer 與 callback executor 會將遮罩保留到最後的錯誤處理；獨立規則彼此隔離。CLI stderr 會遮罩，API 結果、拋出的例外與 CLI 結果資料保留原始值。遮罩於擁有者的請求或執行結束時清除。中止的 history 記為 `error`，journal 步驟維持 `cancelled`，不再擷取錯誤截圖。取消會穿過非嚴格執行、復原／重試、回呼與本機 worker；history 結算失敗也不會取代原始硬中止訊號。

## 命令列介面

每次 `je_auto_control run`（包括 `--dry-run` 與未帶 `--var`）使用獨立變數範圍。頂層 `run_from_description` 與 `StateMachine.run()` 也會隔離變數，同一次執行內的動作與狀態仍可共享；巢狀呼叫沿用已有的執行範圍。自行建立的 `Executor()` 保留自己的變數。

```bash
je_auto_control run script.json [--var name=value] [--dry-run] [--allow-package NAME]
je_auto_control validate script.json          # 別名：lint
je_auto_control fmt script.json [--check]
je_auto_control list-commands [--filter mouse] [--json]
je_auto_control record out.json [--duration 5]
je_auto_control codegen script.json --target pytest -o test_flow.py
je_auto_control failure-bundle failure.zip --error "login timed out"
je_auto_control list-jobs
je_auto_control start-server --port 9938      # TCP socket 伺服器
je_auto_control start-rest   --port 9939      # REST API
je_auto_control version
```

`--var name=value` 會盡量以 JSON 解析（`count=10` 會變成整數），否則視為字串。
`run` 只要有任何動作失敗就以 1 結束（仍會跑完整份腳本），CI 步驟會跟著失敗。舊版 `python -m je_auto_control -e file.json` 進入點仍然可用，它的 `-e`、`-d` 與 `--execute_str` 旗標也同樣在有動作失敗時以 1 結束。由 [TestPioneer](https://github.com/Integration-Automation/TestPioneer) 啟動時（它會設定 `TEST_PIONEER_ARTIFACT_DIR`），以相對名稱要求的 HTML、JSON、XML 報告會寫到該目錄底下。

---

## 伺服器與整合

| 介面 | 啟動方式 | 說明 |
|---|---|---|
| **MCP 伺服器** | `je_auto_control_mcp`（stdio）或 `AC_start_mcp_http_server` | 700 個工具，供 Claude Desktop／Claude Code／自訂 tool loop 使用：完整的 `ac_*` 工具介面，以及常用 GUI 操作的短名稱 alias。除了以 `initialize` 握手的各版協定，也支援無狀態的 MCP 2026-07-28。Bearer 驗證、TLS、稽核記錄、限流、外掛熱重載、CI 假後端。 |
| **REST API** | `je_auto_control start-rest` | Bearer token、逐 IP 限流與鎖定、SQLite 稽核 hook、`/metrics`、`/openapi.json`、`/docs` Swagger UI、`/dashboard`。 |
| **TCP socket 伺服器** | `je_auto_control start-server` | 以換行分隔的 JSON 動作清單。預設綁 `127.0.0.1`。 |
| **pytest 外掛** | 安裝後自動生效 | 提供 fixture 與供 pytest-bdd／behave 使用的 Gherkin step library。 |
| **語言伺服器** | `python -m autocontrol_lsp.server` | 為 `AC_*` 動作 JSON 提供補全與診斷，指令清單直接取自執行期的指令表。 |
| **遠端桌面** | `RemoteDesktopHost` 或 GUI | TCP、WebSocket 或 WebRTC；TOTP、信任清單、TURN 設定、檔案／剪貼簿／音訊同步。 |

除非明確指定，所有伺服器都綁在 `127.0.0.1`。

MCP 視窗狀態工具 `ac_window_minimize`、`ac_window_maximize` 與 `ac_window_restore` 在後端接受要求時回傳視窗 handle，遭拒時回覆 `isError: true`（包括 handle 失效或啟用請求被拒）。Win32 原始 `ShowWindow` 的先前可見性由後端正規化處理。

**套件閘門。** `AC_add_package_to_executor` 與 `AC_add_package_to_callback_executor` 會匯入 Python 套件並把成員註冊成命令，所以從上面任何一個入口送來的動作清單都可能載入 `os` 或 `subprocess`。沒有被放行的套件不會載入：不在允許清單上的套件在匯入前就被拒絕，該動作以 `AutoControlExecuteActionException` 失敗。放行套件（含子模組）的方式：在 Python 裡呼叫 `executor.allow_packages("name", …)`；對所有入口——兩個 CLI、socket／REST／MCP 伺服器與排程器——設定環境變數 `JE_AUTOCONTROL_ALLOWED_PACKAGES`（以逗號分隔的名稱，行程啟動時讀取）；或只對一次 CLI 執行使用 `je_auto_control run script.json --allow-package NAME`（可重複）。`executor.set_allow_arbitrary_packages(True)` 會對所有套件打開閘門，也就是先前版本的預設行為（當時會發 `DeprecationWarning`）。這些都不是 `AC_*` 命令，所以動作清單不能自己打開閘門。

**選用的強化設定。** 下列各項在設定之前都是關閉的，沒設定的伺服器行為與先前相同。`JE_AUTOCONTROL_RBAC_USERS=<使用者檔>` 讓 REST API 與 MCP HTTP 傳輸把 bearer token 對到使用者，並依角色（viewer／operator／admin）授權每一個路由、工具與特權 `AC_*` 命令；此時共用 token 會被拒絕。`JE_AUTOCONTROL_MCP_PATH_ROOTS`（以作業系統的路徑分隔字元分開的目錄）把每一個屬於檔案路徑的 MCP 工具參數限制在這些目錄裡，`JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT=1` 再加上 client 的 `roots/list`，`JE_AUTOCONTROL_MCP_ENV_REF_ALLOW` 限制 `ac_resolve_ref` 可以讀哪些 `env://` 名稱。`JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY` 讓端點只能驗證 Ed25519 簽章的動作檔而不能簽章（`create_signing_keypair`；私鑰留在簽章的機器上）。遠端桌面的 viewer 只把 host 推來的檔案寫在 `~/Downloads/AutoControl` 底下（`JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR`）；這一項預設就是開的。

REST GUI 在使用者存放檔啟用時顯示 RBAC 模式並停用共用 token 欄位。`rest_api_registry.status()` 提供 `rbac_enabled`，該模式的 `token` 為 `null`；請使用個別使用者 token。只實作 `check()` 的自製 REST gate 仍可用於共用 token 模式；RBAC 要求已驗證的使用者 context，會拒絕沒有身分的成功結果。

RBAC viewer 不會取得列管的敏感讀取工具，即使 MCP `readOnlyHint` 為 true：剪貼簿／歷史、本機文件／資料／SQL 與 dotenv 讀取、參照解析、認證資料產生、持久存放區讀取、對外檢查、麥克風擷取與外部 VLM 請求都需要 operator／admin。斷言容器的 spec 也可能讀取這些資源，因此同樣需要 operator。螢幕觀察與純輸入解析維持既有分類。`ac_realize_item`、`ac_idempotency_begin` 與 `ac_rate_limit` 會改變狀態，已從 `--read-only` 模式排除。

間隔／cron 排程、觸發器、熱鍵、watchdog 規則、webhook、e-mail 觸發器與 observer 回呼會保留註冊者身分。每次觸發重新檢查來源使用者檔與角色；已刪除的使用者、無法使用的來源檔與 viewer 不能執行背景工作。啟動 daemon 不會改變既有工作的擁有者。擁有者資訊不保存 RBAC bearer token；未帶 `store_path` 的明確 Python `AuthorizationContext` 保留角色快照，未在 RBAC 下註冊的工作會清除 worker 原有身分。observer／watchdog 回呼使用獨立變數範圍，watchdog 動作失敗不會算成成功排除彈窗。巢狀回呼會保留呼叫端的失敗計數；webhook 擁有者被撤銷權限時回應 HTTP 403 與 `fired: false`。

### 遠端桌面的線路協定

把主機開出去之前值得先知道，而且這段在其他文件裡都沒有寫。預設傳輸是**裸 TCP
上的長度前綴分幀**（不需要額外相依），連線一開始就是 **HMAC-SHA256 的
challenge／response 握手**：驗證沒過的觀看端在拿到任何一張畫面之前就會被斷掉。
JPEG 影格依設定的 FPS 與品質編碼，再透過一個共用的**最新影格槽**發給已驗證的
觀看端——所以慢的觀看端是**掉影格**，不會把其他人一起卡住。觀看端送來的輸入是
JSON，會先比對**動作允許清單**才交給既有的輸入包裝層執行，觀看端無法自己發明
新的操作。

```python
# 讓別人連進來——開一個主機，把 token 與 port 給對方
from je_auto_control import RemoteDesktopHost
host = RemoteDesktopHost(token="hunter2", bind="127.0.0.1",
                         port=0, fps=10, quality=70)
host.start()
print("listening on", host.port, "viewers:", host.connected_clients)
```

```python
# 控制另一台機器——連上去並送輸入
from je_auto_control import RemoteDesktopViewer
viewer = RemoteDesktopViewer(host="10.0.0.5", port=51234, token="hunter2",
                             on_frame=lambda jpeg: ...)
viewer.connect()
viewer.send_input({"action": "mouse_move", "x": 100, "y": 200})
viewer.disconnect()
```

也可以用 IP 允許清單（CIDR 網段或個別位址）限制誰連得進來，清單外的對端在握手
階段就會被拒絕：

```python
RemoteDesktopHost(token="tok", ip_allowlist=["10.0.0.0/8", "192.168.1.100"])
```

---

## 平台支援

| 平台 | 後端 | 輸入 | 螢幕擷取 | 錄製 | 視窗管理 |
|---|---|:---:|:---:|:---:|:---:|
| Windows 10 / 11 | Win32 ctypes（可選 Interception 驅動） | ✅ | ✅ | ✅ | ✅ |
| macOS 10.15+ | pyobjc / Quartz | ✅ | ✅ | ✅¹ | ✅ |
| Linux X11 | python-Xlib（可選 `uinput`） | ✅ | ✅ | ✅ | ✅ |
| Linux Wayland | 經桌面 portal 的 libei，或 ydotool／wtype ＋ 擷取工具 | ✅ | ✅ | ❌ | ❌ |
| FreeBSD／OpenBSD／NetBSD | python-Xlib，與 Linux 同一套 X11 後端 | ✅² | ⚠️² | ✅² | ✅² |
| Android | adb + uiautomator2 | ✅ | ✅ | — | — |
| iOS | WebDriverAgent / facebook-wda | ✅ | ✅ | — | — |

¹ macOS 的錄製走 Quartz event tap，需要**輔助使用**權限
（系統設定 → 隱私權與安全性 → 輔助使用）。沒有授權時會直接拋出並指名
缺的是哪個權限，而不是安靜地錄到一個空的 session。

² BSD 直接跑同一套 X11 後端——同一個 X server、同一個 `python-Xlib`，而輸入、
錄製與視窗管理就只相依這一個套件。`freebsd` CI job 在真的 FreeBSD 14 上驅動真的
輸入，再從 X server 讀回來；OpenBSD 與 NetBSD 走同一條程式路徑，只是沒有 CI
runner。唯一的例外是螢幕擷取，而卡的是打包不是平台：它走 Pillow／mss 與 OpenCV，
而 `opencv-python`、`pillow`、`cryptography` 都沒有發 FreeBSD wheel。從 ports
建起來之後，擷取、影像比對、OCR 與動作加密也都能用——`import je_auto_control`
本身已經不需要它們任何一個。

Wayland 的輸入在 libei 走不通時會退回 `ydotool` CLI，而這條退路需要
**ydotool 1.0 以上**。AutoControl 送的每一個參數都是那一版才有的；0.1.x
（Debian bookworm 與目前所有 Ubuntu 仍以這個名字提供，Debian trixie 則根本沒有）
對同一批參數回傳 0 卻不送出任何事件。AutoControl 會偵測並直接拒絕，
而不是為根本沒送出的輸入回報成功。Arch、Fedora 與 Debian unstable 提供的是 1.0。

這條退路要能**準確定位**，還有一個前提:合成器的指標加速度必須是關的。
`ydotool mousemove --absolute` 並不送任何絕對事件——它先把游標推到合成器夾取的
那個角落，再送相對位移，所以這段位移會被合成器加速。對真的 wlroots session 量到的是:
libinput 的預設 profile 讓游標走的距離正好是要求的兩倍。ydotool 自己的 `--help`
也是這樣寫的；AutoControl 每個行程會記一次警告，而不是安靜地把點擊放到錯的地方。
請對 ydotoold 的裝置關掉加速度（sway:`input type:pointer accel_profile flat`
加上 `pointer_accel 0`），或是裝上 `liboeffis`，改走協定層本來就是絕對座標的 libei。

倍率是合成器自己的設定，用戶端讀不回來，所以只有你知道它關了沒有：
`JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat` 表示已經關掉，移動就不再出聲；
`=strict` 則寧可拒絕這次移動，也不讓點擊落在別的地方；不設定就維持
「警告一次後照樣移動」的預設。

Wayland 的螢幕擷取需要合成器對應的工具，因為沒有單一工具能涵蓋全部：wlroots 系
（sway、Hyprland、river）用 `grim`，GNOME 用 `gnome-screenshot`，KDE 用 `spectacle`。
裝好其中一個之後，所有擷取路徑——截圖、影像與錨點定位、OCR、螢幕錄影、遠端桌面——都會
經由它。三個都沒裝也還有 `gdbus`：最後會嘗試 `xdg-desktop-portal`，只是第一次可能會跳
同意對話框。再不行，擷取會帶著安裝提示明確失敗，而不是回傳空白的 XWayland root；
`je_auto_control.api.run_diagnostics()`（以及 GUI 的 Diagnostics 分頁）的 `screen_capture`
檢查會回報目前使用哪一層。

有一件只在 Wayland 出現、需要事先規劃的事：**擷取回來的圖裡可能有滑鼠游標。**
這裡沒有任何一條擷取要求游標，但只要 backend 沒有游標平面（包含任何以
`WLR_NO_HARDWARE_CURSORS=1` 執行的 session），wlroots 就會畫**軟體游標**並把它
合成進輸出緩衝區，而擷取交回來的正是那一份。Windows 與 X11 都不含游標，所以
「定位器、樣板比對或 OCR 在目標中間看到一個游標形狀的洞」只會在這裡發生。
Wayland 不讓用戶端讀游標位置，所以沒有東西可以可靠地遮或閃避：請在擷取之前
把指標移離要拍的區域。`screen_capture` 檢查會以 `cursor_may_be_captured` 回報這件事。

如果以上都不適用你的環境，可以直接指定自己的指令——它優先於所有偵測，`{output}` 會被
換成暫存 PNG 路徑：

```bash
export JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mycapture --png {output}"
```

Wayland 禁止非特權用戶端進行全域輸入錄製——若要錄製，請設定
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` 並在 X11 session 下執行。視窗管理支援
Windows、macOS（pyobjc）與 X11（含 XWayland）；純 Wayland session 的協定不讓用戶端看到別的程式的視窗，
所以 `list_windows()` 回傳空清單，其餘視窗操作一律拋出帶原因的 `AutoControlUnsupportedOperationException`。對於會忽略合成輸入的應用程式，
可選用驅動層後端（`JE_AUTOCONTROL_WIN32_BACKEND=interception`、
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`、ViGEm 虛擬手把）；驅動未安裝時會自動退回原本行為。

---

## 文件與範例

| 資源 | 內容 |
|---|---|
| [`examples/`](../examples/) | 34 個自足腳本：截圖點擊、OCR、排程器、遠端桌面、agent loop、可觀測性、錄製、變數、熱鍵、觸發器、報表、MCP、REST、機密、外掛、computer use、Wayland、跨主機 DAG、chat-ops、pytest/BDD、錨點定位、動作日誌。 |
| [Read the Docs](https://autocontrol.readthedocs.io/en/latest/) | 完整 API 參考，含英文與中文。 |
| [architecture_explore.md](../architecture_explore.md) | 逐層記錄每個模組的職責。 |
| [docs/CAPABILITY_MATRIX.md](../docs/CAPABILITY_MATRIX.md) | 能力 × 平台對照矩陣。 |
| [docs/API_LIFECYCLE.md](../docs/API_LIFECYCLE.md) | 穩定 API 與棄用政策。 |
| [docs/updates/](../docs/updates/README.md) | 更新紀錄：各版本說明與完成的工作，每月一個檔（原 `WHATS_NEW.md`）。 |
| [CHANGELOG.md](../CHANGELOG.md) | 相容性變更記錄。 |
| [SECURITY.md](../SECURITY.md) | 安全政策與回報方式。 |

---

## 開發

```bash
git clone https://github.com/Integration-Automation/AutoControlGUI.git
cd AutoControl
pip install -r dev_requirements.txt
uv sync                 # 或：以已提交的 uv.lock 做可重現安裝
```

```bash
python -m pytest test/unit_test/headless      # 無頭單元測試
python -m pytest test/integrated_test/        # 跨模組流程測試

ruff check je_auto_control/
pylint je_auto_control/
bandit -c pyproject.toml -r je_auto_control/
```

歡迎貢獻——請見 [CONTRIBUTING.md](../CONTRIBUTING.md) 與
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)。CI 會強制兩條規則：`import je_auto_control`
絕不能載入 PySide6；每個功能都必須同時具備無頭 API 與 GUI 介面。

---

## 授權

[MIT License](../LICENSE) © JE-Chen。
內含與選用第三方元件的授權請見 [Third_Party_License.md](../Third_Party_License.md)。

- **首頁**：https://github.com/Integration-Automation/AutoControlGUI
- **PyPI**：https://pypi.org/project/je_auto_control/
- **文件**：https://autocontrol.readthedocs.io/en/latest/

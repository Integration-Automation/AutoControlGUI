# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** 是一套跨平台的 Python GUI 自動化框架。它能驅動滑鼠與鍵盤、在畫面上找到目標
（樣板比對、OCR、作業系統無障礙樹，或視覺模型）、錄製與重播操作流程，並以 JSON 動作檔執行——
支援 Windows、macOS、Linux（X11 與 Wayland）、BSD、Android 與 iOS。

每項能力都以三種形式提供：**Python API**、可在 JSON 檔／CLI／伺服器使用的 **`AC_*` 動作指令**，
以及 **GUI 分頁**。沒有任何功能只存在於 GUI。

**[English](../README.md)** · **[简体中文](README_zh-CN.md)**

---

## 為什麼選擇 AutoControl

- **一套 API，七個平台。** `wrapper/platform_wrapper.py` 在匯入時挑選後端；同一份腳本在
  Windows、macOS、X11 與 Wayland 上都不需要改寫。
- **不寫 Python 也能腳本化。** 811 個 `AC_*` 指令涵蓋全部功能，因此一個 JSON 檔能做到函式庫
  能做的任何事——包含迴圈、分支、try/catch、巨集與變數。
- **預設無頭執行。** `import je_auto_control` 絕不會載入 Qt。GUI 是選用套件，包在同一個無頭核心之外。
- **四種定位方式。** 樣板比對、OCR、無障礙樹、視覺語言模型——可透過錨點定位器與自癒後備串接組合。
- **相依基線輕薄。** REST 伺服器、JSON Schema 驗證、JWT、TOTP、WebSocket 框架、ACME 用戶端、
  USB/IP 協定與 Prometheus 指標全部以標準庫實作；較重的相依都是選用。

---

## 安裝

```bash
pip install je_auto_control            # 核心
pip install je_auto_control[gui]       # 加上 PySide6 桌面應用程式
```

需要時才安裝的選用套件：

| Extra | 啟用的功能 |
|---|---|
| `gui` | PySide6 桌面應用程式（49 個分頁） |
| `webrtc` | WebRTC 遠端桌面、USB 直通（`aiortc`、`av`） |
| `signaling` | 獨立的訊令／rendezvous 伺服器（`fastapi`、`uvicorn`） |
| `discovery` | mDNS / Zeroconf 區網主機探索 |
| `pdf` / `office` | PDF 與 Excel／Word／PowerPoint 讀取 |
| `fuzzy` / `locale` | `rapidfuzz` 模糊比對、`babel` 地區解析 |
| `s3` / `audio` | S3 產出物儲存、系統音量控制 |

**Windows arm64** 的 `find_image*`、BGR `screenshot()` 與固定畫面自愈使用
NumPy／Pillow 後端，基本安裝包含 NumPy 2.4.6。進階 OpenCV 處理／影片與安全版本
cryptography 仍缺上游 wheel；秘密金庫、動作簽章／加密、ACME／TLS 與加密錄影
仍不可用。共用後端的相依錯誤屬於框架例外家族。platform smoke job 已加入
原生 arm64 影像測試；本機替代後端測試會封鎖 OpenCV，並保留既有契約。

**系統需求：** Python ≥ 3.10（Windows arm64≥ 3.11，CPython 官方建置從那裡開始）。
Linux 請先安裝建置前置套件：

```bash
sudo apt-get install cmake libssl-dev
```

OCR、VLM 與 LLM 後端（`pytesseract`、`easyocr`、`paddleocr`、`anthropic`、`openai`）
都是按需載入——只裝你實際會用到的。

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
| 滑鼠 | `click_mouse`、`set_mouse_position`、`mouse_scroll` | `AC_click_mouse` | Auto Click |
| 鍵盤 | `write`、`hotkey`、`type_keyboard` | `AC_write`、`AC_hotkey` | Auto Click |
| 螢幕與像素 | `screenshot`、`screen_size`、`get_pixel` | `AC_screenshot` | Screenshot |
| 影像比對 | `locate_image_center`、`locate_and_click` | `AC_locate_and_click` | Image Detect |
| OCR 文字 | `click_text`、`wait_for_text`、`read_text_in_region` | `AC_click_text`、`AC_wait_text` | OCR Reader |
| 無障礙樹 | `find_accessibility_element`、`click_accessibility_element` | `AC_a11y_find`、`AC_a11y_click` | Accessibility |
| 視覺模型定位 | `locate_by_description`、`click_by_description` | `AC_vlm_locate`、`AC_vlm_click` | VLM |
| 錨點定位 | — | `AC_anchor_click`、`AC_anchor_locate` | — |
| 自癒定位器 | `self_heal_click`、`self_heal_locate` | `AC_self_heal_click` | Self-Healing |
| 自然語言規劃 | `plan_actions`、`run_from_description` | `AC_llm_plan` | LLM Planner |
| Computer-use agent | `AgentLoop`、`run_agent` | `AC_run_agent` | Computer Use |
| 錄製與重播 | `record`、`stop_record` | `AC_record`、`AC_stop_record` | Record |
| JSON 腳本 | `execute_action`、`execute_files` | 全部 811 個指令 | Script、Script Builder |
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
| 執行歷史 | — | — | Run History |
| 指標與追蹤 | `default_metric_registry`、`render_metrics_text` | — | — |
| 系統診斷 | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| 測試碼產生 | `generate_code` | — | — |

除了這張表，`utils/` 底下還有 311 個無頭套件，涵蓋斷言、韌性、資料品質、i18n 稽核、遮蔽、
治理、可觀測性等等。完整的逐模組地圖在 **[architecture_explore.md](../architecture_explore.md)**。

---

## 命令列介面

```bash
je_auto_control run script.json [--var name=value] [--dry-run]
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
`run` 只要有任何動作失敗就以 1 結束（仍會跑完整份腳本），CI 步驟會跟著失敗。舊版 `python -m je_auto_control -e file.json` 進入點仍然可用。

---

## 伺服器與整合

| 介面 | 啟動方式 | 說明 |
|---|---|---|
| **MCP 伺服器** | `je_auto_control_mcp`（stdio）或 `AC_start_mcp_http_server` | 733 個工具，供 Claude Desktop／Claude Code／自訂 tool loop 使用。除了以 `initialize` 握手的各版協定，也支援無狀態的 MCP 2026-07-28。Bearer 驗證、TLS、稽核記錄、限流、外掛熱重載、CI 假後端。 |
| **REST API** | `je_auto_control start-rest` | Bearer token、逐 IP 限流與鎖定、SQLite 稽核 hook、`/metrics`、`/openapi.json`、`/docs` Swagger UI、`/dashboard`。 |
| **TCP socket 伺服器** | `je_auto_control start-server` | 以換行分隔的 JSON 動作清單。預設綁 `127.0.0.1`。 |
| **pytest 外掛** | 安裝後自動生效 | 輕量 `je_auto_control_pytest` 入口，提供 fixture 與 Gherkin 步驟。升級 editable 工作樹後須重新安裝；明確指定的舊外掛路徑仍相容。 |
| **語言伺服器** | `python -m autocontrol_lsp.server` | 為 `AC_*` 動作 JSON 提供補全與診斷，指令清單直接取自執行期的指令表。 |
| **遠端桌面** | `RemoteDesktopHost` 或 GUI | TCP、WebSocket 或 WebRTC；TOTP、信任清單、TURN 設定、檔案／剪貼簿／音訊同步。 |

除非明確指定，舊版 `python -m je_auto_control -e/-d/--execute_str` 與 `je_auto_control run`
在動作失敗時回傳結束碼 1，成功時為 0；目錄執行累積所有檔案的失敗，stderr 回報失敗數。

公開動作呼叫會隔離變數。需要跨呼叫共用時，使用
`with je_auto_control.execution_scope({"name": "value"}) as scope:`。
巢狀動作共用當次範圍，平行分支與 DAG 節點深複製變數；REST／MCP 請求各自隔離。
明確持有的 `Executor` 在公開範圍外保留自己的狀態。

USB 直通以請求 ID 配對回覆、分片資料與錯誤，遲到回覆不會完成重試。
舊版或尚未確認能力的主機逾時後，須重連並建立新 client；原 handle 的 `closed` 為真。
新版主機回傳 ID，保留原有框標頭與舊端點相容性。

所有伺服器都綁在 `127.0.0.1`。

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

Beta `je_auto_control.api.mobile` 新增凍結的 `DeviceContext` identity，以及延遲建立的
`open_device(context)` session，提供 `bind()`、`capabilities`、`cancel()` 與可重複 `close()`。
矩陣 worker 各有獨立 owner，未指定 target 的 mobile 命令也使用它；重複配置的 target
及外來 client override 會被拒絕。binding 外的 helper 保留相容預設。原生請求逾時
各自受 owner 限制；取消會拒絕晚到結果，且只回收該 client 啟動的 Android helper。
`connected` 僅代表邏輯生命週期。`probe_device_contexts`、`AC_probe_mobile_devices` 與 MCP
`ac_probe_mobile_devices` 不連線或輸入，只檢查依賴；遠端查詢需 host admin。
Device Matrix 在 Actions 提供查詢，矩陣改在背景執行；Script Builder 共用指令。
見[行動裝置指南](../docs/source/Zh/doc/mobile/mobile_doc.rst)及
[不操作硬體的範例](../examples/mobile_contexts.py)。裝置可達性、授權、SDK bootstrap
整體截止時間與恢復仍列驗收。

`DeviceSession` 另提供 `capture()`、`perform(Gesture)` 與 `type_text()`。
`DeviceFrame` 保存不可變 PNG、原生 viewport／方向及 `pixel_to_point()`；`rotated()`
保留換算。UIKit point 不等於 Retina 截圖 pixel，舊 iOS 數值輸入保持相容。
Gesture 附上 `frame=frame` 時，輸入前再檢查 owner／geometry。
擷取時方向改變或長寬比不符會拒絕，避免猜測旋轉。Android Unicode 經 SDK
IME／剪貼簿路徑；`AdbClient.text`／`AC_android_text` 在輸入前拒絕非 ASCII。
SDK 可能設定輸入法／剪貼簿，原生恢復仍列驗收。frame 的 `ocr()`、`locate(strategy)`
共用既有 bytes；binding 內的 `self_heal_locate`／`self_heal_click` 使用同一裝置畫面
及原生 touch，不退回桌面。mobile 全畫面搜尋拒絕桌面 `screen_region` 與非左鍵。
`mobile_capture`、`mobile_gesture`、`mobile_type_text` 對應 `AC_mobile_*`、MCP
`ac_mobile_*` 與 Builder schema，可在 Device Matrix Actions 執行。需提供 device
物件或使用矩陣 owner；遠端操作需 host admin。文字在 action／journal 參數中遮罩，
回應不複誦。WDA pinch 需支援 `/actions`，失敗屬框架例外。
[畫面換算範例](../examples/mobile_frame_mapping.py) 不會輸入。

影像比對與 `screenshot()` 優先使用 OpenCV；缺少時使用 NumPy／Pillow 後端。
Windows arm64 的 Python 3.11+ 會安裝 NumPy 2.4.6。正規化灰階比對、BGR 截圖陣列、
影像檔解碼／編碼、比對預覽及固定畫面自愈沿用既有 Python／AC／GUI／MCP 入口。
替代後端接受 uint8／float32 陣列與 8-bit 影像檔；畫面最多 16,777,216 像素，
每個分塊 FFT 最多 4,194,304 格，超出預算或不支援的操作會拋出框架型別錯誤。
進階 OpenCV 處理／影片與加密／簽章仍需其原生相依。

¹ macOS 的錄製走 Quartz event tap，需要**輔助使用**權限
（系統設定 → 隱私權與安全性 → 輔助使用）。沒有授權時會直接拋出並指名
缺的是哪個權限，而不是安靜地錄到一個空的 session。

² BSD 直接跑同一套 X11 後端——同一個 X server、同一個 `python-Xlib`，而輸入、
錄製與視窗管理就只相依這一個套件。`freebsd` CI job 在真的 FreeBSD 14 上驅動真的
輸入，再從 X server 讀回來；OpenBSD 與 NetBSD 走同一條程式路徑，只是沒有 CI
runner。唯一的例外是螢幕擷取，而卡的是打包不是平台：它走 Pillow／mss 與 OpenCV 或 NumPy 轉換，
而 `opencv-python`、`pillow`、`cryptography` 都沒有發 FreeBSD wheel。從 ports
建起來之後，擷取、影像比對、OCR 與動作加密也都能用——`import je_auto_control`
本身已經不需要它們任何一個。

Wayland 輸入預設使用 libei；CLI 輸入需明確設定
`JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli`，並安裝 **ydotool 1.0 以上**。AutoControl 送的每一個參數都是那一版才有的；0.1.x
（Debian bookworm 與目前所有 Ubuntu 仍以這個名字提供，Debian trixie 則根本沒有）
對同一批參數回傳 0 卻不送出任何事件。AutoControl 會偵測並直接拒絕，
而不是為根本沒送出的輸入回報成功。Arch、Fedora 與 Debian unstable 提供的是 1.0。

`probe_capabilities()`（Beta `je_auto_control.api.capabilities`）、
`AC_probe_capabilities` 與 MCP `ac_probe_capabilities` 分別回報輸入／擷取狀態（`available`、`needs_permission`、
`needs_dependency`、`unsupported`），不請求授權、不送輸入、不截圖，也不載入原生函式庫。
XWayland 明確限於 X11 視窗；找到工具不代表已驗證合成器支援。原生授權取消、失敗或撤銷時
停止輸入，不自動選擇 CLI。Wayland 診斷的 Actions 選單可停止原生控制或允許新的授權嘗試；
下一次明確輸入請求才顯示授權。現有 liboeffis 綁定不支援 restore token，也不保存 token。

預設 libei session 在專用 helper 子程序執行。私有 JSON IPC 每則訊息上限
64 KiB，每批最多 128 個事件；輸入請求時限 3 秒，啟動與授權總時限 38 秒。
逾時、取消或 helper 死亡會終止連線並要求明確重新授權，不重送結果不明的輸入。
正常關閉會在同一份授權下釋放已按住的鍵與按鈕；crash 後的撤銷裝置清理由合成器負責。
診斷的停止／重試操作沿用這份生命週期。`LibeiBackend` 保留為原生驗證使用的
低階程序內綁定，直接呼叫者須負責其程序生命週期。

GUI 與 `AC_diagnose` 預設使用被動檢查；`AC_diagnose include_active=true` 才進行截圖／游標檢查。
Python 為相容保留預設的主動診斷，被動模式使用 `run_diagnostics(include_active=False)`。
這些本機功能不需要付費 API 或 API key。


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

Executor 動作日誌不需要全域輸入 hook。實驗中的 Wayland `PhysicalRecorder` 底層
使用既有讀取權限，讀取明確選定的實體 `/dev/input/event*` 節點，排除核心 virtual／uinput
裝置；回傳原始裝置事件，不轉為桌面座標或重播動作，也不修改 ACL。
`StopShortcutSession` 會明確請求 portal 停止快捷鍵、顯示實際綁定並關閉自己的授權；
拒絕後須先 close 再 start 才重試。Beta `je_auto_control.api.wayland_input` 與舊門面提供上述底層及五個腳本操作：
`start_physical_recording(devices)`、`stop_physical_recording()`、
`start_wayland_stop_shortcut(preferred_trigger='F7')`、`stop_wayland_stop_shortcut()`、
`wayland_input_status()`。各有 `AC_*` 指令、小寫 MCP 工具與 Script Builder schema。
動作日誌遮罩原始停止結果；遠端 RBAC 的五項操作皆要求主機管理權限。
診斷頁提供明確 Actions、JSON 裝置路徑輸入、希望使用的快捷鍵、實際綁定／狀態與原始結果；
每個面板與腳本預設資源獨立持有。停止綁定會停止原生輸入控制並設定持有者的合作取消
`stop_event`，不會中斷任意 Python 工作。原生桌面驗收仍列於 D3／H3。停止與明確重試可取消待授權的原生連線，不會等待其 cache 鎖；取消後的 grant 不能再被發布。
舊 Wayland 全域錄製 hook 仍不可用。視窗管理支援
Windows、macOS（pyobjc）與 X11（含 XWayland）；純 Wayland session 的協定不讓用戶端看到別的程式的視窗，
所以 `list_windows()` 回傳空清單，其餘視窗操作一律拋出帶原因的 `AutoControlUnsupportedOperationException`。對於會忽略合成輸入的應用程式，
可選用驅動層後端（`JE_AUTOCONTROL_WIN32_BACKEND=interception`、
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`、ViGEm 虛擬手把）；驅動未安裝時會自動退回原本行為。

---

## 文件與範例

| 資源 | 內容 |
|---|---|
| [`examples/`](../examples/) | 29 個自足腳本：截圖點擊、OCR、排程器、遠端桌面、agent loop、可觀測性、錄製、變數、熱鍵、觸發器、報表、MCP、REST、機密、外掛、computer use、Wayland、跨主機 DAG、chat-ops、pytest/BDD、錨點定位。 |
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

Linux／macOS Python 3.10 quality job 透過 gdb／lldb 保存 `native-diagnostics`
artifact，包含原生堆疊、套件版本及測試退出碼。原有 coverage 命令及斷言繼續執行；
收集診斷不代表已定位 USB ACL 的間歇崩潰原因。
LLDB 略過啟動器的 exec 暫停；其他非致命停止會視為診斷失敗，不捏造崩潰退出碼。
兩個 debugger 都將 SIGINT 傳給 Python，讓緊急停止斷言正常執行。
Quality 測試安裝 WebRTC／signaling extras 與 HTTP 測試 client。
GUI 翻譯表保留子元件 wrapper，對自身元件使用 weak proxy，避免自身循環引用
把 GUI 銷毀延後到工作執行緒的 GC。

共用 D-Bus 取消會移除連線並喚醒進行中的 I/O；最後一個操作退出時才關閉 descriptor。
讀取每 100 ms 檢查取消，保留原請求時限，拒絕取消後的完成結果；舊 descriptor
回收前不能重連。


macOS Quartz／AppKit 與錄製 tap 僅在原生操作時載入，匯入及純 CLI 檔案錯誤
不初始化這些框架。明確 `grab_logical(metrics=...)` 在所有平台採用虛擬畫面幾何；
macOS 預設擷取仍逐螢幕轉成 Retina points。EI helper 取消也會保留 socket 至
transaction 退出，以短輪詢保留總時限，並拒絕取消後的完成結果。

Docker CI 可手動選擇 `d3-native`，執行 sway、EIS、portal、seat 與 uinput
檢查。seat／uinput 映像用已安裝的 wheel 驗證真實 ydotool 核心裝置會在開啟前
被排除，沒有錄回事件或遺留描述符；原生失敗日誌保存 14 天。執行指令與證據範圍見
[Wayland 驗收](../docs/WAYLAND_ACCEPTANCE.md)。

手動執行 `quality.yml` 可選 `verification_scope=native-shortcut`，僅跑 installed-wheel／
私有 bus 檢查；預設會執行全部 quality jobs。

portal owner 消失或替換會撤銷待授權及有效的快捷鍵 grant；有效 grant 撤銷時
通知該 owner 的停止 callback。原生傳輸驗證使用獨立 GDBus、私有 bus 與 installed wheel，
不代表 GNOME／KDE 真人授權或實體鍵態恢復已驗收。

---

## 授權

[MIT License](../LICENSE) © JE-Chen。
內含與選用第三方元件的授權請見 [Third_Party_License.md](../Third_Party_License.md)。

- **首頁**：https://github.com/Integration-Automation/AutoControlGUI
- **PyPI**：https://pypi.org/project/je_auto_control/
- **文件**：https://autocontrol.readthedocs.io/en/latest/

動作檔改用 Ed25519 第 2 版 JSON 簽章側檔。使用
`je_auto_control signing-keygen --private-key private.pem --public-key public.pem`
建立金鑰，`je_auto_control sign flow.json --private-key private.pem` 簽署，
`je_auto_control verify flow.json --public-key public.pem` 驗證。執行端只部署公鑰，
設定 `JE_AUTOCONTROL_SIGNING_PUBLIC_KEY` 與 `JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS=1`；
私鑰保留在離線簽署端。驗證不會建立金鑰；舊 HMAC 須明確開啟遷移選項。
完整部署及遷移範例見中英文 Sphinx 功能文件。

MCP 使用 schema 語意標記真正的檔案欄位，JSONPath、套件名稱與一般文字保持原義。
`JE_AUTOCONTROL_MCP_ROOTS` 指定允許根目錄，以 OS 路徑分隔符分開
（Windows 用 `;`，Unix 用 `:`）。每個連線的 `roots/list` 與部署設定取交集；
空清單拒絕檔案參數，未設定則在收到 client roots 前保留既有檔案存取。
這不會自動開啟唯讀模式。MCP 預設拒絕 `env://`，使用
`JE_AUTOCONTROL_MCP_ALLOWED_ENV=PUBLIC_SETTING,BUILD_ID` 明確允許名稱；
`file://` 使用同一根目錄策略。Python 本機解析保持原行為，可明確傳入
`policy=je_auto_control.PathPolicy(...)`。

TCP／WebSocket viewer 預設收檔到 `~/Downloads/AutoControl`，本機可用
`JE_AUTOCONTROL_DOWNLOAD_DIR` 指定目錄。Host 須傳入 `reports/result.txt` 等相對
目的地；絕對路徑、磁碟／UNC、目錄穿越與 symlink 越界會被拒絕。
可用 `FileReceiver(base_dir=Path(...))` 選擇其他受限目錄；host 收檔保留既有行為。

螢幕區域使用全域輸入座標，包含副螢幕的負座標。新 Windows 行程在 GUI 初始化前
優先啟用 per-monitor DPI v2；縮放副螢幕上以舊系統 DPI 策略錄製的座標與樣板
需要重新錄製。嵌入的主程式保留已設定的 DPI 策略。macOS 逐螢幕縮成 point
後拼接，主螢幕與區域截圖也使用 point，並支援較舊的 Pillow。
Set-of-Marks 圖例保留全域座標，結果提供擷取的 `origin`。

Anthropic Agent 歷史在三張截圖上限內只追加；超過時以目標、已完成動作數、
最近五十個動作及結果、最新截圖建立新對話。已送出的訊息與簽署 thinking 區塊
保留原樣，不移入新對話。一般工具、beta computer-use 與 GA toolset 都適用。
`AC_run_agent` 沿用現有預設工具匯出。付費 API 驗證需配置 key，待辦見 `Progress.md`。


REST／MCP 個人身分採 opt-in：以 `UserStore(Path("users.json"))` 建立使用者，
角色可選 `viewer`、`operator`、`admin`，啟動伺服器或 GUI 前將
`JE_AUTOCONTROL_USERS` 設為該檔案。viewer 可觀察畫面；operator 可操作輸入與
循序動作腳本；admin 可額外管理使用者、主機、檔案、簽章、稽核與背景工作。
工具搜尋與呼叫使用相同權限，巢狀 executor 指令也檢查。
未設定變數時保留共用 token；已設定但使用者檔為空或不可讀時拒絕登入。
HTTP MCP 會話僅屬於已驗證的使用者，稽核記錄包含 `user_id`。

Admin Console 的 Actions 選單提供重新整理、新增、移除、角色與 token 輪替，
與本機伺服器共用同一 UserStore。門面公開 `rbac_*` 與 `UserStore`；
JSON／Script Builder 提供 `AC_user_add`、`AC_user_list`、`AC_user_remove`、
`AC_user_set_role`、`AC_user_rotate_token`，MCP 使用相應小寫名称。
命令 token 可由 `${secrets.USER_TOKEN}` 提供，結果僅含使用者資料。
GUI 產生的 token 僅顯示一次供保存。


加密依賴下限為 `cryptography>=50.0.0`（lock：50.0.2）。Windows arm64 保留
optional markers，上游仍無符合安全下限的 wheel；Intel Mac 需原始碼編譯。
詳見[安裝矩陣](../docs/CAPABILITY_MATRIX.md)。缺少依賴時，相關能力拋出
門面公開的 `CryptoDependencyError`；`CryptoUnavailableError` 相容 RuntimeError，
`CryptoImportError` 相容 ImportError。錯誤附安裝指引，非加密操作與 Qt-free 匯入可繼續使用。

## 視窗生命週期與版面快照

`focus_window` 確認實際前景視窗，焦點遭拒時拋出
`AutoControlActionException`。`wait_for_window` 每次等待不超過剩餘逾時，亦支援無限 poll 值。
Windows 列舉略過 DWM 隱藏及零面積視窗；投遞文字只送一次字元訊息，控制鍵送含掃描碼與
放開旗標的成對按鍵訊息，並接受 `enter`、`esc` 別名。

`capture_window` 讀取可見邊界，不移動或還原視窗。新的 Windows `save_window_layout`
快照包含原生位置與顯示狀態，`restore_window_layout` 還原時不因邊框而偏移，並保留最大化／
最小化狀態。舊版只有幾何資料的 JSON 仍可讀取；重新儲存快照才能保留原生位置。
注入的 geometry／mover 仍沿用幾何契約。貼齊／格狀／階梯排列使用含原點偏移的主螢幕工作區，
避開工作列。macOS 依視窗 ID 還原時查詢離開螢幕的視窗，仍須取得 Accessibility 授權。

## 鍵盤正確性與秘密輸入

`write("Hi\r\nthere")` 保留大小寫，CRLF 只按一次 Enter。Windows 的字面文字
優先使用 Unicode 注入；明確指定 `is_shift=True` 時，Windows／X11 與 macOS 都會
按住及放開 Shift。Windows 快捷鍵接受 `plus`、`minus`、`comma`、`period`、`slash`
等 OEM 名稱。`type_unicode_keys` 將換行／Tab／退格送為控制鍵。配置表包含區域 OEM
鍵，Shift 半邊無法翻譯時回傳 `None`。

秘密文字使用 `ac.write_secret(secret)` 或 `ac.write(text, secret=True)`。
兩者回傳 `None`，不留下輸入日誌或錄製紀錄；後端失敗資訊改為通用的框架例外。
腳本使用 `["AC_write_secret", {"secret": "${secrets.LOGIN}"}]`；MCP 提供
`ac_write_secret(secret=...)`。Script Builder 隱藏秘密欄位；請儲存秘密參照，因為
動作檔仍會包含傳入的參數。執行器回呼收到遮蔽後的副本，紀錄也遮蔽具名與位置形式的
秘密輸入。WebRunner 的 `WR_ac_basic_auth` 已使用此 `secret` 參數契約。

`mouse_scroll` 預設改為 `scroll_up`，各平台正值都往上滾動。依賴舊預設向下的 X11
腳本請明確傳 `scroll_direction="scroll_down"`。座標使用 `int(round(value))`，
移動前拒絕 NaN／無限值，包括滾動目標。剪貼簿格式描述中缺少的名稱統一為空字串。

其他區域鍵使用 `oem_1` 至 `oem_8`、`oem_102` 等實體鍵名，
不保證在所有配置上輸入相同字元。

## 影像與 OCR 邊界

影像匹配先讀檔案位元組再解碼，因此 Windows 支援非 ASCII 路徑。二維陣列與
Pillow `L` 樣板保留灰階；解碼／匹配失敗拋出 `ImageNotFoundException`。空白或損毀
的影像檔維持 `read_image` 文件所述的 `ValueError` 契約。OCR 會保留長的左框，
讓從框內開始、在下一框結束的片語仍可匹配。

影像及點擊中心使用整數向下取整，包含負螢幕座標。區域擷取拒絕空白／非有限矩形，
並與桌面取交集，不將螢幕外像素補黑。`grab_logical` 回傳裁切後的左上原點；影像
匹配與 OCR 加上此實際原點。Windows、macOS 全域 point 與 Linux 區域截圖共用
此行為。無法預先取得桌面邊界時，使用已擷取畫面的邊界。

Jeffrey_RPA 原有拒絕 slash 的測試需要配合已核准的 OEM 快捷鍵契約更新。
可攜測試遷移補丁位於 `docs/compatibility/jeffrey-rpa-oem-test-migration.patch`；
驗證使用測試副本搭配目前的下游程式碼。等正式 editable 批次停止、整合此分支時再套用。

遠端執行採用伺服器持有的明確 capability 清單。未知指令需 admin 權限，
provider 的 `readOnly` 提示不會授予權限；儲存截圖至檔案也需 admin。巢狀、載入與流程區塊動作在插值及
位置／預設參數繫結後，檢查宣告的檔案路徑。平行與延後工作保留呼叫者身分及允許
根目錄；每個遠端請求與延後執行都有獨立腳本變數。設定的簽章及加密金鑰也必須位於
有效根目錄內，或改用明確的記憶體金鑰。未設定 policy 的本機呼叫沿用既有行為。
色彩／HSV 與 VLM 結果使用實際裁切後的擷取原點。Windows 還原接受最小化視窗
回到先前最大化狀態。

## 結構化動作日誌（Beta）

使用具型別的 `je_auto_control.api.journal` 入口錄製動作及讀取指定 run。
相同三項操作也提供於門面、`AC_execute_journaled`、`AC_read_action_journal`、
`AC_list_journal_runs`、MCP 與 Script Builder。Run History 的 Actions 選單提供錄製及唯讀預覽。

```python
from je_auto_control.api.journal import execute_journaled, read_action_journal
run = execute_journaled([["AC_sleep", {"seconds": 0}]], "actions.jsonl", run_id="demo")
events = read_action_journal("actions.jsonl", run_id=run["run_id"])
```

Schema 版本 1 分開儲存輸入與結果，包含 run／step／parent ID、來源檔案路徑及步驟索引。
開始與結束記錄在共用 run 鎖內追加；讀取時保留開始順序並彙整各步驟最新狀態。
中斷步驟維持 `incomplete`。完整 `${secrets.NAME}` 輸入參照會保留；秘密字面值在一般 log
或追加日誌前遮罩，並標示不可重播。未知 payload 物件省略並附原因，日誌序列化不呼叫其 repr／str。

要明確包覆 executor 呼叫，可使用 `with ActionJournal(path).run()`。
設定 `JE_AUTOCONTROL_ACTION_JOURNAL` 可啟用 executor 自動錄製；未設定時沿用既有行為。
讀取及預覽不執行動作。日誌路徑及其鎖檔遵循有效檔案系統 policy。

## 固定畫面自愈比較（Beta）

使用 `je_auto_control.api.healing` 比較相同已儲存畫面的定位版本，資料包含
標註目標框、預期未命中、原點及像素／邏輯縮放。
```python
from je_auto_control.api.healing import compare_healing_versions
report = compare_healing_versions("benchmarks/self_healing/dataset.json", {
    "before": {"template_path": "benchmarks/self_healing/before.png"},
    "after": {"template_path": "benchmarks/self_healing/after.png"}},
    report_path=".test-tmp/healing-report.json")
```

JSON 與 HTML 報告保留 frame hash、期望幾何及原始 run／step 來源，列出影像命中、
VLM 嘗試、未命中、錯誤及未知標籤。正確率、誤判率與恢復率附分子／分母；
p50／p95 對所有嘗試採線性插值。無成本資料時顯示 unknown；未標註不算正確，
VLM 猜錯不算恢復。歷史操作驗證與定位結果分開，不能歸因於新比較版本。

`create_template_candidate`、`preview_template_candidate`、
`validate_template_candidate`、`accept_template_candidate`、`revert_template_revision`
提供不可變快照及明確審閱。接受前須有正確正例、已標註資料全數正確、無錯誤／誤判，
且原始樣板及候選 hash 未改動。預覽不套用變更；還原檢查目前仍為已接受候選。

六項操作均有對應 `AC_*`、MCP 與 Script Builder。Self-Healing 的 Actions 選單
透過保留 scope 的背景工作執行比較／修訂，面板顯示指標、失敗及原始步驟表與兩張預覽。
HealEvent schema 2 保留實際擷取身份、策略耗時、backend／model 及日誌 ID，仍可讀
舊 schema 1。缺少的證據保持 unknown。版本控制中的合成 benchmark 是離線證據，
實機及付費模型驗證分開進行。

## 日誌候選腳本產碼（Beta）

使用 `je_auto_control.api.codegen` 產生指定 run 的候選：
```python
from pathlib import Path
from je_auto_control.api.codegen import generate_candidate_from_log
candidate = generate_candidate_from_log(Path("benchmarks/journal_codegen/actions.jsonl"), run_id="demo")
print(candidate.code, candidate.manifest, candidate.warnings)
```

產碼驗證單一日誌快照，保留內容 hash、所有 step／parent／source 身份、狀態及
已觀察到的 retry 次序。僅完成且可重播的葉節點交給既有產碼器；失敗、中斷及
遮罩步驟仍留在 manifest 與警告。完整 `${secrets.NAME}` 參照保留，秘密字面值及
結果不轉成重播輸入；不求值輸入 repr，也不執行產物。

候選明確標示為 **observed path only**，按開始順序串行排列，不重建原本分支／
迴圈／retry／parallel 語意。檢查已安裝指令、必要 Python 參數及 executor dry-run，
Python 目標另通過 AST 驗證；Robot 的 Python AST 指標不適用。執行或擴充前須審閱。
```powershell
python -m je_auto_control.cli codegen --from-log benchmarks/journal_codegen/actions.jsonl --run-id demo -o .test-tmp/test_observed.py
```

`-o` 儲存原始碼及 `.manifest.json`、`.actions.json` 附檔，不能覆寫輸入日誌。
省略時 CLI 將原始碼輸出至 stdout，警告至 stderr。既有 target／style／name／
failure-bundle 旗標可用；日誌模式預設 `actions`，一般動作檔仍為 `calls`。
`generate_journal_candidate`、`AC_generate_journal_candidate`、
`ac_generate_journal_candidate` 回傳相同結構化 JSON 產物。

Recording Editor 與 Script Builder 的 Actions 提供候選審閱，保留 scope 的背景工作
產生遮罩後差異、原始碼及來源唯讀預覽。匯入是獨立編輯操作；匯出儲存已審閱候選
及附檔。預覽與匯入均不執行候選動作。`benchmarks/journal_codegen` 合成範例是離線契約證據。

缺少已記錄解析綁定的一般 `${var}` 輸入會略過並顯示警告，避免誤用新執行器的變數。
驗證也檢查 block 指令的物件參數及必填欄位。日誌對位置參數按簽章辨識秘密，
遮罩敏感變數 getter 的回傳結果，並將未處理的子步驟失敗傳到容器／run 狀態；
成功捕捉或重試處理的失敗仍保持成功狀態。
插值變數名稱在記錄前保守視為私密資料。
已辨識的私密純量（包含數值 PIN）也會在結果／日誌副本中遮罩。

## 持久化設定伺服器（Beta）

訊令服務以 SQLite 保存設定 bucket，重啟後仍保留。使用 `--config-store PATH`
或 `AC_CONFIG_STORE_PATH`；預設在首次使用時解析為
`~/.je_auto_control/config_sync.sqlite`。匯入 API 或建立 app 不會建立資料庫。

`PUT /config/{user_id}` 必須傳入包含 `schema_version: 2`、`base_revision`、
`operation_id`、`bucket` 的新版 envelope。版本檢查與寫入在同一交易完成。
GET 回傳已提交的 `revision` 及 `cas_supported: true`；過期寫入回 HTTP 409。
相同操作重送回原提交版本，不覆寫後來的資料；重用 ID 傳不同資料會被拒絕。
帳號隔離、共享秘密與資料量／帳號上限仍有效，瀏覽器 preflight 支援 PUT。
WebRTC 待配對連線仍採 TTL。

`je_auto_control.api.config_sync` 提供 `ConfigStore`、`ConfigBucket`、
`ConfigSyncError`、`ConfigRevisionConflict`、`ConfigStoreCapacityError`。
ConfigSyncClient 預設使用受保護的因果同步與持久化 outbox。
明確使用 `SyncClientOptions(legacy_writes=True)` 時，也必須開啟伺服器的
`--allow-legacy-config-writes` 遷移選項。設定同步分頁使用共用受保護服務。

## 因果同步與離線重送（Beta）

使用 `causal_upsert`／`causal_remove` 搭配用戶端穩定的 `device_id` 編輯定義。
`SyncEntry` 帶有版本向量、來源及操作 ID；`merge_entries` 保留並行修改的雙方資料，
不依本機時鐘挑選勝方。`ConfigBucket.entries()` 排除未解決衝突與刪除項目。
審閱後可明確做因果編輯解決衝突；舊版時間戳記 helpers 仍保留。

`ConfigSyncClient.sync()` 收到確認的 HTTP 409 後重新讀取、合併並有限次重試。
SQLite `SyncOutbox` 依 endpoint 與帳號保存原 envelope，成功與否不確定時，
重啟後仍以原操作 ID 重送。認證僅留在記憶體；pending、衝突與重試耗盡的資料不丟棄。
`retry_pending(cancel=...)` 使用有限退避並在傳送間檢查取消；`close()` 釋放資料庫，
保留佇列資料。

共用 `__sync_devices__` 登錄記錄確認版本與退休狀態。新刪除只在 CAS envelope
取得提交版本，所有已知有效裝置確認後才回收，不因經過幾天而移除。
退休或登錄衝突會阻擋增量同步及 push；`full_resync()` 明確取得完整受保護快照後再加入。
完整同步前必須審閱待送操作；`retire_device()` 也須明確呼叫。
本機 `SyncOutbox` peer 介面可跨重啟保留退休狀態。
目前證據是受控 SQLite／HTTP 測試，實體多機驗證仍待完成。

## 定義與資產同步（Beta）

設定同步分頁、六個 `AC_config_sync_*`／`ac_config_sync_*` 入口及 Script Builder
共用 headless 的預覽、受保護交換、明確套用、持久化重送、本機狀態及資產服務。
面板顯示提交版本、待送數、保留衝突、離線及 CAS 保護；Actions menu 的 worker
有獨立取消事件，在操作之間檢查取消，目前有逾時限制的請求結束後釋放用戶端。

本機 JSON 的 `scripts`、`locators`、`hotkeys`、`triggers`、`address_book` 各自
對應 ID／定義物件。未變動的快照保留因果 ID；重建 adapter 時應保存其 state mapping。
檔案服務將因果 state 放在明確工作目錄，依帳號與正常化 endpoint 隔離。
命名秘密、依函式簽章綁定的 action 參數、已知秘密的回顯、認證 URL、絕對機器路徑
轉成本機 `{"$local": "/欄位/路徑"}` 參照；`${secrets.NAME}` 原樣保留。
接收端缺少本機參照會列為未解決。任意 Python／原始碼及未分類 literal 不在此
結構化隱私契約內；接收定義不啟動 listener、引擎、連線或腳本。

預覽及交換保留所有因果候選，不套用本機定義。套用檢查原檔雜湊；`choices`
明確選取 `sync_conflict` 陣列索引，例如 `{"locators/button": 0}`，解決後推進
所有已知候選的向量。收到的熱鍵／觸發器在加入前停用，停用熱鍵不進入 listener 快照。

資產清單含 `path`、`sha256`、`size`；六個入口中的資產操作從明確來源目錄接收，
Python `sync_assets` 支援 streaming transport。每檔限制 256 MiB，拒絕越界、symlink
及 Windows 轉向檔名，完整大小／雜湊驗證後才原子取代。取消、損毀或斷線清除
本次暫存檔，既有目的檔保留；此前完成的檔案維持發布。定義宣告的 `assets` 必須
先在定義檔目錄下驗證才能套用；資產作為資料保存，雜湊驗證不判斷內容是否含秘密。

資料夾維持只新增／更新：內容雜湊偵測同 mtime 修改，連續兩次穩定觀察後傳送，
失敗重試且接收檔案不回送。停止時仍保留尚未結束 sender 的所有權。TCP 剪貼簿
使用有限 origin／event／hash 去重，抑制收到內容的下一次回送，舊 envelope 仍可讀。
目前證據是受控 HTTP／SQLite、檔案及 offscreen Qt；實體多機驗證仍待完成。

## 遠端連線所有權（Beta）

Remote Desktop 每個面板各自擁有 TCP、WebSocket、WebRTC 的 host／viewer session。
連線或關閉一個面板會保留其他面板與腳本。callback 保存請求授權與 session generation；
已結束連線的排隊影格、狀態、傳檔與訊令結果會丟棄。面板銷毀會停止所屬傳輸與
WebRTC 背景工作；清理失敗的傳輸保留在 registry，供明確重試。

24 個傳輸指令都接受 keyword-only `session_id`。省略時選取該 transport／role 的
script default；新 default 只替換原 default。明確 ID 配置新的具名連線，不改 default；
仍在記錄中的已配置 ID 不可重用。既有七個 TCP MCP 工具接受相同 ID，另提供
17 個 WebSocket／WebRTC 及三個生命周期工具。Script Builder 以有限 JSON 編輯輸入物件與 region。

`je_auto_control.api.remote_sessions` 匯出不可變的 `RemoteSession`、`SessionStatus`
（同一快照型別）、`SessionEvent`、型別化錯誤、`get_remote_session`、
`disconnect_session`、`list_remote_session_events`。AC／MCP 的 JSON 操作為
`AC_remote_session_status`、`AC_remote_disconnect_session`、`AC_remote_session_events`
及對應小寫工具名稱。optional `owner` 核對擁有者；遠端授權仍需 `MANAGE_HOSTS`。
事件最多保存 1,024 筆，非 default 已關閉 session 保存 256 筆；狀態與事件不含秘密或資源物件。

session `active` 表示本機配置成功；WebRTC 對端就緒程度以傳輸的 `authenticated`／`state`
判斷。GUI 多 viewer host 的狀態另含 `peers`／`connected_clients`。session／事件只存在
本行程，不是持久化設定同步資料。`disconnect_session(id, owner=...)` 只影響該連線。
目前證據是受控 transport 替身與 offscreen Qt；實體多機驗證仍待完成。

## 同步復原與延後 Apply（Beta）

Exchange 在第一次網路請求前保存尚未送出的本機發布意圖。Retry 先與最新的受保護
快照做因果合併，才建立 CAS 請求；Preview 與開始前取消的操作不排入發布意圖。
已送出但結果未明的請求保留原 ID 與內容。明確 Retry 可重新嘗試耗盡的重送；
只有伺服器確認 HTTP 409 的請求才可重新合併並原子替換。未提交的刪除 receipt
重新指定到新 CAS revision；每次重新合併前再次驗證遠端隱私。
本機狀態回傳 `recovery` 各狀態數量，Exchange 用 `recovery_required` 區分需要
復原的情況與網路離線。

Exchange 與 Retry 不修改本機定義。收到預覽不代表已套用：只有明確 Apply 解決
全部項目與必要資產／參照後才推進 `applied_revision`，下一次 Exchange 才發布
該確認。未解決項目仍保留刪除義務，因此延後 Apply 不會讓已回收資料復活。
直接因果 client 預設確認回傳快照；需要明確本機套用的 adapter 使用
`SyncClientOptions(acknowledge_on_sync=False)`。只有同一因果刪除的 receipt 資料
會合併；獨立編輯或不同 JSON 值仍需衝突審閱。

Quick Connect 在最後交付畫面、錯誤與游標時檢查 session generation；WebRTC
影片切換使用相同保護，停止、替換與認證成功會撤銷預約重連。資料夾同步保留
仍在結束中的傳送者，等停止後才允許重啟。舊剪貼簿只抑制連續相同內容，允許
A→B→A；新版仍以有限事件 ID 去重，並抑制一次收到內容的回送。
證據來自受控 SQLite／網路邊界與 offscreen Qt；實體多機驗證仍待完成。

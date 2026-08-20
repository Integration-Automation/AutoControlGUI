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
- **不寫 Python 也能腳本化。** 773 個 `AC_*` 指令涵蓋全部功能，因此一個 JSON 檔能做到函式庫
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
| `gui` | PySide6 桌面應用程式（48 個分頁） |
| `webrtc` | WebRTC 遠端桌面、USB 直通（`aiortc`、`av`） |
| `signaling` | 獨立的訊令／rendezvous 伺服器（`fastapi`、`uvicorn`） |
| `discovery` | mDNS / Zeroconf 區網主機探索 |
| `pdf` / `office` | PDF 與 Excel／Word／PowerPoint 讀取 |
| `fuzzy` / `locale` | `rapidfuzz` 模糊比對、`babel` 地區解析 |
| `s3` / `audio` | S3 產出物儲存、系統音量控制 |

**系統需求：** Python ≥ 3.10。Linux 請先安裝建置前置套件：

```bash
sudo apt-get install cmake libssl-dev
```

OCR、VLM 與 LLM 後端（`pytesseract`、`easyocr`、`paddleocr`、`anthropic`、`openai`）
都是按需載入——只裝你實際會用到的。

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
python -m je_auto_control          # 或：je_auto_control.start_autocontrol_gui()
```

錄製一段流程、在視覺化 Script Builder 裡編輯，然後存成 CLI 能直接執行的同一種 JSON 格式。

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
| JSON 腳本 | `execute_action`、`execute_files` | 全部 773 個指令 | Script、Script Builder |
| 變數與流程控制 | `execute_action_with_vars` | `AC_set_var`、`AC_loop`、`AC_for_each`、`AC_try`、`AC_retry` | Variables |
| 資料驅動執行 | — | `AC_for_each_row`（CSV／JSON／SQLite／Excel） | Data Sources |
| 斷言 | `assert_text`、`assert_image` | `AC_assert_text` 等 21 個 | Assertions |
| 測試套件 | `run_suite` | `AC_run_suite` | Test Suites |
| 排程（間隔 + cron） | `default_scheduler` | — | Scheduler |
| 全域熱鍵 | `default_hotkey_daemon` | — | Hotkeys |
| 事件觸發 | `default_trigger_engine` | `AC_email_trigger_add` | Triggers、Webhooks、Email |
| 視窗管理 *(僅 Windows)* | `list_windows`、`focus_window` | `AC_focus_window`、`AC_snap_window` | Window Manager |
| 剪貼簿（文字 + 影像） | `get_clipboard`、`set_clipboard`、`get_clipboard_image`、`set_clipboard_image` | `AC_clipboard_get`、`AC_clipboard_set`、`AC_clipboard_get_image`、`AC_clipboard_set_image` | — |
| 遠端桌面 | `RemoteDesktopHost`、`RemoteDesktopViewer` | `AC_start_remote_host`、`AC_remote_connect` | Remote Desktop |
| USB 列舉與直通 | `list_usb_devices`、`enable_usb_passthrough` | `AC_usb_*`（16 個指令） | USB Devices、USB Share |
| 機密保險庫 | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| 報表（HTML／JSON／XML） | `generate_html_report` | `AC_generate_html_report` | Report |
| 執行歷史 | — | — | Run History |
| 指標與追蹤 | `default_metric_registry`、`render_metrics_text` | — | — |
| 系統診斷 | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| 測試碼產生 | `generate_code` | — | — |

除了這張表，`utils/` 底下還有 310 個無頭套件，涵蓋斷言、韌性、資料品質、i18n 稽核、遮蔽、
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
舊版 `python -m je_auto_control -e file.json` 進入點仍然可用。

---

## 伺服器與整合

| 介面 | 啟動方式 | 說明 |
|---|---|---|
| **MCP 伺服器** | `je_auto_control_mcp`（stdio）或 `AC_start_mcp_http_server` | 676 個工具，供 Claude Desktop／Claude Code／自訂 tool loop 使用。Bearer 驗證、TLS、稽核記錄、限流、外掛熱重載、CI 假後端。 |
| **REST API** | `je_auto_control start-rest` | Bearer token、逐 IP 限流與鎖定、SQLite 稽核 hook、`/metrics`、`/openapi.json`、`/docs` Swagger UI、`/dashboard`。 |
| **TCP socket 伺服器** | `je_auto_control start-server` | 以換行分隔的 JSON 動作清單。預設綁 `127.0.0.1`。 |
| **pytest 外掛** | 安裝後自動生效 | 提供 fixture 與供 pytest-bdd／behave 使用的 Gherkin step library。 |
| **語言伺服器** | `python -m autocontrol_lsp.server` | 為 `AC_*` 動作 JSON 提供補全與診斷，指令清單直接取自執行期的指令表。 |
| **遠端桌面** | `RemoteDesktopHost` 或 GUI | TCP、WebSocket 或 WebRTC；TOTP、信任清單、TURN 設定、檔案／剪貼簿／音訊同步。 |

除非明確指定，所有伺服器都綁在 `127.0.0.1`。

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
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` 並在 X11 session 下執行。視窗管理目前僅
Windows 有實作，其他平台會拋出明確的 `NotImplementedError`。對於會忽略合成輸入的應用程式，
可選用驅動層後端（`JE_AUTOCONTROL_WIN32_BACKEND=interception`、
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`、ViGEm 虛擬手把）；驅動未安裝時會自動退回原本行為。

---

## 文件與範例

| 資源 | 內容 |
|---|---|
| [`examples/`](../examples/) | 27 個自足腳本：截圖點擊、OCR、排程器、遠端桌面、agent loop、可觀測性、錄製、變數、熱鍵、觸發器、報表、MCP、REST、機密、外掛、computer use、Wayland、跨主機 DAG、chat-ops、pytest/BDD、錨點定位。 |
| [Read the Docs](https://autocontrol.readthedocs.io/en/latest/) | 完整 API 參考，含英文與中文。 |
| [architecture_explore.md](../architecture_explore.md) | 逐層記錄每個模組的職責。 |
| [docs/CAPABILITY_MATRIX.md](../docs/CAPABILITY_MATRIX.md) | 能力 × 平台對照矩陣。 |
| [docs/API_LIFECYCLE.md](../docs/API_LIFECYCLE.md) | 穩定 API 與棄用政策。 |
| [WHATS_NEW.md](../WHATS_NEW.md) | 各版本更新說明。 |
| [CHANGELOG.md](../CHANGELOG.md) | 相容性變更記錄。 |
| [SECURITY.md](../SECURITY.md) | 安全政策與回報方式。 |

---

## 開發

```bash
git clone https://github.com/Intergration-Automation-Testing/AutoControl.git
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

- **首頁**：https://github.com/Intergration-Automation-Testing/AutoControl
- **PyPI**：https://pypi.org/project/je_auto_control/
- **文件**：https://autocontrol.readthedocs.io/en/latest/

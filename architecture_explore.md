# AutoControl 架構全覽（architecture_explore）

> 本文件為全專案架構掃描結果，逐層記錄每個模組的職責。
>
> **掃描方法**：以 AST 走訪 `je_auto_control/`、`autocontrol-lsp/`、`autocontrol_driver/`、`AutoControl/`、`exe/`、`benchmarks/`，
> 擷取每個模組的 docstring 與頂層公開名稱；統計數字取自實際檔案，非估算。
> 指令數與公開 API 數以 `executor.known_commands()` 與 `je_auto_control.__all__` 在工作樹上實測取得。
>
> **掃描時間**：2026-08-21　**版本**：`pyproject.toml` version `0.0.220`　**分支**：`feat/qt-thread-marshal-isolation`

---

## 1. 專案定位與規模

`je_auto_control` 是一套跨平台 GUI 自動化框架，涵蓋 Windows（Win32 API）、macOS（pyobjc/Quartz）、
Linux X11（python-Xlib）與 Linux Wayland（libei / ydotool），並延伸到 Android（ADB / uiautomator2）與
iOS（WebDriverAgent）。核心能力是滑鼠／鍵盤控制、影像辨識、螢幕擷取、動作腳本化與報表產生；
在此之上長出了 AI agent、遠端桌面、USB 直通、MCP／REST／TCP 伺服器、可觀測性與測試治理等子系統。

| 指標 | 數值 |
| --- | ---: |
| Python 模組總數（含周邊子專案） | 1,030 |
| 程式碼總行數 | 140,157 |
| `je_auto_control/utils/` 子套件數 | 310 |
| `AC_*` 動作指令數（`known_commands()` 實測） | 773 |
| 套件門面 `__all__` 公開名稱數 | 1,238 |
| GUI 分頁數（`main_widget` 註冊） | 48 |
| MCP 工具數（`build_default_tool_registry()` 實測） | 676 |
| `test_*.py` 測試檔／測試函式 | 478 / 4,654 |
| 範例腳本 | 27 |

**技術基線**：Python ≥ 3.10、MIT 授權、必要相依只有 `je_open_cv`／`opencv-python`／`pillow`／`mss`／
`defusedxml`／`cryptography`（加上各平台專屬的 pyobjc、python-Xlib）；其餘全部是選用 extras
（`gui`、`webrtc`、`signaling`、`discovery`、`pdf`、`office`、`fuzzy`、`s3`、`locale`、`audio`）。
大量子系統刻意只用標準庫實作（REST 伺服器、JSON Schema、JWT、TOTP、WebSocket 框架、ACME、
USB/IP 協定、Prometheus 指標），以維持這條輕相依基線。

---

## 2. 分層架構

```
┌──────────────────────────────────────────────────────────────────────────┐
│  介面層 Entry Points                                                      │
│  cli.py (je_auto_control 指令) │ __main__.py (argparse) │ gui/ (PySide6)  │
│  utils/socket_server (TCP)     │ utils/rest_api (HTTP)  │ utils/mcp_server │
│  utils/chatops (Slack)         │ utils/pytest_plugin    │ autocontrol-lsp  │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  全部只呼叫下面這一層，不含業務邏輯
┌───────────────────────────────▼──────────────────────────────────────────┐
│  執行核心 Execution Core                                                  │
│  utils/executor/action_executor.py  ── Executor.event_dict（773 個 AC_*） │
│  utils/executor/flow_control.py     ── 34 個區塊指令（迴圈/分支/try/巨集） │
│  utils/script_vars ── ${var} 插值   │ utils/json ── action 檔 I/O          │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│  能力層 utils/（310 個子套件，全部無 Qt 相依）                             │
│  影像辨識 │ OCR │ 無障礙樹 │ 定位自癒 │ AI/Agent │ 遠端桌面 │ USB         │
│  報表觀測 │ 資料 │ 安全 │ 韌性 │ 系統整合 │ 排程觸發 │ 網路協定           │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│  平台無關 API  wrapper/                                                   │
│  auto_control_mouse / keyboard / screen / image / record / window         │
│  platform_wrapper.py ── 依 sys.platform 載入唯一後端                      │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│  平台後端 Platform Backends（僅載入當前 OS）                              │
│  windows/ (ctypes Win32 + Interception 驅動)                              │
│  osx/ (pyobjc Quartz)                                                     │
│  linux_with_x11/ (python-Xlib + 選用 uinput)                              │
│  linux_wayland/ (libei via portal/EIS + ydotool/wtype + 擷取工具分層)     │
│  android/ (ADB + uiautomator2)  │  ios/ (WebDriverAgent)                  │
└──────────────────────────────────────────────────────────────────────────┘
```

**三條不可違反的架構約束**（由 CLAUDE.md 定義、CI 測試強制）：

1. **`import je_auto_control` 絕不載入 PySide6**。GUI 進入點在 `start_autocontrol_gui()` 內延遲匯入。
   （已於工作樹實測確認：匯入門面後 `sys.modules` 無任何 PySide6。）
2. **每個功能都必須同時有無頭 API 與 GUI 介面**。業務邏輯一律住在 `utils/` 或 `wrapper/`，
   Qt widget 只是把使用者輸入翻譯成對無頭核心的呼叫。
3. **每個功能都要接上 `AC_*` 指令**，讓它自動可從 JSON 動作檔、TCP 伺服器、排程器、
   MCP 伺服器與視覺化腳本編輯器使用，不需要寫任何 Python 膠水碼。

---

## 3. 核心設計模式

| 模式 | 落點 | 說明 |
| --- | --- | --- |
| **Strategy** | `wrapper/platform_wrapper.py` | 依 `sys.platform` 只匯入當前 OS 的 `keyboard`／`mouse`／`screen`／`recorder` 實作；Linux 再細分 Wayland／X11，Wayland 後端不可用時自動退回 XWayland 並記警告。新增平台不需要改 wrapper。 |
| **Facade** | `je_auto_control/__init__.py` | 把 1,200 個公開名稱集中再匯出，使用者只 `import je_auto_control`。`api/core.py` 另提供一個小而穩定的版本化門面（7 個名稱）給新整合使用。 |
| **Command** | `utils/executor/action_executor.py` | `Executor.event_dict` 是字串 → callable 的分派表；JSON 動作檔即指令序列，因此可錄製、序列化、重播、簽章。 |
| **Observer** | `utils/callback/`、`utils/observer/`、`utils/triggers/` | 動作完成後觸發回呼；畫面出現／消失／變化與外部事件（webhook／IMAP／檔案）驅動腳本。 |
| **Template Method** | `utils/generate_report/` | HTML／JSON／XML 三個產生器共用「收集紀錄 → 格式化 → 寫檔」骨架，各自實作渲染。 |
| **Adapter / Backend seam** | `accessibility/backends/`、`ocr/backends/`、`vision/backends/`、`llm/backends/`、`agent/backends/`、`hotkey/backends/`、`usb/passthrough/*_backend.py`、`usbip/backend.py` | 每個外部能力都有抽象基底 + 具體實作 + null fallback，讓無相依環境仍可載入與測試。 |
| **Adapter（螢幕擷取）** | `utils/cv2_utils/screen_grabber.py` | 全框架唯一決定「這台機器怎麼讀螢幕」的地方。平台後端若發布 `grab_image`（目前只有 Wayland 需要），就把它包成呼叫端已在用的形狀（`ImageGrab` 或 `mss`）；否則原樣交還真正的函式庫，Windows／macOS／X11 行為完全不變。後端另可發布 `layout_origin`，由 `backend_layout_origin()` 轉給需要把畫面上的點換回螢幕座標的路徑（`grab_logical`、mss shim 的 monitor 矩形）。 |
| **Registry / Singleton** | `remote_desktop/registry.py`、`rest_api/rest_registry.py`、`profiler`、`run_history`、`secrets` | 行程級單例，讓 `AC_*` 指令能操作長生命週期的伺服器與狀態。 |

---

## 4. 三條主要執行路徑

**A. JSON 動作腳本（最主要路徑）**

```
action.json ─► utils/json/json_file.read_action_json
            ─► utils/executor/action_schema.validate_actions   （結構驗證，拒絕未知指令）
            ─► Executor.execute_action
                 ├─ _resolve_runtime_args  ── ${var}/${secrets.*} 插值（巢狀 body 延後解析）
                 ├─ flow_control BLOCK_COMMANDS ── AC_loop / AC_if_* / AC_try / AC_retry …
                 └─ event_dict[name](**args) ── 呼叫 wrapper 或 utils 的實作
            ─► default_profiler.measure + observability 指標
            ─► 執行紀錄 dict（每個動作一筆，重複動作加序號後綴）
```

錯誤處理原則：`AutoControlException` 家族在此被「收納」成紀錄而非中止整份腳本；
但 `AutoControlAssertionException`（`AC_assert_*` 失敗）即使在 `raise_on_error=False` 下仍會往上拋，
確保斷言不會被靜默吃掉。`execute_files` 會先呼叫 `require_signed_actions` 驗簽。

**B. 錄製 → 重播 → 產碼**

```
wrapper/auto_control_record.record ─► 平台 listener（win32/x11/osx）
   ─► stop_record / record_to_json ─► action list
   ─► utils/semantic_recording.enrich  （加語義錨點，可換機重播）
   ─► utils/recording_edit             （裁切／過濾／縮放）
   ─► utils/codegen                    （產生 pytest / python / robot 程式碼）
```

**C. 遠端與外部驅動**

```
TCP socket_server ─┐
REST rest_api     ─┤
MCP mcp_server    ─┼─► execute_action（同一個全域 Executor 實例）
ChatOps chatops   ─┤
Scheduler/Triggers─┘
```

所有伺服器預設綁 `127.0.0.1`；REST 有 Bearer token + 限流，MCP 有稽核與限流，
socket server 有 8 MiB 讀取上限與 30 秒 handler timeout。

---

## 5. 逐層模組清單

### 5.1 套件入口與公開介面

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `je_auto_control/__init__.py` | 1,970 | **套件門面**。集中匯入並再匯出 1,200 個公開名稱，以功能區塊註解分段（callback／exception／executor／a11y／vision／clipboard…）。 |
| `je_auto_control/__main__.py` | 70 | 舊版 argparse 進入點：`-e` 執行單檔、`-d` 執行整個目錄、`--execute_str` 執行 JSON 字串、`-c` 建立專案。 |
| `je_auto_control/cli.py` | 323 | **主 CLI**（`je_auto_control` console script）。子命令：`run`（含 `--var`／`--dry-run`）、`validate`／`lint`、`list-commands`、`fmt`、`record`、`codegen`、`failure-bundle`、`list-jobs`、`start-server`、`start-rest`、`version`。所有子命令延遲匯入，確保不碰 Qt。 |
| `je_auto_control/api/__init__.py` | 22 | 版本化整合進入點。 |
| `je_auto_control/api/core.py` | 19 | **穩定無頭 API 門面**：只暴露 `execute_action`、`execute_action_with_vars`、`generate_code`、`run_diagnostics`、`create_failure_bundle`、`failure_bundle_on_error`、`FailureBundleOptions`。mypy 型別契約只針對這一面。 |
| `je_auto_control/utils/deprecation.py` | 35 | 公開 API 的一致性棄用警告。 |
| `je_auto_control/utils/http_headers.py` | 32 | 入站 HTTP 標頭的共用防禦式解析。 |
| `je_auto_control/utils/sqlite_support.py` | 56 | 選用標準函式庫 `sqlite3` 的取用點：`require_sqlite3()`／`sqlite3_available()`／`SQLITE_ERRORS`。十個以 SQLite 存放狀態的子系統都經由這裡，所以 FreeBSD 這種把 `sqlite3` 另外包成 `databases/py-sqlite3` 的 Python 仍然 import 得起門面。 |

### 5.2 wrapper 抽象層

平台無關 API，所有上層（executor、GUI、伺服器）只呼叫這裡，不直接碰後端。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `wrapper/platform_wrapper.py` | 73 | **Strategy 樞紐**。依 `sys.platform` 匯入唯一後端並匯出 `keyboard`、`keyboard_check`、`keyboard_keys_table`、`mouse`、`mouse_keys_table`、`special_mouse_keys_table`、`screen`、`recorder`；載入失敗直接拋 `AutoControlException`（fail fast）。 |
| `wrapper/_platform_windows.py` | 325 | Windows 後端組裝：Win32 ctypes 模組 + 虛擬鍵表 + 選用 Interception 驅動。 |
| `wrapper/_platform_osx.py` | 156 | macOS 後端組裝（Quartz 事件 + osx 虛擬鍵表）。 |
| `wrapper/_platform_linux.py` | 267 | X11 後端組裝（python-Xlib + 選用 uinput）。 |
| `wrapper/_platform_wayland.py` | 57 | Wayland 後端組裝（libei／ydotool／grim）。 |
| `wrapper/auto_control_mouse.py` | 366 | 滑鼠 API：位置讀寫、按下／放開／點擊、捲動、座標前處理、送訊息給指定視窗。 |
| `wrapper/auto_control_keyboard.py` | 273 | 鍵盤 API：鍵表查詢、按下／放開／敲擊、`write` 字串、`hotkey` 組合鍵、按鍵狀態偵測。 |
| `wrapper/auto_control_screen.py` | 103 | 螢幕 API：`screen_size`、`screenshot`（可指定區域）、`get_pixel`。 |
| `wrapper/auto_control_image.py` | 83 | 影像 API：`locate_all_image`、`locate_image_center`、`locate_and_click`。 |
| `wrapper/auto_control_record.py` | 107 | 錄製 API：`record`／`stop_record`／`record_to_json`（支援 stop event 與逾時）。 |
| `wrapper/auto_control_window.py` | 278 | 視窗管理門面：列舉、尋找、聚焦、等待、關閉、顯示狀態、幾何、所屬行程 PID、依行程列舉／最小化視窗、不搶焦點的投遞式輸入（目前僅 Windows 實作）。 |

### 5.3 平台後端

#### Windows（`windows/`，23 檔／1,894 行）

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `core/utils/win32_ctype_input.py` | 73 | `SendInput` 的 ctypes 結構定義與送出。 |
| `core/utils/win32_vk.py` | 188 | Windows 虛擬鍵碼對照表。 |
| `core/utils/win32_keypress_check.py` | 21 | `GetAsyncKeyState` 按鍵狀態查詢。 |
| `mouse/win32_ctype_mouse_control.py` | 220 | 滑鼠事件產生（含多螢幕絕對座標換算）。 |
| `keyboard/win32_ctype_keyboard_control.py` | 55 | 鍵盤事件產生。 |
| `record/win32_input_hook.py` | 207 | 單一一組低階鍵鼠 hook（`WH_KEYBOARD_LL`／`WH_MOUSE_LL`）＋訊息迴圈，產生帶時間戳的事件時間軸；停止時以 `PostThreadMessageW(WM_QUIT)` 收掉執行緒，不會每錄一次就漏一條。 |
| `record/win32_record.py` | 41 | 把 `win32_input_hook` 的時間軸轉成 action list（含按鍵放開、滾輪與間隔）；整形本體與 macOS 共用 `utils/input_macro/recorder_base.py`。 |
| `screen/win32_screen.py` | 89 | 螢幕尺寸與像素讀取。**每支 Win32 函式都明寫 argtypes/restype**（HDC 是指標寬度，走預設的 c_int 會截斷，錯誤會沉默地擴散到 GetPixel／ReleaseDC），並持有自己的 user32／gdi32 handle。import 時呼叫 `SetProcessDPIAware()`——**行程層級且不可還原**，實體↔邏輯座標換算請走 `utils/monitor_layout`。 |
| `window/windows_window_manage.py` | 366 | 視窗列舉／聚焦／關閉／最小化／幾何／所屬行程 PID／投遞式輸入（`auto_control_window` 的實作）。**每支 Win32 函式都明寫 argtypes/restype**，並持有自己的 user32 handle，避免把原型外溢到別的模組；hwnd 一律是 int。 |
| `message/window_message.py` | 97 | 直接對視窗送 `WM_*` 訊息（背景輸入）。 |
| `interception/_dll.py` | 231 | `interception.dll` 的延遲 ctypes 載入與結構定義。 |
| `interception/keyboard.py` | 71 | 經 Interception 驅動的鍵盤輸入（繞過部分反自動化偵測）。 |
| `interception/mouse.py` | 161 | 經 Interception 驅動的滑鼠輸入。 |

#### macOS（`osx/`，17 檔／907 行）

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `core/utils/osx_vk.py` | 114 | macOS 虛擬鍵碼表。 |
| `mouse/osx_mouse.py` | 137 | Quartz `CGEvent` 滑鼠事件。 |
| `keyboard/osx_keyboard.py` | 129 | Quartz 鍵盤事件。 |
| `keyboard/osx_keyboard_check.py` | 24 | 按鍵狀態查詢。 |
| `listener/osx_listener.py` | 253 | 專屬執行緒上的 listen-only `CGEventTap`＋自己的 `CFRunLoopRunInMode` 切片；不在 import 時建 `NSApplication`，也不用會卡住呼叫緒的 `AppHelper.runEventLoop()`。修飾鍵由 `flagsChanged` 的旗標還原成 press／release，座標取 `CGEventGetLocation`（左上原點，與重播送出的座標同一空間）。 |
| `record/osx_record.py` | 41 | 錄製。捕捉後的整形（舊版按下事件 Queue、時間軸、只錄滑鼠／只錄鍵盤）走共用的 `utils/input_macro/recorder_base.py`。 |
| `screen/osx_screen.py` | 143 | 螢幕擷取與尺寸（含 Retina 座標處理）。 |
| `pid/pid_control.py` | 64 | 以 PID 操作應用程式。 |

#### Linux X11（`linux_with_x11/`，19 檔／1,215 行）

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `core/utils/x11_linux_display.py` | 14 | 共用 `Xlib.display.Display` 實例。 |
| `core/utils/x11_linux_vk.py` | 197 | X11 keysym 對照表。 |
| `mouse/x11_linux_mouse_control.py` | 133 | XTest 滑鼠事件。 |
| `keyboard/x11_linux_keyboard_control.py` | 85 | XTest 鍵盤事件。 |
| `listener/x11_linux_listener.py` | 195 | XRecord 監聽。 |
| `record/x11_linux_record.py` | 73 | 錄製。 |
| `screen/x11_linux_screen.py` | 62 | 螢幕尺寸與擷取。 |
| `uinput/_device.py` | 234 | `/dev/uinput` 封裝（核心層輸入，選用）。 |
| `uinput/keyboard.py` | 33 | uinput 鍵盤後端，介面與 X11 版一致。 |
| `uinput/mouse.py` | 116 | uinput 滑鼠後端。 |

#### Linux Wayland（`linux_wayland/`，17 檔／2,836 行）

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `_detect.py` | 77 | Wayland session 偵測與 CLI 工具探測。 |
| `_ydotool_cli.py` | 134 | 判定安裝的是哪一代 ydotool 命令列，擋掉會靜默失效的 0.1.x（對本專案送的 argv 回傳 0 卻不送任何事件）。 |
| `_ctypes_bind.py` | 75 | libei／liboeffis 共用的 ctypes 載入與 prototype 綁定。 |
| `_dbus_client.py` | 24 | 只用標準函式庫的 D-Bus session bus 客戶端（連線／認證／`Hello`／`AddMatch`／一次方法呼叫／等訊號）。portal 的回應是**指名送給發出呼叫的那條連線**,所以訂閱與呼叫必須同一條連線——這是 `gdbus monitor` + `gdbus call` 兩個行程做不到的事。 |
| `_select_input.py` | 85 | 決定使用原生 libei 或 CLI shim；`active_backend()` 是 keyboard／mouse 的唯一入口，`emitted()` 讓被拒絕的單次發送退回 CLI。 |
| `_layout.py` | 83 | 版面原點的共用查詢。擷取與輸入不是同一個座標空間,差的就是這個原點:libei 的 region offset 是 `uint32`（描述不了負原點）,`ydotool mousemove --absolute` 的原點是合成器夾取的那個角落——兩條路都要減掉它,所以放在這裡而不是各自複製。讀數快取一秒——擷取那一側刻意不快取,但 ydotool 每次絕對移動都會問,不快取等於每次移動多開一個 `wlr-randr` 行程。 |
| `oeffis.py` | 196 | liboeffis 綁定：跑完 RemoteDesktop portal 交握，交出 EIS fd。 |
| `libei.py` | 611 | libei 綁定與完整握手（seat 綁定能力 → 由事件取得 device → start_emulating → 每次發送後 frame）。另負責絕對指標的座標空間:讀回裝置的 region,把版面座標映射進去,沒有任何 region 涵蓋就拒絕（libei 對這種移動是靜靜丟掉的）。 |
| `mouse.py` | 384 | 滑鼠後端：移動、按鈕與捲動都 libei 優先，退回 ydotool；送往 libei 時垂直捲動軸取負（kernel `REL_WHEEL` 與 `wl_pointer` 正負號相反）。退到 ydotool 的絕對移動會先減掉版面原點（`--absolute` 是相對於版面左上角,不是版面座標的 `(0, 0)`),並依 `pointer_accel_mode()` 處理指標加速度——倍率讀不回來,只有操作者知道,所以由 `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL` 宣告:未設定＝每個行程警告一次後照送、`flat`＝已關掉加速度故靜靜送出、`strict`＝拒絕這次移動。 |
| `keyboard.py` | 173 | 鍵盤後端：libei 優先，退回 ydotool／wtype。 |
| `keymap.py` | 155 | 友善鍵名 → evdev key code。 |
| `capture.py` | 236 | 擷取分層：操作者自訂指令 → grim → gnome-screenshot → spectacle → portal。 |
| `portal.py` | 207 | `org.freedesktop.portal.Screenshot` 最後備援,經 `_dbus_client` 直接講 D-Bus（不再需要安裝 `gdbus`,只要有 session bus）。 |
| `screen.py` | 266 | 螢幕後端；發布 `grab_image` 與 `layout_origin`（擷取畫面左上角的版面座標，有螢幕在主螢幕左側／上方時為負），全框架的擷取都經由它。 |
| `listener.py` / `record.py` | 48 / 34 | 監聽與錄製 stub（Wayland 限制）。 |

#### 行動裝置

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `android/adb_client.py` | 183 | `adb` CLI 的薄封裝。 |
| `android/client.py` | 91 | `uiautomator2.Device` 的延遲封裝。 |
| `android/find.py` | 104 | uiautomator2 widget 樹的元素查詢。 |
| `ios/client.py` | 94 | `facebook-wda`（WebDriverAgent）封裝。 |
| `ios/find.py` | 86 | XCUITest 無障礙查詢。 |
| `ios/input.py` | 46 | iOS 觸控與按鍵原語。 |
| `ios/screen.py` | 32 | iOS 裝置螢幕擷取與尺寸。 |

### 5.4 能力層 `utils/`（310 個子套件）

以下依主題分組。每個子套件都是獨立可匯入的無頭模組，不含任何 Qt 相依。


### 5.4.1 執行引擎與腳本資產

> 24 個套件、約 12,900 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/action_lint/` | 328 | action 檔 linter 與 JSON Schema 產生器（CI 用 `python -m` 進入點） |
| `utils/action_signing/` | 248 | action 檔 HMAC-SHA256 簽章與 Fernet 加密，`execute_files` 會強制驗簽 |
| `utils/checkpoint/` | 120 | 流程檢查點與續跑，讓長 action list 具持久性 |
| `utils/codegen/` | 157 | 由 action list 產生可執行的 pytest / python / robot 測試碼 |
| `utils/dag/` | 475 | 跨主機 DAG 編排器（圖模型 + runner） |
| `utils/decision_table/` | 103 | DMN 風格決策表：規則 + 命中策略，把分支外部化 |
| `utils/deterministic/` | 96 | 決定性執行控制：固定亂數種子 + 凍結時鐘 |
| `utils/executor/` | 9,075 | **核心**。`Executor` 指令分派表（773 個 `AC_*`）、參數插值、乾跑、逐步 callback；`flow_control` 提供 34 個區塊指令（迴圈／分支／try／巨集／變數） |
| `utils/flow_debugger/` | 136 | action list 的單步除錯器與追蹤器 |
| `utils/input_macro/` | 342 | 定時輸入事件：錄製結果的整形（`timeline`／`InputRecorder`，Windows 與 macOS 共用）、重播與宣告式輸入序列 DSL |
| `utils/json/` | 74 | action JSON 檔讀寫與正規化格式化（`fmt --check` 的後端） |
| `utils/json_store/` | 61 | JSON 字典檔持久化的共用小工具（內部管線） |
| `utils/loop_guard/` | 140 | 機械式卡死迴圈偵測（agent loop 用） |
| `utils/plugin_loader/` | 85 | 掃描外部 Python 外掛目錄並註冊其 `AC_` callable |
| `utils/plugin_sdk/` | 68 | 外掛 SDK：透過 entry points 發佈／載入第三方 `AC_*` 指令 |
| `utils/project/` | 182 | 專案腳手架：建立目錄結構與範本 action 檔 |
| `utils/recording_edit/` | 150 | 不重錄的前提下裁切／過濾／縮放已錄製的 action list |
| `utils/saga/` | 93 | Saga 協調器：失敗時以 LIFO 補償動作回滾 |
| `utils/script_vars/` | 190 | 執行期變數作用域與 `${var}` / `${secrets.*}` 插值 |
| `utils/skill_library/` | 116 | 具名可重用 action 序列（skill）的持久化倉庫 |
| `utils/state_machine/` | 181 | 宣告式有限狀態機驅動 action JSON |
| `utils/stubs/` | 236 | 為 `AC_*` 指令面產生型別 stub |
| `utils/test_record/` | 64 | 全域測試紀錄單例，記錄每個動作的參數與例外 |
| `utils/work_queue/` | 180 | 交易式工作佇列（dispatcher／performer），支撐大量批次執行 |

### 5.4.2 框架基礎設施

> 14 個套件、約 2,650 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/callback/` | 200 | Observer 模式：`callback_executor` 以字串名觸發功能，執行後呼叫回呼 |
| `utils/config_bundle/` | 400 | 使用者設定的單檔匯出／匯入 |
| `utils/critical_exit/` | 97 | 監看緊急停止鍵的守護執行緒，用於中止失控腳本 |
| `utils/diagnostics/` | 322 | 跨子系統的「一切正常嗎」健檢，附 `python -m` 進入點 |
| `utils/dbus_client/` | 680 | 只用標準函式庫的 D-Bus session bus 客戶端。原本在 `linux_wayland/` 為 portal 交握而寫，AT-SPI 無障礙後端成為第二個使用者後搬到這裡（`utils/` 在分層上在各 OS 套件之上） |
| `utils/exception/` | 210 | **例外階層根**。所有錯誤繼承 `AutoControlException`，加上集中式錯誤訊息字串（`exception_tags`） |
| `utils/failure_bundle/` | 187 | 可攜、已遮蔽的失敗診斷 ZIP（截圖 + 診斷 + log 尾段） |
| `utils/file_process/` | 26 | 目錄檔案列舉（`execute_dir` 的後端） |
| `utils/logging/` | 71 | `autocontrol_logger` 單例 + 輪替檔案 handler |
| `utils/package_manager/` | 98 | 動態載入套件並把 executor 注入其中 |
| `utils/path_guard/` | 99 | 命令列傳入路徑的正規化與邊界檢查（防路徑穿越） |
| `utils/platform_id/` | 62 | 作業系統家族的單一判定點。`sys.platform` 原本在一百多處跟字面清單比對，而那些清單都沒有 BSD；`is_x11_unix()` 問的是「這是不是 X11 unix」，這才是守衛一直想問的問題 |
| `utils/shell_process/` | 159 | `ShellManager`：以 argv list 執行外部命令（禁用 `shell=True`） |
| `utils/start_exe/` | 39 | 啟動另一個執行檔行程 |

### 5.4.3 排程、觸發與背景監看

> 11 個套件、約 3,544 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/hotkey/` | 727 | 全域熱鍵守護行程，把 OS 層熱鍵綁到 action 檔（Win/macOS/X11 三後端） |
| `utils/idle_keepawake/` | 212 | 偵測使用者閒置時間並在無人值守執行期間阻止系統睡眠 |
| `utils/lock_session/` | 163 | 鎖定工作站、等待解鎖並分類鎖定狀態轉換 |
| `utils/observer/` | 220 | 反應式畫面觀察者，在出現／消失／變化時觸發 |
| `utils/recurrence/` | 324 | RFC 5545 重複規則解析與發生時間展開 |
| `utils/scheduler/` | 352 | 間隔式與 cron 式的 action JSON 排程器 |
| `utils/session_guard/` | 62 | 驅動輸入前先偵測工作階段是否已鎖定／非互動 |
| `utils/triggers/` | 1,146 | 事件驅動觸發引擎：影像／視窗／像素／檔案／webhook／IMAP 郵件 |
| `utils/voice/` | 87 | 語音指令路由：把辨識到的語句對應到 `AC_*` action list |
| `utils/watchdog/` | 173 | 背景彈窗／中斷看門狗，供無人值守自動化 |
| `utils/watcher/` | 78 | 無頭輪詢原語：滑鼠位置、像素顏色、log tail |

### 5.4.4 輸入模擬與動作品質

> 22 個套件、約 2,610 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/act_in_view/` | 76 | 先把目標捲進視野，待其可操作後再動作 |
| `utils/act_modes/` | 67 | actionability 閘門之上的 trial／force 動作模式 |
| `utils/action_effect/` | 110 | 判定一個動作是否真的產生效果，並歸因到目標區域 |
| `utils/action_grounding/` | 80 | 動作前的接地守衛（邊界檢查 + 吸附到元素） |
| `utils/actionability/` | 163 | 動作前就緒閘門（可見 + 穩定 + 啟用 + 未被遮擋） |
| `utils/ensure_state/` | 72 | 冪等地把控制項／設定帶到期望狀態 |
| `utils/field_entry/` | 76 | 清空再輸入的欄位填寫慣用法（Playwright `fill`） |
| `utils/gamepad/` | 311 | 虛擬遊戲手把後端（Windows ViGEmBus 驅動） |
| `utils/humanize/` | 183 | 擬人輸入：貝茲曲線滑鼠路徑 + 抖動打字節奏 |
| `utils/ime_state/` | 144 | 讀取即時 IME 組字／轉換狀態，確保 CJK 輸入安全 |
| `utils/key_hold/` | 107 | 按住按鍵一段時間，或以固定頻率自動重複 |
| `utils/modifier_state/` | 76 | 跨一組動作按住修飾鍵，並保證安全釋放 |
| `utils/mouse_path/` | 92 | 多路徑點滑鼠手勢（沿折線移動或拖曳） |
| `utils/mouse_relative/` | 59 | 相對位移滑鼠移動 |
| `utils/postcondition/` | 138 | 宣告式的動作預期結果規格，對照畫面驗證 |
| `utils/step_repair/` | 114 | 失敗／無效動作的修復策略（自我修正迴圈） |
| `utils/table_grid_fill/` | 141 | 以 OCR 文字填滿格線表格，取得可定址的表格 |
| `utils/input_reach/` | 111 | 送出去的輸入到不到得了：桌面鎖定查詢（免費）＋ 實際送一個 F13 確認沒有被過濾（有副作用，只給診斷用） |
| `utils/keyboard_layout/` | 148 | 向系統問「這個鍵盤配置下每個鍵印出什麼字」（`ToUnicodeEx`），問不到退回 US 對照表 |
| `utils/text_unicode/` | 135 | 輸入任意 Unicode（emoji／CJK／重音字）：優先送字元按鍵事件，不支援時退回剪貼簿貼上 |
| `utils/tween_drag/` | 95 | 沿曲線的緩動插值拖曳 |
| `utils/verify_field/` | 112 | 打字後讀回欄位，確認內容確實落地 |

### 5.4.5 影像辨識與畫面分析

> 37 個套件、約 5,067 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/annotate/` | 114 | 截圖標註：畫框、highlight、箭頭、標籤 |
| `utils/barcode/` | 53 | 一維條碼（EAN／UPC）解碼，解碼器可注入 |
| `utils/color_match/` | 103 | 在 HSV 通道上做顏色感知的樣板比對 |
| `utils/color_region/` | 79 | 以顏色定位畫面區域（遮罩 + 連通元件） |
| `utils/color_stats/` | 95 | 區域顏色統計：平均色與主色 |
| `utils/coordinate_space/` | 84 | 模型網格座標與實體像素之間的座標空間對映 |
| `utils/cv2_utils/` | 637 | OpenCV 基礎層：擷取後端選擇（`screen_grabber`，Pillow／mss 或平台後端）、截圖、樣板比對（走 `grab_logical`，涵蓋所有螢幕）、螢幕錄影、影片錄製、連通元件、影像堆疊的取用口（`optional`，Windows arm64 沒有 wheel 時語意報錯） |
| `utils/edge_lines/` | 120 | 以 Hough 轉換偵測線條／格線／分隔線 |
| `utils/edge_match/` | 112 | 邊緣形狀（Chamfer／距離轉換）樣板比對 |
| `utils/feature_match/` | 129 | ORB 特徵比對：在旋轉／縮放／主題變更下定位樣板 |
| `utils/hsv_segment/` | 91 | HSV 色彩空間分割（抗光照的顏色遮罩 + blob 框） |
| `utils/icon_classify/` | 113 | 從像素形狀判斷一個框是哪一類元件 |
| `utils/image_dedup/` | 83 | 感知雜湊影像去重（Pillow aHash/dHash） |
| `utils/image_quality/` | 77 | 在 OCR／比對前評分影像品質（銳利度／對比／亮度） |
| `utils/img_histogram/` | 99 | 顏色直方圖指紋與變化偵測（抗光照） |
| `utils/marks_layout/` | 124 | Set-of-Marks 標籤的不重疊排版與可讀配色 |
| `utils/match_autothresh/` | 105 | Otsu 自動門檻，免去手動調 `min_score` |
| `utils/match_ensemble/` | 63 | 多樣板共識比對（多張參考圖投票到同一位置） |
| `utils/match_stability/` | 68 | 比對前的靜止閘門與跨影格的比對持續性 |
| `utils/match_trust/` | 136 | 樣板比對可信度評分（次峰比 + peak-to-sidelobe） |
| `utils/monitor_layout/` | 317 | 多螢幕／虛擬桌面幾何（在哪個螢幕、位置、重映射）＋ `logical_frame` 以滑鼠座標空間擷取畫面 |
| `utils/motion_regions/` | 73 | 兩影格間的局部變化／活動偵測（absdiff） |
| `utils/perceptual_diff/` | 100 | 感知式（YIQ）影像差異，抑制反鋸齒邊緣誤報 |
| `utils/preprocess/` | 185 | OCR／比對前的影像前處理（灰階、二值化、去傾斜…） |
| `utils/qr/` | 59 | 從影像或螢幕區域解碼 QR code（OpenCV） |
| `utils/rotated_match/` | 145 | 容忍旋轉與縮放的樣板比對（尺度空間 × 角度掃描） |
| `utils/saliency/` | 107 | 頻譜殘差視覺顯著性：顯著圖與排序後的顯著區域 |
| `utils/scale_detect/` | 84 | 偵測樣板實際渲染的顯示縮放／視覺 DPI |
| `utils/screen_grid/` | 143 | 供 VLM 接地用的粗粒度標號網格（點 ↔ 格對映） |
| `utils/set_of_marks/` | 150 | Set-of-Marks 疊圖：為畫面元素編號供 VLM 指認 |
| `utils/shape_locator/` | 105 | 以邊緣／輪廓偵測定位元件（矩形／形狀，免樣板） |
| `utils/ssim/` | 140 | 結構相似度比較：感知分數 + 變化區域 |
| `utils/subpixel_match/` | 101 | 以二次曲面擬合做次像素級比對精修 |
| `utils/theme_normalize/` | 92 | 主題無關的影像正規化，讓亮色樣板能配對深色模式 |
| `utils/video_report/` | 133 | 影片步驟疊圖報告：把截圖加字幕串成操作導覽影片 |
| `utils/visual_match/` | 427 | 會回傳信心值的樣板比對（分數、多尺度、find-all + NMS）；擷取走 `grab_logical`，命中座標已加回虛擬桌面原點，單色樣板直接拒收 |
| `utils/visual_regression/` | 221 | 桌面 GUI 的視覺回歸測試（黃金圖比對） |

### 5.4.6 OCR 與文字理解

> 19 個套件、約 3,180 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/bidi_check/` | 116 | 雙向文字 QA（bidi 控制碼、巢狀平衡、Trojan-source 掃描） |
| `utils/column_layout/` | 150 | 從垂直空白推斷欄位，處理無框線表格 |
| `utils/confusables/` | 112 | 易混淆／同形字偵測（Unicode 欺騙骨架） |
| `utils/form_fields/` | 128 | 多方向關聯表單標籤與值，並讀取核取方塊狀態 |
| `utils/fuzzy/` | 94 | 模糊字串比對與去重（預設 difflib，有 rapidfuzz 則優先） |
| `utils/grid_locator/` | 71 | 以 (row, column) 從邊界框定址表格／網格儲存格 |
| `utils/guardrail/` | 108 | 針對畫面／OCR 文字的啟發式 prompt-injection 防護 |
| `utils/heading_segment/` | 69 | 判定 OCR 行是標題或內文，建出文件大綱 |
| `utils/near_dup/` | 105 | 近似重複文字偵測（SimHash／MinHash） |
| `utils/ocr/` | 1,112 | OCR 引擎門面 + 三個後端（Tesseract／EasyOCR／PaddleOCR）、版面結構化與跨詞比對（`text_span`） |
| `utils/pii_text/` | 98 | 自由文字中的 PII 偵測與遮蔽（email／電話／SSN／卡號／IP／IBAN） |
| `utils/readability/` | 137 | 可讀性評分（Flesch、Flesch-Kincaid、Gunning Fog、SMOG、ARI） |
| `utils/reading_flow/` | 119 | 以遞迴 XY-cut 推導欄位感知的閱讀順序 |
| `utils/search_index/` | 140 | 記憶體內 BM25／TF-IDF 全文檢索 |
| `utils/text_blocks/` | 88 | 把 OCR 行組成段落與項目符號／編號清單 |
| `utils/text_diff/` | 148 | unified diff 產生、套用與三方合併 |
| `utils/text_normalize/` | 63 | Unicode 正規化與 slug 產生 |
| `utils/text_regions/` | 157 | 免模型的畫面文字區域偵測（MSER）：區域與行 |
| `utils/text_similarity/` | 165 | 字串距離度量（文字比對用） |

### 5.4.7 無障礙樹與原生控制項

> 16 個套件、約 4,279 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/a11y_audit/` | 355 | 以無障礙樹 + OCR 進行無障礙與 i18n 稽核 |
| `utils/accessibility/` | 2,818 | 跨平台無障礙樹定位與錄製；Windows UIA／macOS AX／null 三後端。支援限定視窗（換搜尋起點，不是過濾）、逐節點可中斷走訪、`IUIAutomation2` 連線逾時、名稱子字串比對與排序、`control_get_state` 一次讀完值／勾選／選取／數值（密碼欄位不回內容） |
| `utils/ax_events/` | 29 | 反應式 UIA 事件等待（focus-changed） |
| `utils/ax_props/` | 44 | 讀取豐富 UIA 屬性（enabled／offscreen／help／status／快捷鍵） |
| `utils/ax_text/` | 102 | 透過 UIA TextPattern 取得原生文字（讀取／尋找／選取／屬性） |
| `utils/ax_tree_walk/` | 118 | 可讀、可定址的無障礙樹後處理（角色名 + 節點路徑） |
| `utils/contrast_map/` | 120 | 取樣實際顏色以評定畫面文字的可讀性（WCAG） |
| `utils/control_patterns/` | 88 | 延伸 UIA 控制項模式動作（Expand／Select／Range／Scroll） |
| `utils/cvd_simulate/` | 125 | 模擬色覺缺陷並標示在該狀況下會撞色的顏色 |
| `utils/element_repository/` | 105 | 原生 UI 元素的具名定位器倉庫（object repository） |
| `utils/focus_order/` | 95 | 鍵盤焦點順序：預期 Tab 序列、WCAG 稽核與設定焦點 |
| `utils/legacy_accessible/` | 45 | MSAA 橋接，處理 UIA 無法建模的舊控制項 |
| `utils/selection_view/` | 57 | 容器選取狀態與檢視切換（Selection／MultipleView 模式） |
| `utils/table_pattern/` | 65 | 原生表格的表頭與儲存格定址（UIA TablePattern／GridItem） |
| `utils/transform_window/` | 70 | 以 UIA Transform／Window 模式移動、調整大小與視窗狀態 |
| `utils/virtualized/` | 43 | 實體化虛擬化清單／網格中的離屏項目 |

### 5.4.8 元素定位、自我修復與智慧等待

> 23 個套件、約 3,995 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/ab_locator/` | 336 | A/B 定位器框架：同時競速 N 種策略並記錄各自勝率 |
| `utils/adaptive_timeout/` | 84 | 由觀測到的步驟耗時推導等待逾時，而非硬猜 |
| `utils/anchor_locator/` | 438 | 錨點定位器：以空間關係組合 影像／OCR／VLM／a11y 四種來源 |
| `utils/app_idle/` | 108 | 等應用程式不再忙碌，再驅動下一步 |
| `utils/change_localize/` | 80 | 把畫面變化歸因到實際改變的元素框 |
| `utils/critic_features/` | 85 | 每步的 critic 特徵集合與規則式步驟評分 |
| `utils/element_diff/` | 88 | 跨影格的幾何感知元素比對（穩定 ID、移動追蹤） |
| `utils/element_parse/` | 106 | 融合並排序畫面元素框（IoU、合併、多來源融合、閱讀順序） |
| `utils/element_proposal/` | 86 | 免樣板、免模型地從原始像素提出乾淨元素清單 |
| `utils/element_scoring/` | 105 | 加權候選評分（角色 + 名稱相似度 + 鄰近度 + 啟用狀態） |
| `utils/expect_poll/` | 137 | 反覆取值直到符合條件（Playwright `expect.poll` 風格） |
| `utils/grounding_consensus/` | 127 | 對同一目標的多個接地提案做自我一致性投票 |
| `utils/heal_analytics/` | 77 | 自癒事件記錄的分析（治癒率、脆弱定位器） |
| `utils/locator_chain/` | 112 | 可組合／可過濾的候選定位器（chained-locator 慣用法） |
| `utils/locator_repair/` | 117 | 自癒回寫：把修正後的定位器持久化 |
| `utils/observation/` | 92 | 供 VLM／agent 接地用的 token 預算內、帶索引的 a11y 文字觀察 |
| `utils/observation_delta/` | 103 | token 預算內的觀察差異：兩個 UI 影格之間變了什麼 |
| `utils/screen_state/` | 143 | 語義畫面狀態：快照／差異與結構化畫面描述 |
| `utils/scroll_find/` | 84 | 捲動直到目標影像／文字可見 |
| `utils/self_healing/` | 342 | 自癒定位器：先影像樣板、失敗改用 VLM，並留稽核記錄 |
| `utils/semantic_recording/` | 423 | 為錄製內容加上語義錨點，支援換機重播與自癒重播 |
| `utils/settle_detector/` | 76 | 以純函式介面判定 UI 是否已靜止 |
| `utils/smart_waits/` | 646 | 智慧等待：以影格差異取代 `time.sleep` |

### 5.4.9 AI / Agent / LLM

> 13 個套件、約 20,610 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/a2a/` | 92 | A2A（agent-to-agent）agent card 產生 |
| `utils/agent/` | 1,250 | 閉環 Computer-Use Agent 主迴圈 + Anthropic／OpenAI／Computer-Use 三後端 |
| `utils/agent_memory/` | 151 | agent 的持久化情節記憶（goal → trajectory → outcome） |
| `utils/agent_replay/` | 63 | 可攜的 agent 軌跡追蹤（記錄 observation→action 並重播） |
| `utils/agent_trace/` | 129 | agent 可觀測性：OpenTelemetry GenAI 慣例的 LLM span |
| `utils/cost_telemetry/` | 292 | 每次呼叫的 LLM 成本遙測：token 數 + 估算美金 |
| `utils/cua_action/` | 127 | 標準化 computer-use 動作結構（Anthropic／OpenAI → `AC_*`） |
| `utils/llm/` | 357 | 自然語言 → action list 規劃器 + Anthropic／null 後端 |
| `utils/mcp_registry/` | 92 | MCP registry `server.json` 資訊清單產生（可被發現） |
| `utils/mcp_server/` | 17,323 | **無頭 MCP 伺服器**（16K LOC，預設註冊 676 個工具＝657 個 `ac_*` + 19 個別名）：stdio + HTTP 傳輸、工具工廠與處理器、資源、prompt、稽核、限流、外掛熱重載 |
| `utils/tool_use_schema/` | 180 | 把 `AC_*` 指令匯出成 Claude／OpenAI 的 tool-use schema |
| `utils/trajectory_eval/` | 106 | agent 軌跡評估：依評分規準為一次執行打分 |
| `utils/vision/` | 448 | VLM 元素定位器（依描述找元素）+ Anthropic／OpenAI／null 後端 |

### 5.4.10 遠端桌面與 USB

> 6 個套件、約 17,726 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/admin/` | 327 | 多主機管理主控台：平行輪詢 N 個 AutoControl REST 端點 |
| `utils/config_sync/` | 245 | 透過訊令伺服器做跨機器設定同步 |
| `utils/device_matrix/` | 138 | 行動裝置矩陣：同一 action list 於多台裝置平行執行 |
| `utils/remote_desktop/` | 11,846 | **遠端桌面子系統**（56 檔／11.7K LOC）：TCP／WebSocket／WebRTC 三條傳輸路徑、主機與檢視端、訊令伺服器、TURN／中繼、多檢視者、錄影、信任清單、TOTP、稽核鏈 |
| `utils/usb/` | 4,250 | 跨平台 USB 列舉／熱插拔／裝置直通（WinUSB、IOKit、libusb 後端 + ACL + WebRTC DataChannel 通道） |
| `utils/usbip/` | 920 | USB/IP 線路協定主機端（協定封包、TCP 伺服器、libusb URB 後端） |

### 5.4.11 伺服器、網路協定與外部整合

> 24 個套件、約 5,900 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/acme_v2/` | 598 | 完整 ACME v2 用戶端（RFC 8555），不依賴 certbot |
| `utils/chatops/` | 628 | Chat-ops bot：接收 Slack／Discord／webhook 的 slash 指令並路由到動作 |
| `utils/cookie_jar/` | 103 | RFC 6265 cookie jar |
| `utils/email_send/` | 116 | SMTP 寄信（email 觸發器的發送端搭檔） |
| `utils/events/` | 82 | 對外 CloudEvents 發送（執行生命週期事件） |
| `utils/http_cassette/` | 110 | 錄製／重播 HTTP 互動，做離線決定性 API 測試 |
| `utils/http_client/` | 132 | 零依賴 HTTP(S) 用戶端，供 action 步驟呼叫 API |
| `utils/http_conditional/` | 87 | 條件式 HTTP 請求與快取驗證器 |
| `utils/http_content/` | 103 | HTTP 內容協商與回應解壓縮 |
| `utils/http_problem/` | 116 | RFC 9457 problem+json 解析 |
| `utils/jwt/` | 172 | JWT（HMAC 家族）編碼、解碼與 claim 驗證 |
| `utils/link_header/` | 112 | RFC 8288 Link header 解析與分頁 |
| `utils/multipart/` | 139 | multipart/form-data 建構與解析 |
| `utils/notify/` | 95 | 跨平台桌面通知 |
| `utils/notify_channels/` | 100 | 對外聊天／webhook 通知（Slack／Discord／Teams／raw） |
| `utils/otp/` | 37 | TOTP 一次性密碼產生（自動化 2FA 登入） |
| `utils/outbox/` | 92 | 交易式 outbox，保證至少一次的事件投遞 |
| `utils/pytest_plugin/` | 373 | pytest 外掛 + BDD step library（`pytest11` entry point） |
| `utils/rest_api/` | 1,739 | 純標準庫 REST 前端：路由、Bearer 驗證、限流、Prometheus 指標、OpenAPI 3.1 產生 |
| `utils/socket_server/` | 131 | 執行 action JSON 的執行緒式 TCP 指令伺服器（預設綁 127.0.0.1） |
| `utils/sse_client/` | 112 | Server-Sent Events 用戶端解析 |
| `utils/tls_acme/` | 447 | TLS 自動化：HTTP-01 挑戰伺服器、金鑰／CSR、自動續期 |
| `utils/url_canon/` | 115 | RFC 3986 URL 正規化與查詢字串工具 |
| `utils/webrunner_bridge/` | 161 | 把 action JSON 橋接到 WebRunner（`je_web_runner`） |

### 5.4.12 報表、可觀測性與測試治理

> 34 個套件、約 6,896 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/anomaly/` | 107 | 單一序列異常偵測 |
| `utils/approval/` | 102 | Approval testing：以核可基準線驗證產出物 |
| `utils/assertion/` | 863 | 斷言 DSL：畫面狀態驗證 + 組合子 |
| `utils/baggage/` | 111 | W3C Baggage 傳遞 |
| `utils/canonical_log/` | 90 | canonical log line 與結構化 JSON 日誌 |
| `utils/ci_annotations/` | 62 | 由執行結果輸出 CI 工作流程註記（GitHub Actions） |
| `utils/compliance/` | 136 | 合規：把治理證據對應到 SOC2／ISO 27001 控制項 |
| `utils/failure_hooks/` | 396 | 失敗 → 工單自動化：開 Jira／Linear／GitHub issue |
| `utils/failure_signature/` | 74 | 把錯誤訊息正規化成穩定的 SHA-256 失敗簽章並分群 |
| `utils/flake_cluster/` | 103 | 以共同失敗 Jaccard 相似度為易碎測試分群 |
| `utils/flakiness/` | 150 | 以執行歷史分析不穩定測試 |
| `utils/generate_report/` | 310 | HTML／JSON／XML 三種報表產生器（Template Method） |
| `utils/media_assert/` | 233 | 媒體斷言：音訊活動與影片動態檢查 |
| `utils/observability/` | 661 | Prometheus 格式指標 + OpenTelemetry 相容 trace + `/metrics` 匯出伺服器 |
| `utils/otlp_export/` | 81 | OTLP/JSON span 匯出 |
| `utils/percentiles/` | 103 | 可合併的串流延遲摘要與精確百分位數 |
| `utils/process_doc/` | 85 | 由錄製的 action list 產生逐步 SOP 文件 |
| `utils/process_mining/` | 110 | 流程探勘：從動作日誌挖掘可自動化的候選 |
| `utils/profiler/` | 422 | 逐動作效能剖析器 + 資源剖析器 |
| `utils/quarantine/` | 190 | 易碎測試隔離區，讓套件執行器跳過已知不穩定案例 |
| `utils/run_diff/` | 123 | 兩次執行軌跡的差異（LCS 對齊：新增／移除／狀態翻轉／退化） |
| `utils/run_history/` | 377 | 執行歷史儲存與產出物管理 |
| `utils/sarif/` | 134 | 以 SARIF 2.1.0 匯出發現項，供 GitHub／Azure code scanning |
| `utils/slo/` | 112 | SLO 評估：SLI、錯誤預算與多視窗燃燒率告警 |
| `utils/smoothing/` | 67 | 數列移動平均平滑 |
| `utils/soft_assert/` | 62 | 軟斷言：累積檢查並在區塊結束時一次拋出 |
| `utils/stats/` | 213 | 描述統計與 A/B 顯著性檢定（純標準庫） |
| `utils/step_timeline/` | 81 | 每次執行的步驟瀑布圖與瓶頸（關鍵路徑）步驟排名 |
| `utils/test_select/` | 123 | 以執行歷史做風險導向的測試選取 |
| `utils/test_shard/` | 87 | 以耗時為權重的套件切分與分片結果合併 |
| `utils/test_suite/` | 442 | QA 套件編排：把扁平 action list 評分為測試案例 + CI 報表 |
| `utils/time_travel/` | 381 | 錄製 session 的時光回溯除錯（控制器 + 播放器） |
| `utils/timeseries/` | 143 | 時間序列轉換（rate／降採樣／重採樣） |
| `utils/trace_context/` | 162 | W3C Trace Context 傳遞 |

### 5.4.13 資料來源、結構驗證與 i18n

> 24 個套件、約 3,892 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/checksum/` | 132 | 檢查碼演算法：Luhn、Verhoeff、Damm、ISO 7064 MOD 97-10 |
| `utils/config_schema/` | 109 | 型別化設定結構驗證 |
| `utils/data_drift/` | 125 | 分布漂移偵測 |
| `utils/data_profile/` | 121 | 資料剖析與結構推斷 |
| `utils/data_quality/` | 185 | 資料品質：列結構驗證、欄位擷取、遮蔽 |
| `utils/data_source/` | 182 | 資料驅動執行：從 CSV／JSON／SQLite／Excel 載入資料列 |
| `utils/dataset_diff/` | 89 | 表格資料列差異比對（CDC 風格） |
| `utils/gettext_catalog/` | 296 | GNU gettext 目錄 I/O（解析 .po、編譯／讀取 .mo、訊息查詢） |
| `utils/i18n_test/` | 130 | 國際化／在地化測試輔助 |
| `utils/json_contract/` | 135 | JSON 契約／快照比對：`match_json`、`diff_json`、`snapshot_json` |
| `utils/json_patch/` | 312 | JSON Pointer（6901）、JSON Patch（6902）與 Merge Patch（7386） |
| `utils/json_schema/` | 374 | JSON Schema（Draft 2020-12 子集）驗證 |
| `utils/jsonpath/` | 179 | 精簡 JSONPath 查詢 |
| `utils/list_format/` | 72 | 地區感知清單格式化（CLDR 風格的「A、B 和 C」） |
| `utils/locale_collation/` | 128 | 地區感知字串排序（決定性多層排序鍵） |
| `utils/locale_parse/` | 68 | 地區感知數字／貨幣／日期解析與格式化（選用 babel） |
| `utils/message_format/` | 236 | ICU-lite MessageFormat（plural／select／selectordinal） |
| `utils/office/` | 162 | Office 文件無頭讀寫（Excel／Word／PowerPoint） |
| `utils/pdf/` | 87 | PDF 讀取與斷言（選用 pypdf 後端） |
| `utils/referential/` | 75 | 跨資料集的參照完整性檢查 |
| `utils/schema_compat/` | 162 | JSON Schema 相容性分級 |
| `utils/sql/` | 78 | 對 SQLite 的臨時唯讀 SQL 查詢 |
| `utils/test_data/` | 205 | 帶種子的合成測試資料產生（純標準庫） |
| `utils/xml/` | 250 | XML 檔讀寫與結構變更（`defusedxml`） |

### 5.4.14 安全、機密與合規

> 13 個套件、約 2,279 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/config_redaction/` | 75 | 設定結構與 log 字串的機密遮蔽 |
| `utils/egress/` | 114 | 無頭 HTTP 用戶端的網路外連允許清單守衛 |
| `utils/governance/` | 199 | 治理：maker-checker 核准閘門與即時憑證租約 |
| `utils/license_policy/` | 139 | 以 SBOM 元件評估 SPDX 授權允許／拒絕政策 |
| `utils/provenance/` | 104 | SLSA 建置來源證明（in-toto v1） |
| `utils/rbac/` | 272 | 角色型存取控制與逐使用者稽核歸因 |
| `utils/redaction/` | 457 | 截圖遮蔽層：規則偵測 + 政策 + 協調器（上傳 VLM 前先遮） |
| `utils/sbom/` | 108 | SBOM（CycloneDX）產生 |
| `utils/secret_ref/` | 126 | URI scheme 形式的值參照解析 |
| `utils/secrets/` | 269 | 加密機密儲存庫，供 `${secrets.NAME}` 解析 |
| `utils/secrets_scan/` | 98 | 掃描 action JSON／資料中應入庫卻硬編碼的機密 |
| `utils/vex/` | 130 | OpenVEX 陳述撰寫與漏洞分類處置 |
| `utils/vuln_scan/` | 188 | 以 OSV 比對 SBOM 元件的漏洞（純標準庫） |

### 5.4.15 韌性、流量控制與設定

> 14 個套件、約 1,706 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/artifact_store/` | 114 | S3 相容產出物儲存（報表／截圖／錄影） |
| `utils/assets/` | 155 | 環境範圍的型別化資產／設定儲存（UiPath Assets 風格） |
| `utils/bulkhead/` | 134 | Bulkhead 併發隔離 + 伺服器限流標頭解析 |
| `utils/chaos/` | 153 | 決定性混沌實驗（穩態假說 + 故障注入） |
| `utils/dedup_window/` | 63 | 時間視窗內的訊息去重 |
| `utils/dotenv/` | 101 | `.env` 檔解析與序列化 |
| `utils/feature_flags/` | 173 | 功能旗標評估，含目標規則與決定性灰度 |
| `utils/idempotency/` | 114 | 冪等鍵儲存與已存回應重放 |
| `utils/layered_config/` | 110 | 分層設定解析 |
| `utils/optimistic/` | 105 | 樂觀併發的版本化儲存 |
| `utils/rate_limit/` | 162 | 用戶端限流：token bucket、滑動視窗、throttle |
| `utils/resilience/` | 110 | 韌性原語：退避重試與斷路器 |
| `utils/retry_budget/` | 147 | 重試預算：以牆鐘期限與 full jitter 約束重試 |
| `utils/sequence_gap/` | 65 | 逐串流的序號缺口偵測 |

### 5.4.16 系統、視窗與剪貼簿

> 16 個套件、約 2,403 行。

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `utils/clipboard/` | 489 | 跨平台無頭剪貼簿存取（文字 + 影像）＋ `win32_clipboard_api.py`：**所有剪貼簿格式共用的 Win32 原型與 open/alloc/lock 流程**（`open_clipboard()` 會等過短暫被別的行程佔住的剪貼簿——Win32 一次只允許一個行程開啟，別人正在複製就必然失敗）（`argtypes` 只宣告一半曾讓四支 writer 在 64 位元上必然丟 `OverflowError`，見 CHANGELOG）。`set_clipboard_image` 同時接受 PNG 位元組與檔案路徑——先前這個名字在本子套件裡有**兩份不同簽章的實作**（`clipboard.py` 吃 bytes、`clipboard_image.py` 吃路徑），匯錯來源只會在執行期才炸，已合併成一支 |
| `utils/clipboard_files/` | 96 | 剪貼簿檔案清單（CF_HDROP）：純 DROPFILES 封裝 + Win32 存取 |
| `utils/clipboard_formats/` | 151 | 檢視與分類剪貼簿可用格式（純分類／差異 + Win32 列舉） |
| `utils/clipboard_history/` | 109 | 剪貼簿歷史：環形緩衝 + 背景輪詢器 |
| `utils/clipboard_rich_formats/` | 254 | 豐富剪貼簿格式 — RTF 與 CSV/TSV 編解碼 + Windows 存取 |
| `utils/file_assoc/` | 92 | 解析哪個應用程式被註冊來開啟某副檔名 |
| `utils/file_dialog/` | 60 | 驅動原生檔案 開啟／儲存／資料夾選擇 對話框 |
| `utils/file_drop/` | 96 | 以 WM_DROPFILES 把檔案拖放到視窗 |
| `utils/rich_clipboard/` | 131 | 豐富剪貼簿格式 — HTML（CF_HTML）建構／解析／存取 |
| `utils/shell_open/` | 97 | 以預設應用開啟檔案，或以預設瀏覽器開啟 URL |
| `utils/system_volume/` | 194 | 讀取與控制系統主音量與靜音狀態 |
| `utils/trash/` | 88 | 把檔案移到系統資源回收筒（可復原刪除） |
| `utils/window_capture/` | 255 | 逐視窗截圖、視窗版面儲存／還原、貼齊與排列 |
| `utils/window_geometry/` | 81 | 視窗客戶區幾何（外框內縮、client→screen 對映） |
| `utils/window_layout/` | 134 | 視窗拼貼／版面規劃器（左右半、四象限、網格、層疊） |
| `utils/window_zorder/` | 76 | 視窗 z 序控制（最上層／移到最前／送到最後） |

### 5.4.17 大型子系統的檔案級剖析

上表以子套件為單位；以下把行數最大的幾個子系統展開到檔案層。

#### `utils/executor/`（9,075 行）— 執行核心

| 檔案 | 行數 | 職責 |
| --- | ---: | --- |
| `action_executor.py` | 8,125 | `Executor` 類別與 `event_dict` 分派表（773 個指令），另含數百個把 utils 能力接成指令的 adapter 函式；全域單例 `executor` 與 `add_command_to_executor()` 擴充點。 |
| `flow_control.py` | 530 | 真正的流程控制：`AC_loop`／`AC_for_each`／`AC_while_*`／`AC_if_*`／`AC_try`／`AC_retry`／`AC_parallel`／`AC_define_macro`／`AC_call_macro`／變數指令（`AC_set_var`／`AC_get_var`／`AC_inc_var`）。`LoopBreak`／`LoopContinue` 以例外實作。34 個區塊指令的分派表 `BLOCK_COMMANDS` 也在這裡，含下一列匯入的資料來源指令。 |
| `flow_data_commands.py` | 253 | `AC_*_to_var` 資料來源與轉換指令：shell、時鐘、亂數、PDF、TOTP、SQL、檔案、HTTP、OCR，加上 `AC_assert_var`／`AC_assert_db`／`AC_assert_duration`／`AC_transform_var`。都不執行巢狀 action list，所以沒有迴圈／分支語意。 |
| `action_schema.py` | 128 | action list 的結構驗證：形狀、參數型別、未知指令拒絕。單一走訪同時支援兩種消費方式：`validate_actions()` 遇到第一個問題就拋、`unknown_command_names()` 收齊全部不認得的名字（REST `/execute` 用它回 400）。 |
| `mouse_aliases.py` | 39 | 單鍵點擊別名（`AC_click_left` 等），executor 與 callback executor 共用。 |

#### `utils/mcp_server/`（17,323 行，676 個工具）— 最大子系統

| 檔案 | 行數 | 職責 |
| --- | ---: | --- |
| `tools/_factories.py` | 8,739 | 工具工廠：每個函式回傳一個領域的 `MCPTool` 清單（把 `AC_*` 能力包成 MCP 工具）。 |
| `tools/_handlers.py` | 4,651 | 把 MCP 工具呼叫橋接到 AutoControl 無頭 API 的 adapter。 |
| `server.py` | 713 | JSON-RPC 2.0 over stdio 的最小 MCP 伺服器：連線範圍狀態、行內／併發分派、工具與 resource／prompt 處理器。 |
| `http_transport.py` | 514 | MCP 的 HTTP 傳輸。 |
| `http_sessions.py` | 234 | MCP 的 HTTP 傳輸用的 session 身分:`Mcp-Session-Id` 註冊表,以及每個 session 那條常駐的 server→client SSE 串流。 |
| `_client_requests.py` | 217 | 伺服器主動送出的請求：`roots/list`／`elicitation/create`／`sampling/createMessage`,對應表與回應路由,以及破壞性工具的確認交握。 |
| `_protocol.py` | 165 | JSON-RPC 線路格式：版本與識別常數、`_MCPError`、決定失敗工具行為的錯誤 tuple、envelope 產生器、工具回傳值轉 `content` 區塊。不碰伺服器狀態。 |
| `resources.py` | 303 | MCP resource 提供者。 |
| `prompts.py` | 220 | MCP prompt 目錄。 |
| `fake_backend.py` | 184 | CI／無頭測試用的記憶體內假後端。 |
| `plugin_watcher.py` | 149 | 檔案變更時熱重載外掛工具的背景 watcher。 |
| `tools/_base.py` | 147 | 工具註冊表的共用型別與輔助。 |
| `tools/_validation.py` | 107 | MCP 工具用到的 JSON Schema 子集驗證器。 |
| `tools/plugin_tools.py` | 90 | 把外掛載入的 `AC_*` callable 包成 `MCPTool`。 |
| `log_bridge.py` | 90 | 把 Python logging 記錄橋接成 MCP `notifications/message`。 |
| `audit.py` | 78 | MCP 工具呼叫稽核記錄。 |
| `context.py` | 71 | 傳給 opt-in 工具處理器的每次呼叫上下文。 |
| `rate_limit.py` | 48 | 工具呼叫的 token bucket 限流。 |
| `__main__.py` | 87 | `je_auto_control_mcp` console script 進入點。 |

#### `utils/remote_desktop/`（11,846 行／56 檔）

三條傳輸路徑並存：**TCP**（JPEG 影格）、**WebSocket**（同協定換傳輸）、**WebRTC**（aiortc 視訊 + DataChannel）。

| 檔案 | 行數 | 職責 |
| --- | ---: | --- |
| `webrtc_host.py` | 683 | WebRTC 主機：串流螢幕視訊並接受檢視端輸入;session 生命週期、DataChannel 接線、檔案收發。 |
| `webrtc_viewer.py` | 638 | WebRTC 檢視端：接收視訊並送出輸入。 |
| `host.py` | 625 | TCP 主機：接受迴圈、TLS 包裝、連線／認證握手、音訊與剪貼簿廣播、檔案推送、單次 token。 |
| `viewer.py` | 623 | TCP 檢視端。 |
| `host_service.py` | 542 | 無頭 WebRTC 主機執行器 + 多平台服務安裝器。 |
| `host_client.py` | 406 | TCP 主機的每連線處理器：一個檢視端一個實例,擁有它的認證交換、sender／audio／receiver 三條執行緒,以及入站訊息的路由表。 |
| `registry.py` | 370 | `AC_remote_*` 指令使用的行程級單例。 |
| `webrtc_transport.py` | 360 | 共用 WebRTC 管線：asyncio 橋接執行緒、螢幕視訊軌、設定。 |
| `multi_viewer.py` | 314 | 每個連入檢視端各跑一個 `WebRTCDesktopHost` 的協調器。 |
| `signaling_server.py` | 297 | 獨立的 WebRTC SDP 交換 rendezvous 服務。 |
| `audit_log.py` | 288 | SQLite 雜湊鏈稽核記錄。 |
| `host_capture.py` | 280 | TCP 主機的影格與游標產生：螢幕列舉、監視器索引轉擷取區域、預設 JPEG／游標 provider,以及 `FrameProductionMixin`（游標輪詢、擷取迴圈、上線編碼）。 |
| `ws_protocol.py` | 277 | 最小 RFC 6455 WebSocket 框架與握手。 |
| `file_transfer.py` | 273 | 分塊檔案傳輸。 |
| `relay.py` | 270 | NAT 穿透失敗時的 TCP 中繼。 |
| `fingerprint.py` | 250 | TOFU 主機指紋驗證。 |
| `turn_config.py` | 234 | coturn 設定產生器。 |
| `presence.py` | 221 | 多檢視者的執行緒安全在場註冊表。 |
| `jpeg_recorder_encrypted.py` | 223 | AES-GCM 加密版 session 錄影。 |
| `address_book.py` | 209 | 檢視端的主機通訊錄。 |
| `audio.py` / `webrtc_audio.py` / `webrtc_mic.py` | 206 / 190 / 152 | 音訊擷取播放、音訊軌、麥克風上行。 |
| `webrtc_files.py` | 205 | 專屬 DataChannel 的分塊檔案傳輸。 |
| `webrtc_host_auth.py` | 195 | 檢視端認證與核准：token 檢查、信任清單／IP 白名單自動放行、手動接受／拒絕、SAS、逾時關閉。 |
| `lan_discovery.py` | 189 | mDNS／Zeroconf 區網探索。 |
| `video_codec.py` | 182 | TCP／WS 路徑的可插拔視訊編解碼。 |
| `webrtc_host_media.py` | 172 | 重新協商與 recvonly 軌管理。aiortc 沒有 `removeTransceiver`,所以開／關不對稱——開是加軌重新 offer,關只能設 inactive 並停掉 receiver。 |
| `hw_codec.py` | 169 | 硬體 H.264 編碼偵測與啟用。 |
| `webrtc_stats.py` | 163 | 把 aiortc 的 `RTCStats` 報告輪詢成精簡 dict。 |
| `connect_coordinator.py` | 149 | 由使用者輸入的目標決定該用哪條傳輸。 |
| `adaptive_bitrate.py` | 148 | 依統計調整主機擷取 FPS。 |
| `signaling_client.py` | 145 | 純標準庫的訊令用戶端。 |
| `trust_list.py` | 144 | 自動接受的檢視端信任清單。 |
| `webrtc_inspector.py` | 138 | 行程級的 `StatsSnapshot` 滾動視窗。 |
| `input_dispatch.py` | 133 | 在主機端套用輸入訊息。 |
| `session_recorder.py` | 129 | 以 PyAV 把 WebRTC 影格錄成 mp4。 |
| `totp.py` | 129 | RFC 6238 TOTP（零外部相依）。 |
| `file_sync.py` | 126 | 輪詢式資料夾鏡像。 |
| `transport.py` | 123 | 可插拔的型別化訊息傳輸。 |
| `host_access.py` | 105 | TCP 主機的檢視端核准與存取控制：`PendingViewer`、權限字串、分享碼的 TOTP 候選值、IP 白名單。`host` 與 `host_client` 共用,所以獨立成模組。 |
| `protocol.py` | 96 | 長度前綴的 TCP 框架。 |
| `resume_tokens.py` / `session_quality_cache.py` / `rate_limit.py` | 95 / 86 / 85 | 快速重連 token、每 session 品質快取、檢視端限流。 |
| `host_id.py` / `viewer_id.py` | 82 / 78 | 主機與檢視端的持久身分。 |
| `permissions.py` / `clipboard_sync.py` / `wake_on_lan.py` / `session_actions.py` / `auth.py` | 65 / 73 / 57 / 41 / 29 | 逐 session 權限、剪貼簿同步、WOL、SAS 注入與螢幕遮蔽、HMAC 挑戰回應。 |
| `ws_host.py` / `ws_viewer.py` / `jpeg_recorder.py` | 41 / 30 / 139 | WebSocket 傳輸變體與 TCP 路徑錄影。 |

#### `utils/usb/`（4,250 行）與 `utils/usbip/`（920 行）

| 檔案 | 行數 | 職責 |
| --- | ---: | --- |
| `usb/passthrough/session.py` | 595 | 逐 peer 的 USB 直通 session。 |
| `usb/passthrough/viewer_client.py` | 561 | 檢視端的直通協定用戶端。 |
| `usb/passthrough/backend.py` | 464 | 後端 ABC + libusb 實作。 |
| `usb/passthrough/winusb_backend.py` | 458 | Windows WinUSB 後端（ctypes）。 |
| `usb/passthrough/acl.py` | 433 | 逐裝置 ACL。 |
| `usb/passthrough/iokit_backend.py` | 222 | macOS IOKit 後端。 |
| `usb/passthrough/webrtc_channel.py` | 168 | 把直通協定橋到 WebRTC `usb` DataChannel。 |
| `usb/passthrough/loopback.py` | 158 | 行程內 loopback 傳輸（測試用）。 |
| `usb/passthrough/protocol.py` | 133 | 線路框格式。 |
| `usb/passthrough/descriptor.py` | 133 | USB 標準裝置描述元解析。 |
| `usb/passthrough/key_provider.py` | 123 | ACL 的可插拔 HMAC 金鑰來源。 |
| `usb/passthrough/commands.py` | 151 | 無頭直通指令（單一真實來源）。 |
| `usb/usb_devices.py` | 286 | 跨平台 USB 裝置列舉。 |
| `usb/usb_watcher.py` | 214 | 輪詢式 USB 熱插拔監看。 |
| `usbip/protocol.py` | 331 | USB/IP 線路格式封裝／解析。 |
| `usbip/server.py` | 236 | USB/IP 主機端 TCP 伺服器。 |
| `usbip/libusb_backend.py` | 209 | 以 PyUSB／libusb 執行 URB 的正式後端。 |
| `usbip/backend.py` | 88 | 可插拔 URB 執行後端。 |

#### `utils/rest_api/`（1,739 行）

| 檔案 | 行數 | 職責 |
| --- | ---: | --- |
| `rest_server.py` | 468 | HTTP 前端主體。 |
| `rest_handlers.py` | 486 | 端點實作。 |
| `rest_openapi.py` | 422 | 走訪路由表產生 OpenAPI 3.1 規格。 |
| `rest_auth.py` | 143 | Bearer token 驗證 + 逐 client 限流閘門。 |
| `rest_metrics.py` | 75 | Prometheus 曝露端點。 |
| `rest_registry.py` | 75 | 保存執行中 REST 伺服器的行程級單例。 |
| `__main__.py` | 56 | `python -m je_auto_control.utils.rest_api` 進入點。 |

#### 其他多檔子套件

| 子套件 | 檔案組成 |
| --- | --- |
| `accessibility/` | `accessibility_api.py`（公開 API）、`element.py`（dataclass）、`tree.py`（遞迴樹傾印）、`recorder.py`（輪詢式事件錄製）、`backends/`：`base.py` 330 行抽象、`windows_backend.py` 915 行（comtypes UIA）、`windows_query.py` 170 行（UIA 搜尋起點、可中斷走訪、快取請求、NULL COM 指標判定與 `UIA_ERRORS`）、`windows_state.py` 98 行（控制項狀態讀取與密碼欄位判定）、`macos_backend.py` 125 行（pyobjc AX）、`null_backend.py` fallback |
| `agent/` | `agent_loop.py`、`computer_use.py`、`backends/`：`anthropic.py`、`anthropic_computer_use.py`（435 行）、`openai.py`、`base.py` |
| `ocr/` | `ocr_engine.py`（門面）、`structure.py`（版面）、`backends/`：`tesseract_backend.py`、`easyocr_backend.py`、`paddleocr_backend.py`、`base.py` |
| `vision/` | `vlm_api.py`、`backends/`：`anthropic_backend.py`、`openai_backend.py`、`null_backend.py`、`_parse.py`、`base.py` |
| `llm/` | `planner.py`、`backends/`：`anthropic_backend.py`、`null_backend.py`、`base.py` |
| `hotkey/` | `hotkey_daemon.py`、`backends/`：`windows_backend.py`（RegisterHotKey + 訊息幫浦）、`linux_backend.py`（XGrabKey）、`macos_backend.py`（CGEventTap）、`base.py` |
| `observability/` | `metrics.py`（334 行 Prometheus 原語）、`tracing.py`（OTel 相容 + no-op fallback）、`exporter.py`（`/metrics` 伺服器） |
| `triggers/` | `trigger_engine.py`（輪詢引擎）、`webhook_server.py`（HTTP 推送）、`email_trigger.py`（IMAP 輪詢） |
| `chatops/` | `router.py`（傳輸無關指令路由）、`slack_bot.py`（Slack adapter）、`handlers.py`（內建處理器） |
| `redaction/` | `rules.py`（偵測器）、`policies.py`（政策）、`engine.py`（協調器） |
| `failure_hooks/` | `backends.py`（Jira／Linear／GitHub）、`manager.py`（扇出）、`report.py`（資料類別） |
| `test_suite/` | `runner.py`、`result.py`、`reports.py` |
| `semantic_recording/` | `enrich.py`（加錨點）、`replay.py`（換機重播）、`self_healing.py`（自癒重播） |
| `tls_acme/` | `challenge.py`、`keys.py`、`renewal.py` |
| `pytest_plugin/` | `plugin.py`（pytest11 進入點）、`keywords.py`、`bdd_steps.py`（Gherkin） |
| `cv2_utils/` | `screen_grabber.py`、`screenshot.py`、`template_detection.py`、`screen_record.py`、`video_recording.py`、`blobs.py`、`optional.py` |
| `action_lint/` | `linter.py`、`schema.py`、`__main__.py`（CI 使用） |
| `time_travel/` | `controller.py`、`player.py` |
| `dag/` | `graph.py`、`runner.py` |
| `run_history/` | `history_store.py`、`artifact_manager.py` |
| `self_healing/` | `locator.py`、`heal_log.py` |
| `ab_locator/` | `runner.py`、`store.py` |
| `cost_telemetry/` | `pricing.py`、`store.py` |
| `governance/` | `governance.py`、`credential_broker.py` |
| `profiler/` | `profiler.py`、`resource_profiler.py` |
| `script_vars/` | `interpolate.py`、`scope.py` |
| `humanize/` | `motion.py`（貝茲路徑）、`typing.py`（抖動節奏） |
| `assertion/` | `assertions.py`、`combinators.py` |
| `scheduler/` | `scheduler.py`、`cron.py` |
| `stubs/` | `generator.py`、`__main__.py` |
| `config_bundle/` | `config_bundle.py`、`__main__.py` |
| `diagnostics/` | `diagnostics.py`、`__main__.py` |
| `xml/` | `xml_file/xml_file.py`、`change_xml_structure/change_xml_structure.py` |
| `generate_report/` | `generate_html_report.py`、`generate_json_report.py`、`generate_xml_report.py` |

### 5.5 GUI 層（`gui/`，84 檔／26,367 行）

GUI 是**選用 extra**（`pip install je_auto_control[gui]`，PySide6 + qt-material），且刻意保持「薄」：
每個分頁只把使用者輸入翻譯成對 `utils/` 無頭核心的呼叫。

#### 骨架

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `gui/__init__.py` | 23 | `start_autocontrol_gui()`：**唯一**會延遲匯入 PySide6 的地方，維持頂層套件 Qt-free。 |
| `main_window.py` | 290 | `QMainWindow`：選單列（File／Actions／View／…）、可關閉分頁、即時語言切換、字級預設、qt-material 主題。分頁分為 core／editing／detection／automation／system 五類。 |
| `main_widget.py` | 423 | 擁有 `QTabWidget`，註冊 48 個分頁，並暴露 show/hide/list API 給選單列。核心分頁在註冊時直接宣告 `(label_key, handler)` 動作對；分頁本體都在下列 mixin。 |
| `_auto_click_tab.py` | 270 | 自動點擊分頁的 mixin 建構器。 |
| `_screenshot_tab.py` | 127 | 截圖／取像素分頁 mixin。 |
| `_image_detect_tab.py` | 106 | 影像偵測分頁 mixin。 |
| `_script_tab.py` | 105 | 腳本執行分頁 mixin。 |
| `_record_tab.py` | 101 | 錄製／回放分頁 mixin。 |
| `_report_tab.py` | 81 | 報表分頁 mixin。 |
| `_i18n_helpers.py` | 67 | 需要即時語言切換的分頁共用的翻譯註冊 mixin。 |
| `language_wrapper/` | 4,977 | 四語系字典（英／日／簡中／繁中）+ `multi_language_wrapper` 執行期切換器與監聽註冊表。 |
| `selector/` | 183 | 拖曳選取螢幕區域的半透明全螢幕覆蓋層與樣板裁切工具（互動式，但都有對應的程式化 API）。 |

> **分頁指令一律走 Actions 選單**：分頁本身只放輸入、表格與結果檢視，指令由視窗層選單暴露。
> 核心分頁在 `main_widget.py` 註冊時宣告動作；功能分頁實作 `menu_actions()`（目前 40 個檔案有此 hook）。
> `test/unit_test/headless/test_actions_menu_gui.py` 會守住這個契約——沒有動作宣告的新分頁會讓 CI 失敗。

#### 48 個分頁

| 分頁 | 模組 | 行數 | 職責 |
| --- | --- | ---: | --- |
| auto_click | `_auto_click_tab.py` | 270 | 自動點擊：座標、間隔、熱鍵、`write`、捲動。 |
| screenshot | `_screenshot_tab.py` | 127 | 截圖、選區、螢幕尺寸、取像素色。 |
| image_detect | `_image_detect_tab.py` | 106 | 樣板裁切、定位、定位全部、定位並點擊。 |
| record | `_record_tab.py` | 101 | 錄製／停止／回放／存檔／載入。 |
| script_builder | `script_builder/` | 5,708 | **視覺化腳本編輯器**：`command_schema.py`（4,924 行 `AC_*` 參數綱要）、`step_model.py`（步驟模型與 AC JSON 序列化）、`step_list_view.py`（含巢狀 body 的樹狀檢視）、`step_form_view.py`（綱要驅動表單）、`builder_tab.py`。 |
| flow_editor | `flow_editor/` | 490 | 節點式流程圖檢視：`layout.py`（純 Python 佈局演算法，可單測）、`scene.py`（Qt 場景繪製）、`tab.py`。 |
| script | `_script_tab.py` | 105 | 載入／執行單檔或整個目錄、內建編輯器執行。 |
| recording_editor | `recording_editor_tab.py` | 244 | 裁切、過濾、重新縮放錄製內容。 |
| variables | `variables_tab.py` | 166 | 檢視、灌入、清除 executor 執行期作用域。 |
| secrets | `secrets_tab.py` | 188 | 解鎖保險庫並管理 `${secrets.NAME}`。 |
| vlm | `vlm_tab.py` | 112 | 用文字描述 UI 元素，交由模型定位。 |
| self_healing | `self_healing_tab.py` | 195 | 自癒定位器管理與治癒記錄。 |
| ocr_reader | `ocr_tab.py` | 170 | 傾印區域文字或以 regex 搜尋。 |
| accessibility | `accessibility_tab.py` | 131 | 瀏覽 OS UI 樹並依 role/name 點擊。 |
| live_hud | `live_hud_tab.py` | 99 | 即時 HUD：滑鼠位置、游標下像素色、log tail。 |
| llm_planner | `llm_planner_tab.py` | 182 | 自然語言描述 → 預覽 → 執行。 |
| computer_use | `computer_use_tab.py` | 166 | 從 GUI 啟動 Anthropic 閉環 agent。 |
| scheduler | `scheduler_tab.py` | 138 | 註冊間隔式 action JSON 執行。 |
| hotkeys | `hotkeys_tab.py` | 130 | 將全域熱鍵綁到 action 檔。 |
| triggers | `triggers_tab.py` | 321 | 影像／視窗／像素／檔案事件監看。 |
| webhooks | `webhooks_tab.py` | 210 | 將 HTTP 請求綁到 action 腳本。 |
| email_triggers | `email_triggers_tab.py` | 224 | 將 IMAP 信箱綁到 action 腳本。 |
| test_suite | `test_suite_tab.py` | 163 | 執行 QA 套件規格並管理易碎隔離區。 |
| assertions | `assertions_tab.py` | 130 | 執行單一畫面狀態斷言並顯示通過／失敗。 |
| data_source | `data_source_tab.py` | 136 | 預覽無頭資料層載入的資料列。 |
| flakiness | `flakiness_tab.py` | 117 | 依執行歷史排序間歇失敗的腳本。 |
| a11y_audit | `a11y_audit_tab.py` | 114 | 從即時樹找出無障礙／i18n 缺陷。 |
| device_matrix | `device_matrix_tab.py` | 111 | 一份 action list 跨多裝置平行執行。 |
| media_checks | `media_checks_tab.py` | 116 | 音訊活動與影片動態斷言。 |
| run_history | `run_history_tab.py` + `run_history_timeline.py` | 462 | 瀏覽過去的排程／觸發／熱鍵執行，含自訂時間軸元件。 |
| profiler | `profiler_tab.py` | 131 | 視覺化逐動作耗時熱點。 |
| window_manager | `window_tab.py` | 128 | 列出、聚焦、關閉視窗。 |
| plugins | `plugins_tab.py` | 83 | 從使用者目錄載入額外 `AC_` 指令。 |
| webrunner | `webrunner_tab.py` | 188 | 從 GUI 驅動 `je_web_runner`。 |
| dag_runner | `dag_tab.py` | 188 | 編輯、驗證、執行跨主機 DAG。 |
| chatops | `chatops_tab.py` | 108 | 在接上 Slack 前先本機測試 slash 指令。 |
| trace_replay | `trace_replay_tab.py` | 187 | 拖曳捲動時光回溯錄製內容。 |
| remote_desktop | `remote_desktop/`（17 檔） | 6,240 | 見下。 |
| presence | `presence_tab.py` | 152 | 多檢視者在場名單。 |
| rest_api | `rest_api_tab.py` | 198 | 啟停 HTTP 前端並顯示 URL 與 token。 |
| admin_console | `admin_console_tab.py` | 313 | 管理多個遠端 AutoControl REST 端點。 |
| audit_log | `audit_log_tab.py` | 192 | 瀏覽並驗證防竄改雜湊鏈。 |
| inspector | `inspector_tab.py` | 121 | WebRTC 檢測器：即時摘要與近期統計取樣。 |
| usb_devices | `usb_devices_tab.py` | 121 | 唯讀列舉 + 熱插拔監看控制。 |
| usb_browser | `usb_browser_tab.py` | 310 | 檢視端 USB 裝置瀏覽器。 |
| usb_share | `usb_passthrough_panel.py` + `usb_passthrough_prompt.py` | 704 | AnyDesk 風格 USB 直通面板與主機端 ACL 授權對話框。 |
| diagnostics | `diagnostics_tab.py` | 91 | 執行子系統檢查並顯示結果。 |
| report | `_report_tab.py` | 81 | 產生 HTML／JSON／XML 報表。 |

#### 遠端桌面 GUI（`gui/remote_desktop/`，17 檔／6,254 行）

| 模組 | 行數 | 職責 |
| --- | ---: | --- |
| `webrtc_panel.py` | 2,555 | WebRTC 子分頁主體。 |
| `webrtc_dialogs.py` | 493 | WebRTC GUI 用的自訂對話框與清單元件（待審檢視者、信任清單、通訊錄、遠端檔案表、稽核記錄、LAN 瀏覽）。 |
| `connection_screen.py` | 672 | Quick Connect —— AnyDesk 風格單畫面入口。 |
| `viewer_panel.py` | 542 | 「控制另一台機器」子分頁。 |
| `webrtc_known_hosts.py` | 340 | TOFU 釘選庫瀏覽器：`KnownHostsDialog` 與帶外釘選用的小表單。由 `webrtc_dialogs` 再匯出。 |
| `host_panel.py` | 334 | 「分享這台機器」子分頁。 |
| `frame_display.py` | 228 | 繪製 JPEG 影格並發出遠端輸入事件的元件。 |
| `webrtc_workers.py` | 195 | 訊令流程的背景 `QThread` worker。 |
| `tab.py` | 165 | 外層容器分頁。 |
| `_helpers.py` | 189 | 面板共用輔助：翻譯、Qt→AC 鍵滑鼠對應、TLS context、狀態徽章、指紋與時間格式化。 |
| `remote_screen_window.py` | 140 | 檢視端的彈出視窗。 |
| `tray_icon.py` | 98 | WebRTC 主機的系統匣圖示。 |
| `annotation_overlay.py` | 88 | 主機端標註的透明最上層覆蓋。 |
| `sparkline.py` | 77 | WebRTC 統計面板的迷你走勢圖。 |
| `blanking_overlay.py` | 71 | 遠端連線期間的隱私遮蔽全螢幕覆蓋。 |
| `viewer_screen_window.py` | 46 | 顯示連入檢視端分享畫面的彈出視窗。 |

### 5.6 周邊子專案與資產

| 目錄 | 內容 | 職責 |
| --- | --- | --- |
| `autocontrol-lsp/` | 8 檔／752 行 | **AC_* action JSON 的語言伺服器**：`server.py`（JSON-RPC over stdio）、`handlers.py`（純函式 LSP 處理器，易單測）、`diagnostics.py`（診斷清單）、`documents.py`（記憶體文件庫）、`commands.py`（從 executor 取得所有指令，自動同步）。 |
| `autocontrol_driver/` | 1 檔 | 產生 AutoControl driver 的小工具。 |
| `AutoControl/executor/` | 3 檔 | 由 `create_project_dir` 產生的專案範本示範（單檔／整個目錄／錯誤檔案三種執行方式）。 |
| `exe/start_autocontrol_gui.py` | 4 行 | 打包成執行檔用的 GUI 啟動器。 |
| `benchmarks/core_latency.py` | 32 行 | 對穩定無頭進入點的可重複煙霧基準測試。 |
| `examples/` | 27 個腳本 | 從截圖點擊、OCR、排程、遠端桌面、agent loop、可觀測性，一路到 computer-use、Wayland、跨主機 DAG、chatops、pytest/BDD、anchor locator。 |
| `browser-extension/` | manifest v3 擴充 | 瀏覽器端配合元件（background／content script／popup）。 |
| `docker/` | Dockerfile ×8 + compose + 9 支驗證／伺服器腳本 | 無頭容器（`Dockerfile`）、帶 XFCE 桌面的容器（`Dockerfile.xfce`),以及四個**驗證用**映像:`Dockerfile.wayland`（sway headless,擷取路徑 + `libei_verify.py` 對真的 libei.so 解析符號）、`Dockerfile.eis`（`eis_server.py` 用 ctypes 綁 libeis 起一個真的 EIS server,`eis_verify.py` 把 libei sender 對著它跑完整握手與發送）、`Dockerfile.portal`（`portal_server.py` 自己佔住 `org.freedesktop.portal.Desktop`,真的 `dbus-daemon` + 真的 liboeffis 跑完 RemoteDesktop 交握）、`Dockerfile.ydotool`（真的 uinput 裝置,`ydotool_verify.py` 直接讀回 `/dev/input/eventN`）、`Dockerfile.seat`（`headless,libinput` + builtin seat,合成器真的吃下 ydotool 裝置,`seat_verify.py` 從 `grim -c` 的像素讀回游標落點）、`Dockerfile.x11`（真的 Xvfb + openbox,`x11_verify.py` 用 `xev` 把注入的事件從真的客戶端讀回（含 `synthetic NO`,這是 XTest 跟 `XSendEvent` 的差別）,另用 ImageMagick `import` 做獨立擷取對照,跑兩種螢幕版面）。全部接在 `.github/workflows/docker.yml`。 |
| `k8s/helm/` | Helm chart | Kubernetes 部署。 |
| `ci_templates/.gitlab-ci.yml` | — | 供使用者專案複製的 GitLab CI 範本。 |
| `docs/` | Sphinx（`API`／`Eng`／`Zh`／`getting_started`） | Read the Docs 文件。 |
| `architecture_diagram/` | drawio + png | 既有的架構圖原始檔。 |
| `test/` | `unit_test/headless`（主要）、`unit_test/flow_control`、`integrated_test`、`gui_test`、`manual_test`、`verify`、`test_source` | 478 個 `test_*.py`／4,654 個測試函式。**注意**：`test/unit_test/` 下的 `*_test.py` 是會真的驅動滑鼠鍵盤的手動示範腳本，因此 `pyproject.toml` 把 `python_files` 釘成 `test_*.py`。`unit_test/headless/conftest.py` 有一個 autouse fixture，每個測試結束都沖掉 Qt 排隊中的 `deleteLater()`——不沖會讓殘留的 widget 在後面某個不相干的測試裡被銷毀，曾經整個直譯器 `__fastfail`。`test_doc_counts.py` 守住文件引用的指令／工具／子套件／範例數,`test_doc_line_counts.py` 守住所有行數（`--fix` 可一次重新產生）。 `verify/macos_verify.py` 是在真的 `macos-14` runner 上量測 TCC 到底允許什麼的探針（macOS 是唯一沒有容器可用的支援平台），不被 pytest 收集。 |

---

## 6. 擴充點

| 想加什麼 | 該動哪裡 | 不需要動什麼 |
| --- | --- | --- |
| **新平台後端** | 新增 `je_auto_control/<platform>/` 實作 backend 介面，並在 `wrapper/platform_wrapper.py` 加一個分支 | 所有 wrapper 模組與上層 |
| **新 `AC_*` 指令** | 在 `utils/` 寫無頭實作 → 加進 `Executor.event_dict` → 加進 `gui/script_builder/command_schema.py` | executor 分派邏輯本身 |
| **執行期外掛指令** | `add_command_to_executor({"AC_x": fn})`，或用 `utils/plugin_loader`（掃描目錄）／`utils/plugin_sdk`（entry points） | 核心程式碼 |
| **新 GUI 分頁** | 在 `gui/` 新增 widget（只做 UI 翻譯）→ 在 `main_widget.py` `_add_tab` 註冊 → 提供 `menu_actions()` | 主視窗選單建構邏輯 |
| **新 OCR／VLM／LLM／a11y 後端** | 在對應 `backends/` 實作 base 協定 | 呼叫端 |
| **新報表格式** | 仿 `generate_report/` 既有三者的骨架新增產生器 | 執行紀錄收集 |
| **新 MCP 工具** | 在 `mcp_server/tools/_factories.py` 加工廠、`_handlers.py` 加 adapter | 傳輸層 |

---

## 7. 品質閘門與工程約束

**CI 工作流程**（`.github/workflows/`）：

| 檔案 | 用途 |
| --- | --- |
| `dev.yml` | 開發分支測試。 |
| `stable.yml` | 合併到 main 後版本遞增並上傳 PyPI（使用 `PYPI_API_TOKEN`）。 |
| `release.yml` | 發佈流程（上傳步驟目前關閉）。 |
| `quality.yml` | 靜態分析與型別檢查。 |
| `platform-smoke.yml` | 跨平台煙霧測試。 |
| `docker.yml` | 容器映像建置。 |
| `action-json-lint.yml` | 用 `python -m je_auto_control.utils.action_lint` 檢查 action JSON。 |

**設定基線**（`pyproject.toml`）：

- **pytest**：`testpaths` 限定 `test/unit_test/headless` 與 `test/unit_test/flow_control`；`--strict-markers --strict-config`。
- **coverage**：`fail_under = 35`（實測基線，CI 只確保不退步），排除 `gui/` 與 `language_wrapper/`。
- **mypy**：只對穩定 API 面把關；`follow_imports = "silent"`，numpy stub 以 `follow_imports_for_stubs` 略過。
- **bandit**：排除 `test`／`docs`／`language_wrapper`（翻譯字典會誤觸 B105），只跳過 B101。

**程式碼硬約束**（CLAUDE.md）：循環複雜度 ≤ 10、認知複雜度 ≤ 15、函式 ≤ 75 行、參數 ≤ 7、
巢狀 ≤ 4、檔案 ≤ 750 行、行寬 ≤ 120；禁止裸 `except`、可變預設參數、`eval`/`exec`、
`shell=True`、`pickle` 反序列化外部資料、函式庫程式碼中的 `print` 與 `assert`；
socket 預設綁 `127.0.0.1`；資源一律用 `with`。

**例外設計**（`utils/exception/exceptions.py`）：所有框架錯誤都繼承 `AutoControlException`，
讓 executor、背景輪詢迴圈、請求處理器與 GUI slot 這四種收納邊界能用單一 `except` 攔住整個家族。
**不可**新增直接繼承 `Exception` 的兄弟類別——那會靜默逃出每一道邊界。

---

## 8. 附錄：各層規模

| 層／子系統 | 檔案數 | 行數 |
| --- | ---: | ---: |
| `gui/` | 89 | 26,542 |
| `utils/mcp_server/` | 21 | 17,323 |
| `utils/remote_desktop/` | 56 | 11,846 |
| `utils/executor/` | 6 | 9,075 |
| `utils/usb/` | 17 | 4,250 |
| `je_auto_control/`（頂層 3 檔） | 3 | 2,363 |
| `utils/accessibility/` | 13 | 2,818 |
| `wrapper/` | 3,068 | 3,013 新增 `window_backends/`：視窗管理的平台縫（`base` / `windows_backend` / `x11_backend` / `macos_backend` / `null_backend`）。放在 `wrapper/` 而不是 `utils/`，因為它必須 import `windows/`、`linux_with_x11/`、`osx/`，而 `utils/` 在分層上在那三者之上。 |
| `windows/` | 23 | 1,894 |
| `utils/rest_api/` | 8 | 1,739 |
| `utils/agent/` | 8 | 1,250 |
| `linux_with_x11/` | 19 | 1,215 |
| `linux_wayland/` | 17 | 2,836 |
| `utils/triggers/` | 4 | 1,146 |
| `utils/ocr/` | 9 | 1,112 |
| `utils/usbip/` | 5 | 920 |
| `utils/assertion/` | 3 | 863 |
| `osx/` | 17 | 907 |
| `autocontrol-lsp/` | 8 | 744 |
| `utils/hotkey/` | 7 | 727 |
| 其餘模組（約 286 個 `utils/` 子套件 + `android/`／`ios/`／周邊小工具） | 691 | 50,522 |
| **總計** | **1,024** | **140,092** |


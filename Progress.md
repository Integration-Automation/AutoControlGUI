# Progress

## 跨平台與 GUI 全面改版

`TODO` — 重設 UI、重寫並優化 GUI、修正 Wayland 與函式庫問題、跨機器同步、
深化全套 mypy、補齊 iOS／Android、MCP 逐步揭露、自愈定位器量測、動作日誌 codegen、
完整範例與文件。涉及 `gui/`、`linux_wayland/`、`android/`、`ios/`、
`utils/{config_sync,remote_desktop,mcp_server,self_healing,codegen,executor}/` 與型別／文件驗證。
核准設計：[跨平台自動化與 GUI 改版](docs/superpowers/specs/2026-10-02-platform-gui-modernization-design.md)。
實作計畫：[分階段交付計畫](docs/superpowers/plans/2026-10-02-modernization-index.md)，待審閱。
現有 `[Answer]` 決策沿用。

`WIP` — 計畫 A（既有決策與執行契約）已交付，A2、A7 在 2026-10-08、其餘在 2026-10-09（U-20261009-01…14）；
各項沒驗到或沒做完的部分在本檔下面三節（輸入與視窗、macOS、這一輪修正留下的後續）。計畫 F（GUI）：F1 的延遲分頁註冊與 F2 的導覽／搜尋／主題已交付（U-20261008-02）。
計畫 B（動作日誌、自愈量測、codegen）、C（持久化同步與遠端 session；其中 C4 的擁有者模型已做）、D（Wayland）、E（Android／iOS）、G（MCP 逐步揭露）、H（型別深化與總驗收）尚未開始。F 還缺：

- **窄視窗的內容是被擠壓而不是可捲動**：`gui/main_widget.py` 給 `QTabWidget` 明確的最小尺寸讓視窗能縮到 640×420，
  但分頁內容沒有包進 `QScrollArea`；包進去會改變 `tabs.indexOf(entry.widget)` 這個 PyBreeze 與測試都在用的關係，要一起設計。
- **主題與面板狀態不會記住**：`AutoControlGUIUI.set_theme`、導覽面板的顯示與寬度、字級都只活在當次執行；
  要用 `QSettings` 存，並讓測試不寫到使用者的設定。
- **`qt-material` 還在 `[gui]` extra**：`gui/main_window.py` 已不匯入它。移除要同時改 `pyproject.toml`、`dev.toml`、
  `requirements.txt`、`uv.lock` 與 mypy 的 override，並先確認 PyBreeze 沒有靠這個 extra 取得它。
- **分頁的關閉鈕是 Fusion 內建圖示**：計畫規定主題不新增點陣圖相依，換圖示要用 Qt 內建向量或既有資產。
- **Remote Desktop 與 Script Builder 仍在啟動時建立**（預設開啟），啟動時間 2.6–2.7 秒裡大半是它們與門面匯入。
- **F1 的 `TabRegistry.open/close` 介面與 `close` 釋放訂閱**：現在關閉分頁只是從分頁列移除，widget 留著。
- **F3**（共用 worker、取消、關閉時不碰已銷毀物件、`webrtc_panel.py` 拆分）與 **F4**（啟動／記憶體基準、mixed-DPI、
  功能對等測試）尚未開始。

**只記未完成的事。** 完成的工作記在 [docs/updates/](docs/updates/README.md)（每月一個批次檔，
索引與查詢指令在它的 README），相容性變更寫進 [CHANGELOG.md](CHANGELOG.md)；完成的項目
從本檔移除，同一個 commit 在 `docs/updates/` 補一筆 `#done` 條目，不在這裡累積歷史。

狀態標記：

| 標記 | 意思 |
| --- | --- |
| `TODO` | 已決定要做，尚未開始 |
| `WIP` | 進行中，工作樹已有部分成果 |
| `BLOCKED` | 卡在外部條件（硬體、第三方、上游套件） |
| `DECIDE` | 需要維護者拍板才能往下走 |

---

## 750 行上限的既有豁免清單

`CLAUDE.md` §Size and complexity limits 規定:超標檔案只能列在這裡,列不進來的就是缺陷。
清單上的檔案**可以改、可以變短,但不得再變長**——要再長就得先拆。
行數為實測（`len(text.splitlines())`）；`webrtc_panel.py` 於 2026-08-22 拆出
`advanced_group.py`、2026-09-23 拆出 `trusted_group.py` 後降到 2,530，上限跟著往下走。
**這張表現在有測試在守**：`test/unit_test/headless/test_file_length_budget.py` 比對本表與樹，
超標未列、列上的檔案變長、或已經縮到線內卻還留著的列，都會紅。

| 檔案 | 行數 | 為何還沒拆 |
| --- | ---: | --- |
| `utils/mcp_server/tools/_handlers_executor_bridge.py` | 1,429 | 2026-09-23 拆 `_handlers.py` 時新建。253 個純委派（中位數 3 行）：`from action_executor import _x` 再 `return _x(...)`,沒有分支。**不套用 flat data tables 條款**——那一條講的是「一個對照表或清單」,這裡是 252 個函式定義。再切下去只能照 MCP 工廠領域分（159 個領域）,那會把同一種委派散進十幾個檔,而它們之間沒有語意邊界。規則照舊:只准變短。 |
| `gui/remote_desktop/webrtc_panel.py` | 2,527 | 單一 Qt 面板,但已含連線、監視器選擇、頻寬自適應、麥克風、錄影五組互動狀態。應拆成 panel + 各控制器。 |
| `utils/accessibility/backends/windows_backend.py` | 805 | 已拆出 `windows_query.py`（193）、`windows_state.py`（98）與 `windows_reads.py`（142,2026-09-23;拆完 801,同日加焦點查詢的委派 +4）。剩下的是同一套 UIA COM 生命週期管理,再拆會把 `CoInitialize`／介面釋放的配對邏輯切散。 |

**本質豁免（依 `CLAUDE.md` 的「flat data tables」條款,不算既有豁免）**:
`utils/mcp_server/tools/_factories.py`（9,001,MCP 工具註冊表）、
`utils/executor/action_executor.py`（8,260,`AC_*` 分派表）、
`gui/script_builder/command_schema.py`（5,057,每個 `AC_*` 的參數 schema）、
`je_auto_control/__init__.py`（1,970,門面 re-export）、
`gui/language_wrapper/{english,japanese,traditional_chinese,simplified_chinese}.py`
（1,326／1,213／1,193／1,192,語系字串表；以上皆 2026-09-23 實測）。

### 2026-08-19 決議:上表的實測行數就是新的上限

2026-08-18 重新實測時,表上原有的七列**全部**變長,而 `CLAUDE.md` 明寫
「列上的檔案不得再變長,要再長就得先拆」,所以這裡曾標成 `[DECIDE]`。
**維護者已於 2026-08-19 拍板:接受實測數字當新基準**——不為了回到舊數字而去拆
`_handlers.py`（4,789）與 `webrtc_panel.py`。上表的行數即是各自的新上限,
規則不變:只准變短,再變長就得先拆。
（`_handlers.py` 後來還是拆了:2026-09-22 拆出 QA 主題,2026-09-23 再拆出九個主題模組,
本體降到 522 行、離開上表。見 `docs/updates/` 的 U-20260922-05 與 U-20260923-09。）

同一批裡有六個檔案在 2026-08-19 已經拆回線內、從表上移除,做法寫在
commit `46f4cd5` 的說明裡（`docs/updates/` 沒有對應條目：舊的 `WHATS_NEW.md` 從沒記過這件事）。

行數沒有任何 CI 在把關（`quality.yml` 的五個 job 裡只有 ruff 管到這一節的限制,而它只管行寬),
所以這張表只會在有人手動實測時才會被發現對不上——上次就是。

---

## Windows arm64:裝得起來了，但少了影像與加密

`TODO` — 上游仍未發 wheel（`opencv-python`、`cryptography`），但安裝本身不再是卡點

這一項曾經是 `BLOCKED`，而那個判斷只對一半。上游確實沒有發 wheel，
這件事到今天（2026-08-20）重新實測依舊成立；但「裝不起來」卡的不是程式，
是 `pyproject.toml` 無條件要求那兩個套件。實測：把 `cryptography`、`cv2`、
`je_open_cv`、`numpy`、`PIL` 五個全擋掉之後，`import je_auto_control`、executor、
MCP 工具表、`cli`、`api.generate_code`、`api.create_failure_bundle` **全部照常跑**。

所以修法是一個 PEP 508 環境標記，三個相依共用同一個：

```
sys_platform != 'win32' or platform_machine != 'ARM64'
```

`windows-11-arm` 已經回到 `platform-smoke.yml` 的矩陣（只跑 3.14，CPython 的
官方 win-arm64 build 從 3.11 才有）。其他平台拿到的東西一個位元都沒變。

### 還沒有答案的：Windows arm64 上這些功能不能用

裝得起來不等於功能齊。該平台上以下四組會拋帶提示的錯誤，而不是默默失效：

| 功能 | 缺的是 | 錯誤形式 |
| --- | --- | --- |
| 影像比對、截圖轉 BGR、螢幕錄影 | `opencv-python`／`je_open_cv` | `utils/cv2_utils/optional.py` 的 `require_cv2()`／`require_je_open_cv()` 拋 `RuntimeError` |
| 動作檔加密與 Ed25519 簽章（`action_signing`） | `cryptography` | 拋 `CryptographyUnavailableError`（也是 `RuntimeError`；HMAC 簽章不受影響） |
| 秘密金庫（`${secrets.NAME}`） | `cryptography` | 同上 |
| ACME／TLS 發證、加密錄影 | `cryptography` | 模組層 `ImportError` 轉述（照 `webrtc_transport` 慣例） |

這四組在 arm64 上能不能回來，**完全取決於上游**：

| 依賴 | win_arm64 | 實測（2026-08-20） |
| --- | --- | --- |
| `opencv-python>=4.8,<6` | **沒有** | 任何版本都沒有，pip 回的是 `from versions: none`。`je_open_cv` 自己是純 Python，但相依 opencv-python，所以一起卡——標記也必須一起下。 |
| `cryptography>=50.0.0` | **沒有** | wheel 只出到 **46.0.3**，46.0.4 起上游就不再發 win_arm64。`>=50.0.0` 是**安全下限**（GHSA-537c-gmf6-5ccf 與 GHSA-g6cj-pr64-35w5），不能為了 arm64 降回去。 |
| `pillow==12.3.0` | 有 | `pillow-12.3.0-cp3xx-win_arm64.whl` 一直都在。**曾經被寫成卡點，那是猜的，它從來不是。** |
| `mss`／`defusedxml` | 有 | 純 Python。這三個加上 Pillow 就是 arm64 實際裝到的全部。 |
| `PySide6==6.11.1`／`qt-material==2.17` | 有 | `[gui]` extra 在 arm64 上裝得起來。 |
| `aiortc` | **沒有** | 卡在傳遞相依 `google-crc32c`，與本專案的選擇無關；`av` 自己有 wheel。 |

重驗指令（不需要 arm64 機器，也不需要 runner）：

```bash
pip install --dry-run --only-binary=:all: --platform win_arm64 --python-version 3.12 --target /tmp/probe 'opencv-python>=4.8,<6' 'cryptography>=50.0.0'
```

兩行 `ERROR: No matching distribution` 就是現況。**哪天其中一行不見了，就把
`pyproject.toml` 上那個標記拿掉**（三行一起），
`test/unit_test/headless/test_arm64_dependency_markers.py` 會帶著你改完。

注意一個驗證上的陷阱：**`pip --platform` 不會換掉 marker 的評估環境**，
它只影響 wheel 相容性標籤，所以拿本機做 `--dry-run` **驗不到標記的效果**（兩個
套件依舊會被要求）。能驗的是兩件事：直接評估 marker（上面那支測試在做的），
以及 `windows-11-arm` 那一格自己綠。

### 一個刻意的取捨：cv2 只包兩扇門

`cv2` 在 33 個檔、共 76 句 import，全部是函式內 lazy。這次**只**在兩個大家一定會
經過的門換成 `require_cv2()`／`require_je_open_cv()`：`wrapper/auto_control_screen.py`（截圖）
與 `utils/cv2_utils/template_detection.py`（樣板比對）。其餘七十幾句維持原樣，在 arm64 上
會得到 `ModuleNotFoundError: No module named 'cv2'`。全包一輪是大面積 diff，且對呼叫端
並沒有多提供可以行動的資訊——哪天語意不足再說。

## Wayland:剩下的都不是「缺一台機器」

這一項曾經三度寫成「要一台 VM」——先是 portal 交握,再是 ydotool 的絕對移動落點,
中間還有負原點的擷取。三次都不是,三次都是同一個誤判:**把「合成器／桌面做不到的事」
當成了「容器做不到的事」**。portal 是 D-Bus 介面,誰佔住那個名字誰就是 portal;
「會吃 libinput 裝置的 seat」是 wlroots 的 `WLR_BACKENDS=headless,libinput` 加
`LIBSEAT_BACKEND=builtin` 加 `SEATD_VTBOUND=0`（第四個條件是 udev 要比 ydotoold 早起
來)。都已經是 CI job 了,見 [docs/updates/2026-08.md](docs/updates/2026-08.md) 的 U-20260819-02（原本在這裡的「已經有答案的」一節）與 U-20260818-01、U-20260819-01。

**下次要往這裡加「需要一台 VM／真桌面」之前,先問這件事到底是誰做不到。**

### 還沒有答案的

- **`eis_device_pause()` 在 libeis 1.3.901 對 sender client 沒有送出任何東西。**
  對兩個 live device 呼叫 pause 再 dispatch,client 端的 ei fd 4 秒內完全沒有可讀資料。
  所以 `LibeiBackend._on_event` 的 `DEVICE_PAUSED`／`DEVICE_REMOVED` 分支**仍然沒有
  peer 可以驅動**。`eis_verify.py` 把這件事寫成「要嘛有反應,要嘛根本沒被通知」,
  若哪天 libeis 開始送了,client 忽略它就會當場失敗。真的合成器上會不會不一樣,未知。
- **`ei_device_start_emulating()` 的 sequence number 沒有被送到對面。**
  刻意送 4242 過去,server 讀回來是 0。我們這邊的計數本身符合標頭檔的約定
  （每次呼叫至少 +1）,所以不影響正確性,只是從對面驗不到。
- **同意對話框「長什麼樣子、真人要按多久」。** portal 這一層現在驗到的是對話框
  *產生的東西*:准（Response 0）、拒（Response 1）、以及一直不回答。三種我們都在真的
  bus 上跑過,三種都得在自己的時限內收斂。至於真的 mutter 對話框長什麼樣、真人猶豫
  三十秒會不會撞到別的東西,那是 mutter 的事,CI 裡沒有人可以去按它。

**緩解**:驗不到的擷取部分有逃生門——`JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND` 讓操作者
直接指定自己的擷取指令（`{output}` 會被換成暫存 PNG 路徑）,優先於所有偵測。

---

## 輸入、視窗與擷取修正：還沒在真的桌面與 Jeffrey_RPA 上驗過

`BLOCKED` — 程式已改完（U-20261009-03、-04、-05），但驗證全部是假後端；Jeffrey_RPA 的正式批次在跑，不能在它的環境裡換版本

2026-10-08 實測：Jeffrey_RPA（`NovelAI_RPA`）的 venv 是從 PyPI 裝的 `je_auto_control`，不是這個工作樹的 editable install，
所以這裡的修改不會直接影響正在跑的批次；它升級套件時才會拿到。升級前要做的事：

- **在 Jeffrey_RPA 跑 `test/test_je_facade.py`**（原本的解除條件），並看 `_gui_control.py` 對下列行為變更有沒有依賴：
  `write()` 大寫與 `is_shift` 在 Windows／X11 生效、`"\r\n"` 只按一次 Enter、`mouse_scroll` 預設方向改為 `scroll_up`
  （X11／Wayland 上 `mouse_scroll(3)` 由往下變往上）、小數座標四捨五入、`focus_window` 在 Windows 沒拿到前景會丟例外、
  `list_windows` 不再列出 DWM cloak 與零面積視窗、`post_key` 對可列印字元只送 `WM_CHAR`。
- **混合 DPI 螢幕上的座標與樣板要重錄**：Windows 改成 per-monitor v2 之後，縮放比例與主螢幕不同的螢幕上，
  座標變成原本的「該螢幕縮放／主螢幕縮放」倍（125% 副螢幕配 100% 主螢幕是 ×1.25），截圖是實體像素、不再是縮小的影像；
  在那些螢幕上錄的點擊座標、`screen_region`、視窗版面與裁出來的樣板都要重做。主螢幕上的不受影響。
  這台機器現在只接一個螢幕，位移量是推導的，沒有量過；第三個螢幕接在縮放螢幕之後時，原點會不會也移動，未知。
- **舊版存的視窗版面檔要重存**：`save_window_layout` 改存 `GetWindowRect`，舊檔還原會偏右 7 px、縮小 14×7 px。
- **真的 Win32 行為沒有實測**：`post_key` 在真的編輯框是否只出現一個字、DWM cloak 過濾掉的是哪些視窗、
  `MoveWindow` 對最大化視窗與另一個 DPI 的螢幕是否能原樣還原，都只用假的 `user32` 驗過。
- **X11／Wayland**：大寫與 Shift 標點的判斷假設 `keysym_to_keycode` 把大寫字母對到小寫的 keycode，沒有對著 X server 跑過。

**還沒決定的小事**：Windows 鍵表沒有 `slash` 這個名字。`plus`／`minus`／`comma`／`period` 與 `oem_1`…`oem_8` 都有，
但鍵表的註解刻意不替 `oem_*` 取好讀的別名，因為它們隨鍵盤配置而變（`oem_2` 只有在美式配置上是 `/`）。
要加的話是 `wrapper/_platform_windows.py` 的 `keyboard_key_aliases` 一行。

**MCP 的 `_show_command`**（`utils/mcp_server/tools/_handlers_system.py`，`window_minimize` 等）仍不看 `show_window` 的新回傳值。

---

## macOS 的修正只對著假的 Quartz 驗過

`TODO` — 要一台真的 Mac（Retina，最好接第二個螢幕）；CI 的 macos-14 能跑其中一部分

U-20261009-06 與 -04 改了四件事，全部在 Windows 上以假的 pyobjc／Quartz 物件測試：

- **`click_mouse(clicks=2)`**：按下與放開現在帶 `kCGMouseEventClickState`（第 n 次點擊是 n）。應用程式是否因此認得雙擊，沒看過。
  `test_osx_mouse_click_state.py` 有三個只在 darwin 跑的測試會把欄位讀回來，第一次執行在 CI。
- **還原最小化視窗**：`_info_for` 改用 `kCGWindowListOptionIncludingWindow`，`list_windows` 會附上最小化的視窗。
  `test_window_backend_macos_real.py` 會在 macOS CI 真的開一個視窗、最小化、列出、還原，**從沒執行過**；
  `test_a_really_minimised_window_stays_in_the_listing` 依賴最小化視窗的 Quartz 邊界或標題仍對得上它的 AX 元素，最可能紅。
  沒加 AX 逾時，沒回應的 app 會拖慢列出；同一行程裡與最小化視窗同原點或同標題的螢幕外輔助視窗可能被誤列。
- **`grab_logical`**（`utils/monitor_layout/macos_frame.py`）：改成點座標、逐螢幕擷取後拼接。三個假設要實機確認：
  `screencapture -R` 接受含負值的全域點座標、Pillow 的 `scale_down=True` 給出點尺寸的影像、`CGDisplayBounds` 與 Quartz 滑鼠事件同一個座標空間。
  每一格要為每個螢幕各開一次 `screencapture`。

---

## 這一輪修正留下的後續

`TODO` — 各項都是 2026-10-09 那批（U-20261009-01…14）交付時明確沒做的部分

- **Intel Mac 安裝要編譯 `cryptography`**：下限拉到 50 之後 `macosx_10_9_x86_64` 沒有 wheel（探測：最新只到 48.0.1），
  `pip install je_auto_control` 在 Intel Mac 需要 Rust 工具鏈。沒有在 Intel Mac 上實際編過。
- **簽章分離擋不住能寫檔的人**：能執行寫檔指令（shell、檔案類指令）的人仍能換掉公鑰檔本身，保護那個檔是作業系統權限的事；
  私鑰是未加密的 PEM（0600，Windows 上沒驗權限位元），沒有通行碼選項；遷移模式開著時 HMAC 簽章會被接受。
  強制簽章經 socket／REST／MCP 的端到端沒有跑過，覆蓋的是共用的 `read_executable_action_json` 與指令本身。
- **RBAC**（`JE_AUTOCONTROL_RBAC_USERS`，預設關閉）：
  - 延後執行的工作不帶角色：operator 註冊的排程、觸發器、熱鍵、watchdog 之後執行時沒有身分，裡面的特權指令不會被擋。
  - 使用者只能用 Python 管（`UserStore.add_user/set_role/rotate_token/remove_user`），沒有 `AC_*`、CLI 或 GUI；`Capability.MANAGE_USERS` 因此沒有任何路由或工具對應。
  - `gui/rest_api_tab.py` 仍顯示共用 token，RBAC 開啟後那個 token 會被拒絕。
  - viewer 拿得到所有標成唯讀的工具，包括 `ac_sql_query`、`ac_load_dotenv`、`ac_get_clipboard`、`ac_jwt_encode`，沒有重新分類。
  - 只實作 `check()` 的自製 REST gate 現在會 `AttributeError`（要有 `authenticate()`）。
  - 沒對真的 client（Claude Desktop、VS Code、內建 dashboard）試過；SSE、無狀態與 `subscriptions/listen` 路徑、TLS 加 RBAC 沒有測試。
- **MCP 路徑根目錄**（`JE_AUTOCONTROL_MCP_PATH_ROOTS`，預設關閉）管不到的參數：執行動作清單的工具、
  有時才是路徑的參數（`ac_open_path`／`ac_plan_open`／`ac_file_association`／`ac_act_in_view` 的 `target`，`ac_launch_process`／`ac_shell` 的 `argv`／`command`）、
  `ac_handle_file_dialog` 的 `path`、自由格式物件裡的路徑（`ac_run_suite` 的 `spec`、`ac_run_dag` 的 `definition`、`ac_assert_all` 的 `specs`）、沒標註的外掛工具。
  檔案 symlink 的跳脫在這台機器上建不出來（只跑了目錄 junction）；POSIX 的 `:` 分隔與 `~` 沒在 Linux／macOS 跑。
  `roots/list` 來的根目錄要另外開 `JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT` 才算數——這是實作時定的，請維護者確認。
- **USB passthrough**：client 仍在 `reply_timeout_s`（10 秒）放棄，即使呼叫端要的 `timeout_ms` 更長（host 接受到 60 秒）；
  對新 host 逾時已經無害，對舊 host 正常使用就會進入「需重連」。通道層的 ERROR（passthrough 關閉、bad frame、host 沒有 session）在 session 之前送出、不帶請求編號，
  呼叫仍是等到逾時。沒對真的舊版 host、真的 WebRTC 通道或真的 USB 裝置跑過。
- **變數範圍**：`je_auto_control run --dry-run --var`、observer 回呼（`AC_observe_add` 與 MCP 的 observe bridge）、
  `utils/llm/planner.py` 與狀態機預設 runner 仍用行程層級的範圍。排程／觸發／熱鍵／webhook／e-mail 的隔離是在 `run_counting_failures` 測的，沒有把每個 daemon 真的觸發一次。
  free-threaded 版（執行緒繼承 context）上，一次執行裡另開的執行緒會看到該次執行的範圍，沒測。
- **遠端桌面的擁有者模型**：Quick Connect 沒有狀態列，它的連線被取代時視窗只是關掉；主機的 Stop 會停任何擁有者開的 host（刻意的）；
  只用假的 viewer／host 測過，真的 viewer 被擠掉時會不會觸發 `on_error` 而多跳一個警告框，沒看過。
- **套件閘門**：`execute_action` 會先驗完所有指令名稱才執行，所以「載入套件」與「用它的指令」寫在同一份清單裡會以 unknown command 失敗，與閘門無關（既有限制）。
  repo 根目錄的舊範例 `AutoControl/keyword/keyword1.json` 載入 `time`，現在預設會被拒絕。
- **`pytest --cov` 沒有重新量過**：進入點搬到 `je_auto_control_pytest` 之後，它是否還少算，未知；規則仍是 `coverage run -m pytest`。
- **快到 750 行上限的檔案**：`utils/usb/passthrough/viewer_client.py`（748）、`gui/remote_desktop/connection_screen.py`（729）、
  `utils/mcp_server/server.py`（734）、`utils/mcp_server/http_transport.py`（727）、`utils/agent/backends/anthropic_computer_use.py`（723）——下一次要加東西就得先拆。
- **Sphinx 沒有建置過**：這批改了 35 個 `.rst`，都沒有渲染檢查。

---

## Computer use 的預設還是 beta 的 `computer_20251124`

`TODO` — 在 `claude-opus-5`（兩種形式都接受）上實測 GA toolset 後，把它設成所有模型的預設

`utils/agent/backends/anthropic_computer_use.py` 已支援 `computer_toolset_20260801`（`_computer_toolset.py`：成員名即動作、
一回合多個呼叫逐一執行後一次回覆、每個 `tool_result` 帶 `toolset_name`、截圖縮到高解析度層級的 2576 px／4784 visual tokens 內並換算座標、`zoom` 以全解析度裁切回覆），
`claude-opus-5-5` 自動使用它；其他模型仍預設 beta 形式，因為 toolset 只以假 client 測過、還沒對真的 API 跑過。

**附帶**：`AC_run_agent` 現在預設只提供一組聚焦的 computer-use 工具，OpenAI 不再收到整個命令目錄；需要更大的工具集時，應由應用程式明確用 `export_openai_tools(only=[...])` 建立 agent。

---


## libei 的 `ei_unref` 在半開交握上會 SIGSEGV

`BLOCKED` — 上游（libei 1.3.901）

`linux_wayland/libei.py` 的 `_teardown` **刻意每個行程漏一個 context 與一個 fd**，
因為對一個還沒完成交握的 handle 呼叫 `ei_unref` 會直接 SIGSEGV。
這是在驅動使用者桌面的函式庫裡的 crash，所以寧可漏也不能當。

**這條本來就該在這裡。** 兩支 verify 腳本都會印 `*** REVISIT ***` 並叫讀者
來翻 `Progress.md`，而這裡一直什麼都沒寫：

- `docker/libei_verify.py`：「The workaround in `LibeiBackend._teardown` can probably go」
- `docker/eis_verify.py`：「`ei_unref` now SEGFAULTS on a live context too」

重驗方式就是跑那兩支腳本（`eis-verification` job 已經在跑）；哪天 banner 不再
出現，就把 `_teardown` 的迴避拿掉。形狀與 arm64 那條一樣：卡上游、有一行重驗。

---

## Agent 的歷史壓縮還沒對真的 API 跑過

`TODO` — 需要付費實機跑一次多步驟任務；離線測試只驗得到請求的形狀

U-20261009-11 之後，Anthropic 的兩條路徑（`anthropic.py`、`anthropic_computer_use.py` 的 beta 與 GA toolset）不再改寫已送出的回合：
截圖超過 3 張（或 base64 超過 20,000,000 字元）時，以一則「目標＋已執行的動作」摘要加最新截圖開新對話。OpenAI 後端照舊就地修剪。
假 client 驗到的是：前綴只增不改、重開後只有一則 `[image, text]`、沒有孤兒 `tool_result`、沒有重播 thinking。沒驗到的：

- 重開的歷史在強制 thinking 綁定的帳號（Opus 5.5／Fable 5.1）上是否被接受。
- 模型只憑摘要能不能接著做——上限是 3，大約每 3 張截圖就壓縮一次，摘要最多列最新 60 個動作、每個截到 240 字元。
- 真的桌面 PNG 的請求大小離 32 MB 多遠。
- 兩個後端都沒送 `cache_control`，所以現在本來就沒有 prompt cache；要開的話是另一個請求形狀的改動。

---

## `test_usb_acl_prompt.py` 讓 Python 3.10 的 headless 測試間歇 segfault

`TODO` — `test/unit_test/headless/test_usb_acl_prompt.py::test_bridge_remember_persists_acl_rule` 在 `coverage run -m pytest` 下讓行程 SIGSEGV（exit 139），整個 `pytest-headless` job 因此失敗：2026-09-26 連續三次 AutoControl Code Quality（ubuntu-22.04／3.10），2026-09-30 一次（macos-14／3.10），2026-10-08 一次（ubuntu-22.04／3.10，PR #501，重跑該 job 後通過）；同一次其他版本都過，之後的 run 又過，所以是間歇的。原因還沒查：先在 3.10 開 `faulthandler` 重跑這一支，看崩在哪個原生呼叫。

---


# Progress

## 跨平台與 GUI 全面改版

`WIP` — 計畫 A–H 的程式都已交付（A 在 U-20261009-01…14，B–H 在 U-20261009-15…26，留下的缺口在 U-20261009-27…32）；還沒做到的是**實機驗證**、要維護者決定的幾件事，與下面各節列的少數缺口

核准設計：[跨平台自動化與 GUI 改版](docs/superpowers/specs/2026-10-02-platform-gui-modernization-design.md)。
實作計畫：[分階段交付計畫](docs/superpowers/plans/2026-10-02-modernization-index.md)。
這一批幾乎全部只對假後端測試：沒有在真的桌面打字或點擊、沒有 Mac、沒有 Linux 桌面、沒有 Android／iOS 裝置、沒有真的 MCP client、
沒有對付費 API 送過請求。每一節寫的是該領域還缺什麼證據或功能。

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
| `PySide6==6.11.1` | 有 | `[gui]` extra 在 arm64 上裝得起來（量的時候 extra 還含 `qt-material==2.17`，2026-10-09 已移除）。 |
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

### 2026-10-09 加進來、還沒在 Linux 上跑過的（U-20261009-21）

能力狀態機（`wrapper/capabilities.py`）、授權記錄（`linux_wayland/authorisation.py`）、實體事件讀取與停止快捷鍵（`input_events.py`、`global_shortcuts.py`）、
選用的 libei helper 行程（`JE_AUTOCONTROL_WAYLAND_EI_WORKER=1`，預設關閉）都是在 Windows 上對假物件寫的。要看 CI 的 `portal-verification`、
`eis-verification`、`wayland-verification` 三個 job 的輸出（新增的都是 `info` 行，不改變 job 的結果）：

2026-10-09 在 #510 的 CI 第一次對真的函式庫跑過，結果：

- **同意被拒絕**：真的 liboeffis 回的是 `Portal denied Start`，規則認得。第一版規則只看有沒有 "denied"，把「portal 不給 EIS descriptor」
  （`Error calling ConnectToEIS: Permission denied`）也當成使用者拒絕；`portal-verification` 的 `*** REVISIT ***` 抓到，已改成只認 `Portal denied …` 開頭。
  修正後同一個 job 再跑一次，六種結束方式的分類全部正確、沒有 `REVISIT`（20/20）。同意對話框放著不回答（逾時）仍會退回 ydotool。
- **helper 行程對真的 EIS server 可用**：按鍵、絕對移動、按鈕、捲動都到達，與行程內路徑相同；延遲中位數 0.340 ms（行程內 0.096 ms），p95 0.393 ms。
  正常關閉時按住的鍵會先放開；helper 被 SIGKILL 時 server 沒收到 key-up，放開交給合成器。
- **半開交握**：崩潰確定是 `ei_unref`；3 次半開交握行程內漏 9 個 fd，經 helper 漏 3 個，helper 都以 exit status 1 結束、沒有殘留行程。
  既有的真實函式庫檢查（20/20）在改過的 `oeffis.py`／`libei.py`／`_select_input.py`／`portal.py` 上仍然通過。

還沒有實證的：

- 沒有任何腳本從 server 端切斷一個連線中的 client，所以 `EI_EVENT_DISCONNECT` 對應到 `revoked` 沒有實證。
- helper：SIGTERM 時放開按鍵、經 portal（fd 路徑）而非 socket 路徑，沒有 job 會跑到。
- `compositor_identity`、uinput／藍牙裝置在 sysfs 的位置、`struct input_event` 的配置、GlobalShortcuts 的線上格式與哪些桌面有實作、XWayland 的可及範圍：
  都只有 `test/manual_test/wayland_authorisation_checklist.md` 的人工步驟，**沒有執行過**。
- `record.py`／`listener.py` 仍然丟 `NotImplementedError`（既有測試要求），`PhysicalRecorder` 沒有接到 `record()`。

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

---

## macOS 的修正：CI 驗到一半，其餘要一台真的 Mac

`TODO` — 要一台真的 Mac（Retina，最好接第二個螢幕）

U-20261009-06 與 -04 的 macOS 部分是在 Windows 上對假的 pyobjc／Quartz 寫的。2026-10-09 在 CI 的 macos-14（3.10 與 3.14）跑過的：

- **還原最小化視窗**：`test_window_backend_macos_real.py` 的兩個測試（真的開視窗、最小化、以 id 查、列出、還原）通過。
  第一次執行時是紅的：`kCGWindowListOptionIncludingWindow` 以 id 查不到同一行程剛最小化的視窗，`_info_for` 因此加了以完整清單查找的後備路徑。
- **點擊次數欄位**：`test_osx_mouse_click_state.py` 的 darwin 專屬測試通過——真的 Quartz 事件會保存寫進去的 `kCGMouseEventClickState`，`doubleClickInterval()` 是正數。

還沒驗的：

- **應用程式是否把 `click_mouse(clicks=2)` 認成雙擊**：只確認了欄位的值，沒有對真的應用程式送事件。
- **`grab_logical`**（`utils/monitor_layout/macos_frame.py`，點座標、逐螢幕擷取後拼接）完全沒在 macOS 跑過。三個假設要實機確認：
  `screencapture -R` 接受含負值的全域點座標、Pillow 的 `scale_down=True` 給出點尺寸的影像、`CGDisplayBounds` 與 Quartz 滑鼠事件同一個座標空間。
  每一格要為每個螢幕各開一次 `screencapture`。CI 的 runner 是 1x 單螢幕，測不到 Retina 與副螢幕。
- **`list_windows` 在真的桌面上的成本與誤列**：沒加 AX 逾時，沒回應的 app 會拖慢列出；同一行程裡與最小化視窗同原點或同標題的螢幕外輔助視窗可能被誤列。

---

## 安全與伺服器：留下的缺口

`TODO` — U-20261009-29、-30 之後還開著的

**要維護者過目或決定的：**

- `utils/rbac/policy.py` 的 `DATA_TOOLS`（42 個需要 `read_data` 的工具）是實作時分的類；刻意留在 `read_screen` 的有
  `ac_list_run_history`、`ac_costs_*`、`ac_trace_export`、`ac_self_heal_log_list`、`ac_usb_acl_list`、`ac_vlm_locate`／`ac_self_heal_locate`（會花 VLM 費用）。
- Script Builder 現在永遠不顯示 `AC_user_add`／`AC_user_rotate_token` 回傳的 token（要從 Users 群組、CLI 或腳本取得）。
- 唯讀模式現在在三種工具模式都強制執行，而外掛工具一律被登記成會變更的：**唯讀的 MCP server 不會執行任何外掛工具**。要不要讓外掛宣告自己唯讀。
- `UsbAcl(path, default_policy="allow")` 遇到被竄改的檔案會回報 `integrity_ok False`，但 `decide()` 仍回 allow（早於這批修改；倉庫內的呼叫端都用預設的 deny）。
- 設定同步：一台裝置加入「已經有內容」的 bucket 時仍會多提交一個 revision（這個登記是之後的刪除會等它的依據；要拿掉是 `merge.awaits_ack` 的一行，代價是那個保證）。

**還沒做的：**

- **Intel Mac 安裝要編譯 `cryptography`**（下限 50 沒有 `macosx_10_9_x86_64` wheel），沒有在 Intel Mac 上實際編過。
- **簽章**：能執行寫檔指令的人仍能換掉公鑰檔本身；遷移模式開著時 HMAC 簽章會被接受。Windows 上新建的私鑰檔只有目前使用者可讀
  （SYSTEM、Administrators、備份代理因此讀不到），沒在 FAT／網路磁碟或提權帳號下試過；POSIX 的權限位元檢查在這台機器上是跳過的。
- **RBAC**：observer 的 predicate 仍不帶身分（只讀螢幕）；`AC_llm_run` 沒有 `owner` 參數；沒對真的 client（Claude Desktop、VS Code、內建 dashboard）試過。
  MCP HTTP 的 `list_changed` 廣播遇到停住的 client，會讓註冊的執行緒在每條串流上最多等 30 秒。
- **MCP 路徑根目錄**管不到的：執行動作清單的工具、自由格式物件裡的路徑、沒標註的外掛工具、`ac_launch_process` 的 `argv` 與 `ac_shell` 的 `command`（刻意不管）。
  `path-or-other` 有已知的誤判：開了根目錄時，像 `/help` 這種文字目標或剛好對到根目錄外既有檔案的值會被拒絕。
  檔案 symlink 的跳脫在這台機器上建不出來；POSIX 的 `file:` URL、`:` 分隔與 `~` 沒在 Linux／macOS 跑。
- **MCP 漸進揭露**：沒對任何真的 client 跑過；`tools/list` 的分頁游標與 `-32602` 是憑對規格的記憶寫的。
- **USB passthrough**：沒對真的舊版 host、真的 WebRTC 通道或真的 USB 裝置跑過。`usb_acl.json` 改成單一檔案（簽章內嵌）之後，**舊版讀不了新檔、會全部拒絕**；
  沒有對真的舊版安裝做過降版測試。
- **設定同步**：
  - 沒有做過真的兩台機器同步；CI 新加的 `[signaling]` 安裝行與版本 pin 還沒在任何 runner 上跑過。
  - 過渡期風險：墓碑只等已經列在 `peers` 底下的裝置，所以每台機器都要先用這一版同步一次，之後才能有人刪東西。
  - `ConfigBucket.upsert` 不帶 `origin=` 時現在存的是帶版本的項目，直接讀 `bucket.sections[s][id]["field"]` 的程式會壞（`bucket.values(section)` 兩種形狀都能讀）。
  - 沒有自動的剪貼簿轉送，所以 `automatic=True`（`ClipboardEchoGuard.should_send`）在產品裡沒有呼叫端。
  - 上傳超過伺服器上限的 blob 時，伺服器依宣告長度回 413 就關閉連線；還在送 body 的 client 可能先看到連線被重設（Windows 的 CI 上發生過），
    回報的就是連線錯誤而不是「太大」。`HttpAssetTransport` 沒有先問上限。
  - 資料夾鏡像靠修改時間判斷變更：對方送來的檔案落地後，同一個時間刻度內的本機編輯不會被推送（CI 上的測試因此要把 mtime 往後推）。
  - blob：沒有自動回收（只有 `DELETE` 與用量清單）；配額是單一行程內的鎖，兩個 server 行程共用一個資料夾時可能超出一個 blob。
  - Config Sync 分頁沒有區段選擇與 `assets_server` 開關；`examples/29_config_sync.py` 還是從 `utils.config_sync` 匯入而不是門面。

---

## 動作日誌、候選腳本與自愈量測：留下的缺口

`TODO` — U-20261009-31 之後還開著的

- 完全比對的秘密遮蔽有三個限制：日誌開始之前就解出的值它不知道；短於 4 個字元的值不比對；應用程式變形後回顯的值只靠樣式規則。
- Robot 輸出的檢查是自己寫的結構檢查，**不是 Robot 的 parser**，沒和 `robot --dryrun` 對過（`robotframework` 沒安裝）。
- 沒量過日誌在真的執行上的負擔；沒試過多個行程寫同一個日誌檔；`artifacts` 的 mtime 規則（2 秒寬限）只在 NTFS 上測過。
- 自愈量測：`vlm` 策略只用假的與 null 後端跑過，沒對真的 Anthropic／OpenAI 送過請求（指定真的後端會把每一格送出去、要花錢）；
  宣告式 `verify`（`image_gone`／`image_present`／`text_present`）的螢幕探測都是假的，`text_on_screen` 沒對真的 OCR 引擎跑過；
  GUI 沒有影像 diff；區域限定的樣板比對沒對真的螢幕跑過。
- 候選腳本的 diff 對話框沒有真的以 modal 執行過，也沒在螢幕上看過兩種主題。

---

## 行動裝置（Android／iOS）：完全沒有在裝置上跑過

`BLOCKED` — 需要 Android 模擬器或實機、iPhone 與 WebDriverAgent；這台機器連 `adb` 都沒有

U-20261009-18 的每一個裝置面呼叫都只對假的 ADB／uiautomator2／WDA 測過。`uiautomator2` 與 `facebook-wda` 沒有安裝在開發環境裡，
方法名稱與參數是憑記憶寫的，第一次接上真的 SDK 很可能要修：

- uiautomator2：`send_keys`、`drag`、空 selector 的 `gesture(...)`（捏合）、`clipboard`／`set_clipboard`、對話框按鈕的 resource id。
- facebook-wda：`app_launch`／`app_terminate`／`app_state`、`alert.*`、`set_clipboard`、`status()`、`orientation` 的值、元素的 `pinch`、`screenshot()` 回傳 PIL 影像。
- 旋轉方向：螢幕截圖以面板自然方向回來時，`landscape_left` 轉 270°、`landscape_right` 轉 90°，是從文件推的，沒看過。
- Android：`input draganddrop` 是否存在、`monkey` 啟動輸出、`pidof`／`pm path` 的結束碼、`dumpsys activity activities` 的格式、`pkill -INT screenrecord` 能否收尾 MP4。
  ADBKeyBoard 的送達無法由裝置確認，是從 IME 被選取推定的。
- 已知限制：iOS 捏合忽略 `x`／`y`／`span`；iOS `app_state` 不會回 `not_installed`；iOS 的安裝／檔案／錄影沒有 adapter（只有 `MobileExtension` 協定與註冊點）；
  Mobile 分頁的 probe／run 會卡住 GUI 執行緒到裝置回應或逾時。`AC_android_shell` 刻意不做成 MCP 工具，**請維護者確認**。
- 沒有 `examples/` 的實機腳本以外的 smoke；Xcode／WDA 的建置與簽章只寫成前置條件。

---

## GUI：留下的缺口

`TODO` — U-20261009-27、-28 之後還開著的

- **Accessibility 分頁的 3 個動作與 A11y Audit 仍在 GUI 執行緒上**：Windows 的 UIA 後端（`accessibility/backends/windows_backend.py`）快取一個 COM 自動化物件、
  沒有做每個執行緒的 COM 初始化；開發環境沒裝 `comtypes`，無法驗證搬到別的執行緒後還能用，所以沒有盲改。要先改後端（擁有 COM apartment 的執行緒，或每執行緒初始化）。
  **同一個原因的新風險**：從 GUI 啟動的腳本現在跑在工作執行緒上，腳本裡的 `AC_a11y_*` 會從新的執行緒呼叫 UIA，這條路徑沒有實際跑過。
- **stop 叫不醒的等待**：`AC_wait_window`、`AC_wait_text`、smart wait、`AC_expect_poll` 用的是自己的 `time.sleep`，會跑到自己的逾時；
  已經進到後端的單一指令（一次影像搜尋、OCR、HTTP 請求、shell 指令）不會被打斷。非腳本的分頁工作在後端無法取消，只是結果被丟掉。
  ChatOps 的 router 會接住 `AutoControlException`，被停止的 `/run` 回的是「run failed: ExecutionStopped …」而不是「Stopped.」。沒有 stop／list 的 MCP 工具。
- **WebRTC 停止路徑裡沒搬的**：`StatsPoller.stop()`、`_stop_adaptive`、`_stop_lan_advertise`，沒量過它們會不會卡。
- **`dispose()`**：`RemoteDesktopTab.dispose()` 只停計時器，連線中的 viewer 或 host 刻意留在 registry；`_ViewerPanel`、`QuickConnectScreen` 與 WebRTC 面板自己沒有 `dispose()`；
  只在需要時才開 worker 的分頁（computer use、DAG、VLM、USB browser）沒有。
- **切換主題後約 0.4 秒內**，被暫存的分頁其 `window()` 不是主視窗；關閉後留作隱藏子元件的分頁仍是同步重設樣式。基準（`benchmarks/gui_*.py`）CI 仍不設門檻。
- **一個沒修的隱患**：`webrtc_host_connection._produce_offer` 與 `webrtc_viewer_connection._answer_off_thread` 把工作結果接到對面板的強參照回呼上；
  沒有 parent 的面板（測試裡）會因此在孫物件的解構子裡被銷毀而中止行程。應用程式裡面板都有 parent。`SlowOp` 已改成弱參照，這兩處還沒。
- **把 Python 建的 widget 放進分頁列在結束時崩潰**：已查明觸發條件——分頁列按鈕上接了 Python callable、又有排隊中的 `deleteLater()`、而行程經 `os._exit` 離開；
  先把 deferred delete 沖掉就不會。機制（Qt 在行程結束時釋放那個 slot）是推論，沒有 C 堆疊可看。`_tab_close_icon.py` 沒有改回自訂按鈕。
- **對真實 Qt 型別的型別檢查**：`test/verify/typing_extras_exempt.txt` 列著 70 個模組（66 個在 `gui/`、4 個在 `utils/remote_desktop/`，共 711 個錯誤，
  多半是 mixin 呼叫它所混入的 widget 的方法），只准變少。
- 遠端桌面的輸入改成佇列送出後，`AC_remote_send_input` 回的 `{"sent": True}` 意思是「已排入」；`SO_SNDTIMEO` 的 POSIX 包法與經 TLS socket 的行為沒在這台機器上驗過。
- 沒在 macOS／Linux 上看過新的關閉鈕、捲動與重設樣式；沒在真的多螢幕桌面試過視窗位置還原；PyBreeze 沒有對這一版跑過；各語系新增的字串（日文、簡體中文）沒有母語者看過。

---

## 雜項

`TODO` — 小項目，各自獨立

- **`DECIDE`：`pytest --cov` 可以放行了嗎**。進入點搬到 `je_auto_control_pytest` 之後重新量過（2026-10-09）：`coverage run -m pytest` 87.35%，`pytest --cov` 87.32%。
  `CLAUDE.md` 與 `test_coverage_measurement.py` 仍規定只能用 `coverage run`；要不要放寬由維護者決定。
- **本機的共用 `.venv` 裝著 `je_auto_control_dev 0.0.136`**，它的 `pytest11` 進入點還是舊的重量級路徑；重裝即可，不影響 CI。
- **三個新的 CI job 還沒在 GitHub 上跑過**（`typing-extras`、`docs`、`free-threaded-scope`）；`free-threaded-scope` 用的是 `3.14t`，setup-python 在 Windows 上怎麼命名那個直譯器沒驗過，紅了就拿掉。
- **free-threaded**：變數範圍已修成只在綁定它的執行緒上有效，並在 3.14.8t（Windows）跑過。`rbac/authorization.py`、`self_healing/locator.py`、`wrapper/device_context.py`
  也用 `ContextVar`，在 free-threaded 版上仍會被執行緒繼承，沒有檢查。
- **能力探測**：Windows 的鎖定工作站、session 0、低完整性與擷取失敗分支只用假資料判斷；macOS 的三個 preflight 呼叫只對假物件跑過，
  pyobjc 的 `Quartz` 有沒有 `CGPreflightListenEventAccess` 未知（沒有的話 `recording`／`stop_shortcut` 回 `unknown`）。
- **Windows 的版面鍵名**（`slash` 等 8 個）只在美式配置上實際呼叫過。
- **狀態機 `on_enter` 的單一動作寫法**以前一直被拒絕、從沒執行過（已修，U-20261009-24）：依賴「它不會跑」的既有狀態機現在會跑它。

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

2026-10-09：新增選用的 helper 行程（`linux_wayland/ei_worker.py`、`ei_client.py`、`ei_transport.py`，`JE_AUTOCONTROL_WAYLAND_EI_WORKER=1`）把 libei 隔離在子行程裡，
**預設關閉，原本的行程內路徑與刻意的洩漏沒有動**。兩支 verify 腳本現在會分類 teardown 並量 helper 的延遲與洩漏；要等 CI 的輸出才知道 helper 是否真的可用。

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

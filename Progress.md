# Progress

## 跨平台與 GUI 全面改版

`TODO` — 重設 UI、重寫並優化 GUI、修正 Wayland 與函式庫問題、跨機器同步、
深化全套 mypy、補齊 iOS／Android、MCP 逐步揭露、自愈定位器量測、動作日誌 codegen、
完整範例與文件。涉及 `gui/`、`linux_wayland/`、`android/`、`ios/`、
`utils/{config_sync,remote_desktop,mcp_server,self_healing,codegen,executor}/` 與型別／文件驗證。
核准設計：[跨平台自動化與 GUI 改版](docs/superpowers/specs/2026-10-02-platform-gui-modernization-design.md)。
實作計畫：[分階段交付計畫](docs/superpowers/plans/2026-10-02-modernization-index.md)，待審閱。
現有 `[Answer]` 決策沿用。

`TODO` — 真機與付費 API 驗收暫緩，待明確恢復後執行；其餘目前缺環境的實驗先略過，相關項目保留未驗證。

`WIP` — 改版仍缺以下內容；原生平台與正式環境驗收缺口另列於後。
計畫 D1 仍缺 portal session 關閉／恢復、compositor 重啟的狀態與原生驗收、
擷取結果與擁有者 context 的接合，以及原生 session 的重試／取消／停止控制。
D2 仍缺 helper 隔離與半開交握資源回收；D3 的錄製／全域停止／Windows 原生崩潰證據仍缺，詳見計畫與下方生命週期待辦。
計畫 E（Android／iOS）、G（MCP 逐步揭露）、H（型別深化與總驗收）尚未開始。F 還缺：

- **Remote Desktop 與 Script Builder 仍在啟動時建立**（預設開啟），啟動時間 2.6–2.7 秒裡大半是它們與門面匯入。
- **F1 的遺留面板釋放**：擁有者直接建立的核心表單與 Remote Desktop 在關閉時仍保留 widget；需隨 F3 遷移直接控制項引用、執行中工作與連線生命週期，再啟用銷毀。
- **F2 其餘**：計畫指定的 `WorkspaceShell` 介面、右側可收合詳情，以及各面板的空白／錯誤／permission states 還沒全面交付。
- **F3** 還缺共用 `TaskController` 接入其餘面板、backend timeout／cancel 傳遞與關閉生命週期遷移，
  以及 `webrtc_panel.py` 的 dialog／worker／session 拆分。
- **F4**（啟動／記憶體基準、mixed-DPI、功能對等測試）尚未開始。
- **F3 Windows 原生釋放驗收**：`test/unit_test/headless/test_remote_desktop_host_id.py` 的 freed-thread-state abort 尚缺 Windows 原生堆疊與獨立根因確認。

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
行數以 `len(text.splitlines())` 量測；檔案縮短時，上限跟著往下走。
**這張表現在有測試在守**：`test/unit_test/headless/test_file_length_budget.py` 比對本表與樹，
超標未列、列上的檔案變長、或已經縮到線內卻還留著的列，都會紅。

| 檔案 | 行數 | 為何還沒拆 |
| --- | ---: | --- |
| `utils/mcp_server/tools/_handlers_executor_bridge.py` | 1,429 | 純委派函式（函式內匯入後立即轉呼叫，沒有分支），不適用 flat data tables 豁免。需先定義領域邊界再拆分。 |
| `gui/remote_desktop/webrtc_panel.py` | 2,488 | 單一 Qt 面板,但已含連線、監視器選擇、頻寬自適應、麥克風、錄影五組互動狀態。應拆成 panel + 各控制器。 |
| `utils/accessibility/backends/windows_backend.py` | 805 | 剩餘 UIA COM 生命週期管理仍需保留 `CoInitialize`／介面釋放的配對；拆分前須建立這些配對的回歸。 |

**本質豁免（flat data tables）**：`utils/mcp_server/tools/_factories.py`、
`utils/executor/action_executor.py`、`gui/script_builder/command_schema.py`、
`je_auto_control/__init__.py` 與
`gui/language_wrapper/{english,japanese,traditional_chinese,simplified_chinese}.py` 語系字串表。

## Windows arm64:裝得起來了，但少了影像與加密

`TODO` — 上游仍未發 wheel（`opencv-python`、`cryptography`），但安裝本身不再是卡點

### 還沒有答案的：Windows arm64 上這些功能不能用

裝得起來不等於功能齊。該平台上以下四組會拋帶提示的錯誤，而不是默默失效：

| 功能 | 缺的是 | 錯誤形式 |
| --- | --- | --- |
| 影像比對、截圖轉 BGR、螢幕錄影 | `opencv-python`／`je_open_cv` | `utils/cv2_utils/optional.py` 的 `require_cv2()`／`require_je_open_cv()` 拋 `RuntimeError` |
| 動作檔加密與 Ed25519 簽章（`action_signing`） | `cryptography` | 拋 `CryptographyUnavailableError`（也是 `RuntimeError`；HMAC 簽章不受影響） |
| 秘密金庫（`${secrets.NAME}`） | `cryptography` | 同上 |
| ACME／TLS 發證、加密錄影 | `cryptography` | 模組層 `ImportError` 轉述（照 `webrtc_transport` 慣例） |

`BLOCKED` — 仍需相容的上游 wheel：`opencv-python>=4.8,<6`、
`cryptography>=50.0.0` 與 `aiortc` 的傳遞相依 `google-crc32c`。
不能為相容性降低 cryptography 安全下限。上游提供相容版本後，需重驗安裝與功能，
再移除 `pyproject.toml` 中相應平台標記並同步更新
`test/unit_test/headless/test_arm64_dependency_markers.py`。

重驗指令（不需要 arm64 機器，也不需要 runner）：

```bash
pip install --dry-run --only-binary=:all: --platform win_arm64 --python-version 3.12 --target /tmp/probe 'opencv-python>=4.8,<6' 'cryptography>=50.0.0'
```

重驗通過後，需調整相應環境標記與 `test_arm64_dependency_markers.py`，保留安全下限。

注意一個驗證上的陷阱：**`pip --platform` 不會換掉 marker 的評估環境**，
它只影響 wheel 相容性標籤，所以拿本機做 `--dry-run` **驗不到標記的效果**（兩個
套件依舊會被要求）。能驗的是兩件事：直接評估 marker（上面那支測試在做的），
以及 `windows-11-arm` 那一格自己綠。

## Wayland 生命週期與驗收

`TODO` — 下列上游行為與原生桌面互動仍需驗證。

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

---

## 輸入、視窗與擷取修正：還沒在真的桌面與 Jeffrey_RPA 上驗過

`TODO` — 原生桌面與正式批次升級前的行為驗收暫緩。

- **正式批次升級前的桌面行為驗收**：需核對 `_gui_control.py` 對下列行為的實際依賴：
  `write()` 大寫與 `is_shift` 在 Windows／X11 生效、`"\r\n"` 只按一次 Enter、`mouse_scroll` 預設方向改為 `scroll_up`
  （X11／Wayland 上 `mouse_scroll(3)` 由往下變往上）、小數座標四捨五入、`focus_window` 在 Windows 沒拿到前景會丟例外、
  `list_windows` 不再列出 DWM cloak 與零面積視窗、`post_key` 對可列印字元只送 `WM_CHAR`。
- **混合 DPI 座標與樣板**：需實測各螢幕上的舊版座標、`screen_region`、視窗版面與樣板，
  包含縮放不同的副螢幕、負原點與多螢幕排列；必要時重新錄製，不能以推導代替驗收。
- **舊版存的視窗版面檔要重存**：`save_window_layout` 改存 `GetWindowRect`，舊檔還原會偏右 7 px、縮小 14×7 px。
- **真的 Win32 行為沒有實測**：`post_key` 在真的編輯框是否只出現一個字、DWM cloak 過濾掉的是哪些視窗、
  `MoveWindow` 對最大化視窗與另一個 DPI 的螢幕是否能原樣還原，都只用假的 `user32` 驗過。
- **X11／Wayland**：大寫與 Shift 標點的判斷假設 `keysym_to_keycode` 把大寫字母對到小寫的 keycode，沒有對著 X server 跑過。

**還沒決定的小事**：Windows 鍵表沒有 `slash` 這個名字。`plus`／`minus`／`comma`／`period` 與 `oem_1`…`oem_8` 都有，
但鍵表的註解刻意不替 `oem_*` 取好讀的別名，因為它們隨鍵盤配置而變（`oem_2` 只有在美式配置上是 `/`）。
要加的話是 `wrapper/_platform_windows.py` 的 `keyboard_key_aliases` 一行。

---

## macOS 的修正：CI 驗到一半，其餘要一台真的 Mac

`TODO` — 要一台真的 Mac（Retina，最好接第二個螢幕）

還沒驗的：

- **應用程式是否把 `click_mouse(clicks=2)` 認成雙擊**：只確認了欄位的值，沒有對真的應用程式送事件。
- **`grab_logical`**（`utils/monitor_layout/macos_frame.py`，點座標、逐螢幕擷取後拼接）完全沒在 macOS 跑過。三個假設要實機確認：
  `screencapture -R` 接受含負值的全域點座標、Pillow 的 `scale_down=True` 給出點尺寸的影像、`CGDisplayBounds` 與 Quartz 滑鼠事件同一個座標空間。
  每一格要為每個螢幕各開一次 `screencapture`。CI 的 runner 是 1x 單螢幕，測不到 Retina 與副螢幕。
- **`list_windows` 在真的桌面上的成本與誤列**：沒加 AX 逾時，沒回應的 app 會拖慢列出；同一行程裡與最小化視窗同原點或同標題的螢幕外輔助視窗可能被誤列。

---

## 這一輪修正留下的後續

`TODO` — 下列整合、安全與平台驗證仍未完成。

- **Intel Mac 安裝要編譯 `cryptography`**：下限拉到 50 之後 `macosx_10_9_x86_64` 沒有 wheel（探測：最新只到 48.0.1），
  `pip install je_auto_control` 在 Intel Mac 需要 Rust 工具鏈。沒有在 Intel Mac 上實際編過。
- **簽章分離擋不住能寫檔的人**：能執行寫檔指令（shell、檔案類指令）的人仍能換掉公鑰檔本身，保護那個檔是作業系統權限的事；
  私鑰是未加密的 PEM（0600，Windows 上沒驗權限位元），沒有通行碼選項；遷移模式開著時 HMAC 簽章會被接受。
  強制簽章經 socket／REST／MCP 的端到端沒有跑過，覆蓋的是共用的 `read_executable_action_json` 與指令本身。
- **RBAC**（`JE_AUTOCONTROL_RBAC_USERS`，預設關閉）：
  - 使用者只能用 Python 管（`UserStore.add_user/set_role/rotate_token/remove_user`），沒有 `AC_*`、CLI 或 GUI；`Capability.MANAGE_USERS` 因此沒有任何路由或工具對應。
  - viewer 的其餘影像檔案型、mobile 與外掛唯讀工具仍需全面盤點 capability；自製工具仍依提示採預設分類。
  - 沒對真的 client（Claude Desktop、VS Code、內建 dashboard）試過；SSE、無狀態與 `subscriptions/listen` 路徑、TLS 加 RBAC 沒有測試。
- **MCP 路徑根目錄**（`JE_AUTOCONTROL_MCP_PATH_ROOTS`，預設關閉）管不到的參數：執行動作清單的工具、
  有時才是路徑的參數（`ac_open_path`／`ac_plan_open`／`ac_file_association`／`ac_act_in_view` 的 `target`，`ac_launch_process`／`ac_shell` 的 `argv`／`command`）、
  `ac_handle_file_dialog` 的 `path`、自由格式物件裡的路徑（`ac_run_suite` 的 `spec`、`ac_run_dag` 的 `definition`、`ac_assert_all` 的 `specs`）、沒標註的外掛工具。
  檔案 symlink 的跳脫在這台機器上建不出來（只跑了目錄 junction）；POSIX 的 `:` 分隔與 `~` 沒在 Linux／macOS 跑。
  `roots/list` 來的根目錄要另外開 `JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT` 才算數——這是實作時定的，請維護者確認。
- **USB passthrough**：client 仍在 `reply_timeout_s`（10 秒）放棄，即使呼叫端要的 `timeout_ms` 更長（host 接受到 60 秒）；
  對新 host 逾時已經無害，對舊 host 正常使用就會進入「需重連」。通道層的 ERROR（passthrough 關閉、bad frame、host 沒有 session）在 session 之前送出、不帶請求編號，
  呼叫仍是等到逾時。沒對真的舊版 host、真的 WebRTC 通道或真的 USB 裝置跑過。
- **變數範圍**：free-threaded 原生執行緒繼承與同時存取範圍的行為尚未實測。
- **遠端桌面的擁有者模型**：Quick Connect 沒有狀態列，它的連線被取代時視窗只是關掉；主機的 Stop 會停任何擁有者開的 host（刻意的）；
  只用假的 viewer／host 測過，真的 viewer 被擠掉時會不會觸發 `on_error` 而多跳一個警告框，沒看過。
- **套件閘門**：`execute_action` 會先驗完所有指令名稱才執行，所以「載入套件」與「用它的指令」寫在同一份清單裡會以 unknown command 失敗，與閘門無關（既有限制）。
  repo 根目錄的舊範例 `AutoControl/keyword/keyword1.json` 載入 `time`，現在預設會被拒絕。
- **`pytest --cov` 沒有重新量過**：進入點搬到 `je_auto_control_pytest` 之後，它是否還少算，未知；規則仍是 `coverage run -m pytest`。
- **快到 750 行上限的檔案**：`utils/usb/passthrough/viewer_client.py`（748）、`gui/remote_desktop/connection_screen.py`（729）、
  `utils/mcp_server/server.py`（734）、`utils/mcp_server/http_transport.py`（727）、`utils/agent/backends/anthropic_computer_use.py`（723）——下一次要加東西就得先拆。

---

## Computer use 的預設還是 beta 的 `computer_20251124`

`TODO` — 在 `claude-opus-5`（兩種形式都接受）上實測 GA toolset 後，把它設成所有模型的預設

驗收入口：`utils/agent/backends/anthropic_computer_use.py` 與 `_computer_toolset.py`。
需驗證多呼叫回覆、toolset 名稱、截圖尺寸、座標換算與 zoom；未取得真實 API 證據前，
其他模型的預設切換仍待完成。

---

## libei 半開交握的資源隔離尚未完成

`TODO` — D2 helper 隔離；不能直接移除 `linux_wayland/libei.py::_teardown` 的半開保護。

需依 D2 計畫把原生配置、portal／交握、事件送出與 teardown 放進擁有的 helper，
補上有界 IPC、request ID、逾時與取消，以及 parent close／reap。
半開交握失敗仍會留下 context／fd；直接重複建立 backend 可能重複累積，
需驗證 helper 結束後資源可回收，且取消不影響其他擁有者。
`docker/libei_verify.py` 與 `docker/eis_verify.py` 保留原生故障／成功邊界檢查；
裝置暫停與序號回讀、真實合成器權限流程仍待對應環境驗證。

---

## Agent 的歷史壓縮還沒對真的 API 跑過

`TODO` — 需要付費實機跑一次多步驟任務；離線測試只驗得到請求的形狀

需驗證 `utils/agent/backends/anthropic.py`、`anthropic_computer_use.py` 的 beta／GA 路徑，
以及 OpenAI 歷史剪裁在真實 API 上的行為：

- 重開的歷史在強制 thinking 綁定的帳號（Opus 5.5／Fable 5.1）上是否被接受。
- 模型只憑摘要能不能接著做——上限是 3，大約每 3 張截圖就壓縮一次，摘要最多列最新 60 個動作、每個截到 240 字元。
- 真的桌面 PNG 的請求大小離 32 MB 多遠。
- 兩個後端都沒送 `cache_control`，所以現在本來就沒有 prompt cache；要開的話是另一個請求形狀的改動。

---

## `test_usb_acl_prompt.py` 讓 Python 3.10 的 headless 測試間歇 segfault

`TODO` — `test/unit_test/headless/test_usb_acl_prompt.py::test_bridge_remember_persists_acl_rule`
在 Python 3.10 的 Linux／macOS `coverage run -m pytest` 中仍有間歇 SIGSEGV（exit 139）紀錄。
需在對應環境開啟 `faulthandler` 重跑並定位原生呼叫；單次重跑通過不足以證明已修復。

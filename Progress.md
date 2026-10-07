# Progress

## 跨平台與 GUI 全面改版

`WIP` — 重設 UI、重寫並優化 GUI、修正 Wayland 與函式庫問題、
深化全套 mypy、補齊 iOS／Android、MCP 逐步揭露、
完整範例與文件。涉及 `gui/`、`linux_wayland/`、`android/`、`ios/`、
`utils/{mcp_server,executor}/` 與型別／文件驗證。
核准設計：[跨平台自動化與 GUI 改版](docs/superpowers/specs/2026-10-02-platform-gui-modernization-design.md)。
實作計畫：[分階段交付計畫](docs/superpowers/plans/2026-10-02-modernization-index.md)，已核准，依序實作。
現有 `[Answer]` 決策沿用；後續交付包含 E–H 與完整整合驗收。
從 H3 接續原有計畫；不額外新增付費型功能。既有 API 介面及相關修正繼續，
目前以本機／離線測試驗證；缺少真實 API 條件的既有項目保留待驗證。
正向實體裝置擷取、GNOME/KDE 授權與鍵態恢復仍列 H3；
歷史 Qt 原生崩潰的後續追蹤仍保留在下列驗收項目。
WDA 專用 endpoint、外部 client／別名競態、未知建立回覆及 SDK 擷取後的
App session 接續／恢復仍列 H3；受控閒置檢查不能冒充原生互斥證據。
H3 的完整 coverage／跨平台 CI 驗收正在執行；原生及正式下游整合仍保留。
唯讀下游三支測試已重現 slash 遷移需求，正式 editable 安裝未變更。
H3 仍需自有錄製的原生輸出內容、實體鍵態恢復及外部輸入 client 競態證據；
受控 GUI 所有權、重試、container 關閉與 widget 刪除不代表實體恢復或有效錄影。

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
行數為實測（`len(text.splitlines())`）；上表實測值是已核准的上限，只准變短。
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

---

## Windows arm64：上游 OpenCV／影片與安全 crypto wheel

`BLOCKED` — 進階 OpenCV／影片及安全版本 cryptography 仍缺少 Windows arm64 wheel。
上游提供 wheel 前，保留 OpenCV／je_open_cv／crypto 共用相依標記及 cryptography >=50.0.0 下限。
Windows arm64 原生 NumPy／Pillow platform smoke 仍由 H3 驗收；
wheel 解析成功及非 arm64 的替代後端測試不能當作原生執行證據。

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

## 隔離改版的下游整合驗收

`TODO` — 合併 modernization 隔離分支前，先確認 Jeffrey_RPA 的正式 editable 批次
及 Discord bot 已停止；保留目前執行中的原始碼。整合時套用
`docs/compatibility/jeffrey-rpa-oem-test-migration.patch` 更新 slash 快捷鍵測試契約，
再跑下游 `test/test_gui_facade.py`、`test/test_gui_control.py` 與
`test/test_je_facade.py`，並完成 H3 的真實平台驗收。

---

## 多機同步與遠端連線實機驗收

`TODO` — H3 需用兩台實體機器驗證設定並行編輯、離線重送、刪除與退休裝置、
資產完整性、folder／clipboard 防回送，以及 TCP／WebSocket／WebRTC 多面板獨立關閉。
保存版本、連線條件、操作順序與結果；受控 HTTP／SQLite、transport 替身及 offscreen Qt
回歸不能取代這項實機證據。

---


## Computer use 的預設還是 beta 的 `computer_20251124`

`TODO` — 在 `claude-opus-5`（兩種形式都接受）上實測 GA toolset 後，把它設成所有模型的預設

`utils/agent/backends/anthropic_computer_use.py` 已支援 `computer_toolset_20260801`（`_computer_toolset.py`：成員名即動作、
一回合多個呼叫逐一執行後一次回覆、每個 `tool_result` 帶 `toolset_name`、截圖縮到高解析度層級的 2576 px／4784 visual tokens 內並換算座標、`zoom` 以全解析度裁切回覆），
`claude-opus-5-5` 自動使用它；其他模型仍預設 beta 形式，因為 toolset 只以假 client 測過、還沒對真的 API 跑過。

**附帶**：`AC_run_agent backend="openai"` 送出全部約 740 個工具，超過 OpenAI Chat Completions 的 128 個上限，
所以一定失敗——與「`AC_run_agent` 預設工具集」那一條 DECIDE 一起決定。

---


## libei 的 `ei_unref` 在半開交握上會 SIGSEGV

`BLOCKED` — 上游（libei 1.3.901）

`linux_wayland/libei.py` 的 `_teardown` 仍須避開半開 handle 的原生 `ei_unref`。
待 `docker/libei_verify.py` 與 `docker/eis_verify.py` 的 sentinel 確認上游合法清理
不再 SIGSEGV，才能移除這項低階綁定迴避；不要在父程序呼叫已知 unsafe teardown。

---

## `AC_run_agent` 預設把每個 AC_* 指令都交給模型

`DECIDE` — 預設工具集要不要排除高風險指令

`utils/executor/action_executor.py` 的 `_run_agent` 以 `export_anthropic_tools()` / `export_openai_tools()`
不帶 `only=` 建立 backend，所以模型拿得到 `AC_shell_command`、`AC_execute_process`、`AC_android_shell`、
`AC_add_package_to_executor`、`AC_run_agent`、`AC_computer_use`、`AC_execute_action` 等指令。
2026-09-23 已讓 backend 拒絕「沒有提供的工具」，但提供的清單本身就包含這些；
螢幕上的內容（網頁、文件）若誘導模型呼叫 shell，目前不會被擋。

**做法**：`_run_agent` 預設排除上述類別，另加一個 opt-in 參數（例如 `allow_system_commands`）
讓需要的人明確打開；MCP `ac_run_agent` 與 Script Builder 的欄位同步。

**為什麼要拍板**：這會縮小既有的 agent 能力，依賴它跑 shell 的腳本會改變行為。

實測數字（2026-09-25）：預設清單有 741 個指令，含 `AC_run_agent` 本身（模型可以遞迴開 agent）；
`backend="openai"` 超過 Chat Completions 的 128 個工具上限，現在建 backend 時就明確拒絕；
Anthropic 每一步送約 202 KB 的工具 schema、沒有 `cache_control`。拍板後一併決定上限與快取。


---

## macOS 最小化視窗還原的原生驗證

`TODO` — A12 已將 `_info_for` 改為 including-window 查詢並以替身驗證 ID 還原。
仍需在已授權 Accessibility 的 macOS 上實際最小化再還原；離線替身無法證明原生 AX
匹配及 TCC 行為。本機沒有 macOS，原生證據留待 H3 平台驗收。

---

## 行動裝置原生所有權與恢復驗收

`TODO` — E1 的 frozen context、matrix 隔離、被動 metadata、逐請求逾時與取消已建立；
H3 仍需 Android emulator／實機及 remote WDA 驗證裝置可達性、授權失敗、
SDK bootstrap／retry 的整體截止時間，以及取消後實體狀態和自有 helper 回收。
E2 仍需 Unicode 焦點 round-trip、SDK IME／剪貼簿恢復、裝置旋轉後座標與 WDA W3C
雙指手勢支援的原生證據；capture 拒絕擷取中旋轉，不保證擷取後裝置不再旋轉。
不同 endpoint alias 是否指向同一實機不能由配置字串判定。保存 SDK／ADB／WDA
版本、平台與執行證據；fake SDK、受控 ADB argv 及 offscreen Qt 不代替原生驗收。

---


## Agent 付費 API 多回合驗證

`TODO` — 已實作 Anthropic append-only 與截圖上限摘要新對話，需在配置 API key 後
以一般工具、beta computer-use、GA toolset 各跑超過三張截圖的多回合 smoke，
確認 tool_result 配對、thinking 簽章及新對話不出現 400；保存模型、工具版本、回合數與結果。
2026-10-03 未配置 API key，僅核對官方 schema 與離線測試；
既有 Computer use 預設 toolset 切換仍以真實 API 結果為門檻。

---


## 混合 DPI 與 Retina 實機驗證

`TODO` — H3 需在 Windows 混合 DPI 雙螢幕及 Retina Mac（含 1x/2x 與負原點）
執行 `grab_logical`、區域／視窗截圖、定位座標及 Qt 轉換驗證，附 OS、縮放、布局與影像尺寸。
目前 2026-10-03 僅有 Windows 單一 1920×1200、100% 螢幕，無 Retina Mac；
負原點、125% Qt 與混合 Retina 的 fixtures 已通過，但不能取代上述實機驗證。

---

## `test_usb_acl_prompt.py` 讓 Python 3.10 的 headless 測試間歇 segfault

`WIP` — `test/unit_test/headless/test_usb_acl_prompt.py::test_bridge_remember_persists_acl_rule`
在 Linux／macOS Python 3.10 曾間歇 SIGSEGV。Qt 翻譯表背景 GC owner 缺陷已修正，
九個平台 pytest／coverage 目標已通過；這尚不能證明所有歷史 fault 的精確成因。
H3 仍需原生重複／壓力回歸追蹤收斂，任何再現須保存 gdb／lldb 堆疊。
既有 faulthandler 證據見
`docs/updates/2026-10.md` U-20261007-03，不能以 Windows／較新 Python 的通過取代。
本次原生 CI 另在 Linux Python 3.14 的 `test_rd_gui_audit.py` teardown／
`QApplication.allWidgets()` 捕獲 Qt/shiboken crash；需一併定位 GUI cleanup lifecycle，
不能將 debugger 捕獲測試 SIGINT 當作這些崩潰的重現。
E1 另修正有獨立 subprocess 重現的 matrix owner／relay deferred cleanup abort；
此特定回歸通過，也不能直接推論是所有歷史 Qt fault 的原因。

---

## Wayland 原生生命周期與能力驗收

`WIP` — H3 尚缺 Windows arm64 runner 的影像替代 backend 執行證據；已加入 platform smoke。
D1 的桌面授權／撤銷／XWayland scope 仍只有替身及 offscreen Qt 證據；
GNOME/KDE 的允許／拒絕、合成器重啟、裝置 pause/remove、helper crash 後
實體按鍵狀態恢復，以及 restore-token 替代接口仍需 H3 原生驗收。

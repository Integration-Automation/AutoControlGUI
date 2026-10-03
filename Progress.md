# Progress

## 跨平台與 GUI 全面改版

`WIP` — 重設 UI、重寫並優化 GUI、修正 Wayland 與函式庫問題、跨機器同步、
深化全套 mypy、補齊 iOS／Android、MCP 逐步揭露、自愈定位器量測、動作日誌 codegen、
完整範例與文件。涉及 `gui/`、`linux_wayland/`、`android/`、`ios/`、
`utils/{config_sync,remote_desktop,mcp_server,self_healing,codegen,executor}/` 與型別／文件驗證。
核准設計：[跨平台自動化與 GUI 改版](docs/superpowers/specs/2026-10-02-platform-gui-modernization-design.md)。
實作計畫：[分階段交付計畫](docs/superpowers/plans/2026-10-02-modernization-index.md)，已核准，依序實作。
現有 `[Answer]` 決策沿用；產品實作進行中。

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
| 動作檔加密（`action_signing`） | `cryptography` | `_fernet_types()` 拋 `RuntimeError`（Ed25519 簽章同樣需要 cryptography，匯入仍延遲） |
| 秘密金庫（`${secrets.NAME}`） | `cryptography` | 同上 |
| ACME／TLS 發證、加密錄影 | `cryptography` | 模組層 `ImportError` 轉述（照 `webrtc_transport` 慣例） |

這四組在 arm64 上能不能回來，**完全取決於上游**：

| 依賴 | win_arm64 | 實測（2026-08-20） |
| --- | --- | --- |
| `opencv-python>=4.8,<6` | **沒有** | 任何版本都沒有，pip 回的是 `from versions: none`。`je_open_cv` 自己是純 Python，但相依 opencv-python，所以一起卡——標記也必須一起下。 |
| `cryptography>=50.0.0` | **沒有** | wheel 只出到 **46.0.3**，46.0.4 起上游就不再發 win_arm64。而 `>=50.0.0` 是 347ec1e 為了 GHSA-g6cj-pr64-35w5（moderate；50.0.0 修復）訂的**安全下限**，不能為了 arm64 降回去。 |
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

## 隔離改版的下游整合驗收

`TODO` — 合併 modernization 隔離分支前，先確認 Jeffrey_RPA 的正式 editable 批次
及 Discord bot 已停止；保留目前執行中的原始碼。整合時套用
`docs/compatibility/jeffrey-rpa-oem-test-migration.patch` 更新 slash 快捷鍵測試契約，
再跑下游 `test/test_gui_facade.py`、`test/test_gui_control.py` 與
`test/test_je_facade.py`，並完成 H3 的真實平台驗收。

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

## 遠端桌面的 viewer 槽位由各面板共用

`DECIDE` — 要改 `registry` 的擁有權模型

`utils/remote_desktop/registry.py` 的 TCP 與 WS viewer 各只有一個槽位，快速連線（`gui/remote_desktop/connection_screen.py`）、
舊式 viewer 分頁（`viewer_panel.py`）與 `AC_remote_connect` 都寫同一格。每一方連線前先 `registry.disconnect_viewer()`，
於是在一邊連線會切斷另一邊的連線，被切斷的面板卻不知道：它的彈出視窗仍停在最後一格畫面，
「中斷」按鈕則會切斷別人的連線。快速連線的「開始被遠端」也一樣會停掉主機分頁開的 host。

**做法**：registry 記錄每個 viewer／host 由誰開的（owner token），`disconnect_*` 只在 owner 相符時動作；
被別人取代時通知原本的面板收掉自己的視窗。或是反過來讓每個面板持有自己的 viewer，不經 registry。

**為什麼要拍板**：`AC_remote_*` 指令與 MCP 工具依賴「registry 裡就是那一個 viewer」，改成多槽位要一起改它們的語意。

---

## `test_usb_acl_prompt.py` 讓 Python 3.10 的 headless 測試間歇 segfault

`TODO` — `test/unit_test/headless/test_usb_acl_prompt.py::test_bridge_remember_persists_acl_rule` 在 `coverage run -m pytest` 下讓行程 SIGSEGV（exit 139），整個 `pytest-headless` job 因此失敗：2026-09-26 連續三次 AutoControl Code Quality（ubuntu-22.04／3.10），2026-09-30 一次（macos-14／3.10）；同一次其他版本都過，之後的 run 又過，所以是間歇的。原因還沒查：先在 3.10 開 `faulthandler` 重跑這一支，看崩在哪個原生呼叫。

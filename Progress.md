# Progress

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
| `gui/remote_desktop/webrtc_panel.py` | 2,530 | 單一 Qt 面板,但已含連線、監視器選擇、頻寬自適應、麥克風、錄影五組互動狀態。應拆成 panel + 各控制器。 |
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
| 動作檔加密（`action_signing`） | `cryptography` | `_fernet_types()` 拋 `RuntimeError`（簽章本身是 HMAC，不受影響） |
| 秘密金庫（`${secrets.NAME}`） | `cryptography` | 同上 |
| ACME／TLS 發證、加密錄影 | `cryptography` | 模組層 `ImportError` 轉述（照 `webrtc_transport` 慣例） |

這四組在 arm64 上能不能回來，**完全取決於上游**：

| 依賴 | win_arm64 | 實測（2026-08-20） |
| --- | --- | --- |
| `opencv-python>=4.8,<6` | **沒有** | 任何版本都沒有，pip 回的是 `from versions: none`。`je_open_cv` 自己是純 Python，但相依 opencv-python，所以一起卡——標記也必須一起下。 |
| `cryptography>=48.0.1` | **沒有** | wheel 只出到 **46.0.3**，46.0.4 起上游就不再發 win_arm64。而 `>=48.0.1` 是 347ec1e 為了 GHSA-537c-gmf6-5ccf（high）訂的**安全下限**，不能為了 arm64 降回去。 |
| `pillow==12.3.0` | 有 | `pillow-12.3.0-cp3xx-win_arm64.whl` 一直都在。**曾經被寫成卡點，那是猜的，它從來不是。** |
| `mss`／`defusedxml` | 有 | 純 Python。這三個加上 Pillow 就是 arm64 實際裝到的全部。 |
| `PySide6==6.11.1`／`qt-material==2.17` | 有 | `[gui]` extra 在 arm64 上裝得起來。 |
| `aiortc` | **沒有** | 卡在傳遞相依 `google-crc32c`，與本專案的選擇無關；`av` 自己有 wheel。 |

重驗指令（不需要 arm64 機器，也不需要 runner）：

```bash
pip install --dry-run --only-binary=:all: --platform win_arm64 --python-version 3.12 --target /tmp/probe 'opencv-python>=4.8,<6' 'cryptography>=48.0.1'
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

## 鍵盤與滑鼠 wrapper 的輸入修正：等 Jeffrey_RPA 批次停下

`BLOCKED` — Jeffrey_RPA 以 editable install 載入這個工作樹，正式批次（`webrunner_novelai.py`）與 Discord bot 正在跑，並且經 `_gui_control.py` 呼叫 `ac.write`、`ac.hotkey`、`ac.mouse_scroll`；下面每一項都會改變它打出來的字或滾動方向，依工作區規則在它執行期間不動

2026-09-24 稽核用假後端重現：

- **大寫字母打成小寫**：`wrapper/auto_control_keyboard.py:234` `write()` 在 Windows 送的是與小寫相同的虛擬鍵（`_platform_windows.py` 的表裡 `"A"` 與 `"a"` 同一個碼），沒有按 Shift，`"Hi"` 打成 `hi`；X11 很可能一樣。做法：需要 Shift 的字元改走 `_write_char_via_unicode`，或包一層 Shift 按下／放開。
- **`is_shift` 在 Windows 與 X11 無效**：`auto_control_keyboard.py:73`、`:104` 只在 macOS 把它傳下去，其他平台直接忽略，docstring 卻寫「是否同時按下 Shift」。做法：在這一層按住 `keyboard_keys_table["shift"]`，`finally` 放開。
- **`"\r\n"` 按兩次 Enter**：`write()` 把 `\r` 與 `\n` 都對到 `return`，從檔案讀進來的 Windows 換行每行多一個空行。做法：迴圈前把 `\r\n` 換成 `\n`。
- **X11 預設滾動方向與 Windows／macOS 相反**：`wrapper/auto_control_mouse.py` `mouse_scroll(..., scroll_direction="scroll_down")`，正值在 X11 往下、其他平台往上，與 docstring「一份寫法各平台通用」不符。做法：預設改 `scroll_up`，或改 docstring 講清楚（重播路徑已在 U-20260924-14 明確傳 `scroll_up`）。
- **`mouse_scroll` 的 NaN 座標被悄悄夾到桌面邊緣**：`auto_control_mouse.py` 的夾限在 `_coordinate()` 驗證之前，`mouse_scroll(3, x=nan, y=100)` 移到 `(-1920, 100)` 才滾；`set_mouse_position(nan, …)` 則正確丟例外。做法：夾限前先過 `_coordinate()`。
- **座標截斷而非四捨五入**：`set_mouse_position(-0.6, 10.9)` 得到 `(0, 10)`，註解寫的是「rounded point」。做法：`int(round(value))`。

同一次稽核的影像與 OCR 部分也在它的路徑上（Discord bot 的 `!find_image`／`!find_text`），一併等：

- **非 ASCII 路徑與灰階樣板**：`cv2_utils/template_detection.py:126` 經 `je_open_cv` 的 `cv2.imread` 讀樣板，`測試\t.png` 讀不到；2-D 陣列或 PIL `"L"` 樣板丟出 `cv2.error`，不在 `wrapper/auto_control_image.py` 的例外清單裡。做法：路徑改走 `cv2_utils/image_file.read_image`，2-D 直接用，`cv2.error` 包成 `ImageNotFoundException`。
- **部分超出螢幕的 `screen_region` 被補黑**：`monitor_layout/logical_frame.py:143` 沒有先和畫面取交集，PIL `crop` 補零，可能回傳螢幕外的命中；寬或高為負時丟裸 `ValueError`。做法：先取交集（回傳裁過的原點），非正的寬高丟框架例外。
- **OCR 跨框比對漏掉從長框中段開始的字串**：`ocr/text_span.py:330` 的視窗超過「目標長度＋40」就整個丟掉最左框，即使目標從那框開始；`"Save As"` 在長句框之後就找不到。做法：只有剩下的部分仍不短於目標時才丟左框。
- **負座標的中心點差一**：`wrapper/auto_control_image.py:48`、`:73` 的 `int((x1 + x2) / 2)` 向零截斷。做法：`(x1 + x2) // 2`。

**解除條件**：Jeffrey_RPA 沒有批次在跑（`webrunner.pid` 的行程不在、Discord bot 停止）；改完在 Jeffrey_RPA 跑 `test/test_je_facade.py`。

---

## RBAC 還沒接到 REST API 與 MCP server

`DECIDE` — 要不要把 `utils/rbac` 接上兩個伺服器，以及現有單一共用 token 怎麼過渡（維護者拍板）

`utils/rbac/users.py` 有使用者、角色與權杖驗證（2026-09-24 已補上：壞檔不覆寫、權杖不得重複），但沒有任何程式
import 它：`rest_api/rest_auth.py` 與 `mcp_server/http_transport.py` 都只比對一個共用 token，稽核 log 也沒有
`user_id`。模組 docstring 已改成照實描述。

**做法**：`RestAuthGate.check` 改成先查 `UserStore.authenticate`、再依路由對應的 `Capability` 呼叫 `can()`；
MCP 的 bearer 比對同理；稽核寫入帶上 `user_id`。

**要先想清楚**：沒有任何使用者時是否退回共用 token（相容現有部署）；viewer／operator／admin 各能呼叫哪些路由與工具。

---

## 能執行動作的人也能替檔案簽章

`DECIDE` — `JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` 要防的是誰（維護者拍板）

`AC_sign_action_file` 用預設的個人金鑰簽章，所以凡是能透過 socket、REST 或 MCP 執行動作的人，都能先簽一個檔再用
`AC_execute_files` 執行它；內嵌的動作清單本來就不驗簽。現在的強制簽章只擋得住「能改檔案、但不能執行動作」的人。

**選項**：簽章指令在強制模式下只准本機 CLI 使用；或簽章金鑰與執行權限分開保存（簽章端不在執行端）。

---

## USB passthrough viewer 以種類配對回覆，逾時的回覆會交給下一個請求

`DECIDE` — 協定要不要加請求編號（線上格式改動，新舊版本相容要一起想）

`utils/usb/passthrough/viewer_client.py:413`（`_on_opened`）與 `:466`（`_complete_pending`）只按 OPEN／LIST／claim
配對回覆，回覆沒有序號。請求逾時後，對同一種類的下一個請求會拿到遲到的舊回覆：`open(aaaa)` 逾時、`open(bbbb)`
收到 `aaaa` 的 OPENED，claim 綁錯裝置；bulk 讀逾時後，下一次傳輸拿到上一次的資料。host 接受最長 60 秒的
`timeout_ms`，client 預設 10 秒就放棄，正常使用就會遇到（2026-09-24 稽核重現）。

**選項**：在 payload 加一個由 client 產生、host 原樣帶回的請求編號（舊 host 不帶就退回現在的配對）；或逾時後把該
claim 標成需排空，丟掉下一個回覆——但 host 若根本沒回，會丟掉正確的回覆。

---

## 全域 executor 的變數會留到下一次執行

`DECIDE` — 每次頂層執行要不要有自己的變數範圍（行為改動，維護者拍板）

`execute_action_with_vars`（`utils/executor/action_executor.py`）把變數種進全域 `executor` 後從不清除，REST、MCP、
socket server 的執行也都用同一個 `executor`；`for_each` 的迴圈變數與巨集參數同樣留著。下一次執行裡的 `${user}`
會安靜地取到前一個呼叫者的值，而不是報 `Unknown variable`（2026-09-24 稽核重現）。模組文件把這個範圍描述成
「共用」，所以有人可能依賴它在執行之間傳值。

**選項**：`execute_action_with_vars` 與各伺服器入口每次開一個新的 `VariableScope`（`AC_set_var` 在單次執行內照舊）；
或保留共用，但在伺服器入口清空，並在文件寫明。

**附帶**：`AC_circuit_call`、`AC_bulkhead_run`、`AC_run_chaos`、`AC_run_dag` 的巢狀動作跑在全域 `executor` 上，
在 `AC_parallel` 分支裡因此用到父層的變數範圍，而不是分支自己的。

---

## 舊式 CLI（`-e`／`-d`／`--execute_str`）在動作失敗時仍然結束碼 0

`DECIDE` — 要不要讓舊式入口也以結束碼 1 回報動作失敗（跨專案契約，PyBreeze 與 TestPioneer 以子程序呼叫）

`je_auto_control/__main__.py` 執行完不看 `recorded_failures()`；`je_auto_control run` 在 `cli.py` 已經會回 1。
同一個會失敗的腳本，`run` 回 1，`-e`、`-d`、`--execute_str` 回 0（2026-09-24 稽核重現）。

**要先確認**：PyBreeze（`AI_CONTEXT.md` §5）與 TestPioneer 的 `parallel_run` 怎麼解讀這個結束碼——若把非 0 當成
「無法執行」而非「有動作失敗」，改了會讓它們把一次有失敗步驟的執行回報成錯誤。改的話兩邊的 `architecture.md` §6
與相容性測試要一起更新。

---

## Computer use 的預設還是 beta 的 `computer_20251124`

`TODO` — 在 `claude-opus-5`（兩種形式都接受）上實測 GA toolset 後，把它設成所有模型的預設

`utils/agent/backends/anthropic_computer_use.py` 已支援 `computer_toolset_20260801`（`_computer_toolset.py`：成員名即動作、
一回合多個呼叫逐一執行後一次回覆、每個 `tool_result` 帶 `toolset_name`、截圖縮到高解析度層級的 2576 px／4784 visual tokens 內並換算座標、`zoom` 以全解析度裁切回覆），
`claude-opus-5-5` 自動使用它；其他模型仍預設 beta 形式，因為 toolset 只以假 client 測過、還沒對真的 API 跑過。

**附帶**：`AC_run_agent backend="openai"` 送出全部約 740 個工具，超過 OpenAI Chat Completions 的 128 個上限，
所以一定失敗——與「`AC_run_agent` 預設工具集」那一條 DECIDE 一起決定。

---

## 關閉視窗時，一個超過 10 秒的步驟仍會讓行程 abort

`TODO` — 讓 LLM 請求可以中斷（或在結束時放棄等待而不銷毀 `QThread`），再把 LLM 規劃分頁也接上停止

`gui/_worker_thread.py:_stop_running_threads` 在結束時先呼叫 worker 的 `request_stop()`，再共用 10 秒等執行緒結束；
computer use 與 DAG 在下一步／下一個節點之前停下。但一個步驟本身（一次 LLM 請求、一個 DAG 節點）或
`gui/llm_planner_tab.py` 的 `plan_actions` 呼叫若超過 10 秒，PySide 在結束時銷毀仍在執行的 `QThread`，行程會以 abort 結束。

---

## MCP registry 的 server 名稱與專案網址還是舊組織

`DECIDE` — 要發布到 MCP registry 前得先定名稱，改名會影響已發布的項目

`utils/mcp_registry/registry.py` 的 `_SERVER_NAME` 是 `io.github.intergration-automation-testing/autocontrol`，
`_REPO_URL` 與 `pyproject.toml` 的 Homepage / Code、`README.md` 的 clone 網址都還是
`Intergration-Automation-Testing/AutoControl`；repo 現在在 `Integration-Automation/AutoControlGUI`（舊網址只是轉址）。
registry 以 GitHub 帳號驗證 `io.github.<org>/` 命名空間，舊組織名發布不了。

**做法**：決定正式名稱（例如 `io.github.integration-automation/autocontrol`），在同一輪改 `registry.py`、
`pyproject.toml`、三份 README 的網址。

---

## pytest11 進入點會把整個門面拉進每一次 pytest

`DECIDE` — 要不要把進入點搬到一個精簡的頂層模組（打包層的改動，維護者拍板）

`pyproject.toml` 的 `pytest11` 進入點指向 `je_auto_control.utils.pytest_plugin.plugin`。
外掛模組本身很輕（只 import pytest，fixture 裡才 import 本套件），但它是**套件的子模組**，
所以 Python 會先跑 `je_auto_control/__init__.py`——量到 **1,355 個模組**。機器上任何一個
安裝了本套件的環境，每一次 pytest 啟動都付這筆成本（Jeffrey_RPA 因此在 `pytest.ini` 用
`-p no:je_auto_control` 擋掉它）。pytest 官方文件建議的形狀正是「進入點指向只 import pytest
的精簡模組」。

改法：新增頂層模組（例如 `je_auto_control_pytest.py`，`[tool.setuptools] py-modules`），
進入點改指它，`utils/pytest_plugin/plugin.py` 轉為 re-export 以維持
`pytest_plugins = ["je_auto_control.utils.pytest_plugin"]` 這條路。

**為什麼要拍板**：(1) 這是發佈產物的改動，會在 site-packages 多一個頂層名字；
(2) 進入點改了要重裝才生效（本機的 editable 安裝、CI 的 `pip install -e .`）；
(3) `test/unit_test/headless/test_coverage_measurement.py` 的前提會改變——它現在釘住
「外掛載入時門面已經在 `sys.modules` 裡」，改完就不成立，那份說明與測試要一起改寫
（CI 仍可繼續用 `coverage run -m pytest`）。

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

## `cryptography` 的安全下限要不要拉到 50

`DECIDE` — 要不要用 Intel Mac 的預編 wheel 換掉一個本套件沒用到的漏洞範圍

`pyproject.toml` 的 `cryptography>=48.0.1` 仍包含 GHSA-g6cj-pr64-35w5（high,`>=44.0.0, <50.0.0`,
PKCS#7 EnvelopedData 解密的 Bleichenbacher oracle）的範圍。本套件沒有呼叫 PKCS#7 解密
（用的是 Fernet，以及 aiortc 的 DTLS），所以目前不受影響。`uv.lock` 已鎖在 50.0.1。

**為什麼要拍板**:49.0.0 起上游不再發 `macosx_10_9_universal2` wheel，只剩 `macosx_11_0_arm64`。
下限拉到 `>=50.0.0` 之後，Intel Mac 上的 `pip install` 要從原始碼編譯（得先裝 Rust 工具鏈）。
CI 只有 macos-14(arm64)，量不到這一點。重新檢查（不需要機器）:

```bash
pip install --dry-run --only-binary=:all: --platform macosx_10_9_x86_64 \
    --python-version 3.12 --target /tmp/probe 'cryptography>=50'
```

---

## Viewer 端要不要把 host 推來的檔案關在一個目錄裡

`DECIDE` — 這是改一個已寫進文件的功能，由維護者決定

`host.send_file_to_viewers(source, dest_path)` 由 **host** 指定 viewer 機器上的完整路徑
（`docs/source/{Eng,Zh}/doc/new_features/new_features_doc.rst` 的範例是 `/tmp/from_host.bin`），
viewer 端的 `FileReceiver`（`utils/remote_desktop/file_transfer.py`）照單全收：`expanduser`、
建立父目錄、寫入。也就是被控端可以在控制端機器的任何可寫位置放檔案。模組說明的
「trusted token holders == trusted users」只涵蓋 host 端；viewer 連上一台被入侵的 host 時沒有這層保護。

**做法**：`FileReceiver` 加 `base_dir`，viewer（`viewer.py` 的 `_ensure_file_receiver`、GUI 的
`viewer_panel.py`）預設給一個下載目錄，只保留相對路徑並拒絕跳出 `base_dir`；host 端維持現狀。

**為什麼要拍板**：`dest_path` 的語意會從「viewer 上的絕對路徑」變成「viewer 下載目錄裡的相對路徑」，
現有腳本與文件範例都要跟著改。

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


---

## MCP 工具的檔案路徑參數要不要限制在工作區根目錄裡

`DECIDE` — 限制範圍與預設值由維護者決定

MCP 工具的檔案參數（`path`、`file_path`、`db`、`image_path`、`golden_path`、`output_path`… 約 100 個）
不受任何根目錄限制；只有 `resources/read` 關在 `roots/list` 的根目錄裡。完整模式下這不是新的權限
（`ac_execute_actions` 本來就能做任何事），但 `JE_AUTOCONTROL_MCP_READONLY=1` 的部署仍能讀到根目錄外的
任意檔案：例如 `ac_load_dotenv` 會把任何檔案解析成 KEY=VALUE 回給模型，`ac_read_document`、
`ac_extract_pdf_text` 也一樣。2026 年 MCP 伺服器通報最多的一類就是這種路徑越界。

**做法**：在 `utils/mcp_server/tools/_factories.py` 的 schema 裡把真正是檔案路徑的屬性標上
`"format": "path"`（不能照名字判斷：`ac_json_query` 的 `path` 是 JSON 路徑，`template`／`source`／
`target` 有時是檔案有時不是），`server.py` 的 `_prepare_tool_call` 在設定了根目錄時先 `realpath`
再檢查是否落在根目錄內，不在就回 `-32602`。

**為什麼要拍板**：根目錄從哪來（新的環境變數、沿用 `roots/list`、或兩者），唯讀模式要不要預設開啟；
預設開啟會讓現有讀取工作區外檔案的用法失效。

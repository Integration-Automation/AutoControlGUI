# Progress

**只記未完成的事。** 已出貨的內容寫進 [WHATS_NEW.md](WHATS_NEW.md)，相容性變更寫進
[CHANGELOG.md](CHANGELOG.md)；完成的項目從本檔移除，不累積歷史。

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
行數為 2026-08-19 實測（`len(text.splitlines())`）。

| 檔案 | 行數 | 為何還沒拆 |
| --- | ---: | --- |
| `utils/mcp_server/tools/_handlers.py` | 4,789 | 676 個 MCP 工具的處理函式本體。與 `_factories.py`（表）不同,這裡是邏輯,應該依主題拆成 `_handlers/` 套件（input／screen／window／file／agent…）。拆點清楚,純粹是量大。 |
| `gui/remote_desktop/webrtc_panel.py` | 2,555 | 單一 Qt 面板,但已含連線、監視器選擇、頻寬自適應、麥克風、錄影五組互動狀態。應拆成 panel + 各控制器。 |
| `utils/accessibility/backends/windows_backend.py` | 915 | 已拆出 `windows_query.py`（170）與 `windows_state.py`（98）。剩下的是同一套 UIA COM 生命週期管理,再拆會把 `CoInitialize`／介面釋放的配對邏輯切散。 |

**本質豁免（依 `CLAUDE.md` 的「flat data tables」條款,不算既有豁免）**:
`utils/mcp_server/tools/_factories.py`（8,972,MCP 工具註冊表）、
`utils/executor/action_executor.py`（8,125,`AC_*` 分派表）、
`gui/script_builder/command_schema.py`（5,051,每個 `AC_*` 的參數 schema）、
`je_auto_control/__init__.py`（1,970,門面 re-export）、
`gui/language_wrapper/{english,japanese,traditional_chinese,simplified_chinese}.py`
（1,316／1,203／1,189／1,188,語系字串表）。

### 2026-08-19 決議:上表的實測行數就是新的上限

2026-08-18 重新實測時,表上原有的七列**全部**變長,而 `CLAUDE.md` 明寫
「列上的檔案不得再變長,要再長就得先拆」,所以這裡曾標成 `[DECIDE]`。
**維護者已於 2026-08-19 拍板:接受實測數字當新基準**——不為了回到舊數字而去拆
`_handlers.py`（4,789）與 `webrtc_panel.py`（2,555）。上表的行數即是各自的新上限,
規則不變:只准變短,再變長就得先拆。

同一批裡有六個檔案在 2026-08-19 已經拆回線內、從表上移除,做法寫在
[WHATS_NEW.md](WHATS_NEW.md)。

行數沒有任何 CI 在把關（`quality.yml` 只跑 ruff 與 bandit,而 ruff 只管行寬),
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
來)。都已經是 CI job 了,見下面「已經有答案的」與 [WHATS_NEW.md](WHATS_NEW.md)。

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

### 已經有答案的（都在 CI 裡,做法見 WHATS_NEW）

五個 job 都在 GitHub runner 上跑過了（2026-08-19,PR #481）。`modprobe uinput evdev`
在 runner 上載得起來,`systemd-udevd` 在容器裡也收得到 kernel uevent——這兩件事原本
只在本機（Docker Desktop 的 WSL2 kernel）驗過,曾經記在上面當待辦,現在有答案了。
job 一律寫成模組載不起來就明講失敗,不會靜默跳過,所以哪天 runner 的 kernel 變了會
當場紅掉。

| 面向 | 怎麼驗的 | job |
| --- | --- | --- |
| 擷取路徑 | 真的 wlroots 合成器（sway headless,兩個上不同純色的 output）,27 項 × 2 種版面 | `wayland-verification` |
| libei 協定層 | 真的 `libeis.so.1` server 在 Unix socket 上,20 項 | `eis-verification` |
| RemoteDesktop portal 交握 | 真的 `dbus-daemon` + 真的 `liboeffis`,對面是自己實作的 portal,`ConnectToEIS` 交出通往真 libeis 的活 fd,20 項 | `portal-verification` |
| ydotool CLI | 真的 uinput 裝置,直接讀回 `/dev/input/eventN`,12 項 | `ydotool-verification` |
| ydotool 的絕對移動落在哪 | 真的 wlroots session 吃真的 ydotool 裝置（`headless,libinput` + builtin seat）,游標位置從 `grim -c` 的像素讀回,14 項 × 2 種版面 | `seat-verification` |

擷取那一列的第二種版面是**負原點**:`output HEADLESS-1 position -1280 0`,
也就是「第二台螢幕在主螢幕左邊」的桌面。sway headless 收這個座標,grim 也收負的
`-g`,所以這件事根本不必等 GNOME VM——原本記在這裡說測不到,是把「合成器做得到的事」
當成了「容器做不到的事」。跑起來當場抓到三個真的錯:`size()` 回的是版面右緣不是寬度、
非 grim 層級的裁切用版面座標去裁一張以版面原點為 (0,0) 的圖、`grab_logical()` 一律回
原點 (0,0) 所以比對到的座標整個偏掉。修法見 [WHATS_NEW.md](WHATS_NEW.md)。

portal 那一列是同一個錯誤犯第二次的結果,而它抓到的東西比前一次更嚴重:
`portal.py` 那條「先開 `gdbus monitor`、再用 `gdbus call` 發請求」的路
**在任何真的 bus 上都不可能成功**——portal 的 `Response` 是**指名送給發出呼叫的那條
連線**,兩個 gdbus 行程是兩條連線,監聽的那條永遠不是收件人。在真的 `dbus-daemon` 上
量到的就是這樣:呼叫看得到,回答永遠等不到,每次都走到 30 秒逾時。修法見
[WHATS_NEW.md](WHATS_NEW.md)。

五者都不需要合成器以外的東西,更不需要 GNOME VM。libei 這一層驗掉的包含
capability enum 值與 variadic `ei_seat_bind_capabilities`、event-type enum 值、
`start_emulating` → 事件 → `frame` 的實際上線內容、live context 的 teardown
安全性（原本每個行程漏一個 context + 一個 fd,已修）、以及絕對指標的座標空間
（region offset 讀得回來且含在座標裡、region 外的移動被靜靜丟掉、負原點的版面要
正規化）。portal 這一層驗掉的是四個呼叫的順序與 client 自己預測的 request path、
`SelectDevices` 收到的裝置遮罩（也就是使用者被要求同意的範圍）、交回來的 fd 真的
承載得起一個 EI session,以及六種拒絕路徑各自都要 fail closed。ydotool 這一層驗掉的是
`click` 位元遮罩、拆邊的 press／release、`mousemove --absolute` 的實際上線內容、
捲動正負號與軸向,以及 `mouse`／`keyboard` 自己組出來的 argv。seat 這一層驗掉的是
`--absolute` 到底相對於哪裡（版面左上角,不是版面座標的 `(0, 0)`)、關掉加速度後
一像素對一像素、沒轉換的 `(0, 0)` 會打到隔壁螢幕、`set_position` 減掉的正好是原點、
以及預設 profile 下的 2 倍加速。

### 一件關於發行版的事實,會影響使用者拿到什麼

- **`liboeffis` 是獨立的二進位套件,`libei1` 不會把它帶進來。** Debian trixie
  **有** `liboeffis1`（1.3.901-1,`liboeffis.so.1`,連 libsystemd 的 sd-bus）——
  這裡原本寫「Debian trixie 沒有」,是錯的,已實測更正。Arch（1.6.0）與 Fedora 也有。
  但因為它不是 `libei1` 的相依,只裝 libei 的機器上 portal 快速路徑仍然是關閉的,
  `connect()` 會退到 `$XDG_RUNTIME_DIR/eis-0` socket,GNOME／KDE 不開那個 socket
  → 退回 ydotool。**所以要用 libei 快速路徑,`liboeffis` 得自己裝。**
- 而那條退路本身,在同一批發行版上原本是壞的——0.1.x 對本專案送的 argv 回傳 0
  卻不送任何事件。已於 2026-08-19 擋掉,見 CHANGELOG 與 WHATS_NEW;此處無待辦。

**緩解**:驗不到的擷取部分有逃生門——`JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND` 讓操作者
直接指定自己的擷取指令（`{output}` 會被換成暫存 PNG 路徑）,優先於所有偵測。

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

## 兩個講好要爬、還沒爬的門檻

`TODO` — 兩者都寫在 `pyproject.toml` 的註解裡，但不在任何待辦清單上

- **覆蓋率**：`fail_under = 35`，註解寫著「Raise toward 70 as legacy modules are
  brought under the stable API contract」。目標是 70，今天是 35，中間沒有計畫。
- **mypy 範圍**：CI 只型別檢查兩條路徑（`quality.yml` 的
  `mypy je_auto_control/api je_auto_control/utils/failure_bundle`）。註解寫著
  「followed legacy modules are analysed for signatures but not reported until they
  join the contract」——同樣是講好要擴、還沒擴。

兩者都不是一次做得完的事，但放在這裡至少讓「下一步是什麼」有一個地方可寫。

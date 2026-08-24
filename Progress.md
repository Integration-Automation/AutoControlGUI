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
行數為 2026-08-19 實測（`len(text.splitlines())`）；`webrtc_panel.py` 於
2026-08-22 拆出 `advanced_group.py` 後降到 2,545，上限跟著往下走。

| 檔案 | 行數 | 為何還沒拆 |
| --- | ---: | --- |
| `utils/mcp_server/tools/_handlers.py` | 4,789 | 676 個 MCP 工具的處理函式本體。與 `_factories.py`（表）不同,這裡是邏輯,應該依主題拆成 `_handlers/` 套件（input／screen／window／file／agent…）。拆點清楚,純粹是量大。 |
| `gui/remote_desktop/webrtc_panel.py` | 2,545 | 單一 Qt 面板,但已含連線、監視器選擇、頻寬自適應、麥克風、錄影五組互動狀態。應拆成 panel + 各控制器。 |
| `utils/accessibility/backends/windows_backend.py` | 923 | 已拆出 `windows_query.py`（170）與 `windows_state.py`（98）。剩下的是同一套 UIA COM 生命週期管理,再拆會把 `CoInitialize`／介面釋放的配對邏輯切散。**2026-08-24 從 918 長到 923**:見下面的說明。 |

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
`_handlers.py`（4,789）與 `webrtc_panel.py`。上表的行數即是各自的新上限,
規則不變:只准變短,再變長就得先拆。

同一批裡有六個檔案在 2026-08-19 已經拆回線內、從表上移除,做法寫在
[WHATS_NEW.md](WHATS_NEW.md)。

行數沒有任何 CI 在把關（`quality.yml` 只跑 ruff 與 bandit,而 ruff 只管行寬),
所以這張表只會在有人手動實測時才會被發現對不上——上次就是。

### 2026-08-24:`windows_backend.py` 從 918 長到 923，理由記在這裡

表上原本寫 915，2026-08-24 實測時工作樹已經是 **918**（表本身就過期了，
正是上一段講的那件事）。這次又 +5，是為了改掉一個真的錯：檔內 37 個
`except (OSError, AttributeError, …)` 攔不到 comtypes 的 `COMError`
（細節見下面覆蓋率那一節與 [CHANGELOG.md](CHANGELOG.md)）。5 行是一個模組層
常數加兩行註解——`CLAUDE.md` 允許「超標檔案再變長」的兩條路是**先拆**或
**在這裡寫明為什麼不拆**，這是後者：拆這個檔的正確切點是 UIA COM 的生命週期
管理，和這次的修正無關，綁在一起會讓一個三行的正確性修補變成大面積 diff。
**新上限是 923**，規則不變。

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

## 兩個門檻：mypy 那半到終點了，覆蓋率那半在往 80 爬

`TODO` — 型別那半 2026-08-22 收工；覆蓋率那半有目標了（80），還沒到

原本這一條記的是兩個只存在於 `pyproject.toml` 註解裡、沒有任何機制的承諾。
2026-08-21 把**機制**補上了（做法見 [WHATS_NEW.md](WHATS_NEW.md)）：
型別契約的豁免清單 2026-08-22 清空，平台縫最後兩個名稱（`keyboard`／`mouse`）
2026-08-23 拿到合約；覆蓋率那半發現不是爬得不夠，是量測起點錯了，修正後地板
從 50 提到 69，隔日再提到 75。

**2026-08-23 維護者拍板：下一個覆蓋率目標是 80。** 這一條留到那時候。
型別那一節留著是因為它記的那幾個坑之後還會踩到。

### 覆蓋率：地板 75，目標 80——本機已過，等九宮格

`TODO` — 目標 **80**（2026-08-23 拍板）。**2026-08-24 本機（Windows／3.14）已到
82.40%**（77.04% 起算，四批：WebRTC 那一族、window backends、accessibility、
hotkey backends），但**地板照舊只跟著九宮格最低那一格走**，所以
`fail_under` 還停在 75，要等 CI 的 `coverage report` 印出來才動。
本機與最低那一格上一次相差約 1.3 點（77.04 對 75.79）。

**這一條要收掉，只差兩件事**：讀一次矩陣把地板提上去，以及下面第 2 項那個
`DECIDE`（掃不到的那批 adapter）。其餘計畫內的項目都做完了。

`fail_under` 一度從 35 提到 50，理由寫在 `pyproject.toml`。**那兩個數字都低了大約
24 點**，而原因不在測試，在量測的起點：

`quality.yml` 用的是 `pytest --cov`，而本套件註冊了 `pytest11` entry point。
pytest 在載入外掛時就會 import `je_auto_control.utils.pytest_plugin.plugin`——
要 import 那個子模組，Python 必須先執行 `je_auto_control/__init__.py`，也就是門面，
連帶把好幾百個模組拉進來。`pytest-cov` 是**在那之後**才開始量的，所以那幾百個模組的
import 期程式碼（`def` 行、類別本體、常數、兩張大分派表）全部被記成「從沒執行過」。

2026-08-23 實測，同一套測試、同一份 `[tool.coverage.run]` 設定，**只差開始的時機**：

| 量法 | 總覆蓋率 |
| --- | ---: |
| `pytest --cov=je_auto_control` | 52.22% |
| `coverage run -m pytest` | **72.05%** |

差 11,962 個 statement。受害最深的正好是最大的幾個檔：`action_executor.py` +786、
`_handlers.py` +684、門面自己 +369、`_factories.py` +209。

**一個註冊了 pytest 外掛的套件，沒辦法用 `pytest --cov` 量自己。**
`quality.yml` 已經改成 `coverage run -m pytest`（先於 pytest 載入任何東西），
`test/unit_test/headless/test_coverage_measurement.py` 把這件事釘住——因為兩種寫法的
差別在綠色的建置裡看不出來：改回去會白送 24 點，而每一格照樣是綠的。

修正後的九宮格已經量出來了（2026-08-23，本 PR 的 run）：

| | 最低 | 最高 |
| --- | --- | --- |
| 修正前（`pytest --cov`） | 50.26%（ubuntu-22.04／3.10） | 51.69%（windows-2022／3.14） |
| 修正後（`coverage run`） | **69.67%**（ubuntu-22.04／3.14） | 70.97%（windows-2022／3.12） |

地板因此設成 **69**——取最低那一格往下取整，與當初 50 取自 50.26% 是同一個慣例。
`[tool.coverage.report]` 的 `precision` 也從預設的 0 提到 2：預設精度下九格全部印
「70%」，而它們其實是 69.67 到 70.97，分不出最低的是哪一格。
順帶把 `fail_under` 的容差從一整個百分點縮到 0.01。
地板只有一個家（`pyproject.toml` 的 `fail_under`），`quality.yml` 不再另外抄一份。

**這一段原本寫「地板得去 XML artifact 裡撈」，那是錯的，2026-08-23 實測更正。**
上面那九個數字是 `coverage report` 印的，也就是 `fail_under` 真正比對的那個數字，
而它**含分支**（`[tool.coverage.run]` 的 `branch = true`）；`coverage.xml` 的
`line-rate` 屬性**不含分支**，所以同一格會高出約 1.8 點——a585e65 那一格
report 印 69.67%，artifact 是 71.07%。照 artifact 設地板，設出來的會是這套測試
過不了的地板。要看單一子系統的缺口用 artifact，要設地板只能用 report。

Windows 是高的那一角，因為門面 import 進來的是**它自己那個平台的後端**；
換句話說剩下的那 30 點裡，有一部分是任何單一平台都拿不到的。

#### 往 80 怎麼爬：走註冊表，而且替身要從型別合約長出來

第一批 2026-08-23 落地（`test/unit_test/headless/test_adapter_registry_sweep.py`，
做法見 [WHATS_NEW.md](WHATS_NEW.md)）。兩個註冊表、一支測試檔：

| 掃什麼 | 參數從哪來 | 換掉什麼 |
| --- | --- | --- |
| 657 個 MCP 工具 | 工具自己宣告的 JSON schema（`_factories.py`） | 被呼叫者 |
| 773 個 `AC_*` 命令 | Script Builder 的 `command_schema.py`；沒有 spec 的用參數標注 | 被呼叫者 |

**關鍵不是「掃」，是替身怎麼來的**：替身的回傳值是從**被呼叫者自己的回傳標注**
造出來的（`Optional[X]` → `None`、容器 → 空容器、純量 → 零值）。這件事
2026-08-22 之前做不到——那時候還有 136 個模組不在型別契約裡，沒有東西可讀。
契約清空之後，「這個轉接函式有權假設什麼」變成程式讀得出來的東西，於是 460 個
MCP adapter 與 372 個執行器 adapter 可以在沒有滑鼠、沒有螢幕、沒有網路的情況下
整段跑完，而且跑的是**剛好等於合約承諾的東西，不多也不少**。

實測（本機 Windows／3.14）：

| | 之前 | 之後 |
| --- | ---: | ---: |
| `_handlers.py` | 37.47% | **75.21%** |
| `action_executor.py` | 55.78% | **73.52%** |
| 全專案 | 71.91% | **74.91%** |

掃不到的是兩種形狀，而且是刻意的：adapter 伸手進**兩個**專案模組（那是組合，
不是轉接），以及 adapter 自己 `import` 第三方套件（那是它在挑後端，回傳取決於
機器）。三個 MCP adapter 需要的比合約承諾的更多，用名字列在測試檔裡，各附一行
理由；**其中任何一個哪天開始通過，測試會要求把它刪掉**，清單不會爛在那裡。

#### 2026-08-23 拍板：`quality.yml` 裝 `[webrtc]` extra

原本這裡是一條 `DECIDE`，寫的是「要嘛讓 CI 裝那個 extra，要嘛承認那 2,900 個
statement 是分母裡的死重」。**維護者選了裝**，理由不是那一點覆蓋率：

`utils/remote_desktop` 底下有 **11 個模組在沒有 `aiortc`／`av` 時於模組層拋
ImportError**，共 2,090 個 statement——在 CI 上是硬性的 0%，寫什麼測試都動不了。
比數字嚴重的是另一件事：**涵蓋 WebRTC host 的 auth、TLS、resume token、檔案傳輸的
測試早就寫好了**，只是每一格都 `importorskip` 略過，等於只在開發機上跑過。

只換這一個變數實測（同一台機器、同一套測試）：那 2,090 個裡有 **513 個**是現有測試
就會蓋到的，端到端 +1.23 點（windows-2022／3.14）。相依在九宮格上都解得開
（`aiortc` 1.15.0 + `av` 17.1.0 對 win_amd64／manylinux x86_64／macos-14 arm64 的
3.10 與 3.14 都有 wheel）。`typing-stable-api` **刻意不裝**——那個閘門的判定不能隨
環境浮動，理由在下一節。

`dev_requirements.txt` 與 `CLAUDE.md` 的開發指令也跟著加了那個 extra：少裝它的人
量到的數字會比 CI 執行的地板低約 4 點。

#### 三個註冊表都掃過了，替身再往合約深一層

`test_adapter_registry_sweep.py` 之後又走了三步（做法見 [WHATS_NEW.md](WHATS_NEW.md)）：

| 這次多掃到的 | 為什麼原本掃不到 |
| --- | --- |
| 92 個 adapter：被呼叫者回傳專案 dataclass | `_value_for` 只認純量與容器，dataclass 直接被判成「模不出來」。現在從 dataclass **自己的欄位標注**造實例，於是 adapter 的 `.to_dict()` 也一起跑起來 |
| 101 個 adapter：被呼叫者是模組層單例的方法 | 匯入的名字不是 function 而是 `default_observer`／`default_scheduler`／`registry` 這種物件。呼叫**單一**方法就是同一個轉接形狀往下一層，方法的標注就是合約；呼叫兩個以上算編排，仍然排除 |
| 31 條 REST 路由 | `rest_handlers` 是同一形狀的第三個註冊表，而現有的 REST 測試走 HTTP 層，在無頭 runner 上多半只是看著 handler 掉進自己的 `except` 回 500 |

REST 那一支的參數來自 `rest_openapi.build_openapi_spec()`——與 handler 不同檔，
所以掃不出「拿被測程式當答案」的循環；順帶白拿一條契約測試：**路由表與 OpenAPI
文件必須描述同一組 API**，多一條少一條都當場紅。

三支共用的機器搬進 `test/unit_test/headless/_contract_sweep.py`，各自只留自己的
參數來源。

#### 現在的九宮格（2026-08-24 實測，本 PR 最後一次 run）

| | 最低 | 最高 |
| --- | --- | --- |
| 上一版（PR #486 首輪） | 69.67%（ubuntu-22.04／3.14） | 70.97%（windows-2022／3.12） |
| 這一版 | **75.79%**（ubuntu-22.04／3.14） | 76.99%（windows-2022，3.11／3.12） |

地板隨之從 69 提到 **75**。這九個數字讀的是 `coverage report`（也就是
`fail_under` 真正比對的那個），不是 artifact 的 `line-rate`——理由見上一節。

#### 剩下的 4 點在哪裡（2026-08-24，ubuntu-22.04／3.14 的 artifact）

以下是 statement 數（artifact 的口徑，不含分支），拿來看缺口分佈：

| 子系統 | 沒蓋到 / 總 statement | 覆蓋率 |
| --- | ---: | ---: |
| `utils/remote_desktop` | 2,297 / 6,622 | 65.3% |
| ~~`utils/accessibility`~~ | ~~824 / 1,397~~ | **2026-08-24 補完（backends 全數 99–100%）** |
| `utils/executor` | 653 / 3,906 | 83.3% |
| `utils/usb` | 573 / 2,137 | 73.2% |
| `utils/mcp_server` | 573 / 4,618 | 87.6% |
| ~~`wrapper/window_backends`~~ | ~~361 / 477~~ | **2026-08-24 補完（100%）** |
| ~~`utils/hotkey`~~ | ~~221 / 426~~ | **2026-08-24 backends 全數 100%** |
| `utils/rest_api` | 146 / 808 | 81.9% |

**要動地板，只能補在每一格都跑得到的程式碼上。** 地板取的是最低那一格，
所以只在 Windows 跑得到的東西補再多也不會動它。把九格的未覆蓋行取交集，
2026-08-24 量到 **9,343 個 statement 在每一格都沒被執行過**——那就是可攜的缺口，
也是唯一會抬地板的地方。最大的幾塊：

| 檔案 | 每一格都沒蓋到 | 備註 |
| --- | ---: | --- |
| `utils/executor/action_executor.py` | 589 | 掃不到的那批 adapter：被呼叫者是 class（沒有回傳標注可讀）、或 adapter 伸手進兩個模組 |
| ~~`utils/accessibility/backends/windows_backend.py`~~ | ~~446~~ | **2026-08-24 補完（99.42%）**，順便修掉 37 個攔不到 `COMError` 的 except |
| ~~`utils/remote_desktop/webrtc_viewer.py`~~ | ~~354~~ | **2026-08-24 補完（100%）** |
| ~~`utils/remote_desktop/webrtc_host.py`~~ | ~~351~~ | **2026-08-24 補完（100%）** |
| `utils/mcp_server/tools/_handlers.py` | 348 | 同 `action_executor.py` |
| `utils/remote_desktop/signaling_server.py` | 155 | **CI 動不了**：要 `[signaling]` extra（fastapi／uvicorn），沒裝 |
| ~~`utils/remote_desktop/multi_viewer.py`~~ | ~~146~~ | **2026-08-24 補完（100%）** |
| ~~`wrapper/window_backends/x11_backend.py`~~ | ~~133~~ | **2026-08-24 補完（100%）**。「只有 Linux 那兩格跑得到」是錯的，見下 |
| ~~`utils/accessibility/backends/linux_backend.py`~~ | ~~132~~ | **2026-08-24 補完（100%）** |

**下一步的順序**：

1. ~~`webrtc_host`／`webrtc_viewer`／`multi_viewer`／`webrtc_transport`／
   `webrtc_audio`~~ **2026-08-24 做完**，見下一節。
2. 掃不到的那批 adapter：目前卡在「被呼叫者是 class」。要嘛從 class 自己的方法標注
   長出一個替身物件，要嘛承認那批不掃——**得先決定，因為前者會讓「跑起來了」和
   「驗到了東西」分家**。
3. ~~`wrapper/window_backends` 與 `utils/accessibility`~~
   **2026-08-24 兩個都整包補完**，見下下節。

`utils/office`（77）與 `signaling_server`（155）**不要碰**：`quality.yml` 沒裝
`[office]`／`[signaling]`，補的測試會整批 skip，對地板一個點都不動。要補之前
先照 `[webrtc]` 的先例把 extra 加進 CI。

#### 2026-08-24：WebRTC 那一族補完了，而「先拆一半」是問錯了問題

上面第 1 項原本寫著「`webrtc_host` 與 `webrtc_viewer` 是兩個大類別，
**先看能不能拆出可測的那一半**」，理由是那兩個 mixin
（`webrtc_host_auth`／`webrtc_host_media`）是拆出來才測得到的先例。
**實際去看之後發現不必拆**：兩個類別的建構子都不碰 aiortc——主機只存下 config、
RateLimiter 與 SessionPermissions，檢視端只存下 callback——而每一個協作對象
（`RTCPeerConnection`、`ScreenVideoTrack`、asyncio 橋接、稽核記錄）都是
模組層名稱或建構參數，換掉就好。擋在 19.83%／14.08% 的從來不是類別的形狀，
是「要跑到第一行得先站起一個 PeerConnection、一個螢幕擷取器和一條背景事件迴圈」。

| 模組 | 之前 | 之後 |
| --- | ---: | ---: |
| `webrtc_host.py` | 19.83% | **100%** |
| `webrtc_viewer.py` | 14.08% | **100%** |
| `multi_viewer.py` | 21.24% | **100%** |
| `webrtc_audio.py` | 0.00% | **96.27%** |
| `webrtc_transport.py` | 27.89% | **88.84%** |

沒補完的兩塊是刻意的：`webrtc_transport._get_cursor_position` 是三條平台分支，
任何一格只跑得到自己那條；`webrtc_audio._enqueue` 裡兩個吞掉的 queue 競態
只有「謊報自己滿了的 queue」造得出來，那是在測替身不是在測程式。

替身集中在 `test/unit_test/headless/_webrtc_doubles.py`（形狀比照
`_contract_sweep.py`），六個測試檔共用；`FakePeerConnection` 刻意把主機端與
檢視端的介面放在同一個類別裡——它替的是同一個 aiortc 型別，照方向拆成兩個
只會讓兩份替身各自漂走。

**要拆的是測試檔，不是被測的類別**，因為 `CLAUDE.md` 的 750 行上限對新檔案
沒有例外。主機拆成 `test_webrtc_host_session.py`（557，offer／answer／狀態／拆除）
與 `test_webrtc_host_channels.py`（739，四條 DataChannel、權限、限流、收件匣）；
檢視端拆成 `test_webrtc_viewer_session.py`（466）／
`test_webrtc_viewer_media.py`（385，m-line 位置與開關）／
`test_webrtc_viewer_control.py`（519）。

**地板還沒動。** 本機（Windows／3.14）全專案 77.04% → 79.40%，363 個新測試，
但地板取的是九宮格最低那一格，**要等 CI 的 `coverage report` 印出來才能改**——
這條規則在上面那節寫過，不從單機的數字推。

#### 2026-08-24：平台後端不是「只有那一格跑得到」，是沒人給過替身

上面第 3 項與缺口表都寫著 `x11_backend.py`／`linux_backend.py`
「只有 Linux 那兩格跑得到」。**實測是錯的**：`wrapper/window_backends/` 底下
八個平台模組，每一句 `import Xlib`／`import Quartz`／`import AppKit`／
`import ApplicationServices`／`import comtypes` **全部在函式內**，所以在一台
沒裝任何一個的 Windows 上這八個模組都 import 得起來——

```bash
python -c "import je_auto_control.wrapper.window_backends.x11_backend"   # 在 Windows 上就過
```

擋住它們的從來不是平台，是**沒有替身**。把套件塞進 `sys.modules` 之後，
同一份測試在九格都跑得到，而不是只有兩格；地板取最低那一格，所以
「九格都漲」比「兩格漲」更有意義。

| 檔案 | 之前 | 之後 |
| --- | ---: | ---: |
| `window_backends/x11_backend.py` | 0.00% | **100%** |
| `window_backends/macos_backend.py` | 0.00% | **100%** |
| `window_backends/__init__.py`（後端選擇） | 46.34% | **100%** |
| `window_backends/base.py` | 63.64% | **100%** |
| `window_backends/windows_backend.py` | 89.19% | **100%** |
| `window_backends/null_backend.py` | 100% | 100% |

**替身要對得上真貨，否則只是自己跟自己同意。** 兩支 stub 的處理不一樣，
因為兩邊的常數性質不同：

- `_xlib_stub.py` 的常數**帶真值**（`SubstructureRedirectMask` 就是 `1 << 20`），
  因為那些數字會真的上線；`test_xlib_stub_values.py` 在有裝 python-Xlib 的地方
  （CI 的兩格 Linux）逐一比對，對不上就當場紅。本機另外用
  `pip install --target` 拉 0.33 實測過一輪，12 個常數全中。
- `_pyobjc_stub.py` 的常數**是哨兵**，因為它們不是 dict key 就是原封不動傳回
  同一支 stub 函式的 token，數值到不了任何算術；`test_pyobjc_stub_names.py`
  改成在 macOS 那兩格比對**名字存在**，另外只釘那三個真的會做位元運算的
  window-list 旗標。

**一個踩到的坑**：`from je_auto_control.windows.window import windows_window_manage`
這種 `from 套件 import 名字`，Python **先用套件的屬性解析**，解析不到才回頭查
`sys.modules`。只把替身放進 `sys.modules["...windows_window_manage"]` 在
Windows 上完全沒效果——真的 Win32 模組會被呼叫。要換掉的是**那個套件**。

本機（Windows／3.14）全專案 79.40% → **80.22%**，184 個新測試。
地板一樣要等九宮格。

#### 2026-08-24：`utils/accessibility` 照抄同一招，並抓到 37 個攔不到的 except

同一個事實在這裡也成立——三個平台後端的 comtypes／pyobjc／D-Bus import
全在函式內，所以塞 `sys.modules` 就能在九格都跑：

| 模組 | 之前 | 之後 |
| --- | ---: | ---: |
| `backends/windows_backend.py` | 17.72% | **99.42%** |
| `backends/linux_backend.py` | 42.41% | **100%** |
| `backends/macos_backend.py` | 0.00% | **100%** |
| `backends/windows_query.py` | 24.75% | **99.01%** |
| `backends/windows_state.py` | 18.75% | **100%** |
| `backends/base.py` | 74.03% | **100%** |
| `backends/__init__.py` | 48.94% | **100%** |

剩的三行在 `_process_name` 的 Win32 失敗路徑（`OpenProcess` 成功但
`QueryFullProcessImageNameW` 失敗），要一個「開得到卻查不到」的行程才踩得到。

**AT-SPI 那一層要換的是 `SessionBus`，不是 `_AtspiConnection`。** 現有的
`test_accessibility_linux.py` 換掉後者，那對測「走訪」是對的，但底下整個
D-Bus 呼叫層一行都沒跑過——而協定就住在那裡（無障礙匯流排不是 session bus、
accessible 是 `(sender, path)` **配對**、狀態位元是**兩個 32-bit word**，
只讀第一個會靜靜丟掉第 31 位以上的每一個狀態）。

**寫測試時抓到一個真的錯，形狀和 WebRTC 那個一模一樣：攔截 tuple 漏了型別。**
comtypes 把 provider 失敗報成 `COMError`，而它直接繼承 `Exception`：

```python
issubclass(COMError, (OSError, AttributeError, ValueError, TypeError))  # False
```

`windows_query._uia_errors()` 存在就是為了講這件事，docstring 也點名了情境
（「視窗在走訪途中關掉，或應用程式停止回應」）。但 `windows_backend.py` 裡
只有**兩個**走訪用的 except 用了那個 tuple，**另外 37 個**——也就是每一個
control pattern——寫的是 `(OSError, AttributeError, …)`，一個都攔不到。
race 很小但真實：`_find_raw` 自己會攔，所以曝露的是「找到之後、讀之前」
那一段。已全部改用同一個 tuple；這只會**放寬**攔截範圍。

#### 2026-08-24：`utils/hotkey/backends` 補完，**所有 backend seam 都有覆蓋了**

`CLAUDE.md` 列的 backend seam 有八個（accessibility／ocr／vision／llm／agent／
hotkey／usb／usbip）。ocr、vision、llm、agent 本來就只差個位數，
accessibility 與 window 這兩天補掉，剩下的就是 hotkey：三個平台、三套完全
不同的機制（`RegisterHotKey` + 訊息幫浦／`XGrabKey`／`CGEventTap` + run loop），
12.64%／24.46%／40.94% **全部到 100%**。

一樣都不需要桌面。Windows 那支把 `user32` 當**參數**傳給真正做事的三個方法，
所以錄音機式的替身在哪裡都能驅動；只有組出 `user32` 的開頭需要
`ctypes.wintypes`，那兩支測試標成只在 Windows 跑。

**又抓到一個真的錯，這次是資源洩漏。** X11 的 `_sync_one` 在 combo 改掉時
只把舊登記從自己的表裡拿掉，**沒有 `ungrab_key`**——舊的組合鍵於是一直被
grab 在 X server 上，被所有應用程式吞掉、什麼也不觸發，而且 `_ungrab_all`
關機時也放不掉（它已經不知道那筆了）。使用者把 `ctrl+alt+k` 改成別的，
`ctrl+alt+k` 就在整個桌面上死到行程結束為止。

同一個檔案其實知道這個形狀——`_grab_masked` 的回滾註解就寫著「留著不放、
`_registered` 又沒更新，會洩漏 grab 並在每次輪詢時噴 BadAccess」——而 Windows
那支一直都在同一個位置 unregister。漏的只有改綁定這條路。

X11 那批測試也把 Xlib stub 從 12 個常數長到 18 個外加一張 keysym 表，
全部照舊在 Linux 兩格對真貨比對（本機也用 python-Xlib 0.33 實測過：31 中 31）。

### mypy：整包把關，**豁免清單已經清空**

`TODO` → **完成（2026-08-22）**

範圍不再是兩條路徑，而是**整包減去一張只准變少的清單**
（`test/verify/typing_contract_exempt.txt`）。差別在於預設值：路徑清單只有人想到才會長，
新模組預設在圈外；現在新模組**預設就在契約裡**。

**2026-08-22 那張清單降到零**：`je_auto_control/` 的 1,018 個檔案在
win32／linux／darwin 三個目標上全部乾淨。清掉 136 個模組的過程與每一群的做法寫在
[WHATS_NEW.md](WHATS_NEW.md)；這裡只留下之後還用得到的五件事：

* **反覆出現的五種形狀**：mixin 讀取宿主的成員（用類別本體裡的
  `if TYPE_CHECKING:` 宣告，執行期會被剝掉）、`self._x = None` 沒有標注
  （mypy 會把屬性的型別判成 `None`）、`callable` 被當成型別用、
  `x: SomeType = None` 的隱含 Optional、以及掉了長度的 tuple。
* **攔截用的 tuple 必須標成 `Tuple[Type[BaseException], ...]`**，而且要收成一個
  模組常數——`except (A, B, *TUPLE)` 的星號解包 mypy 跟不進 `except`。
* **`# type: ignore` 只有當它是那一行的第一個註解時才生效**（已實測），所以有
  `# nosec` 的行要把它放前面。
* **`cv2` 的 stub 會隨版本變**：`pyproject.toml` 把它列在「ship no stubs 的基礎相依」
  底下，但 opencv-python 有附 `.pyi`，閘門會去讀。實測 4.13.0：`MSER_create`、
  `ORB_create`、`VideoWriter_fourcc` 執行期都在、stub 裡都沒有。`>=4.8,<6` 範圍內
  版本一換，判定就可能跟著動——與 numpy 那條註解同一類的坑。
* **要讓 mypy 剪掉一個分支，整條條件都得是它讀得懂的**：`sys.platform == "..."`
  與 `.startswith("...")` 算，`in [...]` 不算，而只要裡面**混進一個函式呼叫**
  （`is_windows()`），`or`／`and` 整條就變成未知、兩邊都會被檢查。所以
  `platform_wrapper` 那種「問 `platform_id` 才知道綁哪個後端」的分支**沒辦法**
  讓自己被剪掉——它綁的三種形狀互不相容，一個型別蓋不住。做法是那兩個名稱進來時
  先落在私有的 `Any` 上、出去時才標合約：後端那一側在 `_platform_*.py` 被檢查，
  呼叫端那一側在 `auto_control_*.py` 被檢查，中間那一接頭本來就沒有東西可查。
  細節見 `wrapper/backend_contract.py` 的 docstring。

清單現在只有標頭、沒有任何條目。**它變長就是退步**，`typing_contract_verify.py`
會在有人讓它變長時紅掉。

#### 已拍板（2026-08-22）：Win32 ctypes 表面用 28 個逐行抑制解決

原本這裡是一條 `DECIDE`，寫的是「`windows/` 底下 8 個模組」。重新實測後是
**16 個模組**，而且**一半不在 `windows/` 底下**（`utils/trash/`、`utils/app_idle/`、
`utils/file_assoc/`、`utils/idle_keepawake/`、`utils/lock_session/`、
`utils/session_guard/`、`utils/usb/passthrough/key_provider.py`、
`gui/main_window.py`）——這一點直接否掉了原本推薦的那一條（照目錄決定用哪個平台量，
分不到這八個）。

**維護者選了逐行 `# type: ignore` 附理由**，實際只用了 **28 行**（原本估的 58
是把同一行在 linux 與 darwin 各算了一次）。做法見 [WHATS_NEW.md](WHATS_NEW.md)，
兩件必須實測的事記在這裡免得再踩：

* **mypy 只認每一行的第一個註解**——接在既有 `# nosec` 後面的 `# type: ignore`
  完全不生效（已實測）。所以有 `# nosec` 的那兩行，marker 放前面、兩個理由併成一句。
* 有九行放不進 120 字元，是**改寫**而不是把理由砍到看不懂：括號換行時 marker 跟著
  左括號走，兩處先把值取出來成區域變數（DPAPI 的 `last_error`、input hook 的
  `kernel32`），讀起來比原本的一行式更清楚。

十六個模組事後都在真的 Windows 機器上重新 import 並實際呼叫過
（`dpapi_available()`、`_windows_locked()`、`check_key_is_press`）——
只有型別檢查器驗過的改寫等於沒人驗過。

有一件事別再踩：**這個閘門的判定不能隨環境浮動**。裝了 `[gui]`／`[webrtc]` 的開發機
與乾淨的 `pip install -e .` 曾經對 38 個模組看法不同（36 個 Qt 模組只在 PySide6
*不在*時才過關，2 個只在 babel／pytest 不在時才失敗）。修法是把所有非基礎相依的
第三方模組壓成 `Any`；其中 `follow_imports = "skip"` 對 `.pyi` 無效、必須同時開
`follow_imports_for_stubs`，正是 numpy 那條註解早就寫過的坑。

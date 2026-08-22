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

## 兩個門檻：機制已經有了，剩下的是把數字往前推

`TODO` — 兩者都已經從「講好要爬」變成「有棘輪在擋」，但都還沒到目的地

原本這一條記的是兩個只存在於 `pyproject.toml` 註解裡、沒有任何機制的承諾。
2026-08-21 把**機制**補上了（做法見 [WHATS_NEW.md](WHATS_NEW.md)），所以這裡改記
還差多少、以及下一步怎麼走。

### 覆蓋率：地板 50，目標 70

`fail_under` 從 35 提到 **50**。35 是第一次實測的基線，之後測試長大了它卻沒動，
於是有 15 個百分點是白讓的：九宮格矩陣每一格都在 50% 以上，而 CI 會放行一個
把三分之一測試刪掉的改動。現在的地板取自矩陣**最低**的那一格
（ubuntu-22.04／3.10，50.26%；最高的是 windows-2022／3.14，51.69%）。

規則寫進註解了：**這是棘輪，不是目標**——測試賺到了就把地板提上去。
往 70 的路上還差 20 點，而覆蓋率排除了 `gui/` 與 `language_wrapper/`，
所以剩下的缺口都在 `utils/` 的無頭模組裡。**下一步**是找出跌破平均的大模組
（`--cov-report=term-missing` 已經開著，CI 每一格都存了 `coverage.xml` artifact），
而不是齊頭式地補測試。

### mypy：整包把關，108 個模組還沒過

範圍不再是兩條路徑，而是**整包減去一張只准變少的清單**
（`test/verify/typing_contract_exempt.txt`）。差別在於預設值：路徑清單只有人想到才會長，
新模組預設在圈外；現在新模組**預設就在契約裡**，1,017 個檔案有 909 個已經過關。

`wrapper` 那一群（6 個模組）在 2026-08-21 清掉了，做法見 [WHATS_NEW.md](WHATS_NEW.md)：
平台縫的八個匯出名稱先宣告型別、再讓分支去綁定，其中三個用
`wrapper/backend_contract.py` 的 Protocol，四個 `_platform_*` 組裝模組各自標注自己綁了什麼。
順帶帶綠了四個原本卡在縫的偶然型別上、自己其實沒問題的模組
（`utils/cv2_utils/screen_grabber`、`utils/executor/mouse_aliases`、
`utils/pytest_plugin/keywords`、`utils/vision/vlm_api`）。

`linux_wayland` 那一群（4 個模組）在 2026-08-22 清掉了：`libei` 的 33 處
`Optional[BoundSymbols]` 改走一個會拋 `LibeiUnavailable` 的存取器（`_api`），
`_detect` 的兩支環境查詢收 `Mapping[str, str]` 而不是 `dict`（預設值就是 `os.environ`），
`capture._write_to_temp_png` 承認它的 writer 會回傳東西而它不看，
`screen.get_pixel` 把 Pillow 那個「每種 mode 的答案聯集」收斂成它自己承諾的三元組。
做法見 [WHATS_NEW.md](WHATS_NEW.md)。

`linux_with_x11`（3）與 `osx`（1）同日清掉：X11 listener 的 `record_queue`
從「型別是 None」變成 `Optional[Queue]`（`stop_record()` 因此不再回一個
簽章不承認的 `None`），`uinput/_device` 的 POSIX 專屬 `O_NONBLOCK` 收進一個
mypy 剪得掉的 `sys.platform` 分支，`osx_keyboard` 的字串 keycode 一律當特殊鍵名。

`windows/` 這一群的**真實錯誤全部清掉了**：`window_message` 匯入一個
`windows_window_manage` 根本沒有匯出的名字（`FindWindowW`），所以那個模組在
Windows 上一直是 import 就炸；`win32_ctype_input` 則有一批標錯的註記
（`_fields_: tuple` 把 ClassVar 重新宣告成 instance variable、`ctypes.POINTER`
與 `user32.SendInput` 被當成型別用）以及一行改寫標準函式庫的
`wintypes.ULONG_PTR = wintypes.WPARAM`——全樹沒有任何地方讀它。
**以 `--platform win32` 檢查時，`je_auto_control/windows/` 底下已經零錯誤。**
剩下的豁免是下面那條 `DECIDE`。

`utils/remote_desktop` 那一群（13 個模組、169 個錯誤，曾是最大的一群）在
2026-08-22 清掉了，錯誤只有兩種形狀：九個模組是 `self._x = None` 沒有標注
（mypy 就把那個屬性的**型別**判成 `None`），其中好幾個把想要的型別寫在行尾註解裡
——事實一直都在，只是寫在沒有檢查器讀得到的地方；另外四個是 mixin 讀取
自己不擁有的屬性，而每個 mixin 的 docstring 早就列出它跟宿主借了什麼，
現在那份清單變成類別本體裡的 `if TYPE_CHECKING:` 宣告（執行期會被剝掉，
所以不可能蓋掉宿主真正綁的東西）。順帶修掉三個行為問題：
`WebRTCLoopBridge._run` 從共用狀態讀 loop、`_get_cursor_position` 在函式內
`import sys as _sys` 導致 mypy 剪不掉平台分支、`totp` 接的是
`base64.binascii.Error`（那個名字只是 `base64` 自己 import 的副作用）。
做法見 [WHATS_NEW.md](WHATS_NEW.md)。

同日再清掉十五個：`utils/accessibility` 那一群（5）、`utils/observability`（3）、
`utils/triggers`（3）、`utils/chatops/router`、`utils/rest_api/rest_server`、
`utils/mcp_server/http_transport`、`utils/element_repository`。四十三個
accessibility 錯誤裡有三十四個是同一個沒標的回傳型別（`_unsupported` 一定會拋，
標成 `NoReturn` 就全清）；另一個反覆出現的是**攔截用的 tuple 沒有被標成 tuple**
（`Tuple[type, ...]` 不算「a tuple of exception classes」，
`except (…, *SQLITE_ERRORS)` 的星號解包 mypy 也跟不進 `except`）。
順帶修掉四個行為問題：`Gauge`／`Histogram` 用
`_labels_key = Counter._labels_key` 借方法、`parse_content_length` 宣告的
`Mapping[str, str]` 三個呼叫端一個都沒給過（給的是 `email.message.Message`）、
`ElementRepository` 把使用者可編輯的 locator 直接 `**kwargs` 丟進無障礙 API、
`_AtspiConnection._call` 在 `with` 之外沒有 bus 可以呼叫。
做法見 [WHATS_NEW.md](WHATS_NEW.md)。

剩下 108 個模組要清。錯誤碼分布是 `attr-defined` 佔大宗，其次
`arg-type`／`union-attr`／`assignment`，成群集中在
`gui`（11＋`gui/remote_desktop` 2）、`utils/mcp_server`（4）、
`utils/usb/passthrough`（4）、`utils/clipboard`（2），其餘散在各處。
以檔案計最大的三個是 `utils/usb/passthrough/winusb_backend.py`（34）、
`gui/_auto_click_tab.py`（31）、`gui/remote_desktop/webrtc_panel.py`（27）。
**下一步**是一次清一個群集，清完把行從清單刪掉——
`python test/verify/typing_contract_verify.py --fix` 會替你改，CI 會在你忘了刪的時候紅掉。
已經清掉的那些留下四個可以直接套用的樣板：mixin 用 `if TYPE_CHECKING:` 宣告
借來的成員、`Optional` 屬性用 `TYPE_CHECKING` 匯入真正的型別去標注、
一定會拋的 helper 標 `NoReturn`、攔截用的 tuple 標
`Tuple[Type[BaseException], ...]` 並收成一個模組常數（不要在 `except` 裡星號解包）。

#### 平台縫還缺的一半：`keyboard` 與 `mouse` 還沒有合約

`TODO` — 八個匯出名稱裡剩這兩個，而它們是被呼叫最多的兩個

`screen`／`keyboard_check`／`recorder` 有 Protocol，少一個成員就在該後端自己的檔案裡紅掉。
`keyboard` 與 `mouse` 維持 `Any`（這也正是 mypy 本來就替它們推出來的型別，沒有變弱），
因為**四個後端的呼叫形狀真的不一樣**——以下是實測簽章：

| 後端 | `press_key` | `press_mouse` | 滑鼠鍵代碼 |
| --- | --- | --- | --- |
| Windows | `(keycode)` | `(press_button: Tuple[int, int, int])` | 三個 Win32 事件旗標的 tuple |
| macOS | `(keycode, is_shift)`（`is_shift` **沒有預設值**） | `(x, y, mouse_button)` | int |
| X11 | `(keycode)` | `(mouse_keycode)` | int |
| Wayland | `(keycode)` | `(mouse_keycode)` | int |

一個 Protocol 描述不了這四種，要補起來得每個平台一組、用 mypy 認得的
`sys.platform` 分支去定義（只認 `== "..."` 與 `.startswith("...")`，`in [...]` **不算**，
已實測）。**前置條件已經備好**：`wrapper/` 裡分辨 macOS 的地方現在一律寫成
`sys.platform == "darwin"`（與 `is_macos()` 等價但剪得掉），其餘分支問的是輸入堆疊
（`is_windows()`／`is_x11_unix()`），所以呼叫端這一側不必再改。

真正的成本在後端那一側：四個平台的 `keyboard`／`mouse` 模組本身都還在豁免清單上，
Protocol 一旦標上去，它們的內部型別錯誤就會一起浮出來。`linux_wayland`、
`linux_with_x11`、`osx` 都已經清完，而 `windows/` 的**真實**型別錯誤也清完了
（見上），只剩下面那條 `DECIDE` 的 ctypes 表面問題。所以前置條件實質上已經到位，
可以開始標 Protocol；下一次動這條的人不必再等別的群集。

#### `DECIDE`：16 個模組的豁免不是它們的錯

**2026-08-22 重新實測，這一條的規模比原本寫的大一倍，而且形狀不同。**
原本寫的是「`windows/` 底下 8 個模組」；實際上是 **16 個模組、58 個錯誤**，
而其中**一半不在 `windows/` 底下**：

| 模組 | 錯誤數 |
| --- | ---: |
| `windows/record/win32_input_hook.py` | 8 |
| `utils/usb/passthrough/key_provider.py` | 8 |
| `windows/core/utils/win32_ctype_input.py` | 6 |
| `windows/core/utils/win32_keypress_check.py`、`windows/interception/_dll.py`、`windows/mouse/win32_ctype_mouse_control.py`、`windows/screen/win32_screen.py`、`windows/window/windows_window_manage.py` | 各 4 |
| `windows/interception/mouse.py`、`gui/main_window.py`、`utils/app_idle/`、`utils/file_assoc/`、`utils/idle_keepawake/`、`utils/lock_session/`、`utils/session_guard/`、`utils/trash/` | 各 2 |

這 16 個模組在 `--platform win32` 上**全部乾淨**，在 linux／darwin 上的錯誤
**100% 是同一件事**：`ctypes` 的 Win32 專屬表面（`windll`、`WinDLL`、
`WINFUNCTYPE`、`WinError`、`get_last_error`）在 typeshed 的非 Windows 目標上
根本沒有宣告。實測方式是把三個平台的結果對比，找出「win32 全綠、其他平台
只錯在這組名字上」的模組——結果是 16 個，沒有一個是「順便還有別的錯」。

**這件事會改動下面第四條的可行性**：`utils/app_idle/`、`utils/trash/`、
`gui/main_window.py` 這些不在任何平台目錄底下，所以「照目錄決定用哪個平台量」
的規則對它們無效。要嘛規則改成看模組內容（難自動判定），要嘛這八個走另一條路。

三條路都實測過，維護者挑一條：

| 做法 | 成本 | 實測結果 |
| --- | --- | --- |
| **剪掉模組本體**（`if TYPE_CHECKING and sys.platform != "win32": raise`） | 每個檔 2 行 | **不能用**。mypy 一旦把模組本體判為 unreachable，`from ... import user32` 的那一端就會拿到 `Cannot determine type of "user32"` [has-type]——把 18 個錯誤換成一串新的、而且落在原本乾淨的模組上。 |
| **一個 shim 模組**把 Win32 專屬的 ctypes 表面集中匯出，非 Windows 分支綁 POSIX 對應物 | 新檔 + 18 個呼叫點改名 | 可行，事實只寫一次；代價是為了型別去動輸入熱路徑的 `user32` handle 建立方式。 |
| **18 個 `# type: ignore[attr-defined]`** 各附理由 | 18 行註記 | 可行，執行期零風險；代價是 18 個抑制，且同一句話重複 18 次。 |

第四條是改閘門本身：讓 `typing_contract_verify.py` 只用模組自己的平台去量
平台專屬模組（`windows/` 只用 win32、`osx/` 只用 darwin、`linux_*` 只用 linux）。
（**但見上面那張表**：有八個受影響的模組不在平台目錄底下，照目錄分不到它們。）
這是三者裡最貼近事實的一條——拿 Linux 去檢查一個只跑得動在 Windows 的模組本來就沒有意義，
而閘門的 docstring 自己寫的多目標理由是「要讀得到平台分支後面的程式碼」，不是這個。
但它會改掉「清單上的模組＝在每個支援平台上都還沒過」這個既定語意，**所以要維護者拍板**。

推薦：第四條，其次是 shim。

有一件事別再踩：**這個閘門的判定不能隨環境浮動**。裝了 `[gui]`／`[webrtc]` 的開發機
與乾淨的 `pip install -e .` 曾經對 38 個模組看法不同（36 個 Qt 模組只在 PySide6
*不在*時才過關，2 個只在 babel／pytest 不在時才失敗）。修法是把所有非基礎相依的
第三方模組壓成 `Any`；其中 `follow_imports = "skip"` 對 `.pyi` 無效、必須同時開
`follow_imports_for_stubs`，正是 numpy 那條註解早就寫過的坑。

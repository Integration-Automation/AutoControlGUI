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
`utils/mcp_server/tools/_factories.py`（8,968,MCP 工具註冊表）、
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

## BSD 上只驗了「判定」，沒驗到「真的驅動輸入」

`TODO` — `.github/workflows/platform-smoke.yml` 的 `freebsd` job

`freebsd` job 在 runner 裡開真的 FreeBSD 14 VM，驗的是
`utils/platform_id`：`sys.platform` 真的長成 `freebsd14`、
`is_x11_unix()` 在上面回 True——也就是每個放寬後的守衛
現在問的那個問題，而這件事只有 BSD 能回答。

**沒驗到的是：X11 backend 在 BSD 上真的移滑鼠、真的送
按鍵。** 原因是量出來的，不是懶：import 任何
`je_auto_control` 底下的東西都會跑門面，而門面在
module scope import OpenCV 與 cryptography。這兩個都沒發 FreeBSD
wheel，改用 ports 裝（`py311-opencv`）拉出來的相依樹跑了
**五十分鐘還沒裝完**，只好取消。一個 smoke job 不能
花一小時。

要補這塊，需要的是一台已經裝好相依套件的真
FreeBSD（或者一個預先烤好依賴的自訂映像），而不是
另一個 CI 小技巧。跑的時候把下面這段跑完就算驗到：

```python
from je_auto_control.linux_with_x11.mouse import x11_linux_mouse_control as m
m.set_position(321, 123)
assert m.position() == (321, 123)
```

## Windows arm64 裝不起來，卡在 opencv-python

`BLOCKED` — 上游（opencv-python 沒有 win_arm64 wheel）

`windows-11-arm` 加進 `platform-smoke.yml` 的矩陣跑了一次，
結果是實測而不是推測：**opencv-python 並沒有發
win_arm64 wheel**，pip 回退到從原碼建，CMake 在 ARM64 上
configure 不起來，花了十二分鐘失敗。cryptography
也在同一輪裡被拉去建。

這不是 CI 設定問題，是**這個套件今天在
Windows arm64 上裝不起來**。所以那一格已從矩陣
移除，並把原因寫在 workflow 的註解裡；哪天上游
發了 wheel，把 runner 加回去就好。

**Linux arm64 是好的**——`ubuntu-22.04-arm` 兩個 Python 版本
都綠，macOS 本來就是 arm64。所以卡住的只有 Windows
這一個組合。

## macOS 的錄製器寫了，但接不上去

`TODO` — `osx/record/osx_record.py`、`osx/listener/osx_listener.py`

`OSXRecorder` 是完整實作，但 `wrapper/_platform_osx.py` 裡寫的是
`recorder = None`，所以它永遠不會被選到。這不是疏失：
`osx_listener.py` 在 **import 時**就呼叫 `NSApplication.sharedApplication()`，
而停止錄製要靠 `AppHelper.runEventLoop()`，那是一個會卡住呼叫緒的
事件迴圈。直接接上去會把這兩件事都搬進 `import je_auto_control`
的路徑上，那是回歸而不是修好。

要接上去得先把 listener 改成：不在 import 時建立 NSApplication，
且把 run loop 放到自己的執行緒。`docs/CAPABILITY_MATRIX.md` 的 Recorder
macOS 格寫的是 `unavailable`，跟現狀一致。

## `mouse_scroll` 的方向在三個平台上不是同一回事

`DECIDE` — `wrapper/auto_control_mouse.py::mouse_scroll`

Windows 與 macOS 用 `scroll_value` 的**正負號**決定捲動方向；Linux 不看正負號,
方向來自 `scroll_direction` 參數,值只取 `abs()`。後者是刻意的:負值以前會讓
`range()` 變空,結果是靜靜地什麼都不捲。

**問題在於:照 Windows 寫法寫出來的可攜程式碼,在 Linux 上不會往上捲,而是往下捲
同樣的次數。**沒有例外、沒有警告,方向就是反的——和 macOS 那個 `write("\b")`
變成打空白是同一類缺陷:靜靜地做了跟要求相反的事。

`x11-verification` job 現在把**實測到的**行為釘住了（四個方向各一項,外加
「負號不決定方向」一項）,所以哪天行為變了 CI 會當場說。要不要讓三個平台一致,
以及一致成哪一種,是相容性決定,需要維護者拍板:

- 讓 Linux 也認正負號 → 修好可攜性,但會改掉 `scroll_direction` 已文件化的語意;
- 維持現狀 → 就得在 `mouse_scroll` 的 docstring 與 README 明講這個平台差異;
- 折衷:正負號在三個平台都認,`scroll_direction` 只在 Linux 當預設方向。

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

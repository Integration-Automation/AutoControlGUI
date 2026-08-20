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

## Windows arm64 裝不起來——是兩個上游，不是一個

`BLOCKED` — 上游（`opencv-python` 沒有 win_arm64 wheel；`cryptography` 在安全下限之上也沒有）

`windows-11-arm` 加進 `platform-smoke.yml` 的矩陣跑了一次，
結果是實測而不是推測：**opencv-python 並沒有發
win_arm64 wheel**，pip 回退到從原碼建，CMake 在 ARM64 上
configure 不起來，花了十二分鐘失敗。所以那一格已從矩陣
移除，並把原因寫在 workflow 的註解裡。

門面已經不在 module scope import OpenCV 了（見
[WHATS_NEW.md](WHATS_NEW.md)），但這裡卡的不是 import
而是 **pip 裝不起來**：那幾個套件仍列在 `pyproject.toml`
的 `dependencies`，`pip install -e .` 第一步就會去建它們。

### 2026-08-20 重新實測：當初只數到一半

不必開 runner——`pip` 可以替別的平台解析，十秒就給出答案：

| 依賴 | win_arm64 | 實測 |
| --- | --- | --- |
| `opencv-python>=4.8,<6` | **沒有** | 任何版本都沒有，pip 回的是 `from versions: none`。`je_open_cv` 自己是純 Python，但它相依 opencv-python，所以一起卡。 |
| `cryptography>=48.0.1` | **沒有** | wheel 只出到 **46.0.3**，46.0.4 起上游就不再發 win_arm64。而 `>=48.0.1` 是 347ec1e 為了 GHSA-537c-gmf6-5ccf（high）訂的**安全下限**，不能為了 arm64 降回去。 |
| `pillow==12.3.0` | 有 | `pillow-12.3.0-cp3xx-win_arm64.whl` 一直都在。**原本這裡寫「把 OpenCV／Pillow 移到 extra」，Pillow 那半是猜的，它從來不是卡點。** |
| `mss`／`defusedxml`／`je_open_cv` | 有 | 純 Python。 |
| `PySide6==6.11.1`／`qt-material==2.17` | 有 | `[gui]` extra 在 arm64 上裝得起來。 |
| `aiortc` | **沒有** | 卡在傳遞相依 `google-crc32c`，與本專案的選擇無關；`av` 自己有 wheel。 |

**所以原本那句「把 OpenCV／Pillow 移到 optional extra，arm64 就能只裝輸入的部分」
是不成立的**——就算 OpenCV 移走，`cryptography` 還是會把 `pip install` 擋在同一個
地方，而它的下限是安全下限，沒有往下讓的空間。要真的讓 arm64 裝得起來，**兩個都得
離開必裝集合**；`cryptography` 今天被六個模組用到（`acme_v2`、`tls_acme`、
`action_signing`、`secrets`、`remote_desktop` 的加密錄影），那是比 OpenCV 更大的
相容性決定。沒有人要求之前不做。

重驗指令（不需要 arm64 機器，也不需要 runner）：

```bash
pip install --dry-run --only-binary=:all: --platform win_arm64 --python-version 3.12 --target /tmp/probe 'opencv-python>=4.8,<6' 'cryptography>=48.0.1'
```

兩行 `ERROR: No matching distribution` 就是現況。哪天其中一行不見了，就是上游發了
wheel，那時把 `windows-11-arm` 加回 `platform-smoke.yml` 的矩陣。

**Linux arm64 是好的**——`ubuntu-22.04-arm` 兩個 Python 版本
都綠，macOS 本來就是 arm64。所以卡住的只有 Windows
這一個組合。

## MCP 的破壞性動作確認,在 HTTP transport 上一次都不會觸發

`DECIDE` — 要嘛補上 session 身分,要嘛改成 fail closed;兩條都會動到行為

`JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1` 的用意是「每個 destructive 工具執行前
先問過人」。這件事在 stdio 上是好的,**在 HTTP transport 上一次都不會觸發**——
而且不是文件原本以為的「initialize 跟 tools/call 落在不同連線時才失效」,是**四種
組合全部失效**。實測(2026-08-20,真的 `HttpMCPServer`,真的 destructive 工具):

| 情境 | 結果 |
| --- | --- |
| 行程內(等同 stdio),同一個 server 物件 | 送出 `elicitation/create`,拒絕就不執行 ✅ |
| HTTP,plain POST,同一條連線 | **不問就執行** |
| HTTP,plain POST,兩條連線 | **不問就執行** |
| HTTP,SSE,同一條連線 | **不問就執行** |
| HTTP,SSE,兩條連線 | **不問就執行** |

原因有兩層,兩層都得處理:

1. `_maybe_confirm_destructive` 在 `self._writer is None` 時直接 return。plain POST
   的 `connection_scope` 沒有 writer(一次 request/response,沒有 server→client 通道),
   所以這條路連問的能力都沒有。
2. 就算是有 writer 的 SSE,`_dispatch_sse` 會把 `close_connection` 設成 True,
   `finish()` 接著呼叫 `forget_connection(id(self))`。而 connection scope 是用
   `id(self)`(TCP 連線)當 key,不是用 MCP session,所以 `initialize` 帶進來的
   `capabilities`(裡面才有 `elicitation`)在下一個 `tools/call` 一定已經被忘掉,
   於是走進「client 沒有 elicitation 能力」那條分支,留一行 INFO log 後**放行**。

也就是說,操作者設了這個變數、以為擋住了,實際上什麼都沒擋,而且只有 INFO log。
文件原本寫「gate every destructive tool」,只註明「舊 client 會 fall through」,
沒說 HTTP 上根本不會啟動——**這一半已經修好了**:兩份 `mcp_server_doc.rst` 都加了
warning,說明它目前只在 stdio 有效,HTTP 請改靠 bearer token 與綁 `127.0.0.1`。
`test_mcp_http_transport.py::test_destructive_confirm_gate_never_fires_over_http`
把現況釘住(plain POST 與 SSE 兩種),哪天有人補好了,那個測試會當場紅掉,
提醒他同一筆改動要把文件的 warning 跟本節一起改掉。

**還沒決定的是行為要往哪邊走**,兩個選項都不是純加法:

- **(A) fail closed** — 變數開著又問不到人時,直接拒絕執行 destructive 工具。
  最貼近操作者的意圖,改動也最小。但會翻掉現有的
  `test_destructive_confirmation_skipped_when_client_lacks_capability`,而且會擋掉
  今天所有沒有 elicitation 能力的 client(包含 HTTP 上的每一個)。
- **(B) 補上 `Mcp-Session-Id`** — 讓 scope 跟著 MCP session 走而不是跟著 TCP 連線,
  這樣 SSE 那條路才有機會真的問出來。這是 MCP 自己的答案,但這個 transport 是
  **刻意**做成 sessionless 的(`do_DELETE` 的註解就這麼寫),而 per-connection 隔離
  正是先前一次重構的重點,有 `test_r3_mcp_connection_isolation` 在守。要動得連那條
  隔離一起重新想,不能只是把 key 換掉。plain POST 就算有了 session 仍然沒有通道,
  所以 (B) 落地後,plain POST 還是得靠 (A) 收尾。

重驗方式:把上表跑一次即可,四種 HTTP 組合都應該是「不問就執行」。

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

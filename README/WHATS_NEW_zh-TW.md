# 本次更新 — AutoControl

## 本次更新 (2026-08-20) — 嬣稱支援的平台，這回真的量過了

整套測試一直只在 `windows-2022` 跑，另加容器裡一次 Linux
執行。macOS 只跑兩行指令。Wayland 有五個 job 對真的對等體
讀回輸入；X11——兩條 Linux 路徑中更老、部署更廣的那一
條——一個都沒有，而且套件裡每一條 X11 斷言都是對著
`python-Xlib` 的 mock 做的。

**測試套件現在真的在它宣稱支援的平台上跑。**
`pytest-headless` 改成 OS 矩陣；Linux 跑在真的 Xvfb 上而不是 Qt 的
offscreen，因為 X11 後端在 import 時就連線，offscreen 會將正好要找的
毛病蓋掉。第一輪就抓到兩個真的 macOS 缺陷：

- `write("\b")` 在 macOS 沒有任何按鍵路徑，會落到空白鍵
  fallback——要求退格，打出來的是空白。
- `system_profiler` 對 Apple 自家裝置回的是 **符號式** vendor
  id（`apple_vendor_id`），而那個欄位文件上寫的是四位十六進位。

**X11 的輸入現在從真的客戶端讀回。** 新的 `x11-verification`
job 跑在真的 Xvfb + 真的視窗管理員上，對照組來自受測對象以外的
程式碼：`xev`、ImageMagick 的 `import`、`xdotool` 與 `xdpyinfo`。
最值得點名的一項是 `synthetic NO`——`XSendEvent` 的事件帶的是
`YES`，大多數 toolkit 會直接丟掉，所以一個患患停止驅動真實
輸入的後端，在只數事件的檢查下仍然會全綠。

**macOS 在 CI 裡其實完全驗得了，跟一般假設相反。**
`macos-14` runner **兩個 TCC 權限都給**：擷取回來的是真像素而不是
被拒時的全黑矩形，`CGEventPost` 真的移得動游標且讀回完全相符，
AX 樹也走得出真的元素。這是先量再斷言的，而且探針在期望表
還是空的時候會拒絕通過。

### 視窗管理不再是 Windows 專屬

以前是：門面在 `sys.platform` 上分支，其他平台一律丟例外，
23 個 `AC_*` 指令跟對應的 MCP 工具在 macOS 與 Linux 上都是死的。
現在走平台縫：Win32、X11 的 EWMH、macOS 的 Quartz + 無障礙 API。

兩件只有真的視窗管理員才能披露的錯，第一版都錯了：

- **矩形是外框，不是客戶區。** Win32 的 `GetWindowRect`
  回的是外框，所有呼叫端都是照那個寫的。
- **移動必須走 `_NET_MOVERESIZE_WINDOW`。** 在 reparenting
  視窗管理員下，客戶端自己的 x/y 是相對於外框的；對 openbox
  要 (300, 220)，直接 `ConfigureWindow` 的結果是落在 (302, 260)。

### Linux 有無障礙後端了

之前完全沒有。新後端走 **AT-SPI2**——它是 D-Bus 協定而不是
函式庫，這就是它不用加新相依的原因：`pyatspi` 與
`gi.repository.Atspi` 是發行版套件，裝不進 venv。

拿真的 bus 跟真的 GTK 程式一驗，當場抓到 D-Bus 客戶端的一個缺口：
**它不會解有號整數**。portal 從來不需要，而 AT-SPI 的 extents 是四個
**有號**值——因為主螢幕左邊（或上方）的螢幕上，視窗坐標是負的。

### BSD 與 arm64

`platform_wrapper` 對非 win/darwin/linux 一律丟「unknown operating
system」，七個 X11 後端模組又各自帶一份同樣的 Linux 專屬守衛。
新的 `utils/platform_id` 是唯一的判定點，`freebsd` job 在 runner 裡開
真的 FreeBSD 14 VM，在真的 X server 上 import X11 模組並把游標移完讀回。
`ubuntu-22.04-arm` 加進 smoke 矩陣且全綠。`windows-11-arm` 試過後拿掉了，而重新實測又挖出當初漏掉的**第二個**卡點：opencv-python 任何版本都沒發 `win_arm64` wheel，cryptography 則從 46.0.4 起不再發，而本專案的下限 `>=48.0.1` 是安全下限（GHSA-537c-gmf6-5ccf），不能為了湊 wheel 往下讓。原本跟 OpenCV 並列的 Pillow 其實一直都有 arm64 wheel，從來不是卡點。這些都不需要 arm64 機器就驗得到——`pip install --dry-run --only-binary=:all: --platform win_arm64` 十秒給答案，指令已連同結論記在 `Progress.md`。


## 本次更新 (2026-08-19) — Wayland 兩個等人拍板的取捨,拍板了

`Progress.md` 上掛著兩個 `DECIDE`:缺的不是工，是決定。兩件事其實是同一個問題犯兩次
——一個合成器的設定,函式庫**量得到**卻**讀不回來**,所以它必須停止假裝自己知道。

- **指標加速度改成由操作者宣告,函式庫照信。** 量到的事實不變:
  `ydotool mousemove --absolute` 送的是相對移動,libinput 預設的 adaptive profile 會
  把它加成兩倍,而倍率沒有任何用戶端讀得回來。沒拍板的是「那要怎麼辦」——繼續警告後
  照送、直接拒絕、還是讓操作者自己講。直接拒絕會讓每一台沒有 `liboeffis` 的 Wayland
  機器整條 `set_position` 不能用,所以答案是宣告:
  `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat` 表示 ydotoold 的裝置已經關掉加速度,
  移動就靜靜地、準確地送出去;`=strict` 表示寧可拒絕這次移動,也不讓點擊落在別的地方;
  不設定就維持現在的「警告一次後照樣移動」,所以今天能跑的東西明天照樣能跑。
  值打錯會退回警告模式,**而且會講出來**——shell profile 裡的一個錯字,不可以靜靜地
  把一次移動升級成「可信賴的精確」。整個判斷只掛在 ydotool 這條路上;libei 在協定層
  本來就是絕對座標。
- **Wayland 擷取裡的軟體游標,寫進文件,不繞過。** 這是 `seat-verification` 順手量到
  的:專案裡沒有任何一條擷取帶 `-c`,也就是沒有人要求游標,而游標還是在圖裡。原因不在
  我們這邊——只要 backend 沒有游標平面,wlroots 就會畫**軟體游標**,而軟體游標是合成進
  輸出緩衝區的,`wlr-screencopy` 交出來的正是那一份。headless 永遠處在這個狀態;
  真桌面上只要跑 `WLR_NO_HARDWARE_CURSORS=1` 也一樣。Windows 的 BitBlt 與 X11 那條路
  都不含游標,所以這是**只在 Wayland 出現的不一致**;指標壓在目標上的時候,定位器、
  樣板比對與 OCR 看到的就是目標中間有一個游標形狀的洞。兩條繞法——擷取前把指標移開再
  移回來、或比對時把指標周圍遮掉——都得先知道指標在哪,而 Wayland 不讓用戶端讀游標
  位置;靠行程內的記錄去猜,使用者一動實體滑鼠就過期,而遮錯位置比看得見游標更糟。
  所以改成寫下來:寫進 capability matrix、三份 README,以及診斷包——`screen_capture`
  檢查現在會帶 `cursor_may_be_captured`,讓那份「解釋定位器為何失敗」的報告自己說出
  原因。檢查本身照量到的樣子斷言,哪天 wlroots 開始尊重 `overlay_cursor`,CI 會當場
  紅掉來通知我們。

## 本次更新 (2026-08-19) — 「會吃 libinput 裝置的合成器」只差三個環境變數

`ydotool mousemove --absolute` 不是絕對移動。它不送任何 ABS 事件:先在兩軸各送一次
`INT32_MIN` 的相對移動,把游標推到合成器夾取的那個角落,再把目標當成相對位移送出去。
**那個角落到底是哪裡**、以及**位移在路上被合成器做了什麼**,是 Wayland 輸入路徑最後
兩個沒有答案的問題——而且兩個都被記成「需要一台跑真桌面、會吃 libinput 裝置的 VM」。

- **兩個都不需要 VM。** wlroots 吃 `WLR_BACKENDS=headless,libinput`:輸出維持虛擬,
  輸入那一半是真的 libinput backend。libseat 的 builtin backend 不靠 logind 就能開
  裝置,而 `SEATD_VTBOUND=0` 讓它不要去搶一個容器根本沒有的 VT。第四個條件最容易漏:
  libinput 是透過 udev 列舉裝置,不是透過 `/dev`,所以 `systemd-udevd` 必須在 ydotoold
  建立裝置**之前**就已經在跑。四個都到位之後,ydotoold 的 uinput 裝置就是一個普通的
  seat 裝置,`grim -c` 會把游標合成進截圖裡,合成器就能用版面座標回答問題。
- **那個角落是版面的左上角,不是版面座標的 `(0, 0)`。** 只有在所有輸出都在非負位置時
  這兩點才是同一點。任何「主螢幕左邊還有一台螢幕」的桌面,兩者就差一個版面原點——所以
  在原點為 `-1280` 的版面上,沒有轉換的「版面 `(0, 0)`」會把游標送到**隔壁那台螢幕**,
  差 1,280 像素。`mouse.set_position` 現在會先減掉 `layout_origin()` 再交給 ydotool,
  這正是擷取路徑早就在做的同一個修正;兩條輸入路徑共用的那個查詢搬進了
  `linux_wayland/_layout.py`,libei 與 ydotool 不會再對「原點是什麼」各說各話。
- **剩下的距離則被指標加速度放大。** 送出去的位移是相對移動,所以 libinput 會加速它:
  對著真的 wlroots session 量到的是,預設的 adaptive profile 讓游標離那個角落的距離
  正好是要求的**兩倍**——因為 `--absolute` 的兩個事件送在同一個 frame 裡,速度直接把
  profile 打到上限。把 `accel_profile flat` 加上 `pointer_accel 0` 之後,同一個呼叫
  就精準到像素。ydotool 自己的 `--help` 一直都寫著「You need to disable mouse speed
  acceleration for correct absolute movement」;後端現在會每個行程記一次這個警告,而不是
  讓點擊安靜地落在錯的地方。函式庫這一側再多做不了什麼——那個倍率是合成器的設定,
  呼叫端讀不回來。
- **新的 `seat-verification` job 把這些全部釘住。** `docker/Dockerfile.seat` 跑的是
  擷取映像的同兩種版面,每種 14 項:sway 真的握著 ydotool 裝置、`--absolute (0, 0)`
  會把游標畫在版面的第一個像素上、關掉加速度後移動是一像素對一像素、沒轉換的
  `(0, 0)` 會打不中它指名的那台螢幕、`set_position` 減掉的正好是原點而且在兩台螢幕上
  都落在指定的像素、以及加速倍率就是量到的 2 倍。裡面沒有任何一項依賴游標主題:每個
  主張都是兩張截圖之間的差,游標圖片相對於熱點的偏移會自己抵銷掉。
- **順手抓到的一件事。** 在這台合成器上,`grim` 明明沒有要求疊上游標,截回來的圖裡
  還是有游標——因為只要 backend 沒有游標平面,wlroots 就會畫**軟體游標**(headless
  永遠如此,任何驅動不給平面、或使用者設了 `WLR_NO_HARDWARE_CURSORS=1` 的 session
  也是)。所有定位器、樣板比對與 OCR 都走同一條擷取,所以指標會在它壓著的東西上挖出
  一個指標形狀的洞。該檢查照量到的樣子記下這個行為,要怎麼處理則列進 `Progress.md`。

## 本次更新 (2026-08-19) — 擷取用的 portal 本來就不可能成功,真的 bus 講出來了

- **`xdg-desktop-portal` 的回答是「指名送給發出呼叫的那條連線」的訊號。**
  `Screenshot` 回的是一個 *request handle*,不是圖;圖稍後才以
  `org.freedesktop.portal.Request::Response` 送達,收件人是呼叫者的 unique bus name。
  bus 對指名訊息只送給收件人,所以別條連線再怎麼加 match rule 也接不到。
- **舊的做法是兩條連線。** 先起一個 `gdbus monitor` 子行程,再用第二次 `gdbus`
  呼叫發請求,然後拿兩條正規表示式去讀 monitor 的 stdout。每次 `gdbus` 都會用自己的
  unique name 開一條自己的連線,所以在聽的那個行程從來就不是收件的那個。在真的
  `dbus-daemon` 上量到的:monitor 看得到呼叫經過,之後什麼都不再印,擷取每次都走完
  整整 30 秒逾時。唯一看得到指名訊號的是完整的 bus monitor（`dbus-monitor`,它會向
  bus 要 `BecomeMonitor`）——為了一張備援截圖去換「觀察使用者 session bus 上每一則
  訊息」的權限,不划算。
- **這一層現在自己講 D-Bus,而且只用一條連線。** `linux_wayland/_dbus_client.py`
  是只用標準函式庫寫的 session bus 客戶端:連線、SASL EXTERNAL 認證、`Hello`、
  `AddMatch`、一次方法呼叫,然後讀到對得上的訊號為止。它刻意不是通用綁定——沒有
  property、沒有 introspection、不匯出物件、不傳檔案描述子（需要那一項的那一個呼叫
  仍然交給 liboeffis）。`portal.py` 會**先**用自己的 unique name 推算出 request path
  並訂閱,再發呼叫;portal 若不理會 `handle_token`,回傳的 handle 也會一起跟。
- **而且這是拿掉一個相依,不是加一個。** 這一層原本需要裝 `gdbus`（glib2),現在只要
  有 session bus 就行,所以這條最後備援的擷取路徑能用的桌面比以前**更多**。安裝提示
  與診斷檢查都改成這麼說了。
- **在真的 bus 上整條驗過。** 新的 `portal-verification` job 跑真的 `dbus-daemon`、
  真的 portal 實作與真的 client:擷取回來的 PNG 位元組解得開,而且就是 portal 畫的
  那幾個像素,路徑是含空白、percent-escape 過的,讀完之後 portal 那個檔案不見了。
  portal 沒能交出圖的每一種收場也都跑過——對話框被關掉、對話框一直開著、成功但沒有
  URI、URI 不是本機檔案——每一種都必須在 AutoControl 自己的時限內 fail closed。

## 本次更新 (2026-08-19) — RemoteDesktop portal 交握也從來不需要 GNOME VM

- **portal 是 D-Bus 介面,不是合成器功能。** 在 GNOME 與 KDE 上要接到 libei,得跑
  `CreateSession` → `SelectDevices` → `Start` → `ConnectToEIS`,最後由 bus 交出一個
  EIS 檔案描述子。這件事本來被記成「沒有 GNOME VM 就驗不到」,理由是
  `xdg-desktop-portal-wlr` 只做 ScreenCast 與 Screenshot、沒有 RemoteDesktop——那是把
  「沒有容器附一個」當成了「沒有容器當得了一個」。對 `liboeffis` 而言,誰佔住
  `org.freedesktop.portal.Desktop`、誰回答那四個呼叫,誰就**是** portal。
- **所以驗證自己去佔那個名字。** `docker/portal_server.py` 是一個跑在私有 session bus
  上的真 D-Bus 服務,它的 `ConnectToEIS` 交回去的是連到 `eis` 那個映像用的同一台真
  `libeis` server 的活連線。真的 `liboeffis` 跑完真的交握;出來的描述子承載得起一個
  真的 EI session;透過它送出的按鍵、絕對移動與按鈕邊緣,由對面一個獨立實作記錄下來。
- **它確定了什麼。** 四個呼叫依規範的順序、送到 client 自己推算出來的 request path;
  `SelectDevices` 要到的是鍵盤與指標、不多要——所以使用者被要求同意的範圍就是這個後端
  真正需要的範圍,`OEFFIS_DEVICE_DEFAULT` 也不是那個 `= 0` 的 all-devices 哨兵值;
  交回來的描述子是一個活的、由呼叫端持有並負責關閉的 socket——這正是把它交給
  `ei_setup_backend_fd`（一個會接管所有權的函式）之所以正確、而不是雙重關閉的原因。
- **以及每一種拒絕。** 同意對話框被關掉、對話框一直開著、描述子被扣住、portal 把
  session 關掉、portal 舊到根本沒有 `ConnectToEIS`、bus 上根本沒有 portal:每一種都
  必須在本專案自己的時限內變成拒絕,而不是卡住或悄悄降級。`OEFFIS_EVENT_CLOSED` 這條
  分支從來沒有 peer 驅動得了,現在有了。
- **仍然沒有宣稱的是什麼。** 同意對話框作為「對話框」本身。CI 裡沒有人去按它,所以
  真的 mutter 對話框長什麼樣、真人會讓它開著多久,那仍然是 mutter 的事。對話框
  *產生的東西*——准、拒、沉默——三種都跑過了。

## 本次更新 (2026-08-19) — 一件記錯了的套件事實

- **Debian trixie 有 `liboeffis`。** `Progress.md` 原本寫沒有,並據此推論 libei 快速
  路徑在 Debian／Ubuntu 上等於是關的。實測:`liboeffis1` 1.3.901-1 就在 trixie/main,
  提供 `liboeffis.so.1`。真正成立、而且對使用者真正有影響的是另一件事:它是**獨立的
  二進位套件**,`libei1` 並不相依於它——所以只裝 libei 的機器上 portal 這條路仍然是關
  的,`connect()` 會退回 GNOME 與 KDE 都不會開的 `eis-0` socket。要走快速路徑,
  `liboeffis` 得自己裝。

## 本次更新 (2026-08-19) — 主螢幕左邊多一台螢幕,Wayland 的擷取整條都讀錯

- **Wayland 沒有「單一螢幕」這回事,而唯一那個平面也不一定從 `(0, 0)` 開始。**
  合成器把所有 output 排在同一個平面上,只要有一台在原點的左邊或上面,這個平面的
  原點就是負的——那正是「我的第二台螢幕在左邊」對合成器的意思。sway 的 headless
  backend 收 `output HEADLESS-1 position -1280 0`,所以這是 CI 立得起來的版面:
  兩個 1280x720 的 output、一張 2560x720 的擷取、左上角那個像素在 x=-1280。
- **`size()` 回的是版面的右緣,不是寬度。** 它算的是各 output 的 `max(x + width)`,
  在上面那個版面是 1280,而 `grab_image()` 回來的畫面寬 2560。凡是把這兩者兜在一起
  的人都信了小的那個:mss shim 的 monitor 清單（連帶 `enumerate_monitors`）、螢幕
  錄影、WebRTC host、MCP 的 monitor 擷取,全都去要了一塊只有桌面一半大的矩形,
  然後當成整個畫面回報。
- **不能自己套區域的層級,裁切裁在錯的座標空間。** 只有 grim 吃幾何參數;
  gnome-screenshot、spectacle、portal 與 `JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND`
  都是把整個版面交回來、由 AutoControl 事後裁切。那個裁切用的是版面座標,而圖的
  (0,0) 是版面原點,所以要 `[-1275, 5, -1175, 55]`（左邊那台螢幕上的一塊）等於向
  Pillow 要一個在畫面左外側 1275 px 的方框,拿回來的是黑色填充。
- **而且比對到的東西會被回報在錯的螢幕上。** `grab_logical()`——樣板搜尋、OCR 與
  visual match 背後的那個擷取——的原點是讀 `GetSystemMetrics` 的,在 Windows 以外
  無話可說,於是一律回 `(0, 0)`,每個命中都被回報在實際位置的右邊 1280 px 處。
  這種錯的表現是「點到別台螢幕」,比「找不到」更難查。
- **修在接縫上,不是修在每個呼叫端。** Wayland backend 發布 `layout_origin()`;
  `size()` 回 bounding box 的**大小**;`grab_image` 裁切前先扣掉原點;
  `screen_grabber.backend_layout_origin()` 則是 `grab_logical` 與 mss shim 去問的
  那一個,讓「自己擷取螢幕的後端」有辦法說出這張畫面從哪裡開始。通用函式庫本來就
  看得見的後端（Windows／macOS／X11）什麼都不用發布,行為完全不變——原點只會被
  問到,不會被猜。
- **對真的合成器兩種版面都驗過。** `wayland-verification` job 現在把那 27 項檢查
  跑兩遍:一遍是兩個 output 從原點並排,一遍是左邊那個在 x=-1280。第二遍才是把
  負原點整條釘死的那一遍——grim 的負 `-g`、回報的尺寸、`layout_origin()`、
  mss shim 的 monitor 矩形、`grab_logical()` 的原點,以及把操作者自訂指令指向 grim
  之後、讓一張**真的**整版面 PNG 走過那條必須位移的裁切路徑。

## 本次更新 (2026-08-19) — 同一個版面問題的輸入側:libei 把移動悄悄丟掉了

- **落在所有 region 之外的絕對移動,libei 會直接丟掉,而且什麼都不說。**
  沒有回傳碼、沒有事件、呼叫端看不到任何錯誤——`ei_device_pointer_motion_absolute`
  就是不把這個事件送上線。`set_position` 於是像游標真的移動過一樣正常返回。
  這是對真的 EIS 對端量出來的,不是推論:裝置只提供一個 `(0, 0, 1920, 1080)`
  的 region 時,`(1919, 1079)` 會到,`(1920, 1080)` 在 server 端連一個事件都沒有。
- **而那些 region 所在的座標空間,不一定就是版面的座標空間。** region 的 offset
  是 `uint32`,所以沒有任何合成器**能**宣告一個在原點左邊或上面的 region——但本專案
  的版面空間是從 `layout_origin()` 開始的,只要有一台螢幕在主螢幕左邊就會變成負的。
  那正是擷取那一半剛修好的同一種桌面。於是兩半差了整整一個原點,也就是
  `get_pixel(x, y)` 與 `set_position(x, y)` 指到不同像素的那個情況——而本來會跑到
  隔壁螢幕的游標,實際上是安安靜靜地哪裡都沒去。
- **`LibeiBackend` 現在會讀裝置的 region,再把座標映射進去。** 綁上了
  `ei_device_get_region` 與四個 `ei_region_get_*`;`_region_point` 對有涵蓋的座標
  原樣送出,對沒涵蓋的改用扣掉版面原點後的座標再試一次,兩者都不涵蓋就拒絕。
  沒有宣告任何 region 的裝置接受任何座標,原樣通過——這一點同樣是量出來的,而那
  就是單螢幕的常見情況,一毛錢都不多花。
- **拒絕是有用的結果,不是失敗。** 它是 `LibeiUnavailable`,所以
  `_select_input.emitted` 會像處理「裝置被暫停」那樣,把這次移動交給 ydotool 那條路。
  libei 一直被寫成快速路徑而非唯一路徑;這個 bug 的真正問題是:被丟掉的移動從來
  到不了後備路徑,因為沒有人知道它被丟掉了。拒絕時也不會送 frame——什麼都沒有被
  緩衝,那裡送一個 frame 只會把上一次發送留在裝置上的東西提交出去。
- **版面原點只在座標沒中的時候才會去問。** 它要花一個 `wlr-randr` 子行程,所以不會
  出現在每一次普通滑鼠移動的路徑上;在 GNOME 與 KDE 上它回 `(0, 0)`——那在那裡是
  正確答案而不是退路,因為那些合成器自己就會把版面正規化。
- **`eis-verification` job 多了五項對真協定的檢查。** client 讀回來的 offset 就是
  合成器宣告的那個;位在 `x=1280` 的 region,往內 100 px 的點要送 `1380` 而不是
  `100`;libei 到今天仍然一聲不吭地丟掉 region 外的移動——這是整個防護所依據的量測,
  所以哪天 libei 改成夾取,這項會當場說出來;AutoControl 會拒絕這種移動而不是弄丟它;
  以及在原點為 `-1280` 的版面上,`(-1280, 10)` 到達 server 時是 `(0, 10)`。
  這個 job 現在跑 20 項。
- **這件事沒有解決的部分。** ydotool 的 `mousemove --absolute` 有它自己的原點——
  它夾到合成器的左上角,再把目標當成相對位移送出——那個角落是不是版面原點,仍然需要
  一台真的會吃 libinput 裝置的合成器才驗得到。它繼續留在 `Progress.md`,不會靠猜測
  去改。

## 本次更新 (2026-08-19) — ydotool 一直回報成功,其實什麼都沒做

- **`apt install ydotool`——這個 backend 自己印的安裝提示——裝到的版本跑不動它送的
  命令列,而且是用「回傳 0」來表達的。** ydotool 1.0 把整套 CLI 換掉了,而 Wayland
  backend 送的每一個參數都是那一版才有的:`mousemove --absolute`、`mousemove
  --wheel`、`click` 的十六進位位元遮罩（拆得開 press 與 release,拖曳整個建立在
  這上面）、以及吃數字 evdev 碼的 `key CODE:STATE`。Debian bookworm、Ubuntu 22.04
  與 24.04 到今天都還是把 0.1.8 叫做 `ydotool`。對真的 uinput 裝置實測:0.1.8 收到
  `click 0x40` **什麼事件都不送,回傳 0**;收到 `mousemove --absolute` 印
  `unrecognised option`,**一樣回傳 0**。而 backend 是用 `check=True` 判斷成敗的,
  只有非零才會拋。所以在這些發行版上,腳本沒點到、沒打到、沒移動,而每一次呼叫都回報成功。
- **舊版 CLI 現在在送出任何東西之前就被擋下。** `linux_wayland/_ydotool_cli.py`
  每個行程只判定一次（滑鼠與按鍵派送付不起每個事件一次 subprocess）,並在錯誤訊息裡
  給出三條路:裝 1.0+ 的套件、自己編、或 `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11`。
  兩個版本都沒有 `--version`,而 1.x 沒起 daemon 連 `--help` 都不回答,所以探測讀的是
  兩邊都會印、不需要 daemon、也沒有副作用的那一樣東西:無參數時的指令清單。認不出來的
  版本一律放行而不是擋掉,免得將來改了字樣的新版被過期的偵測器鎖在門外。
- **兩處安裝提示還錯在第二件事上**:Debian trixie 根本沒有 `ydotool` 套件。
  提示已改成點名真的有的發行版。

## 本次更新 (2026-08-19) — 驗 ydotool 從來不需要桌面,只需要一個讀取端

- **兩個驗證映像記下來的那個缺口,記錯了。** `Dockerfile.wayland` 與 `Dockerfile.eis`
  結尾都寫 ydotool「需要 /dev/uinput 以及一個會消費它的 seat」,而 `Progress.md` 把它
  排在「先建一台 GNOME VM」後面。seat 決定的是注入的事件**會不會送達某處**,不是它
  **能不能被觀察**:ydotoold 建的是普通的 uinput 裝置,kernel 會掛成
  `/dev/input/eventN`,讀那個節點就拿得回 ydotool 寫進去的 `input_event`。
  不需要合成器,不需要桌面 session,不需要 VM。
- **`docker/Dockerfile.ydotool` 與 `docker/ydotool_verify.py` 就是在 CI 裡做這件事,
  12 項檢查。** 過去只對著 mock 斷言的東西現在有答案了:`0xc0`／`0xc1`／`0xc2` 真的是
  BTN_LEFT／BTN_RIGHT／BTN_MIDDLE;拆邊的 `0x40` 與 `0x80` 真的只送 press 或只送
  release(`press_mouse` 與拖曳整個建立在這上面);`key 30:1 30:0` 真的帶的是數字
  evdev 碼;而**捲動正負號是量出來的,不再是假設的**——`-y 1` 到 kernel 是
  `REL_WHEEL +1`、`-y -1` 是 `-1`、`-x 2` 是 `REL_HWHEEL +2`,而且軸沒有互換。
  最後這一項正是捲動那次改動之後,`Progress.md` 一直標著「未實測」的假設。
- **第 12 項檢查驅動的是 backend 自己的函式,不是手寫 argv**,所以「ydotool 拿到這串
  命令列會做什麼」與「AutoControl 送的是什麼」是接起來的,不只是並排。
- **`mousemove --absolute` 送的並不是絕對事件**,這件事在信任它之前值得知道。
  ydotool 1.x 的裝置上沒有 ABS 軸:它先在兩條相對軸上送 `INT32_MIN`,靠合成器把它夾到
  左上角,再把目標當成相對位移送出去。所以 `set_position` 會落在你要的像素,**是因為
  那個夾取**。kernel 這一側現在釘住了;夾取本身是合成器的行為,仍然是開放項。
- **容器拿到的是 `/dev/uinput` 加字元主號 13,不是 `--privileged`。** ydotoold 是在
  容器起來**之後**才建輸入節點,`--device` 涵蓋不到,所以那個 job 只授予
  `--device-cgroup-rule 'c 13:* rmw'`,別的都沒有。

## 本次更新 (2026-08-19) — Wayland 的捲動不再需要 uinput 常駐程式

游標移動、按鍵、按鈕早就走 libei 了,只剩捲動每一格都還要 fork 一次 `ydotool`,
而 `Progress.md` 也寫了原因:正負號是猜的,而捲錯方向不會噴錯,只會安靜地錯。
現在接上了,猜測也換成了兩份獨立佐證加一次實測。

- **兩條路徑對「一格」的正負號定義相反。** 本專案的 `wayland_scroll_direction_*`
  常數是 kernel `REL_WHEEL` 那一套,因為 ydotool 寫進 `/dev/uinput` 的就是它:正值為上。
  libei 是 `wl_pointer`／libinput 那一套,正值為下——libinput 自己的 evdev 讀取端
  就是把 `REL_WHEEL` 取負號換過去的,而另一個有寫明正負號的 libei sender（enigo）
  則是把「正值往下捲」的值原封不動送進 `scroll_discrete`。水平軸不用翻:
  `REL_HWHEEL` 與 libinput 都以右為正。所以送往 libei 時垂直軸取負、水平軸不動——
  這就是 `Progress.md` 在等的那個決定。
- **這個翻轉有對著真的 EIS server 驗,連負值一起。** `docker/eis_verify.py` 多了第 15 項
  檢查,驅動的是**公開的** `mouse.scroll()`（不是上一項檢查驅動的 backend 方法）,
  從 server 端讀回來:上是 `(0, -120)`、下是 `(0, 120)`、右是 `(120, 0)`。這也是唯一
  一次把**負的**離散值送上線;先前那項檢查只送過正值,正負號的 marshalling 若有毛病
  根本沒有地方會現形。
- **被拒絕的發送現在會退回 CLI,也就是程式碼一直宣稱的行為。** `libei` 的模組
  docstring 寫著每個失敗都拋 `LibeiUnavailable`,「`keyboard`／`mouse` 已經把它當成
  *改用 ydotool CLI*」。實際上只有**連線**是這樣處理的。backend 交出去之後,合成器
  暫停了裝置、或 session 在兩次呼叫之間結束,都會直接從 `set_position`、`press_key`、
  `hotkey` 拋出去。把捲動也接上 libei 等於再多一條「明明旁邊就有可用後備卻讓腳本死掉」
  的路,所以這個後備被補成真的:和弦中途被拒會先把已經按下的鍵反序放開,不會留下卡住的
  修飾鍵;按鈕的**放開**被拒則改由 ydotool 放開,不會整個 session 都按著。
- **`LibeiUnavailable` 原本會穿過所有的攔截邊界。** 它只繼承 `RuntimeError`,而
  `CLAUDE.md` 寫得很明白:不是 `AutoControlException` 的框架錯誤「會安靜地逃出每一個
  邊界」——executor、背景輪詢迴圈、請求處理器、GUI slot。現在兩個都繼承,原本接
  `RuntimeError` 的探測照舊能用,邊界也終於看得到它。

## 本次更新 (2026-08-18) — libei 輸入路徑終於有對手可以說話了

Wayland 的**擷取**路徑已經對著真的合成器驗過;**輸入**路徑沒有,而且被記成「需要一台
GNOME VM」。其實不需要。libeis 就是 libei 自己那套協定的 server 端,Debian 有打包,
兩個函式庫可以直接在一條 Unix socket 上對話——所以 `docker/eis_server.py` 起一個真的 EIS
實作,`docker/eis_verify.py` 把 AutoControl 真正的 sender 對著它跑。不需要合成器,
不需要桌面 session,14 項檢查,已接進 CI。

- **離散捲動差了 120 倍。** libei 的離散捲動以「一格的 120 分之一」為單位——跟 Windows
  `WHEEL_DELTA` 同一套慣例——而 `scroll()` 直接送格數,等於一格只送了 1/120 的捲動量。
  libei 自己在執行期就會講（`suspicious discrete event value 1, did you mean 120?`）,
  而這句話 mock 永遠不會印出來。現在 `scroll(0, 1)` 到對面是 `(0, 120)`:一格、正確的軸、
  正確的正負號。這條路徑原本因為「正負號是猜的」而刻意沒接線,結果正負號是這題裡比較小的一半。
- **拆除不再每個行程漏一個 context。** `ei_unref` 在 libei 1.3.901 會 segfault——但只在
  「backend 開了、握手從未推進」那個狀態。有了可以完成握手的對手,live 的情況終於測得到,
  而它是安全的。現在拆除會正常釋放 device 與 context,只有真的會炸的那個狀態才放棄。
- **mock 檢查不到的值都檢查了。** server 端 offer 六個 capability,再把 client 真正綁定的
  讀回來:正好是 AutoControl 要的那四個,所以 `EI_DEVICE_CAP_*` 位元遮罩與 variadic
  `ei_seat_bind_capabilities` 的編組都是對的。keycode、絕對座標、按鍵碼都從線上讀回來比對。
  每次發送都確認有 frame,每個 device 都確認有先開 emulation transaction——沒開的話
  libei 會把事件丟掉。
- **兩件量到但不是我們能修的事**,如實記下而不是含混帶過:libeis 1.3.901 的
  `eis_device_pause()` 對 sender client 沒有送出任何東西,所以 client 的 `DEVICE_PAUSED`
  處理仍然沒有對手可以驅動;`start_emulating` 的 sequence number 也沒有被送到對面
  （刻意送 4242,讀回來是 0）。檢查寫成「要嘛有反應,要嘛根本沒被通知」,
  哪天 libeis 開始送了而 client 忽略它,就會當場失敗。

## 本次更新 (2026-08-18) — 架構地圖的行數重新變成實測值

- **同一個子系統在地圖裡被寫成兩個不同的大小。** `CLAUDE.md` 規定
  `architecture_explore.md` 的每個數字都是實測的,但沒有任何東西在檢查,於是長出了
  兩套並存的計數慣例:§5.4 主題表與 §5.4.17 檔案表數了一行不存在的結尾行——
  `len(text.split("\n"))` 會比以換行結尾的檔案實際行數多一行,套件則是每個檔案多一行
  ——而 §1 的總計與 §8 附錄數的是對的。結果 `utils/executor/` 在一節裡是 8,811 行、
  在另一節裡是 9,001 行,而 §8 那一欄加起來也不等於它自己的總計。除此之外還有大約
  五十列根本是舊的,好幾個 `####` 標題差了幾百行（`linux_wayland/` 還寫著
  10 檔／1,093 行,實際是 14／2,235）,而且有一張主題表多了兩個子套件,它的摘要行
  完全不知情。
- **413 個數字用同一套慣例重新實測**——`len(text.splitlines())`,也就是 `wc -l` 的
  結果,以及 `CLAUDE.md` 自己那段「超過 750 行」判斷所用的算法。§5.4、§5.4.17 與 §8
  現在對每個子系統都一致,§8 各列加起來也等於它寫的總計。
- **`test_doc_line_counts.py` 既是閘門也是修復工具。** 任何被引用的行數跟樹上對不上
  就讓 CI 失敗,並指出是哪幾行;加 `--fix` 就一次全部就地改寫。行數是地圖裡唯一沒有
  閘門的部分——指令、MCP 工具、子套件與範例數早就有 `test_doc_counts.py` 在管——
  這正是它會漂掉的原因。

## 本次更新 (2026-08-18) — 剪貼簿不再因為別的程式正在複製而失敗

- **Windows 剪貼簿同一時間只允許一個行程開啟,而 AutoControl 的每一個剪貼簿呼叫
  在別人開著時都立刻放棄。** 檔案總管、Office 和每個瀏覽器複製時都會佔住剪貼簿
  幾毫秒,這段時間裡 `OpenClipboard` 一律回傳 false,而六個呼叫點——文字、影像、
  HTML、RTF、CSV、檔案拖放、格式列舉——都把它直接翻成
  `RuntimeError: OpenClipboard failed`。在真實桌面上開一個行程迴圈複製實測:大約
  千分之一的開啟會失敗,也就是腳本會因為操作者既看不見也重現不了的原因直接死掉。
  Win32 文件明寫這種情況應該重試,而一個專門用來驅動「別的程式本來就很忙」的機器
  的函式庫,不能把「別人正在複製」當成錯誤。
- **`win32_clipboard_api.open_clipboard()` 現在是唯一開啟剪貼簿的地方**,忙碌時會
  等約 200 毫秒才報錯,而且不論區塊怎麼結束都會關閉。三個自己手寫 open/close 的
  模組——包括兩個比共用模組更早寫的——都改走它,所以新的呼叫點不可能漏掉重試。
- **剪貼簿 round-trip 測試不再依賴機器上其他行程在做什麼。** 這些測試跑的是真實的
  Win32 呼叫,而那正是四個歷史 writer bug 唯一能被看見的地方,所以換成假的後端等於
  刪掉覆蓋率,而不是讓它穩定。改成讀 Win32 剪貼簿序號:寫入與讀回之間序號沒變,就
  代表這段時間沒有別人寫過,斷言測的就只有 AutoControl 自己的程式碼。已在另一個行程
  於測試期間寫入 4,112 次剪貼簿的情況下驗證通過。

## 本次更新 (2026-08-18) — 打錯指令名字回 400,不是 500

- **`POST /execute` 對不存在的 `AC_*` 名字回 `500 {"error": "execute_action failed"}`**,
  跟伺服器自己壞掉時的回應一模一樣。呼叫端無法區分「我自己打錯字」和「服務掛了」,
  錯誤訊息也沒說是哪個名字不認得。
- **所有指令名字現在都在執行前先校驗**,不認得的回 `400`,並在 `unknown_commands`
  裡列出**全部**——包含嵌在流程控制區塊裡的——讓呼叫端一次改完所有拼錯的名字。
  `POST /execute_file` 對讀不到的檔案、不是動作清單的內容、以及不認得的指令名,
  用同樣的方式回應。OpenAPI 規格兩者都寫明了,並說明被拒絕的請求沒有執行任何動作。
- 校驗與收集共用同一次走訪,所以「巢狀動作清單可能藏在哪裡」仍然只有一份定義。

## 本次更新 (2026-08-18) — libei 拆除時的 segfault,以及對真實函式庫的核對

- **`ei_unref` 在 libei 1.3.901 上,只要 backend 已開啟就會讓行程崩潰,而我們的
  fallback 路徑正好一頭撞進去。** libei 握手的每一種失敗都會走到 `_teardown()`,
  所以在任何裝了 libei 而握手沒完成的機器上,AutoControl 會直接 SIGSEGV,而不是
  安靜地改用 ydotool——跟 fail-closed 的承諾完全相反。逐個呼叫實測的結果:沒有
  setup backend 時 `ei_unref` 安全、setup **失敗**後安全、setup **成功**後必炸。
  `ei_disconnect` 在同樣狀態也炸,所以不是我們 refcount 用錯;而標頭檔明寫兩種結果
  都該用 `ei_unref`,因此這是上游的 bug。現在已開啟的 backend 會被**放棄**而不是
  unref——代價是每個行程漏一個 context,換掉一個會驅動使用者桌面的函式庫直接崩潰。
  驗證程式裡有一個哨兵會每次重新確認上游狀態,修好時會提示可以移除 workaround。
- **綁定裡每一個進入點現在都對真的 `libei.so` 解析過。** 拼錯的符號或錯的 `argtypes`
  會毫無阻礙地通過假的符號表,只在使用者的機器上才爆——22 個 prototype 加上 variadic
  的 `ei_seat_bind_capabilities` 現在都是真的驗過。
- **整條 fail-closed 鏈端到端跑過**:連到一個不說 EI 的 socket → 握手逾時 →
  `LibeiUnavailable` → `active_backend()` 回 None → `press_key` 落到 ydotool CLI。
- **`liboeffis` 不是每個發行版都有。** Arch 與 Fedora 有包,**Debian trixie 沒有**。
  沒有它就沒有 portal 路徑,`connect()` 會退到眾所周知的 EIS socket——而 GNOME 與 KDE
  根本不開那個 socket。所以在那些系統上 libei 快速路徑是關閉的,而且會講出來,不會
  看起來莫名其妙地沒作用。

## 本次更新 (2026-08-18) — Wayland 擷取路徑對上真的合成器了

- **`screen.size()` 報單一螢幕,`grab_image()` 卻回傳整個佈局。** `wlr-randr` 的
  parser 抓文件裡第一個 `WxH`,也就是第一個 output 的當前模式。雙螢幕佈局下那只有
  半個畫面——而 mss shim 正是把這兩者組起來用的,所以錄影、WebRTC 與 MCP 的螢幕路徑
  會去要一個只有半個畫面大的區域,而且真的拿到了。`size()` 現在回傳佈局的 bounding
  box,parser 會讀每個啟用中 output 的模式**與位置**。這個 bug 是跑真機才發現的:
  沒有任何 mock 有第二個螢幕。
- **`docker/Dockerfile.wayland` 讓後端在 headless sway 底下跑。** wlroots 的 headless
  backend 不需要 GPU、seat 或顯示器,所以一個真正的 Wayland session 塞得進容器——現在
  也進了 CI,就是 `wayland-verification` job。兩個 output 塗上不同純色,因為在單一顏色
  的畫面上,區域抓錯位置抓不出來,紅藍通道對調更是完全抓不出來。
- **21 項先前只能對 mock 驗的檢查,現在對的是合成器真的畫出來的像素**:grim 的 argv
  與 `-g` 幾何、RGB 通道順序、`wlr-randr` 沒有文件記載的輸出格式、
  `size()`／`grab_image()`／`get_pixel()`／`screenshot()`、
  `je_auto_control.screenshot()` 的 BGR 輸出、`grab_logical()`(定位器與 OCR 路徑)、
  mss shim、以及 `wtype`。
- **容器答不了的部分直接寫明,不含糊帶過。** ydotool 需要 `/dev/uinput`,而 headless
  sway 不吃 libinput 裝置;`xdg-desktop-portal-wlr` 沒有實作 RemoteDesktop,所以根本
  沒有 `ConnectToEIS` 可測。兩者都留在 `Progress.md`。

## 本次更新 (2026-08-18) — libei 輸入,整條打通

- **完整的 portal 握手做完了。** libei 不是「呼叫一個函式就按下一個鍵」的函式庫:
  sender 必須開啟 EIS backend、綁定 seat 的能力、**從事件裡**取得 device、在其上
  `start_emulating`,而且每次發送之後都要 `ei_device_frame`,否則什麼都不會送達。
  這些現在全部有了,所以 `press_key`、`set_position` 與滑鼠按鍵不再需要每個事件
  spawn 一次行程。
- **EIS socket 來自桌面 portal。** 在 GNOME 與 KDE 上它不是磁碟上的路徑,而是由
  `org.freedesktop.portal.RemoteDesktop.ConnectToEIS` 經 D-Bus 交出的 file
  descriptor,前面還有三次非同步的 session 呼叫。**沒有任何命令列工具能把 fd 交進
  這個行程**,所以截圖那條 `gdbus` 路在這裡走不通;改用 `liboeffis`(libei 專案正是
  為此附上它)。liboeffis 不存在時,仍會嘗試眾所周知的 `$XDG_RUNTIME_DIR/eis-0`。
- **device 一律來自事件,不再由 context 冒充。** 先前的綁定把 `struct ei *` context
  傳給收 `struct ei_device *` 的進入點——C 函式庫裡的指標型別混淆。現在從結構上
  不可能發生。
- **探測失敗只付一次代價,不是每次按鍵。** 握手包含一次 portal 往返,可能還有同意
  對話框。結果會在行程內快取,所以「裝了 libei 但不可用」的機器不會每次按鍵重試。
- **所有情況都仍會退回 ydotool。** 函式庫缺失、使用者拒絕、能力只給一半、device 被
  暫停、握手沒完成——每一種都丟 `LibeiUnavailable`,而 keyboard／mouse 本來就把它
  當成「改用 CLI」。scroll 刻意留在 ydotool:它的方向約定有測試釘住,而 libei 的正負號
  一旦猜錯是**靜默**的錯誤行為,不是明確的失敗。
- **ABI 常數是對過上游標頭檔的,不是猜的。** 對完發現三個錯:
  `enum ei_device_capability` 是**位元遮罩**,所以 `EI_DEVICE_CAP_KEYBOARD` 是
  `1 << 2` 而不是 3;`OEFFIS_EVENT_CLOSED` 排在 `OEFFIS_EVENT_DISCONNECTED`
  **之前**;`OEFFIS_DEVICE_ALL_DEVICES` 是 `= 0` 的哨兵值,不是各裝置位元的 OR。
  第一個代價最大——沒有 device 會回報那個能力,所以每次連線都會逾時然後靜默改用 CLI。
  核對過的值現在有測試釘住。另外 session 只申請實際會用到的鍵盤與指標,同意對話框
  不會再要一個沒人用的觸控螢幕授權。

## 本次更新 (2026-08-18) — Wayland 擷取有了保底

- **`xdg-desktop-portal` 為三個 CLI 工具兜底。** `grim`／`gnome-screenshot`／`spectacle`
  沒有任何一個保證會裝（GNOME 自 42 起不再預設安裝 `gnome-screenshot`），所以最後會經由
  `gdbus` 嘗試 `org.freedesktop.portal.Screenshot`，而不是直接放棄。它天生麻煩：portal
  回傳的是 request handle、結果之後才以 signal 送達，所以監聽必須在呼叫**之前**啟動；
  而且同意對話框可能擋在前面，因此等待有 30 秒上限。
- **操作者可以指定自己的擷取指令。**
  `JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mycap --png {output}"` 優先於所有偵測。
  `{output}` 會換成暫存 PNG 路徑，在 `shlex.split` 之後逐一參數替換、不經過 shell，
  所以含空白的路徑仍然是單一參數。這是給內建分層都不適用的環境用的逃生門——包含我們對
  某個工具的 argv 猜錯的情況。
- **libei 主動拒絕它根本送不出輸入的連線。** 這個綁定從頭到尾只握有 `ei` context，
  但每個 device 進入點收的都是 `ei_device`，而且完全沒有跑 libei 的 seat／device／
  `start_emulating`／`frame` 握手——所以它送不出輸入，卻**可能**在會開
  `$XDG_RUNTIME_DIR/eis-0` 的機器上把錯誤的指標傳進 C 函式庫。現在它會在 `connect()`
  就停下並說明原因。呼叫端本來就把這個情況當成「改用 ydotool CLI」，而那正是所有真實
  桌面環境一直在做的事。
- **portal 監聽器不會在收尾時卡死。** 它的 pipe 只在讀取執行緒放手之後才關閉；在有執行緒
  仍阻塞在 `read()` 時關閉串流可能卡在 buffer lock 上，那會讓「逾時」變成它本來要防止的
  「卡住」。

## 本次更新 (2026-08-18) — 容器映像在 Windows 簽出下也能建、能啟

- **在 Windows 上 clone 再 build 出來的容器，一啟動就死。** `.gitattributes` 只寫了
  `* text=auto`，於是 `docker/entrypoint.sh` 與 `docker/entrypoint-xfce.sh` 被簽出成 CRLF。
  shebang 就變成 `#!/bin/sh<CR>`，kernel 去找一個名字末尾帶回車的直譯器，映像 build 得完全正常，
  一跑就丟出 `exec /usr/local/bin/autocontrol-entrypoint: no such file or directory`——
  而那個檔明明就在。CI 永遠看不到：Linux runner 簽出來就是 LF。現在以
  `*.sh text eol=lf` 釘住，並有測試確認沒有任何 entrypoint 帶 CRLF。
- **`.dockerignore` 放在 `docker/`，Docker 根本不會去那裡讀。** Docker 只讀 build *context*
  根目錄的那一份，而文件裡每一道 build 指令都以倉庫根目錄為 context
  （`docker build -f docker/Dockerfile .`），所以那些排除規則一條都沒生效：`.git`、
  `.venv`、`test/` 跟各種快取每次都被丟給 daemon。已移到根目錄。
- **`mss` 墊片的測試量的是開發機的螢幕，不是它自己的假件。**
  `test_screen_grabber.py` 只換掉 `backend_grab_image`，`_backend_screen_size` 還是讀真的
  `platform_wrapper.screen`，所以 `monitors[0]` 報的是開發者手邊那台螢幕。在 1920x1080
  的桌面上會過，在 1280x800 的 Xvfb 下就失敗，而這跟被測程式碼無關。現在假件同時接管接縫的兩半。

## 本次更新 (2026-08-17) — Wayland 看得見螢幕了

- **所有擷取路徑改走平台後端。** `screenshot()`、影像與錨點定位、OCR、smart waits、
  視覺回歸、螢幕錄影、MCP 螢幕工具與遠端桌面，先前各自直接呼叫 `PIL.ImageGrab` 或
  `mss`。這兩者在 Linux 都是讀 X11 root window——在 Wayland 下那個 root 屬於 XWayland，
  不會合成原生 Wayland 視窗。Pillow 確實有退回 `gnome-screenshot`／`grim`／`spectacle`
  的路徑，但它只在 X11 擷取**拋出例外**時才走（`except OSError`）——也就是根本沒有 X
  display 的情況；只要 XWayland 在跑（GNOME、KDE、sway 的預設）就不會觸發。`mss` 則是
  任何情況下都沒有後備。現在 `utils/cv2_utils/screen_grabber.py` 是唯一決定「這台機器怎麼
  讀螢幕」的地方：後端若發布 `grab_image`，就把它包成呼叫端已在用的形狀。Windows、
  macOS 與 Linux X11 不發布任何東西，仍然使用真正的函式庫，行為完全不變。
- **Wayland 擷取涵蓋三種合成器家族，而不只一種。** `grim` 只會說 `wlr-screencopy`，
  GNOME 與 KDE 都沒有實作——所以 `linux_wayland/capture.py` 依序嘗試 `grim`
  （sway、Hyprland、river）、`gnome-screenshot`、`spectacle`，並回報用了哪一個。只有
  `grim` 能自己接受區域參數，其餘的擷取整個螢幕後再裁切。
- **沒有任何擷取工具時明確失敗。** 錯誤訊息會列出各合成器該裝什麼，而不是回傳空白的
  XWayland 擷取——後者在下游只會表現成「找不到樣板」。新的 `screen_capture` 診斷檢查
  會在任何失敗發生前先講清楚目前用的是哪一個工具。
- **`screen.size()` 與 `get_pixel` 在 GNOME／KDE 也能用。** 解析度從 `wlr-randr` 退回
  以擷取結果量測；`get_pixel` 從可用的擷取路徑裁出 1x1 區域。

**仍未完成**：libei 原生輸入路徑與 Wayland 真機驗證，見 [Progress.md](../Progress.md)。

## 本次更新 (2026-07-03) — 穩定 API、失敗診斷包與發佈工程

給新整合用的版本化進入點、可攜式失敗診斷格式,以及強化後的發佈管線。完整參考:[`docs/API_LIFECYCLE.md`](../docs/API_LIFECYCLE.md) 與 [`docs/CAPABILITY_MATRIX.md`](../docs/CAPABILITY_MATRIX.md)。

- **穩定 `je_auto_control.api` 門面**:小巧、延遲載入、有型別的命名空間(`execute_action`、`execute_action_with_vars`、`generate_code`、`run_diagnostics`、failure bundles),新的使用者匯入核心自動化時不必連帶載入數百個選用整合。受書面生命週期政策管轄——移除穩定 API 需要棄用警告加兩個 minor 版本——並由 `utils/deprecation.deprecated` 提供一致、帶中繼資料的警告。CI 以 mypy 檢查此介面型別,並在 Windows/Ubuntu/macOS × Python 3.10/3.14 矩陣上煙霧測試匯入。
- **失敗診斷包**(`create_failure_bundle` / `failure_bundle_on_error`,CLI `je_auto_control failure-bundle out.zip`):一個原子寫入、自足的 `autocontrol.failure-bundle/v1` ZIP,用於診斷失敗的執行——含執行環境資訊的 manifest、已遮罩的 error/context/events、已遮罩的 log 尾段、可選截圖與診斷報告、opt-in 附件。收集器為 best-effort:截圖或診斷探測壞掉會記進 `collector_failures` 而不是丟失整個診斷包。`codegen --failure-bundle` 讓產生的 pytest 流程自動封存自己的失敗證據。秘密遮罩現在也會遮蔽明確的 `key=value` / `Authorization: Bearer` 憑證語法,不論其熵值高低。
- **發佈工程**:發佈從 push-to-main 改為不可變的 `v*` 標籤——新的 `release.yml` 驗證標籤與套件版本一致、建置、煙霧測試 wheel、附上建置來源證明(provenance attestation),並經 PyPI Trusted Publishing 發佈。`quality.yml` 新增 dependency review、覆蓋率下限(fail-under 35,分支覆蓋)與穩定 API 的 mypy 關卡;新的 platform-smoke workflow 在三個作業系統上演練穩定 API。
- **專案文件**:新增 [`SECURITY.md`](../SECURITY.md)(私密安全通報、回應時限、操作預設值)、[`CHANGELOG.md`](../CHANGELOG.md)(Keep-a-Changelog 相容性紀錄)、API 生命週期政策與能力/平台支援矩陣。Sphinx 索引補齊 v182–v223 兩種語言的功能文件。

## 本次更新 (2026-07-02) — 選單驅動 GUI:Actions 選單取代分頁內按鈕

每個分頁的指令現在集中在一個可預期的位置。視窗選單列新增動態 **Actions** 選單,會隨當前分頁重建;分頁只保留輸入欄位、表格與結果/狀態檢視,不再是一排排按鈕。完整參考:[`docs/source/Zh/doc/new_features/v223_features_doc.rst`](../docs/source/Zh/doc/new_features/v223_features_doc.rst)。

- **視窗層級 Actions 選單**:核心分頁在註冊時宣告指令;功能分頁提供 `menu_actions()` 掛鉤,回傳 `(label_key, handler)` 配對。48 個已註冊分頁中有 46 個以此方式呈現指令——Script Builder 與 Remote Desktop 刻意保留互動式面板版面,選單在該處顯示佔位訊息。視窗層級選單無法取代的按鈕維持原位(堆疊觸發器表單內的逐頁瀏覽按鈕、隨可見性切換的資料來源瀏覽按鈕、有狀態的自動更新核取方塊)。無頭迴歸測試守護此契約,分頁不可能默默失去其指令。

## 本次更新 (2026-06-24) — 擴充 UIA 控制模式(展開 / 選取 / 範圍 / 捲動)

以原生模式驅動樹節點、清單/下拉項目、滑桿與捲動,而非像素猜測。完整參考:[`docs/source/Zh/doc/new_features/v181_features_doc.rst`](../docs/source/Zh/doc/new_features/v181_features_doc.rst)。

- **`expand_control` / `collapse_control` / `control_expand_state` / `select_control_item` / `control_range` / `set_control_range` / `scroll_control_into_view`**(`AC_expand_control`、`AC_select_control_item`、`AC_set_control_range` 等):無障礙後端原本只有 Value/Invoke/Toggle/Grid-read 模式,故樹狀檢視、清單/下拉、滑桿與螢幕外列都沒有原生呼叫路徑。本功能在既有後端 ABC 之上補上 ExpandCollapse / SelectionItem / RangeValue / ScrollItem 模式,透過可注入的 `accessibility.backends.get_backend()` 接縫分派(以 fake backend 無頭測試;真正 UIA 呼叫在 Windows 後端)。不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 比對前安定閘 + 命中穩定性

避免在動畫進行中比對,並確認命中跨幀維持穩定。完整參考:[`docs/source/Zh/doc/new_features/v180_features_doc.rst`](../docs/source/Zh/doc/new_features/v180_features_doc.rst)。

- **`region_stability` / `match_persistence`**(`AC_region_stability`、`AC_match_persistence`):`smart_waits.wait_until_screen_stable` 以布林閘控即時迴圈——無法對可注入幀序列評分穩定度,也無法檢查某*命中*是否維持。`region_stability` 以相鄰幀 SSIM 評分(`{stable, mean_ssim, min_ssim}`);`match_persistence` 確認 template 在*每一*幀都找到且中心於 `agree_px` 內一致(`{persisted, n_hits, jitter}`)。重用 `ssim` + `visual_match` + `grounding_consensus`;幀可注入;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 色彩感知樣板比對(HSV)

區分形狀相同的紅色與綠色狀態點。完整參考:[`docs/source/Zh/doc/new_features/v179_features_doc.rst`](../docs/source/Zh/doc/new_features/v179_features_doc.rst)。

- **`match_color` / `match_color_all`**(`AC_match_color`、`AC_match_color_all`):`visual_match` 每個比對器都先轉灰階,故形狀相同的紅 vs 綠無法區分;`color_region` 找已知顏色的 blob 卻無法對多色字形做樣板比對。本功能在 HSV 色相/飽和度上以色彩*距離*度量(`TM_SQDIFF_NORMED`——相關會把絕對色相正規化掉,使紅→綠邊與黑→藍邊同分)。重用 `color_region` 的 RGB 載入器 + `visual_match` 的 resize/NMS/`Match`。`channels` 預設 `("h","s")`(平坦飽和度目標用 `("h",)`);純色 blob 請用 `find_color_region`。不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 多模板共識比對

把同一目標的多個參考裁切投票成單一可信位置。完整參考:[`docs/source/Zh/doc/new_features/v178_features_doc.rst`](../docs/source/Zh/doc/new_features/v178_features_doc.rst)。

- **`match_ensemble` / `vote_centers`**(`AC_match_ensemble`、`AC_vote_centers`):一個按鈕以多種狀態呈現(預設/懸停/按下)但是單一邏輯目標;`ab_locator` 只選一個策略、`match_template(scales=...)` 只掃一個模板——兩者都不融合多參考。本功能比對每個參考,聚類命中中心,只有在 ≥ `min_votes` 個於 `agree_px` 內一致時才接受,回傳 `{point, votes, n_candidates, spread}`——減少換膚/動畫 UI 的誤判。重用 `visual_match.match_template` + `grounding_consensus`;`vote_centers` 為純投票核心。不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 逐步評審特徵 + 規則式步驟評分

把為代理步驟評分所需的證據打包,並內建規則式評分器。完整參考:[`docs/source/Zh/doc/new_features/v177_features_doc.rst`](../docs/source/Zh/doc/new_features/v177_features_doc.rst)。

- **`build_critic_record` / `score_step_rule_based` / `to_judge_prompt`**(`AC_build_critic_record`、`AC_score_step`):`trajectory_eval` 對整條軌跡評分而無逐步證據;`agent_trace` 發出 span 而非品質;`agent_replay` 保存步驟卻不評分。本功能把 `action_effect` + `observation_delta` + `postcondition` 組合成單一逐步記錄,接著 `score_step_rule_based` 給出確定性的 `{outcome, process_score, reasons}`(不需模型),`to_judge_prompt` 把它渲染給可選的 LLM-as-judge。純標準函式庫聚合器;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 標題與內文分類 + 文件大綱

以高度區分標題與內文,並建立文件大綱。完整參考:[`docs/source/Zh/doc/new_features/v176_features_doc.rst`](../docs/source/Zh/doc/new_features/v176_features_doc.rst)。

- **`classify_lines` / `outline`**(`AC_classify_lines`、`AC_outline`):框架中沒有功能把行高對應到標題層級或建立章節大綱——`ocr/structure` / `element_parse` 純屬位置性,`text_blocks` 不排序。本功能套用標準啟發法:行高超過 `heading_ratio` × 中位行高者為標題,不同標題高度成為層級(最高 = 1)。`classify_lines` 為每行標記 `{box, text, role, level}`;`outline` 依序回傳標題作為目錄。純標準函式庫,作用於行字典;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 變化量序列的穩定偵測

判斷 UI 何時安定下來——以純粹、可測試的函式作用於變化序列。完整參考:[`docs/source/Zh/doc/new_features/v175_features_doc.rst`](../docs/source/Zh/doc/new_features/v175_features_doc.rst)。

- **`settle_point` / `is_settled` / `SettleTracker`**(`AC_settle_point`):`smart_waits.wait_until_screen_stable` 把穩定邏輯包在 `time.sleep` 迴圈內、作用於即時幀——你無法餵記錄好的序列,也無法單元測試該決策。本功能把它抽離:給定一串*變化量*(像素差 / 元素數差 / 0-1 digest 是否變),在變化量連續 `quiet_samples` 次維持 ≤ `max_churn` 時回報穩定(尖峰重置 run)。`settle_point` 回傳穩定索引,`SettleTracker` 為供即時迴圈的增量形式。純標準函式庫,不需時鐘、不需擷取;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — OCR 行的段落與清單分組

把 OCR 行分組成段落,並偵測項目符號 / 編號清單。完整參考:[`docs/source/Zh/doc/new_features/v174_features_doc.rst`](../docs/source/Zh/doc/new_features/v174_features_doc.rst)。

- **`group_paragraphs` / `detect_lists`**(`AC_group_paragraphs`、`AC_detect_lists`):`text_regions` 把字形併成行,但沒有功能把那些行分組成段落或偵測清單;`ocr/structure` 止於平面列。`group_paragraphs` 在垂直間距超過 `line_gap_factor` × 中位行高處開始新段落;`detect_lists` 辨識項目符號(`•`/`-`/`*`)或序號(`1.`/`2)`/`a.`)項目,回傳 `{text, marker, indent, box}`。純標準函式庫,作用於行字典;重用 `table_grid_fill` 的框讀取器;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 欄位感知閱讀順序(XY-Cut)

讀多欄版面時*完整讀完*每一欄,而非交錯。完整參考:[`docs/source/Zh/doc/new_features/v173_features_doc.rst`](../docs/source/Zh/doc/new_features/v173_features_doc.rst)。

- **`flow_order` / `xy_cut` / `to_blocks`**(`AC_flow_order`、`AC_xy_cut`):`element_parse.reading_order` 是平面上到下排序,會交錯欄位(讀作 A1, B1, A2, B2…)。本功能以遞迴 XY-cut 還原正確順序——在最寬留白谷切分(垂直 → 欄、水平 → 列),故兩欄頁面讀作 A1, A2, B1, B2。`flow_order` 回傳與 `reading_order` 相同的 `index` 標記契約(欄位感知的直接升級,且命名不遮蔽它);`xy_cut` 暴露區域樹;`to_blocks` 列出葉區塊。純標準函式庫;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — Grounding 自我一致性(提案共識)

把多個 grounding 提案融合成單一一致目標,並附 agreement 分數。完整參考:[`docs/source/Zh/doc/new_features/v172_features_doc.rst`](../docs/source/Zh/doc/new_features/v172_features_doc.rst)。

- **`consensus_point` / `consensus_element` / `is_confident`**(`AC_consensus_point`、`AC_consensus_element`):一個目標可同時以多種方式 grounding(set-of-marks / OCR / 樣板 / a11y / 模型 N 次抽樣)而未必一致。`ab_locator`/`element_scoring` 依歷史排序*策略*;`snap_to_element` 只貼*單一*座標——兩者都不融合*同時*的提案。本功能將候選點聚類(或對候選元素投票),回傳一致的 `point` + `agreement` 比例 + `spread`,而 `is_confident` 標記低一致度目標,讓代理改為放大 / 詢問而非盲目點擊。純標準函式庫;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 次像素樣板比對精修

把比對中心精修到像素的分數位,供拖曳 / 滑桿 / 高 DPI 精度。完整參考:[`docs/source/Zh/doc/new_features/v171_features_doc.rst`](../docs/source/Zh/doc/new_features/v171_features_doc.rst)。

- **`match_subpixel` / `refine_peak`**(`AC_match_subpixel`):每個比對器都從 `cv2.minMaxLoc` 回傳*整數*座標——對拖曳把手、細滑桿或高 DPI 顯示器,這種捨入是主要的點擊落點誤差。本功能以拋物線擬合峰值周圍的 3×3 分數鄰域(x/y 各自獨立,標準 NCC 次像素法),回傳帶浮點 `cx`/`cy` 與套用的 `offset_x`/`offset_y` 的 `SubPixelMatch`。重用 `visual_match._score_map`;`haystack` 可注入;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 失敗 / 無效果動作的修復策略引擎

當動作沒效果時選擇下一個修復戰術——並驅動重試迴圈。完整參考:[`docs/source/Zh/doc/new_features/v170_features_doc.rst`](../docs/source/Zh/doc/new_features/v170_features_doc.rst)。

- **`plan_repair` / `next_tactic` / `run_with_repair`**(`AC_plan_repair`):`self_healing`/`locator_repair` 只修復*無法解析*的定位器;`loop_guard` 只*偵測*卡住迴圈而無戰術選擇。本功能消費效果判定(例如來自 `action_effect`)並回傳有序戰術——`wait_retry` / `relocate` / `nudge` / `scroll_into_view` / `escalate`——接著 `run_with_repair` 以注入的 `act` / `verify` / `apply_tactic` / `verdict_for` / `sleep` 接縫驅動有界重試迴圈,回傳 `RepairOutcome`。純標準函式庫狀態機;不匯入 `PySide6`。與 `action_effect` + `postcondition` 完成自我修正三件套。

## 本次更新 (2026-06-24) — 宣告式動作後置條件

以 JSON 規格斷言動作的預期結果,並對照 before 幀做差異。完整參考:[`docs/source/Zh/doc/new_features/v169_features_doc.rst`](../docs/source/Zh/doc/new_features/v169_features_doc.rst)。

- **`check_postcondition` / `compile_postcondition`**(`AC_check_postcondition`):`expect_poll`/`assert_eventually` 輪詢單一條件,沒有與動作綁定的規格、也沒有 before 基準(因此無法表達「一個*新*對話框出現了」);`trajectory_eval` 是整條軌跡層級。本功能對 after 觀測評估一個小型 JSON 子句規格——`appears`/`disappears`(對照 `before`)、`enabled`/`disabled`、`text_present`/`text_absent`、`count`——回傳逐子句的 `{ok, clauses, failed}` 報告。`compile_postcondition` 把規格轉成 `after -> bool` 判定函式以供 `expect_poll` 使用。純標準函式庫;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 邊緣形狀(Chamfer)樣板比對

以輪廓定位扁平圖示,對填充 / 主題 / 抗鋸齒穩健。完整參考:[`docs/source/Zh/doc/new_features/v168_features_doc.rst`](../docs/source/Zh/doc/new_features/v168_features_doc.rst)。

- **`edge_match` / `edge_match_all` / `chamfer_distance`**(`AC_edge_match`、`AC_edge_match_all`):強度 NCC(`visual_match`)在控制項換填充 / 換主題時分數下降,ORB(`feature_match`)需要扁平圖示缺乏的角點紋理。本功能以*邊緣形狀*比對:對兩圖跑 Canny,對場景邊緣做距離轉換,把樣板邊緣滑過它並以平均邊緣間距(Chamfer)評分。完美輪廓不論填充皆以約 0 成本對齊。重用 `visual_match` 的載入器 / resize / NMS / `Match` 與 `edge_lines` 的 Canny 預設。`haystack` 可注入;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 動作效果分類(我的點擊有沒有效果?)

告訴代理點擊有沒有效果——以及是否發生在它瞄準之處。完整參考:[`docs/source/Zh/doc/new_features/v167_features_doc.rst`](../docs/source/Zh/doc/new_features/v167_features_doc.rst)。

- **`classify_effect` / `effect_near_point` / `is_no_op`**(`AC_classify_effect`、`AC_effect_near_point`):`screen_state`/`element_diff` 回報變了什麼卻不歸因到動作;`loop_guard` 要重複 N 次才標記 no-op。本功能比對前後觀測,並依動作目標點在*第一步*就分類結果為 `no_op` / `changed_near_target` / `changed_elsewhere`(意外對話框)/ `changed`,回傳含變化中心與原因的 `EffectVerdict`。重用 `element_diff.match_elements` + `observation_delta` 的欄位變更檢查。純標準函式庫;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 表單欄位關聯(多方向)+ 核取方塊狀態

即使值在下方或右對齊也能把標籤與值配對,並讀取核取方塊狀態。完整參考:[`docs/source/Zh/doc/new_features/v166_features_doc.rst`](../docs/source/Zh/doc/new_features/v166_features_doc.rst)。

- **`associate_fields` / `match_labels_to_widgets` / `checkbox_state`**(`AC_associate_fields`、`AC_match_labels_to_widgets`):`ocr/structure` 只把 `label:` 與*緊接的下一格*配對——無法處理標籤在上、雙欄 key/value、右對齊值或非文字 widget,且無核取方塊概念。本功能把每個標籤與多*方向*(右 / 下)中 `max_gap` 內最近的對齊值配對,把獨立 widget(核取方塊 / 單選鈕 / 輸入框)配到最近標籤,並由框內暗像素填充比例讀取核取方塊狀態。關聯部分純標準函式庫;只有 `checkbox_state` 觸及像素(隔離在 `visual_match` 灰階載入器之後)。不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 留白投影欄位偵測(無框線表格)

靠留白間隙推導欄位來讀取無框線表格。完整參考:[`docs/source/Zh/doc/new_features/v165_features_doc.rst`](../docs/source/Zh/doc/new_features/v165_features_doc.rst)。

- **`detect_borderless_table` / `column_gutters` / `assign_columns` / `vertical_projection`**(`AC_detect_borderless_table`、`AC_column_gutters`):`ocr/structure` 只有在每一列儲存格左緣 x 都相符時才偵測得到表格——對 ragged / 無框線 / 右對齊欄都失敗;`edge_lines.find_grid` 需要框線,而留白表格沒有。本功能靠*間隙*找欄位:把 OCR 框投影到 x 軸,讀出持續為空的垂直帶作為 gutter,指派欄索引,依間距分群成列,輸出 `{n_rows, n_cols, rows, columns}`。純標準函式庫差分陣列投影(不需 numpy);重用 `table_grid_fill` 的框讀取器。不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 自動門檻樣板比對(對分數圖做 Otsu)

不再手調 `min_score`——由分數圖推導比對門檻。完整參考:[`docs/source/Zh/doc/new_features/v164_features_doc.rst`](../docs/source/Zh/doc/new_features/v164_features_doc.rst)。

- **`match_auto` / `auto_threshold`**(`AC_match_auto`、`AC_auto_threshold`):每次 `match_template_all` 都迫使你猜 `min_score`(太低充滿 NMS 雜訊、太高漏掉換膚目標,且因素材而異)。本功能對*相關性分數直方圖*套用 Otsu,找出背景相關與真正匹配之間的谷,回傳該門檻加上 *separability* 分離度(接近 0 = 單峰、無明確匹配 → 不要信任)。`match_auto` 每個過門檻區域只回傳單一峰(透過 `connected_boxes`,避免寬峰上的重複命中),並以 `floor` 夾住。重用新增的 `visual_match._score_map`;`haystack` 可注入;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 權杖預算化的觀測差異(變更了什麼)

告訴代理*變更了什麼*,而非再次整個畫面。完整參考:[`docs/source/Zh/doc/new_features/v163_features_doc.rst`](../docs/source/Zh/doc/new_features/v163_features_doc.rst)。

- **`delta_observation` / `delta_index` / `summarize_delta`**(`AC_delta_observation`):`serialize_observation` 渲染單一整幀(每回合都撐爆權杖預算);`element_diff` 提供穩定 ID 對應但止於 matched/added/removed 的元素配對。本功能正是缺少的序列化器——比對兩幀,將配對元素分類為 changed(role/name/enabled/value/移動)或 stable,只渲染變動部分:`+ [i] role "name"` / `~ [i] … (fields)` / `- …`(added 與 changed 優先、stable 略去、上限 `max_lines`)。重用 `element_diff.match_elements` + `observation.observation_index`。純標準函式庫;不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 以 OCR 文字填入框線網格(可定址表格)

把有框線表格的線條 + OCR 文字轉成可定址的 `R x C` 表格。完整參考:[`docs/source/Zh/doc/new_features/v162_features_doc.rst`](../docs/source/Zh/doc/new_features/v162_features_doc.rst)。

- **`populate_table` / `assign_text_to_grid` / `table_to_records` / `table_to_csv`**(`AC_populate_table`):`edge_lines.find_grid` 能還原表格的框線幾何但回傳的儲存格是*空的*;OCR 提供文字卻無結構——兩者從未串接。本功能把 OCR 框放入網格(依儲存格中心指派,以重疊比例把關,使橫跨細框線的框不被重複計入),將每個儲存格的文字依閱讀順序串接,標記合併儲存格的 span,並可直接轉成 records / CSV。純標準函式庫,作用於純字典——不需影像、OCR 引擎或裝置。不匯入 `PySide6`。

## 本次更新 (2026-06-24) — 信任評分樣板比對(歧義 / PSR)

在點擊前就知道某次樣板比對雖強但*有歧義*。完整參考:[`docs/source/Zh/doc/new_features/v161_features_doc.rst`](../docs/source/Zh/doc/new_features/v161_features_doc.rst)。

- **`match_with_trust` / `score_peaks`**(`AC_match_with_trust`):`match_template` 只回傳最高分並點擊——但工具列中重複的按鈕或近乎相同的同類元件可能在兩處都相關到 ~0.95,因此高分並非*無歧義*的比對。本功能為像素樣板加入 Lowe 式比值測試(ORB 透過 `feature_match` 已有,`match_template` 從未有):檢視整個相關性曲面,比較全域峰值與排除視窗外的次高峰,計算峰值對旁瓣比(PSR),回傳帶有 `second_score` / `peak_ratio` / `psr` / `is_ambiguous` 的 `TrustedMatch`。重用新增的 `visual_match._score_map`(公開比對器丟棄的完整 `matchTemplate` 曲面)——不重複任何比對程式。`haystack` 可注入;不匯入 `PySide6`。

## 本次更新 (2026-06-23) — 剪貼簿檔案拖放清單(CF_HDROP)

把一份檔案清單放上剪貼簿,可直接貼進 Explorer。完整參考:[`docs/source/Zh/doc/new_features/v160_features_doc.rst`](../docs/source/Zh/doc/new_features/v160_features_doc.rst)。

- **`build_dropfiles` / `parse_dropfiles` / `set_clipboard_files` / `get_clipboard_files`**(`AC_set_clipboard_files`、`AC_get_clipboard_files`):剪貼簿原本能承載文字、影像與(透過 `rich_clipboard`)HTML,卻從未支援*檔案清單*——也就是 Explorer 讀取以進行真正檔案複製的 `CF_HDROP` 內容。建構它相當瑣碎(20 位元組 `DROPFILES` 標頭 + 雙重 null 結尾的 UTF-16 路徑清單 + `pFiles` 位移)。本功能把封裝獨立為純粹、可完整測試的 `build_dropfiles` / `parse_dropfiles` 位元組函式,其上再疊加僅限 Windows 的 `set`/`get_clipboard_files` 薄包裝——與 `rich_clipboard` 處理 `CF_HTML` 的拆分方式相同。不匯入 `PySide6`。

## 本次更新 (2026-06-23) — 粗粒度標籤螢幕網格(VLM Grounding)

以網格儲存格(「點擊 C3」)而非原始像素引用螢幕區域。完整參考:[`docs/source/Zh/doc/new_features/v159_features_doc.rst`](../docs/source/Zh/doc/new_features/v159_features_doc.rst)。

- **`grid_cells` / `cell_for_point` / `point_for_cell`**(`AC_grid_cells`、`AC_cell_for_point`、`AC_point_for_cell`):VLM grounding 在模型指名粗粒度儲存格時,遠比輸出容易幻覺的像素座標更可靠。本功能在螢幕(或 `region`)上鋪設 `rows`x`cols` 網格,以試算表風格標記每個儲存格(左上 `A1`,超過 `Z` → `AA`),並雙向對應——點 → 包含的儲存格、指名儲存格 → 中心點(可直接點擊)。純標準函式庫幾何;唯一裝置相依的路徑是讀取即時螢幕尺寸的預設行為,因此每個函式都可透過明確 `region` 無頭測試。不匯入 `PySide6`。

## 本次更新 (2026-06-23) — 旋轉與縮放容忍的樣板比對

不只縮放,還能找到旋轉或傾斜的樣板。完整參考:[`docs/source/Zh/doc/new_features/v158_features_doc.rst`](../docs/source/Zh/doc/new_features/v158_features_doc.rst)。

- **`match_rotated` / `match_rotated_all` / `scale_space`**(`AC_match_rotated`、`AC_match_rotated_all`):`match_template` 只掃描*縮放*且假設軸對齊——OpenCV 的 `matchTemplate` 不具旋轉不變性,因此傾斜的控制項、旋轉的圖示,或轉到不同角度的刻度盤都會比對失敗。本功能掃描 `angles`(每個以 `cv2.warpAffine` 變形)並與 `np.linspace` 縮放空間交叉,回傳相關性最高、且帶有還原 `scale` + `angle` 的 `RotatedMatch`(`*_all` 版本以 NMS 合併相鄰角度 / 縮放)。重用 `visual_match` 的載入器 / resize / 方法表 / NMS——不重複任何比對或幾何程式。`haystack` 可注入;可無頭測試;不匯入 `PySide6`。

## 本次更新 (2026-06-23) — 一維條碼解碼

從螢幕或影像讀取 EAN / UPC / Code-128 條碼。完整參考:[`docs/source/Zh/doc/new_features/v157_features_doc.rst`](../docs/source/Zh/doc/new_features/v157_features_doc.rst)。

- **`read_barcodes`**(`AC_read_barcodes`):框架已能解碼 QR Code(`read_qr`),但缺少能讀取*一維*條碼(EAN-13/8、UPC-A、Code-128)的功能——這些正是商品、庫存標籤與物流面單上最常見的條碼。本功能透過 OpenCV 的 `cv2.barcode.BarcodeDetector` 解碼,每個條碼回傳 `{text, type, points}`。解碼步驟為可注入接縫(預設呼叫 OpenCV;測試可傳入自己的 `decoder`),因此可完整無頭測試且能優雅降級——若 OpenCV 編譯時未含 `barcode` 模組,回傳 `[]` 而非拋出例外。重用共用的 `visual_match` haystack 載入器;不匯入 `PySide6`。

## 本次更新 (2026-06-23) — 加權候選評分

以信心分數排序模稜兩可的元素候選。完整參考:[`docs/source/Zh/doc/new_features/v156_features_doc.rst`](../docs/source/Zh/doc/new_features/v156_features_doc.rst)。

- **`score_candidates` / `best_candidate`**(`AC_score_candidates`、`AC_best_candidate`):`anchor_locator` 是單一關係 + 距離排序、`ab_locator` 依耗時競賽整個策略——兩者都不以*加權*混合(角色匹配 + 模糊名稱相似度 + 錨點鄰近 + 啟用狀態)排序模稜候選。本功能回傳最佳優先的 `ScoredCandidate` 並含 `matched_on` 明細;名稱相似度可注入(預設 `fuzzy_ratio`,重用——不新增字串距離程式)。純標準函式庫,作用於元素字典;在多個框都可能是目標時驅動自我修復 / grounding。可無頭測試。

## 本次更新 (2026-06-23) — 幾何感知的元素差異與穩定 ID

以重疊跨影格追蹤元素,並給予穩定 ID。完整參考:[`docs/source/Zh/doc/new_features/v155_features_doc.rst`](../docs/source/Zh/doc/new_features/v155_features_doc.rst)。

- **`match_elements` / `assign_stable_ids`**(`AC_match_elements`、`AC_assign_stable_ids`):`diff_snapshots` 以 `(role, name)` 作識別——無法比對改名但未移動或移動了的控制項,也無法跨影格給持久 ID。本功能以 IoU 比對元素框(沿用 `element_parse.iou`):`match_elements` 回傳 `{matched, added, removed}`;`assign_stable_ids` 從 `prior` 影格延續每個元素的 `id`(移動的按鈕保留 id、新增者取得新 id)——讓 agent 能跨回合可靠地引用「element 7」。純標準函式庫、可無頭測試。

## 本次更新 (2026-06-23) — 可攜式 Agent 軌跡記錄(錄製與重播)

記錄 agent 的觀測→動作步驟並重播。完整參考:[`docs/source/Zh/doc/new_features/v154_features_doc.rst`](../docs/source/Zh/doc/new_features/v154_features_doc.rst)。

- **`record_step` / `to_jsonl` / `from_jsonl` / `replay_trace`**(`AC_replay_trace`):`agent_trace` 記錄 OTel span(觀測性)、`trajectory_eval` 只評分、`semantic_recording` 重播人類巨集——都不是可重播的觀測→動作轉錄。本功能是 OmniTool 風格的 `{step, observation, action, result}` JSONL,加決定性重播驅動器(可注入 `runner`、無需即時模型)。執行器命令透過執行器重播每一步的 AC 動作。純標準函式庫、可無頭測試;可從 agent 執行建立回歸 / 訓練資料集。

## 本次更新 (2026-06-23) — 動作前接地防護

拒絕越界點擊;把接近偏離者吸附到真正的元素。完整參考:[`docs/source/Zh/doc/new_features/v153_features_doc.rst`](../docs/source/Zh/doc/new_features/v153_features_doc.rst)。

- **`validate_action` / `snap_to_element` / `in_bounds`**(`AC_validate_action`):`guardrail` 掃文字、`loop_guard` 偵測迴圈——兩者都不在派發前驗證座標動作,所以幻覺 `(9999,-5)` 點擊會打到空處、偏 5px 的點擊會錯過。本功能拒絕螢幕外座標,並在提供 `targets` 時把接近偏離者吸附到最近元素中心,回傳 `{ok, reason, snapped}`。純標準函式庫幾何,作用於元素字典;執行器 `screen` 預設為實際螢幕。可無頭測試;接在 agent 迴圈派發之前。

## 本次更新 (2026-06-23) — 符記預算內的無障礙文字觀測

把無障礙樹轉成 VLM 可操作的已編號文字區塊。完整參考:[`docs/source/Zh/doc/new_features/v152_features_doc.rst`](../docs/source/Zh/doc/new_features/v152_features_doc.rst)。

- **`serialize_observation` / `observation_index` / `flatten_tree`**(`AC_serialize_observation`、`AC_observation_index`):`describe_screen` 給角色*數量* + 平面標籤清單——沒有穩定索引、沒有 `[12] button "Submit" @(x,y)` 行、沒有視口裁切、沒有符記預算。本功能把(巢狀)元素樹扁平化為僅互動項、裁切到視口、依閱讀順序排序、上限 `max_elements`、指派穩定 `index`,並渲染模型可操作的行(「click [12]」)。純標準函式庫,作用於元素字典;與 `fuse_elements`/`set_of_marks` 搭配。可無頭測試。

## 本次更新 (2026-06-23) — 標準化 Computer-Use 動作結構

把 Anthropic / OpenAI agent 動作橋接到 AutoControl 命令。完整參考:[`docs/source/Zh/doc/new_features/v151_features_doc.rst`](../docs/source/Zh/doc/new_features/v151_features_doc.rst)。

- **`from_anthropic` / `from_openai_cua` / `to_ac_command` / `canonical_action`**(`AC_cua_command`):`tool_use_schema` 匯出 AC_* 簽章、`coordinate_space` 縮放——兩者都不*正規化進來的動作酬載*。Anthropic 發出 `{action:"left_click", coordinate:[x,y]}`、OpenAI CUA 發出 `{type:"click", x, y, button}`;這些轉接器把兩者對應為標準動作再對應為可執行的 `[AC_*, params]`(含選用座標空間 `scale`)。純標準函式庫、可無頭測試;執行器命令對任一來源回傳 `{canonical, command}`。

## 本次更新 (2026-06-23) — 視窗客戶區幾何

不論標題列 / 邊框,點擊視窗*內部*。完整參考:[`docs/source/Zh/doc/new_features/v150_features_doc.rst`](../docs/source/Zh/doc/new_features/v150_features_doc.rst)。

- **`get_client_rect` / `client_point` / `frame_insets` / `client_to_screen`**(`AC_get_client_rect`、`AC_client_point`):`get_window_geometry` 只回傳*外框*——沒有客戶區矩形、框邊內縮運算或客戶區→螢幕對應。`client_point("App", x, y)` 把內容相對點對應到螢幕,讓點擊不論外框都落在視窗內;`frame_insets` 回報邊框 / 標題列厚度。`frame_insets`/`client_to_screen` 是純幾何(可無頭測試);`get_client_rect` 使用可注入的 Win32 讀取器(`GetClientRect`+`ClientToScreen`)。

## 本次更新 (2026-06-23) — 感知式(YIQ)影像比對含反鋸齒抑制

會忽略反鋸齒邊緣的視覺回歸比對。完整參考:[`docs/source/Zh/doc/new_features/v149_features_doc.rst`](../docs/source/Zh/doc/new_features/v149_features_doc.rst)。

- **`perceptual_diff` / `assert_perceptual`**(`AC_perceptual_diff`):`image_difference` 計算原始逐通道差、`ssim_compare` 是整體分數——兩者都未使用感知式度量也不忽略反鋸齒(視覺比對誤報的首要來源)。本功能在 YIQ 空間比較(pixelmatch 的色彩度量),並預設以形態學開運算移除單像素反鋸齒細邊差異,只計算實心變化(`include_aa=True` 保留)。回傳 `{diff_pixels, diff_ratio, regions}`;`assert_perceptual` / `max_diff_ratio` 把關回歸測試。可注入影像配對 → 無頭可測(1px 細邊 → 0、實心區塊 → 計入)。

## 本次更新 (2026-06-23) — 軟性斷言(彙整所有失敗)

驗證很多項,一次回報每一個失敗。完整參考:[`docs/source/Zh/doc/new_features/v148_features_doc.rst`](../docs/source/Zh/doc/new_features/v148_features_doc.rst)。

- **`SoftAssertions`**(`AC_soft_assert`):`assert_all` 接受事先建好的規格清單——沒有可隨處呼叫 `check()`、並在區塊退出時一次拋出全部的作用域累加器(JUnit5 `assertAll` / Playwright `expect.soft`)。`with SoftAssertions() as soft: soft.check(...)` 記錄通過/失敗(區塊中永不拋出、回傳布林值可分支),退出時一次拋出列出每個失敗——且永不遮蔽已在傳播的例外。執行器命令彙整 JSON `checks` 清單(eq/ne/gt/lt/contains/truthy)。純標準函式庫、可無頭測試。

## 本次更新 (2026-06-23) — 視窗 Z-order(置頂 / 最前 / 最後)

把視窗釘在最上層、移到最前、或推到後面。完整參考:[`docs/source/Zh/doc/new_features/v147_features_doc.rst`](../docs/source/Zh/doc/new_features/v147_features_doc.rst)。

- **`set_topmost` / `bring_to_front` / `send_to_back` / `plan_zorder`**(`AC_set_topmost`、`AC_bring_to_front`、`AC_send_to_back`):原始 `set_window_position` 存在但未在 facade、無標題包裝也無 topmost 語意——缺少標準 RPA 的「置頂」。`plan_zorder` 是純動作→`SetWindowPos` 常數查找(可無頭測試);以標題操作的設定器透過可注入 driver(`snap_window` 接縫模式)套用,預設為 Win32。

## 本次更新 (2026-06-23) — 局部動態 / 活動偵測

找出兩幀之間哪些子區域在動。完整參考:[`docs/source/Zh/doc/new_features/v146_features_doc.rst`](../docs/source/Zh/doc/new_features/v146_features_doc.rst)。

- **`changed_regions` / `has_motion` / `activity_score`**(`AC_changed_regions`、`AC_has_motion`):`wait_until_screen_stable` 是布林輪詢、`ssim_changed_regions` 是結構性(忽略快速動態)、`diff_screenshots` 非活動區塊。本功能是便宜的 absdiff 路徑——對逐像素差做門檻、膨脹,回傳移動區域方框(由大到小)、布林值,以及移動像素比例。挑選安靜區域或定位轉圈動畫。兩個可注入幀 → 無頭可測;沿用共用連通元件輔助;執行器中 `after` 預設為即時螢幕擷取。

## 本次更新 (2026-06-23) — 色彩直方圖指紋與變化偵測

判斷畫面在光照 / 縮放下是否仍是「同一個」。完整參考:[`docs/source/Zh/doc/new_features/v145_features_doc.rst`](../docs/source/Zh/doc/new_features/v145_features_doc.rst)。

- **`image_histogram` / `compare_histograms` / `histogram_changed`**(`AC_image_histogram`、`AC_histogram_changed`):`image_dedup` 的感知雜湊是空間性的(對顏色/主題脆弱)、`color_stats` 只有單一顏色。正規化色彩直方圖是耐光照/縮放的「同一畫面、還是調色盤變了?」訊號(主題切換、重載、旋轉橫幅)。`image_histogram` 回傳逐通道直方圖(`hsv`/`rgb`/`gray`);`compare_histograms` 提供 correlation/chisqr/intersection/bhattacharyya;`histogram_changed` 比較參考與實際螢幕。可注入影像 → 無頭可測;OpenCV 核心(`cv2.calcHist`/`compareHist`)。

## 本次更新 (2026-06-23) — 豐富剪貼簿(HTML / CF_HTML)

把*格式化*的 HTML 複製貼上到 Word / Outlook。完整參考:[`docs/source/Zh/doc/new_features/v144_features_doc.rst`](../docs/source/Zh/doc/new_features/v144_features_doc.rst)。

- **`build_cf_html` / `parse_cf_html` / `set_clipboard_html` / `get_clipboard_html`**(`AC_set_clipboard_html`、`AC_get_clipboard_html`):基礎剪貼簿只處理純文字 + 影像——富文字貼上需要 `CF_HTML`,其位元組偏移標頭(`StartHTML`/`EndHTML`/`StartFragment`/`EndFragment`)極易出錯。`build_cf_html`/`parse_cf_html` 以純 Python 計算與還原它(往返測試、多位元組 UTF-8 正確);`set/get_clipboard_html` 將其包裝於 Win32 剪貼簿(含純文字後備)。位元組偏移運算可無頭測試;只有 I/O 為 Windows。

## 本次更新 (2026-06-23) — 可串接 / 可過濾的候選定位器

用鏈式呼叫細化已定位的元素:`.within(panel).filter(has_text="Delete").nth(1)`。完整參考:[`docs/source/Zh/doc/new_features/v143_features_doc.rst`](../docs/source/Zh/doc/new_features/v143_features_doc.rst)。

- **`from_boxes` / `Candidates`**(`AC_locate_chain`):`anchor_locator` 是單一關係、`grid_locator` 是儲存格——兩者都不支援對候選集合做可組合細化(Selenium-4 / Playwright 的串接定位慣用法)。本功能是對來自*任何*來源(模板 / OCR / a11y / `fuse_elements`)的框做純後置過濾:`within`(區域裁切)、`filter`(`has_text` / `near` / 面積 / predicate)、`sort_reading`、`nth` / `first` / `last`、`resolve()` / `center()`。每個方法回傳新的 `Candidates`(不變動)→ 完全無頭可測。執行器命令套用 JSON `ops` 清單。

## 本次更新 (2026-06-23) — 重試式數值斷言(expect.poll)

重試*任意*值直到符合,不只限內建檢查。完整參考:[`docs/source/Zh/doc/new_features/v142_features_doc.rst`](../docs/source/Zh/doc/new_features/v142_features_doc.rst)。

- **`expect_poll` / `assert_poll` + matchers**(`AC_expect_poll`):`assert_eventually` 只能輪詢固定字典規格檢查(文字/影像/像素/…)。本功能對任意零參數 `getter` 以任意 `matcher`(`to_equal` / `to_contain` / `to_be_greater_than` / `to_match_regex` / `to_be_truthy` / `to_be_stable`)輪詢直到通過或逾時——OCR 出的總額、列數穩定、自訂判斷式皆可。可注入 `clock`/`sleep` → 具決定性,對應 Playwright 的 `expect.poll`。執行器命令會重複執行巢狀動作直到其結果某鍵符合。

## 本次更新 (2026-06-23) — 線條 / 網格 / 分隔線偵測(Hough)

從原始像素找出表格格線與 UI 分隔線。完整參考:[`docs/source/Zh/doc/new_features/v141_features_doc.rst`](../docs/source/Zh/doc/new_features/v141_features_doc.rst)。

- **`find_lines` / `find_grid` / `find_separators`**(`AC_find_lines`、`AC_find_grid`、`AC_find_separators`):`grid_locator` 分群*已找到*的框、`shape_locator` 找封閉矩形——兩者都無法從像素找出表格格線或分隔線。Canny + 機率 Hough 偵測直線段(分類水平/垂直/斜向),`find_grid` 還原 `{rows, cols, cells}` 讓你定址「第 3 列、第 2 欄」,`find_separators` 回傳長分隔線座標。可注入 haystack → 無頭可測;OpenCV 核心(`cv2.HoughLinesP`)。

## 本次更新 (2026-06-23) — 免模型文字區偵測(MSER)

不跑 OCR 也能找出畫面上文字的位置。完整參考:[`docs/source/Zh/doc/new_features/v140_features_doc.rst`](../docs/source/Zh/doc/new_features/v140_features_doc.rst)。

- **`find_text_regions` / `find_text_lines`**(`AC_find_text_regions`、`AC_find_text_lines`):`shape_locator` 找矩形(不是文字)、`locate_text` 需要 OCR 引擎*以及*確切字串——兩者都無法回答「哪裡有*任何*文字?」。MSER 找出字元 / 詞 / 行區塊,讓腳本能裁切候選框餵給 OCR(比全畫面更快更準),或在未安裝 OCR 相依時偵測標籤出現。`merge` 聯集 MSER 逐字元的巢狀區域;`find_text_lines` 將字元歸為逐行框;空白畫面回傳 `[]`。OpenCV 核心(`cv2.MSER_create`)、可注入 haystack → 無頭可測。

## 本次更新 (2026-06-23) — HSV 色彩空間分割

不論光照都能找出「任一色階的紅色」。完整參考:[`docs/source/Zh/doc/new_features/v139_features_doc.rst`](../docs/source/Zh/doc/new_features/v139_features_doc.rst)。

- **`dominant_hue_regions` / `segment_hsv` / `color_mask`**(`AC_dominant_hue_regions`、`AC_segment_hsv`):`find_color_region` 在 RGB 以各通道 ± 框遮罩——無法比對「同一顏色但不同亮度」(狀態燈、強調色、主題色調)。HSV 把色相與亮度分離,因此「色相帶 + 飽和度 / 明度下限」可在不同光照下捕捉所有色階。`dominant_hue_regions(hue=…)` 自動處理紅色 0/180 環繞;`segment_hsv` 接受明確帶;兩者皆回傳 `{x,y,width,height,area,center}` 區塊並沿用共用連通元件輔助函式。可注入 haystack → 無頭可測。

## 本次更新 (2026-06-23) — 融合並排序螢幕元素框

把原始的 OCR + 圖示 + a11y 框轉成一份乾淨、已編號的元素清單。完整參考:[`docs/source/Zh/doc/new_features/v138_features_doc.rst`](../docs/source/Zh/doc/new_features/v138_features_doc.rst)。

- **`iou` / `merge_boxes` / `fuse_elements` / `reading_order`**(`AC_fuse_elements`、`AC_reading_order`):`set_of_marks` 為乾淨的元素清單編號,但沒有任何功能*產生*它——真實畫面解析會產出三個彼此重疊、有重複且無順序的來源。本功能補上這一步:依 IoU 去除近重複框、聯集 OCR/icon/a11y 並在重疊時保留最可信來源(`source_priority` a11y > ocr > icon)、再由上到下 / 由左到右排序並給予穩定 `index`。純 `dict` 框 → 純標準函式庫、完全無頭可測;直接與 `set_of_marks` 搭配。

## 本次更新 (2026-06-23) — 可操作性閘門(操作前先等待就緒)

目標真正就緒前不要點擊。完整參考:[`docs/source/Zh/doc/new_features/v137_features_doc.rst`](../docs/source/Zh/doc/new_features/v137_features_doc.rst)。

- **`wait_actionable` / `act_when_ready`**(`AC_wait_actionable`):Playwright/Cypress 在每次點擊前都會做可操作性檢查——存在 + 已停止移動 + 啟用 + 未被遮蓋——但 AutoControl 先前沒有(`self_heal_click` 立即點擊;`wait_until_screen_stable` 觀察整個畫面)。本功能把這四項合成單一閘門,回傳 `ActionabilityReport`(各項檢查布林值、目標 `point`、`reason` = 第一個失敗的檢查)。每個訊號都是可注入 callable(`bbox_provider` / `region_sampler` / `enabled_probe` / `hit_tester`)再加可注入 `clock`/`sleep`,因此完全決定性且可無頭測試。執行器命令以模板影像把關。

## 本次更新 (2026-06-23) — 多螢幕 / 虛擬桌面幾何

在多台顯示器間正確擺放視窗與座標。完整參考:[`docs/source/Zh/doc/new_features/v136_features_doc.rst`](../docs/source/Zh/doc/new_features/v136_features_doc.rst)。

- **`enumerate_monitors` + `Monitor` / `virtual_bounds` / `monitor_at_point` / `monitor_for_window` / `to_local` / `to_virtual` / `remap_point`**(`AC_enumerate_monitors`、`AC_monitor_at_point`):`snap_window` / `arrange_grid` / 版面規劃器都假設單一主螢幕 `(width, height)`——對多螢幕無感,無法在第二台顯示器鋪排或處理負原點虛擬桌面。本功能補上實體層:聯集虛擬邊界、某點 / 某視窗屬於哪台螢幕、虛擬↔螢幕區域座標轉換,以及跨解析度 / DPI 的等效位置重映射。對 `Monitor` dataclass 的純幾何 → 完全無頭可測;`enumerate_monitors` 具可注入 provider(預設 `mss`)。

## 本次更新 (2026-06-23) — 影像前處理(供 OCR / 模板比對)

在辨識或比對前先清理畫面。完整參考:[`docs/source/Zh/doc/new_features/v135_features_doc.rst`](../docs/source/Zh/doc/new_features/v135_features_doc.rst)。

- **`preprocess_image` + `to_grayscale` / `binarize` / `upscale` / `denoise` / `deskew` / `enhance_contrast`**(`AC_preprocess_image`):`locate_text` 與 `match_template` 把*原始*擷取直接餵給 OCR / 比對器——小字、暗色主題、低對比與歪斜會嚴重影響兩者,而框架毫無前處理接縫。本功能加入標準流程(灰階 → 放大 → 二值化 → 去歪斜 → 去噪 → CLAHE),倍增其準確度。可注入 haystack → ndarray;`detect_skew_angle` 量測文字旋轉;`binarize` 提供 otsu / adaptive。執行器命令把清理後影像寫入路徑。可對合成陣列無頭測試。

## 本次更新 (2026-06-23) — 排列多個視窗(網格 / 層疊)

一次呼叫排好一整組視窗。完整參考:[`docs/source/Zh/doc/new_features/v134_features_doc.rst`](../docs/source/Zh/doc/new_features/v134_features_doc.rst)。

- **`arrange_grid` / `arrange_cascade`**(`AC_arrange_grid`、`AC_arrange_cascade`):`snap_window` 移動*一個*視窗、版面規劃器只*計算*矩形——這兩個把迴圈補完,接受一組視窗標題並實際把每個符合的視窗移入網格(自動近正方形,或明確 `rows`/`cols` + `gap`)或對角線層疊。以版面規劃器為基礎並沿用 `snap_window` 的可注入 `mover`/`screen_size` 接縫,因此完全無頭可測;回傳移動的視窗數。

## 本次更新 (2026-06-23) — 視窗鋪排 / 版面幾何規劃器

計算應用程式視窗該放在哪裡——半邊、網格、層疊。完整參考:[`docs/source/Zh/doc/new_features/v133_features_doc.rst`](../docs/source/Zh/doc/new_features/v133_features_doc.rst)。

- **`tile_rect` / `grid_rects` / `cascade_rects`**(`AC_tile_rect`、`AC_grid_rects`、`AC_cascade_rects`):`save/restore_window_layout` 重播*精確*的已存位置、`snap_window` 移動*一個*視窗——沒有任何功能能*計算*出全新的多視窗版面。此純幾何規劃器在給定螢幕工作區下,回傳半邊、四分之一、三分之一、R×C 網格與錯位層疊的目標矩形,讓腳本能以決定性方式排列視窗。回傳 `WindowRect`(`.as_tuple()` / `.to_dict()`);`gap` 內縮鋪排間距;跨平台且完全無頭可測;可與任何視窗移動後端組合。

## 本次更新 (2026-06-23) — 以邊緣 / 輪廓定位 UI 元素(免模板)

在從未見過的畫面上找出可點擊的方框。完整參考:[`docs/source/Zh/doc/new_features/v132_features_doc.rst`](../docs/source/Zh/doc/new_features/v132_features_doc.rst)。

- **`find_shapes` / `find_rectangles`**(`AC_find_shapes`、`AC_find_rectangles`):其他定位器都需要一個尋找對象——模板、顏色或文字。這兩個什麼都不需要:Canny 邊緣偵測 + 輪廓擷取回傳各個形狀的邊界框(`{x,y,width,height,area,center,aspect}`,由大到小),讓腳本能結構性地列舉卡片 / 按鈕 / 輸入框並點擊第 N 個。`find_rectangles` 只保留凸四邊形,並加上 `aspect_range=(min,max)` 寬高比過濾(`(1.5,8)` 取寬按鈕)。可注入 haystack → 無頭可測。

## 本次更新 (2026-06-23) — ORB 特徵比對(對旋轉 / 縮放 / 主題穩健)

即使目標旋轉、縮放或換主題也能找到。完整參考:[`docs/source/Zh/doc/new_features/v131_features_doc.rst`](../docs/source/Zh/doc/new_features/v131_features_doc.rst)。

- **`feature_match`**(`AC_feature_match`):像素模板比對(`match_template` / `match_masked`)是做像素相關運算,因此目標一旦旋轉、以未列出的倍率縮放或重新上色(亮 / 暗主題、hover)就會失效。本功能比對 ORB *關鍵點*並擬合 RANSAC 單應矩陣,回傳四個投影 `corners`、`center`、`inliers` 內點數與內點比例 `score`。ORB 邊界 / patch 尺寸會針對圖示大小的模板自動縮小(OpenCV 預設會將其捨棄)。僅用 OpenCV 核心(不需 contrib);可注入 haystack → 無頭可測。

## 本次更新 (2026-06-23) — 結構相似度(SSIM)比較

會告訴你*哪裡*變了的感知式畫面比較。完整參考:[`docs/source/Zh/doc/new_features/v130_features_doc.rst`](../docs/source/Zh/doc/new_features/v130_features_doc.rst)。

- **`ssim_compare` / `ssim_changed_regions`**(`AC_ssim_compare`、`AC_ssim_changed_regions`):像素差(`diff_screenshots`)會因一像素位移而誤報;直方圖(`detect_drift`)對版面無感。SSIM 是標準視覺回歸度量——容忍輕微光照變化、對結構變化敏感。`ssim_compare` 回傳 0..1 分數(1.0 = 完全相同);`ssim_changed_regions` 回傳哪裡移動了的方框。`ignore=[[x,y,w,h]]` 可遮罩即時時鐘 / 游標。純 NumPy + OpenCV(不需 scikit-image);可注入影像配對 → 無頭可測。

## 本次更新 (2026-06-23) — 遮罩模板比對

不論背景如何都能比對圖示。完整參考:[`docs/source/Zh/doc/new_features/v129_features_doc.rst`](../docs/source/Zh/doc/new_features/v129_features_doc.rst)。

- **`match_masked` / `match_masked_all`**(`AC_match_masked`、`AC_match_masked_all`):一般模板比對會計分*每個*像素,因此從某背景裁切出的圖示在不同背景上會比對失敗。本功能只計算你標記為相關的像素——明確的灰階 `mask`,或 RGBA 模板的 alpha 通道——讓透明 /「不在乎」的像素不再拉低分數。回傳與計分模板比對相同的 `Match`(score/center);使用 OpenCV 遮罩 `TM_CCORR_NORMED`,NaN 歸零。可注入 haystack → 無頭可測。

## 本次更新 (2026-06-23) — 依顏色定位螢幕區域

依顏色找出綠色狀態藥丸 / 紅色橫幅。完整參考:[`docs/source/Zh/doc/new_features/v128_features_doc.rst`](../docs/source/Zh/doc/new_features/v128_features_doc.rst)。

- **`find_color_region` / `find_color_regions`**(`AC_find_color_region`):`color_stats` 只描述區域顏色、`assert_pixel` 檢查單點——兩者都不*定位*彩色區域。本功能將接近目標 RGB(在 `tolerance` 內)的像素遮罩起來,回傳相連區塊的框(`{x,y,width,height,area,center}`,由大到小)——用於模板脆弱的狀態燈、進度填充、錯誤橫幅。可注入 haystack → 無頭可測;OpenCV/NumPy 透過 `je_open_cv`。

## 本次更新 (2026-06-23) — 具信心分數的模板比對

回傳分數、搜尋多尺度、找出所有出現處的模板比對。完整參考:[`docs/source/Zh/doc/new_features/v127_features_doc.rst`](../docs/source/Zh/doc/new_features/v127_features_doc.rst)。

- **`match_template` / `match_template_all` / `best_matches` / `TemplateMatch`**(`AC_match_template`、`AC_match_template_all`):既有比對器(`find_object`)為單一尺度且*丟棄分數*。本功能回傳帶 `score`/`scale`/`center` 的 `Match`、搜尋 `scales` 容忍 DPI/縮放,並以非極大值抑制列舉每個出現處。可注入 `haystack`(ndarray/路徑/PIL)→ 無頭可測;OpenCV/NumPy 透過 `je_open_cv` 相依。

## 本次更新 (2026-06-23) — 等待視窗標題(正則)

阻塞直到視窗標題符合正則(或消失)。完整參考:[`docs/source/Zh/doc/new_features/v126_features_doc.rst`](../docs/source/Zh/doc/new_features/v126_features_doc.rst)。

- **`wait_until_window_title`**(`AC_wait_window_title`):`wait_for_window` 以子字串比對且僅等*出現*;`wait_until_window_closed` 為子字串消失。本功能預設以正則表達式比對(`regex=False` 改子字串),並可等待標題消失(`present=False`)——例如等分頁導覽至 `r".*— Checkout$"`。標題來源可注入、無頭可測。

## 本次更新 (2026-06-23) — 表格 / 格線儲存格定位

依(列、欄)從儲存格邊界框定位表格儲存格。完整參考:[`docs/source/Zh/doc/new_features/v125_features_doc.rst`](../docs/source/Zh/doc/new_features/v125_features_doc.rst)。

- **`cluster_grid` / `locate_cell`**(`AC_grid_cell`):`anchor_locator` 處理成對關係,但無法定位二維格線。給定儲存格邊界框(來自 `locate_all_image` / `find_text_matches`),本功能將其分群為列(依中心 y 在 `row_tolerance` 內)與欄(依中心 x),並回傳 0 起算 `(row, col)` 儲存格的中心——可直接點擊。純分群、完全無頭可測。

## 本次更新 (2026-06-23) — 錨點序數與全部定位

挑選第 N 個錨點相對比對,或列舉全部。完整參考:[`docs/source/Zh/doc/new_features/v124_features_doc.rst`](../docs/source/Zh/doc/new_features/v124_features_doc.rst)。

- **`anchor_locate(..., ordinal=N)` / `anchor_locate_all`**(`AC_anchor_locate` ordinal、`AC_anchor_locate_all`):`anchor_locate` 總是回傳單一最近的比對——無法取「標題下方第 2 列」或列出每一列。本功能加入 1 起算的 `ordinal` 選擇器(向後相容;`ordinal=1` 即最近)與回傳依距離排序所有比對的 `anchor_locate_all`——表格/清單列選取的基礎元件。純排序核心、具決定性。

## 本次更新 (2026-06-23) — 在動作群組中持續按住修飾鍵

在多個動作之間持續按住 ctrl/shift,即使出錯也會放開。完整參考:[`docs/source/Zh/doc/new_features/v123_features_doc.rst`](../docs/source/Zh/doc/new_features/v123_features_doc.rst)。

- **`hold_modifiers` / `plan_with_modifiers`**(`AC_with_modifiers`):`hotkey` 會立即放開按鍵——先前無法在多個獨立動作之間持續按住修飾鍵(shift 連點範圍選取、ctrl 連點多選)並保證放開。`hold_modifiers` 是 context manager,進入時按下、離開時(在 `finally`)以反向放開,因此不會外洩;`plan_with_modifiers` 為純計畫。可注入 sink、具決定性。

## 本次更新 (2026-06-23) — Unicode 文字輸入(emoji / CJK)

輸入 `write` 無法處理的任何 Unicode(emoji / CJK / 重音)。完整參考:[`docs/source/Zh/doc/new_features/v122_features_doc.rst`](../docs/source/Zh/doc/new_features/v122_features_doc.rst)。

- **`type_unicode` / `plan_paste` / `unicode_code_units`**(`AC_type_unicode`):`write` 透過虛擬鍵表輸入,對 emoji/CJK/許多重音字會*拋例外*。`type_unicode` 以設定剪貼簿再貼上(`modifier` ctrl/command)可靠地輸入任何文字。`unicode_code_units` 將文字拆成 UTF-16 碼元(代理對)供 KEYEVENTF_UNICODE 後端使用。純計畫 + 可注入 sink、具決定性。

## 本次更新 (2026-06-23) — 等待區域顏色

阻塞直到某顏色填滿(或離開)螢幕區域。完整參考:[`docs/source/Zh/doc/new_features/v121_features_doc.rst`](../docs/source/Zh/doc/new_features/v121_features_doc.rst)。

- **`wait_until_color`**(`AC_wait_color`):`wait_for_pixel` 精確比對單點、`wait_until_pixel_changes` 偵測單點任何變化——兩者都無法等「狀態燈變綠」/「進度條填滿」/「紅色橫幅消失」。本功能計數區域中接近 `target_rgb`(在 `tolerance` 內)的像素,當比例越過 `min_fraction`(或 `present=False` 時低於)即成功。可注入 sampler、無頭可測。純標準函式庫。

## 本次更新 (2026-06-23) — 相對滑鼠移動

從目前位置將指標位移一個增量。完整參考:[`docs/source/Zh/doc/new_features/v120_features_doc.rst`](../docs/source/Zh/doc/new_features/v120_features_doc.rst)。

- **`move_mouse_relative` / `relative_target`**(`AC_move_mouse_relative`):滑鼠 wrapper 只有絕對的 `set_mouse_position`——沒有給相對指標 / 畫布 / FPS 應用與漸進式拖曳用的 `moveRel(dx, dy)`。本功能讀取即時位置並依增量移動;`relative_target` 為純算術,getter/setter 可注入以供無頭測試。純標準函式庫、具決定性。

## 本次更新 (2026-06-23) — 按住按鍵 / 自動重複

按住一個鍵一段時間,或以固定頻率自動重複。完整參考:[`docs/source/Zh/doc/new_features/v119_features_doc.rst`](../docs/source/Zh/doc/new_features/v119_features_doc.rst)。

- **`hold_key` / `plan_key_hold`**(`AC_hold_key`):`type_keyboard` 是瞬間按下+放開——先前沒有「按住此鍵 N 秒」(遊戲移動、按住捲動)或「每秒送 R 次」(自動重複)。`plan_key_hold` 建立決定性操作計畫(按下/等待/放開,或為 `rate_hz` 產生 N 個間隔按鍵事件);`hold_key` 將等待導向可注入的 `sleep`、按鍵導向可注入的 `sink`。純計畫、具決定性。

## 本次更新 (2026-06-23) — 等待消失(阻塞式 vanish 等待)

阻塞直到轉圈圈 / toast / 對話框消失。完整參考:[`docs/source/Zh/doc/new_features/v118_features_doc.rst`](../docs/source/Zh/doc/new_features/v118_features_doc.rst)。

- **`wait_until_gone` / `wait_until_image_gone` / `wait_until_text_gone`**(`AC_wait_image_gone`、`AC_wait_text_gone`):`wait_for_image`/`wait_for_text` 只阻塞到某物*出現*,`observer` 則以非同步回呼在消失時觸發——先前沒有*阻塞式*的「等到此影像/文字消失再繼續」。通用的 `wait_until_gone` 接受任意述詞(可無頭測試);影像/文字輔助函式從定位函式建立。`gone_for_s` 可消抖。回傳 `WaitOutcome`。純標準函式庫。

## 本次更新 (2026-06-23) — 清空再輸入欄位

可靠地設定文字欄位的值(Playwright 的 `fill` 慣用法)。完整參考:[`docs/source/Zh/doc/new_features/v117_features_doc.rst`](../docs/source/Zh/doc/new_features/v117_features_doc.rst)。

- **`set_field_text` / `plan_field_set`**(`AC_set_field_text`):先前沒有單一的「聚焦 → 清空 → 設值」基本元件,且 `write` 對 emoji/CJK 會拋例外。本功能清空欄位(全選 + 刪除)後再輸入文字——可選擇透過剪貼簿(`paste=True`),這是 `write` 無法處理之 Unicode 的安全途徑。`modifier` 為平台指令鍵(`ctrl`/`command`)。純計畫 + 可注入 sink、具決定性。

## 本次更新 (2026-06-22) — 多路徑點滑鼠手勢

讓指標沿著路徑點折線移動或拖曳。完整參考:[`docs/source/Zh/doc/new_features/v116_features_doc.rst`](../docs/source/Zh/doc/new_features/v116_features_doc.rst)。

- **`plan_path` / `move_along_path` / `drag_path` / `path_easings`**(`AC_move_along_path`、`AC_drag_path`):`humanize` 與 `tween_drag` 只在單一起點→終點之間插值——先前無法驅動任意的路徑點鏈(簽名、框選、多停靠點拖曳)並在整段路徑中按住按鍵。`plan_path` 為純緩動點運算(重用 `tween_drag` 的緩動、交接點去重);移動/拖曳透過可注入的 sink 派發以供無頭測試。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 檢查碼演算法

計算/驗證 Luhn、Verhoeff、Damm 與 ISO 7064 MOD 97-10 檢查碼。完整參考:[`docs/source/Zh/doc/new_features/v115_features_doc.rst`](../docs/source/Zh/doc/new_features/v115_features_doc.rst)。

- **`luhn_validate` / `luhn_check_digit` / `verhoeff_*` / `damm_*` / `mod97_10_*`**(`AC_checksum_validate`、`AC_checksum_digit`):`pii_text` 以正則偵測卡號/IBAN 形狀、`data_quality` 做正則驗證,但沒有任何功能計算或驗證*檢查碼*。本功能加入多數識別碼背後的四種方案(卡號/IMEI、國民身分碼、IBAN)——`identifier_validate` 所依據的共用引擎。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 移動平均平滑

平滑雜訊值序列。完整參考:[`docs/source/Zh/doc/new_features/v102_features_doc.rst`](../docs/source/Zh/doc/new_features/v102_features_doc.rst)。

## 本次更新 (2026-06-22) — GNU gettext 目錄 I/O(.po / .mo)

讀取/編譯事實標準翻譯格式。完整參考:[`docs/source/Zh/doc/new_features/v114_features_doc.rst`](../docs/source/Zh/doc/new_features/v114_features_doc.rst)。

- **`parse_po` / `read_mo` / `GettextCatalog` / `parse_po_file` / `read_mo_file`**(`AC_gettext_translate`、`AC_gettext_ngettext`):本專案能偽在地化並渲染 ICU 訊息,卻無法讀取 GNU gettext `.po`/`.mo`。本功能解析 `.po`(上下文、複數、以 `gettext.c2py` 處理 `Plural-Forms` 標頭)、編譯可被 Python 內建 `gettext.GNUTranslations` 載入的標準 `.mo`,並提供 `gettext`/`ngettext`/`pgettext`。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — ICU-lite MessageFormat(複數 / 選擇)

渲染依數量變化的在地化訊息。完整參考:[`docs/source/Zh/doc/new_features/v113_features_doc.rst`](../docs/source/Zh/doc/new_features/v113_features_doc.rst)。

- **`format_message` / `plural_category` / `ordinal_category`**(`AC_format_message`):`i18n_test.check_catalog` 只比較佔位符集合、`interpolate` 只做扁平 `${var}`——兩者都無法渲染 `"{count, plural, one {# item} other {# items}}"`。本功能實作多數應用會用到的 ICU MessageFormat 子集:`select`、`plural`、`selectordinal` 搭配 CLDR 類別、優先於類別的精確 `=N` 選擇器、`#` 數量、`offset:`、巢狀與單引號跳脫。複數規則可注入。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 地區感知清單格式化

依某語言的期望串接項目(「A、B and C」)。完整參考:[`docs/source/Zh/doc/new_features/v112_features_doc.rst`](../docs/source/Zh/doc/new_features/v112_features_doc.rst)。

- **`format_list`**(`AC_format_list`):直接 `", ".join` 只會得到「A, B, C」,沒有「and/or」也沒有在地化。本功能實作 CLDR 清單樣式組合,支援連接(and)/選擇(or)/單位(unit)樣式,並依地區提供連接詞與序列逗號規則(`en`/`es`/`fr`/`de`/`pt`)——`format_list(["a","b","c"])` → 「a, b, and c」,`locale="es"` → 「a, b y c」。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 雙向文字 QA(Trojan-Source 掃描)

抓出隱形的 Unicode 方向格式控制(RTL QA + Trojan-source)。完整參考:[`docs/source/Zh/doc/new_features/v111_features_doc.rst`](../docs/source/Zh/doc/new_features/v111_features_doc.rst)。

- **`detect_bidi_issues` / `bidi_controls` / `is_bidi_balanced` / `base_direction` / `is_trojan_source` / `strip_bidi_controls` / `has_bidi_controls`**(`AC_bidi_check`、`AC_bidi_strip`):`confusables` 抓相似字元,但雙向控制(LRO/RLO/PDF、隔離、標記)可悄悄改變呈現順序——既是 RTL QA 缺口,也是「Trojan Source」攻擊(CVE-2021-42574)。本功能列出控制字元、檢查巢狀平衡、推斷基底方向,並標記重排格式。純標準函式庫(`unicodedata`)、具決定性。

## 本次更新 (2026-06-22) — 可讀性評分

評估文字有多難讀;以閱讀年級把關產生的文案。完整參考:[`docs/source/Zh/doc/new_features/v110_features_doc.rst`](../docs/source/Zh/doc/new_features/v110_features_doc.rst)。

- **`flesch_reading_ease` / `flesch_kincaid_grade` / `gunning_fog` / `smog_index` / `automated_readability_index` / `readability_report` / `readability_stats` / `count_syllables`**(`AC_readability_report`):文字工具能正規化、比對與排名文字,卻從未評估*難度*。本功能在決定性斷詞器與音節啟發式之上加入經典英文可讀性公式,讓測試能斷言畫面訊息或標籤落在目標閱讀年級內。純標準函式庫(`re`/`math`)、具決定性。

## 本次更新 (2026-06-22) — 易混淆字元 / 同形異義字偵測

抓出 Unicode 視覺仿冒(IDN 同形異義字釣魚、仿冒標籤)。完整參考:[`docs/source/Zh/doc/new_features/v109_features_doc.rst`](../docs/source/Zh/doc/new_features/v109_features_doc.rst)。

- **`confusable_skeleton` / `is_confusable` / `detect_homoglyphs` / `is_mixed_script` / `scripts_of`**(`AC_confusable_scan`、`AC_confusable_compare`):西里爾字母 `"а"` 與拉丁字母 `"a"` 在像素上相同,因此 `"pаypal"` 讀來是 `"paypal"` 卻比較不相等。參照 Unicode TR39,本功能將易混淆字折疊為原型骨架(骨架相同即相符),並標記混用文字系統的權杖。純標準函式庫(`unicodedata`)、具決定性。

## 本次更新 (2026-06-22) — 地區感知字串排序

依某語言讀者的期望排序字串。完整參考:[`docs/source/Zh/doc/new_features/v108_features_doc.rst`](../docs/source/Zh/doc/new_features/v108_features_doc.rst)。

- **`sort_strings` / `collation_compare` / `collation_key`**(`AC_collation_sort`、`AC_collation_compare`):Python 預設的 `sorted` 是碼位順序,因此 `"Z" < "a"`,而 `"ä"` 離 `"a"` 很遠。本 Unicode-Collation-lite 鍵先依基底字母、再依變音符號(次層)、再依大小寫(三層)排序,並可用 `tailoring` 字母表讓瑞典文將 `å ä ö` 排在 `z` 之後。純標準函式庫(`unicodedata`)、跨平台具決定性——不像 `locale.strxfrm`。

## 本次更新 (2026-06-22) — 交易型 Outbox

持久化緩衝事件並以至少一次傳遞排空。完整參考:[`docs/source/Zh/doc/new_features/v107_features_doc.rst`](../docs/source/Zh/doc/new_features/v107_features_doc.rst)。

- **`Outbox`**(`AC_outbox_enqueue`、`AC_outbox_pending`):`events.cloud_events` 同步發送且無持久化——當機或網路抖動就會丟失事件。Outbox 先持久化每個事件,再透過注入的 sink 以至少一次傳遞 `drain` 待傳遞項目:sink 失敗時項目維持待傳遞以供重試,直到 `max_attempts`,之後列為死信。`save` / `load` 讓事件能跨重啟存活。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 樂觀並行版本儲存

只在版本未變時更新(compare-and-swap / If-Match)。完整參考:[`docs/source/Zh/doc/new_features/v106_features_doc.rst`](../docs/source/Zh/doc/new_features/v106_features_doc.rst)。

- **`VersionedStore` / `VersionConflict` / `if_match_header` / `check_if_match`**(`AC_cas_put`、`AC_cas_get`):`http_conditional` 以 ETag 做讀取快取,但從不用於寫入並行。本地 compare-and-swap 儲存僅在 `expected_version` 相符時 `put`(過時寫入拋出 `VersionConflict`)、遞增單調版本,並橋接到 HTTP `If-Match` —— ETag 故事的寫入面。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 逐串流序號間隙偵測

依序號偵測遺漏/亂序/重複的訊息。完整參考:[`docs/source/Zh/doc/new_features/v105_features_doc.rst`](../docs/source/Zh/doc/new_features/v105_features_doc.rst)。

- **`SequenceTracker`**(`AC_sequence_observe`):沒有東西追蹤每個串流的單調序號。`observe(stream, seq)` 將每個分類為 `ok` / `duplicate` / `gap`(附 `missing` 序號)/ `reorder`(遲到填補間隙),並提供 `gaps` 與 `high_water`。與 `dedup_window` 互補。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 時間視窗去重

在 TTL 視窗內丟棄重複/重送的訊息。完整參考:[`docs/source/Zh/doc/new_features/v104_features_doc.rst`](../docs/source/Zh/doc/new_features/v104_features_doc.rst)。

- **`DedupWindow`**(`AC_dedup_check`):`work_queue` 只對進行中參照去重,因此已完成的參照會重新入列、重送的 webhook 會重複處理。本滑動視窗收件匣對訊息 id 做 `check_and_mark` —— 首次回傳 `True`、`ttl_s` 視窗內重複回傳 `False` —— 把至少一次投遞轉換成視窗內恰好一次。可注入時鐘、大小有界。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 冪等鍵儲存

副作用只執行一次,重試時重播其回應。完整參考:[`docs/source/Zh/doc/new_features/v103_features_doc.rst`](../docs/source/Zh/doc/new_features/v103_features_doc.rst)。

- **`IdempotencyStore` / `request_fingerprint` / `IdempotencyConflict`**(`AC_idempotency_begin`、`AC_idempotency_complete`):`RetryPolicy` 重試會重跑,`work_queue` 只對進行中參照去重 —— 沒有東西快取第一次結果。本 Stripe 風格儲存為某鍵回傳 `new`/`in_progress`/`completed`、重播已儲存回應、指紋衝突時拋出例外,並支援可注入時鐘 TTL + JSON 持久化。純標準函式庫、具決定性。

- **`sma` / `wma` / `ewma` / `rolling`**(`AC_sma`、`AC_ewma`):`stats.describe` 彙總整個樣本,`timeseries` 把計數器滾成速率,但沒有東西能平滑雜訊訊號。本功能加入尾端簡單/加權/指數加權移動平均與通用滾動歸約器,全部回傳與輸入時間線對齊的等長 list。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 單序列異常偵測

標記單一即時度量序列中的尖峰。完整參考:[`docs/source/Zh/doc/new_features/v101_features_doc.rst`](../docs/source/Zh/doc/new_features/v101_features_doc.rst)。

- **`detect_anomalies` / `mad_anomalies` / `zscore_anomalies` / `ewma_control`**(`AC_detect_anomalies`):`data_drift` 是兩批次分布偏移,`slo.burn_alerts` 只對預算燃燒設門檻 —— 都無法指出單一序列中*哪個*值異常。本功能以穩健 MAD(modified z-score)、純 z-score 與 EWMA 控制圖(可選 in-control 基準)標記離群值 —— `{index, value, score, is_anomaly}` 記錄。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 近似重複文字偵測(SimHash / MinHash)

為文字產生指紋以大規模找近似重複。完整參考:[`docs/source/Zh/doc/new_features/v100_features_doc.rst`](../docs/source/Zh/doc/new_features/v100_features_doc.rst)。

- **`simhash` / `near_duplicates` / `minhash_signature` / `minhash_similarity`**(`AC_simhash`、`AC_near_duplicates`):`fuzzy_dedupe` 是 O(n²) 成對且無穩定指紋,`image_dedup` 只雜湊像素。本功能加入文字對應 —— SimHash(Hamming 距離近似重複分群)與 MinHash(估計 Jaccard),使用固定 `blake2b` 雜湊取得具決定性的指紋。可搭配 `normalize_text`。純標準函式庫。

## 本次更新 (2026-06-22) — 字串距離相似度量

比對打字錯誤與重排 token。完整參考:[`docs/source/Zh/doc/new_features/v99_features_doc.rst`](../docs/source/Zh/doc/new_features/v99_features_doc.rst)。

- **`levenshtein` / `damerau_levenshtein` / `jaro` / `jaro_winkler` / `jaccard` / `dice` / `similarity`**(`AC_text_similarity`):`fuzzy` 只提供 difflib 的 gestalt ratio。本功能補上它缺少的編輯距離與 token 集合度量 —— Jaro-Winkler(短標籤標準)、Damerau(轉置感知)、字元 n-gram Jaccard/Dice —— 並提供統一的 `similarity()` 把每個度量正規化到 `[0, 1]`。可搭配 `normalize_text`。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 時間序列轉換

把計數器轉成速率;降採樣與重採樣。完整參考:[`docs/source/Zh/doc/new_features/v98_features_doc.rst`](../docs/source/Zh/doc/new_features/v98_features_doc.rst)。

- **`ts_rate` / `ts_irate` / `ts_increase` / `ts_delta` / `ts_downsample` / `ts_resample`**(`AC_ts_rate`、`AC_ts_downsample`):`observability` 計數器只存當前值(無處可把計數器轉速率),`cost_telemetry` 只以天分桶。本功能在 `(timestamp, value)` 序列上加入 Prometheus 風格、具重置感知的 rate/increase/delta、tumbling-bucket 降採樣(avg/sum/min/max/first/last/count)與網格重採樣(last/linear/none)。不讀 wall clock、具決定性。純標準函式庫。

## 本次更新 (2026-06-22) — Unicode 文字正規化與 Slug

在 fuzzy/search/OCR 比對前正規化文字。完整參考:[`docs/source/Zh/doc/new_features/v97_features_doc.rst`](../docs/source/Zh/doc/new_features/v97_features_doc.rst)。

- **`normalize_text` / `deaccent` / `slugify` / `normalize_quotes` / `fold_whitespace`**(`AC_normalize_text`、`AC_slugify`):`fuzzy` 與 `search_index.tokenize` 只做小寫,OCR 比對只做 `.lower()`+子字串,因此 `"Café"`(NFC)、`"Café"`(NFD)、`"cafe"` 會比對不相等。本功能補上缺少的正規化層(NFKC + casefold + 空白折疊、去重音、智慧引號對應、ASCII slug)。純標準函式庫(`unicodedata`)、具決定性。

## 本次更新 (2026-06-22) — JSON-Schema 相容性檢查

把結構變更分類為 backward/forward/full。完整參考:[`docs/source/Zh/doc/new_features/v96_features_doc.rst`](../docs/source/Zh/doc/new_features/v96_features_doc.rst)。

- **`check_compatibility` / `diff_schemas` / `is_backward_compatible` / `is_forward_compatible` / `is_full_compatible`**(`AC_check_compatibility`):我們能依結構驗證並產生結構,但無法回答「舊消費者是否仍能讀新資料?」。本功能依 Confluent/Avro backward/forward/full 規則,在物件子集上分類變更(新增必填欄位、移除欄位、收窄/放寬型別、enum 增減)。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 具型別的設定結構

把設定驗證成具型別的物件。完整參考:[`docs/source/Zh/doc/new_features/v95_features_doc.rst`](../docs/source/Zh/doc/new_features/v95_features_doc.rst)。

- **`ConfigSchema` / `ConfigField` / `validate_config` / `coerce`**(`AC_validate_config`):`assets._coerce` 只轉換單一值,`json_schema` 只驗證結構,但沒有東西把已解析設定 dict 綁定成具型別物件並做必填強制與選項約束。本功能轉換型別(`str`/`int`/`float`/`bool`)、套用預設、強制必填/選項,回傳 `{ok, config, errors}` —— 標準函式庫版 pydantic-settings。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — OTLP/JSON Span 匯出

以 collector 攝取的格式匯出 span。完整參考:[`docs/source/Zh/doc/new_features/v94_features_doc.rst`](../docs/source/Zh/doc/new_features/v94_features_doc.rst)。

- **`spans_to_otlp` / `attributes_to_otlp` / `write_otlp`**(`AC_spans_to_otlp`):`agent_trace.to_otel` 回傳扁平 dict,並非有效 OTLP/JSON(沒有 resourceSpans/scopeSpans 巢狀、時間不是 uint64 字串)。本功能把 span 包進正確封套,含 hex ID、uint64 字串時間,以及 OTLP `KeyValue` 屬性編碼 —— OpenTelemetry collector file exporter 讀取的格式。與 `trace_context` 搭配。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 標準日誌行與結構化日誌

每次執行一行寬事件,並帶 trace 關聯。完整參考:[`docs/source/Zh/doc/new_features/v93_features_doc.rst`](../docs/source/Zh/doc/new_features/v93_features_doc.rst)。

- **`CanonicalLogLine` / `JSONLogFormatter` / `bind_trace_context`**(`AC_canonical_log`):`logging_instance` 輸出固定的管線分隔字串,沒有 JSON 也沒有 trace/span 欄位。本功能加入 Stripe 風格的標準日誌行(欄位累積器 + 可注入時鐘的 `timer`)以及攜帶 `trace_id`/`span_id` 的 JSON `logging.Formatter` —— 與 `trace_context` 對應的 log-trace 關聯。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 條件式 HTTP 請求與快取驗證子

略過重新下載未變更的資源(ETag / 304)。完整參考:[`docs/source/Zh/doc/new_features/v92_features_doc.rst`](../docs/source/Zh/doc/new_features/v92_features_doc.rst)。

- **`store_validators` / `conditioned_call` / `is_fresh` / `parse_cache_control` / `is_not_modified`**(`AC_parse_cache_control`、`AC_store_validators`):`http_request` 從不送 `If-None-Match`/`If-Modified-Since` 也不讀 `Cache-Control`,因此每次輪詢都重新下載。本功能擷取驗證子、解析 `Cache-Control`(max-age/no-store/…)、以明確 age 判定新鮮度、為下一個請求加上條件標頭,並偵測 `304 Not Modified`。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — Cookie Jar(HTTP 工作階段攜帶)

跨 HTTP 呼叫攜帶工作階段。完整參考:[`docs/source/Zh/doc/new_features/v91_features_doc.rst`](../docs/source/Zh/doc/new_features/v91_features_doc.rst)。

- **`CookieJar` / `parse_set_cookie`**(`AC_cookie_header`、`AC_parse_set_cookie`):`http_request` 無狀態 —— 沒有工作階段 cookie 在呼叫間延續,login-then-call 流程無法在無頭情況下攜帶工作階段。本功能把 `Set-Cookie` 標頭解析進 jar、建立 `Cookie` 請求標頭,並以 JSON 存/讀 jar(`Max-Age<=0`/空值時清除)。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — HTTP 內容協商與解壓縮

建立 `Accept` 標頭並解碼 gzip/deflate。完整參考:[`docs/source/Zh/doc/new_features/v90_features_doc.rst`](../docs/source/Zh/doc/new_features/v90_features_doc.rst)。

- **`build_accept` / `build_accept_encoding` / `parse_quality_values` / `decode_body` / `negotiated_call`**(`AC_decode_body`、`AC_parse_quality_values`):`urllib`/`http_request` 從不設定 `Accept-Encoding` 也不解碼 `Content-Encoding`,壓縮內文以原始形式抵達。本功能加入 `Accept`/`Accept-Encoding` 建構器、q-value 解析器(依品質排序),以及 gzip/deflate(含 raw deflate)解碼。排除 Brotli(非標準函式庫)。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — multipart/form-data 建立與解析

建立檔案上傳內文。完整參考:[`docs/source/Zh/doc/new_features/v89_features_doc.rst`](../docs/source/Zh/doc/new_features/v89_features_doc.rst)。

- **`build_multipart` / `parse_multipart` / `MultipartFile`**(`AC_build_multipart`、`AC_parse_multipart`):`http_request` 只送 JSON/原始 —— 沒有檔案上傳,且解析 multipart 的標準函式庫 `cgi` 已在 3.13 移除。本功能以可注入的 boundary(位元組穩定)從文字欄位與檔案組裝 `multipart/form-data` 內文,並能解析回 `{fields, files}`。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 設定與日誌的機密遮蔽

在記錄或匯出前遮蔽機密。完整參考:[`docs/source/Zh/doc/new_features/v88_features_doc.rst`](../docs/source/Zh/doc/new_features/v88_features_doc.rst)。

- **`redact_config` / `redact_secret_text`**(`AC_redact_config`、`AC_redact_secret_text`):`utils/redaction` 只模糊截圖,`secrets_scan` 只*偵測* —— 兩者都不回傳遮蔽後的副本。本功能重用 `secrets_scan` 偵測器(鍵名模式、AWS/bearer 格式、高熵)回傳設定結構的遮蔽深層副本,並遮蔽自由文字日誌行中看似機密的 token(保留周圍文字)。vault 參照(`${secrets.*}`)保持不變。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — RFC 8288 Link 標頭與分頁

解析 `Link` 標頭並跟隨 `rel="next"`。完整參考:[`docs/source/Zh/doc/new_features/v87_features_doc.rst`](../docs/source/Zh/doc/new_features/v87_features_doc.rst)。

- **`parse_link_header` / `next_url` / `links_by_rel` / `paginate`**(`AC_parse_link_header`、`AC_next_url`):分頁的 REST API 回傳 `Link: <...>; rel="next"`,但沒有東西解析它。本功能解析該標頭(含逗號的引號值、多個連結)、依關係索引,`paginate` 透過注入的 `fetch`(傳輸/卡帶)跟隨 `rel="next"`,上限為 `max_pages`。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — 參照完整性檢查

跨資料表的外鍵、唯一鍵、accepted-values 與筆數檢查。完整參考:[`docs/source/Zh/doc/new_features/v86_features_doc.rst`](../docs/source/Zh/doc/new_features/v86_features_doc.rst)。

- **`check_foreign_key` / `check_unique_key` / `check_accepted_values` / `check_row_count`**(`AC_check_foreign_key`、`AC_check_unique_key`、`AC_check_accepted_values`、`AC_check_row_count`):`validate_rows` 是單列、單表(其 `unique` 只在單批次內去重)。本功能補上 dbt 風格通用檢查 —— 跨兩表的父子外鍵、單一/複合鍵唯一性、accepted-values、筆數範圍 —— 作用於 `load_rows`/`query_sqlite` 的資料列。純標準函式庫、具決定性。

## 本次更新 (2026-06-22) — URI-Scheme 值參照

在設定中儲存指標而非機密。完整參考:[`docs/source/Zh/doc/new_features/v85_features_doc.rst`](../docs/source/Zh/doc/new_features/v85_features_doc.rst)。

- **`resolve_ref` / `resolve_refs_in` / `is_ref` / `RefResolver`**(`AC_resolve_ref`、`AC_resolve_refs`):`interpolate` 只寫死 `${secrets.NAME}`,`AssetStore` 參照僅限 vault 名稱 —— 沒有通用的讀取時間接。本功能解析 `env://VAR`、`file://path`(可選 `base_dir` 防穿越保護)與 `secret://name`(可注入解析器或 governance broker),並走訪巢狀結構解析每個參照。env 讀取器 / secret 解析器 / 基底目錄皆可注入。純標準函式庫、具決定性。

## 本次更新 (2026-06-21) — W3C Baggage 傳播

跨 HTTP 攜帶橫切鍵值脈絡。完整參考:[`docs/source/Zh/doc/new_features/v84_features_doc.rst`](../docs/source/Zh/doc/new_features/v84_features_doc.rst)。

- **`Baggage` / `parse_baggage` / `format_baggage` / `inject_baggage` / `extract_baggage`**(`AC_baggage_parse`、`AC_baggage_format`):`trace_context` 攜帶 trace/span 身分,但沒有東西傳播橫切脈絡(`run_id`/`tenant`/`experiment`)。本功能實作 W3C Baggage 標頭 —— percent-encoded 的 `key=value` 清單 —— 以不可變的 `Baggage`(set/remove 回傳新實例)與不分大小寫的 inject/extract。與 `trace_context` 搭配。純標準函式庫、具決定性。

## 本次更新 (2026-06-21) — 資料集差異(資料列變更報告)

依鍵比對兩份表格式萃取。完整參考:[`docs/source/Zh/doc/new_features/v83_features_doc.rst`](../docs/source/Zh/doc/new_features/v83_features_doc.rst)。

- **`diff_rows` / `cell_changes` / `summarize_diff`**(`AC_diff_rows`、`AC_cell_changes`):框架能比對畫面/快照,但沒有任何東西能依鍵比對兩個**表格式**資料列集合。本功能為兩側建鍵索引並回報 `{added, removed, changed, unchanged}`(changed 帶 `{key, old, new}`),展開逐欄 `{key, column, old, new}` 變更,並統計每個分類。支援複合鍵;重複鍵以最後一列為準。純標準函式庫、具決定性。

## 本次更新 (2026-06-21) — 分布漂移偵測

檢查今天的資料形狀是否與基準一致。完整參考:[`docs/source/Zh/doc/new_features/v82_features_doc.rst`](../docs/source/Zh/doc/new_features/v82_features_doc.rst)。

- **`psi` / `ks_two_sample` / `categorical_drift` / `detect_drift`**(`AC_detect_drift`、`AC_categorical_drift`):`stats` 有 A/B 實驗檢定,但沒有 Population Stability Index,也沒有針對 reference-vs-current 分布的 KS 雙樣本檢定。本功能加入 PSI(分位分箱的 log-ratio)、KS 統計量與 Kolmogorov p 值,以及類別卡方 + total-variation 摘要 —— 與 `data_profile` 搭配。`detect_drift` 給出一次性的 `{psi, drifted, ks}` 判定。純標準函式庫、具決定性。

## 本次更新 (2026-06-21) — 分層設定解析器

以 `defaults < file < env < CLI` 優先序組合設定。完整參考:[`docs/source/Zh/doc/new_features/v81_features_doc.rst`](../docs/source/Zh/doc/new_features/v81_features_doc.rst)。

- **`LayeredConfig` / `deep_merge` / `SourceTrace`**(`AC_resolve_config`、`AC_explain_config`):`json_patch.merge_patch` 只合併兩份文件,`config_sync` 是 last-write-wins,`AssetStore` 是每環境扁平 —— 都無法組成有序優先序堆疊並深度合併,也無法回報每個鍵由哪層勝出。`add_layer(name, mapping, priority)` 後 `resolve()` 深度合併(巢狀 dict 遞迴、純量/list 取代);`explain("db.host")` 標明勝出層。各層由呼叫端提供(env 由外部傳入,絕不隱含 `os.environ`)。純標準函式庫、具決定性。

## 本次更新 (2026-06-21) — Server-Sent Events (SSE) 用戶端解析器

消費 `text/event-stream` 回應。完整參考:[`docs/source/Zh/doc/new_features/v80_features_doc.rst`](../docs/source/Zh/doc/new_features/v80_features_doc.rst)。

- **`parse_event_stream` / `SSEParser` / `SSEEvent`**(`AC_parse_sse`):MCP 的 HTTP 傳輸會發出 SSE,但沒有任何東西消費它 —— 一個串流的 LLM/agent/chatops 端點會讓 `http_request` 拿到原始 blob。本功能實作 WHATWG event-stream 解析演算法(`event`/`data`/`id`/`retry`、註解、前導空白規則、空白行派發),並提供逐塊的增量 `feed` 與一次性的 `parse_event_stream`。純標準函式庫、完全具決定性。

## 本次更新 (2026-06-21) — Dotenv (.env) 解析

把 12-factor `.env` 檔案讀進設定。完整參考:[`docs/source/Zh/doc/new_features/v79_features_doc.rst`](../docs/source/Zh/doc/new_features/v79_features_doc.rst)。

- **`parse_dotenv` / `load_dotenv` / `dotenv_values` / `dump_dotenv`**(`AC_parse_dotenv`、`AC_load_dotenv`):`load_vars_from_json` 載入扁平 JSON,但沒有任何東西讀取 de-facto 的 `.env` 檔案。本功能把 `KEY=VALUE` 行(`export` 前綴、單/雙引號、`\n`/`\t` 轉義、行內註解)解析成純 dict —— 不依賴 `python-dotenv`。載入器合併進呼叫端提供的 mapping 而非變動 `os.environ`,因此安全且具決定性。純標準函式庫。

## 本次更新 (2026-06-21) — RFC 9457 Problem Details 解析

從 HTTP 回應讀取標準化的 API 錯誤。完整參考:[`docs/source/Zh/doc/new_features/v78_features_doc.rst`](../docs/source/Zh/doc/new_features/v78_features_doc.rst)。

- **`parse_problem` / `is_problem` / `raise_for_problem` / `ProblemDetails`**(`AC_parse_problem`):`http_request` 回傳的非 2xx 內文未經解析,因此流程與 `assert_http` 無法以結構化方式讀取標準化的 API 錯誤。本功能解析 RFC 9457 `application/problem+json` 文件 —— 已註冊的 `type`/`title`/`status`/`detail`/`instance` 成員加上 vendor 擴充欄位 —— 對非 problem 回應回傳 `None`,或拋出 `HttpProblemError`。純標準函式庫、完全具決定性。

## 本次更新 (2026-06-21) — 資料剖析與結構推斷

掃描資料列集合並提出驗證結構。完整參考:[`docs/source/Zh/doc/new_features/v77_features_doc.rst`](../docs/source/Zh/doc/new_features/v77_features_doc.rst)。

- **`profile_rows` / `infer_schema`**(`AC_profile_rows`、`AC_infer_schema`):`validate_rows` 消費手寫結構,`stats.describe` 只彙總單一數值清單 —— 沒有任何東西掃描整個資料列集合。本功能剖析每欄(空值比例、基數、推斷型別、最常見值、數值 min/max/mean)並推斷出 `validate_rows` 相容結構(無空值即 required、相異即 unique、數值邊界)—— 餵給既有驗證器的剖析步驟。純標準函式庫、完全具決定性。

## 本次更新 (2026-06-21) — W3C Trace Context 傳播

跨 HTTP 邊界關聯 span 與日誌。完整參考:[`docs/source/Zh/doc/new_features/v76_features_doc.rst`](../docs/source/Zh/doc/new_features/v76_features_doc.rst)。

- **`SpanContext` / `new_root_context` / `child_context` / `inject_context` / `extract_context`**(`AC_trace_inject`、`AC_trace_extract`):既有追蹤器與 `agent_trace` 的 span 不帶 ID,因此一次 HTTP 呼叫一端的 span 無法與它在另一端觸發的工作關聯。本功能實作 W3C Trace Context 標準 —— 產生/解析/傳播 `traceparent` + `tracestate` 標頭(version-`00`,拒絕格式不符/全零 ID),並以可注入 RNG 讓測試中的 ID 具決定性。純標準函式庫。

## 本次更新 (2026-06-21) — HTTP 錄製與重播卡帶

在 CI 中重跑 API 流程,無需線上伺服器。完整參考:[`docs/source/Zh/doc/new_features/v75_features_doc.rst`](../docs/source/Zh/doc/new_features/v75_features_doc.rst)。

- **`Cassette` / `CassetteMissError`**(`AC_http_replay`):HTTP 用戶端把 `urllib` 傳輸寫死,因此驅動真實 API 的流程無法離線重跑。用戶端現在開放 `build_call` / `urllib_transport` 接縫,本功能加入 VCR 風格卡帶 —— `replay` 為相符請求回傳已錄製回應(純粹、不連網,對 CI 最有價值的一半),`recording_transport` 則是在實際傳輸之上的薄薄轉送。可依 `method`/`url`(可加 `body`)比對;以 JSON `save`/`load` 卡帶。純標準函式庫。

## 本次更新 (2026-06-21) — 隔艙與速率限制標頭

限制並行、遵守伺服器退避。完整參考:[`docs/source/Zh/doc/new_features/v74_features_doc.rst`](../docs/source/Zh/doc/new_features/v74_features_doc.rst)。

- **`Bulkhead` / `next_delay` / `parse_retry_after` / `parse_ratelimit`**(`AC_bulkhead_run`、`AC_retry_after`):`resilience` 復原、`rate_limit` 調速,但沒有任何東西限制*同時*進行的呼叫(緩慢相依會耗盡所有 worker),且 HTTP 用戶端忽略 `Retry-After`/`RateLimit-*`。本功能補上隔艙(滿載時以 `BulkheadFullError` 卸除負載的 bounded-concurrency 許可)以及伺服器建議延遲(delta 秒或 HTTP-date)的剖析器。非阻塞許可計數 → 具決定性、測試免執行緒。純標準函式庫。

## 本次更新 (2026-06-21) — 串流延遲百分位

load/soak 測試的可合併 p99。完整參考:[`docs/source/Zh/doc/new_features/v73_features_doc.rst`](../docs/source/Zh/doc/new_features/v73_features_doc.rst)。

- **`LatencyDigest` / `exact_percentiles`**(`AC_percentiles`):`stats.percentile` 需要完整已排序清單;本功能補上 HdrHistogram 風格的 digest,具 O(1) `record`、記憶體有界(有效位數分桶)以及跨分片彙整的 `merge` —— 這正是從各 worker 結果計算正確彙整 p99 所需的特性。`exact_percentiles` 涵蓋小樣本集情況(任意分位)。純標準函式庫 `math`。

## 本次更新 (2026-06-21) — 服務等級目標(SLO)

SLI、錯誤預算與燃燒率警示。完整參考:[`docs/source/Zh/doc/new_features/v72_features_doc.rst`](../docs/source/Zh/doc/new_features/v72_features_doc.rst)。

- **`evaluate_slo` / `burn_rate` / `burn_alerts` / `default_burn_rules`**(`AC_evaluate_slo`、`AC_burn_alerts`):框架會發出原始訊號卻沒有 SLO 層。本功能在結果紀錄(`[{timestamp, ok}]`)上計算 SLI、對目標計算錯誤預算,以及 Google SRE workbook 的**多視窗多燃燒率**警示(1h 達 14.4×、6h 達 6× 呼叫;3d 達 1× 開票 —— 只有當長短視窗雙雙超過門檻才觸發)。紀錄為純資料、時鐘可注入、完全具決定性。純標準函式庫。

## 本次更新 (2026-06-21) — 混沌實驗

注入故障、驗證系統仍成立。完整參考:[`docs/source/Zh/doc/new_features/v71_features_doc.rst`](../docs/source/Zh/doc/new_features/v71_features_doc.rst)。

- **`ChaosExperiment` / `run_experiment` / `Probe` / `latency_fault` / `exception_fault`**(`AC_run_chaos`):`resilience` 從失敗中*復原*;這則*製造*失敗並檢查穩態假設是否仍成立(Chaos Toolkit 生命週期 —— 之前驗證、注入故障、之後驗證、LIFO 回滾)。探針/故障/回滾皆為 callable;時鐘/RNG/sleep 可注入,因此實驗在測試中**具決定性**地執行,無真正失敗或睡眠。`AC_run_chaos` 以動作清單 spec 驅動。純標準函式庫。

## 本次更新 (2026-06-21) — JSON 合約與快照比對

比對、取差異與快照 JSON 內容。完整參考:[`docs/source/Zh/doc/new_features/v70_features_doc.rst`](../docs/source/Zh/doc/new_features/v70_features_doc.rst)。

- **`match_json` / `diff_json` / `normalize_json` / `snapshot_json`**(`AC_match_json`、`AC_diff_json`):`json_schema` 以撰寫的 schema 驗證、`jsonpath` 擷取,但沒有任何東西能以寬鬆規則比對兩份內容或逐路徑取差異。本功能補上合約/快照比對 —— `partial`(子集)、`match_type`(Pact 風格 `like`)、`ignore` 易變路徑 —— 回傳 `{path, kind}` 不符(`missing`/`extra`/`changed`),外加 golden-master `snapshot_json`。與 `json_schema` + `json_patch` 互補;純標準函式庫。

## 本次更新 (2026-06-21) — SLSA 建置來源證明

證明建置產生了什麼。完整參考:[`docs/source/Zh/doc/new_features/v69_features_doc.rst`](../docs/source/Zh/doc/new_features/v69_features_doc.rst)。

- **`build_provenance` / `subject_for` / `verify_provenance` / `write_provenance`**(`AC_build_provenance`、`AC_verify_provenance`):框架能簽署動作檔並盤點相依套件(SBOM),卻無法證明*哪個建置產生了什麼*。本功能補上 in-toto v1 Statement,攜帶覆蓋檔案 `sha256` 摘要的 SLSA v1 provenance predicate,並附上會重新雜湊產物的驗證器(竄改 → 不符)。與 `action_signing` + `sbom` 互補;純標準函式庫 `hashlib`+`json`,完全離線。

## 本次更新 (2026-06-21) — 功能旗標

以目標規則與推出切換行為。完整參考:[`docs/source/Zh/doc/new_features/v68_features_doc.rst`](../docs/source/Zh/doc/new_features/v68_features_doc.rst)。

- **`FlagStore` / `evaluate_flag` / `is_enabled` / `assign_variant`**(`AC_evaluate_flag`、`AC_flag_enabled`):`decision_table` 是一次性 DMN,`ab_locator` 是定位器 A/B —— 兩者都不是帶黏性 % 推出的產品旗標儲存庫。本功能補上 OpenFeature 形狀引擎:目標規則(`eq`/`in`/`semver_*`…)、加權變體、kill switch,以及一致雜湊分桶(`sha256(key.salt.context_key)`)使主體具**黏性**。回傳 `{value, variant, reason}`(`TARGETING_MATCH`/`SPLIT`/`DISABLED`/`ERROR`)。純標準函式庫、具決定性。

## 本次更新 (2026-06-21) — 文字 Diff、套用與三方合併

套用並合併文字 diff。完整參考:[`docs/source/Zh/doc/new_features/v67_features_doc.rst`](../docs/source/Zh/doc/new_features/v67_features_doc.rst)。

- **`unified_diff` / `apply_unified` / `three_way_merge`**(`AC_unified_diff`、`AC_apply_unified`、`AC_three_way_merge`):`difflib` 會*產生* unified diff,但標準函式庫無法*套用*,也沒有三方合併。本功能補上缺少的套用器(走訪 `@@` 區塊、驗證 context、不符即拋出)與以行為單位的三方合併(不重疊編輯乾淨合併;重疊則產生 `<<<<<<<` 衝突標記)。與 `json_patch`(結構化 JSON)互補;純標準函式庫 `difflib`。

## 本次更新 (2026-06-21) — 行事曆週期規則(RRULE)

排程「每月第 2 個星期二」。完整參考:[`docs/source/Zh/doc/new_features/v66_features_doc.rst`](../docs/source/Zh/doc/new_features/v66_features_doc.rst)。

- **`parse_rrule` / `occurrences` / `next_occurrence`**(`AC_rrule_occurrences`、`AC_rrule_next`):排程器的 cron 只是 5 欄位間隔式 —— 無法表達「每月第 2 個星期二」、「每月最後一個工作日」或「連續 10 次的每個工作日」。本功能補上 RFC 5545(iCalendar)RRULE 解析器 + 發生時刻展開器,支援 `FREQ`/`INTERVAL`/`COUNT`/`UNTIL`/`BYDAY`(含序數如 `2MO`/`-1FR`)/`BYMONTHDAY`/`BYMONTH`/`BYSETPOS`/`WKST`。純標準函式庫 `datetime`+`calendar`,時鐘可注入使 `next_occurrence` 具決定性。

## 本次更新 (2026-06-21) — 統計與 A/B 顯著性

判斷差異是否為真。完整參考:[`docs/source/Zh/doc/new_features/v65_features_doc.rst`](../docs/source/Zh/doc/new_features/v65_features_doc.rst)。

- **`describe` / `percentile` / `two_proportion_z_test` / `welch_t_test` / `cohens_d` / `chi_square_2x2`**(`AC_describe_stats`、`AC_ab_significance`):`ab_locator` 以原始成功率排名,`run_history` 儲存時長,但沒有任何東西計算百分位或顯著性。本功能補上分析層 —— 摘要統計 + p50/p90/p95/p99、雙比例 z 檢定(含信賴區間)、Welch t 檢定(以不完全 beta 取得精確 t 分布 p 值,免 SciPy)、Cohen's d,以及 2×2 卡方。常態 CDF 以 `math.erf` 精確計算;已對齊教科書數值(含 chi²=z² 恆等式)。純標準函式庫 `math`+`statistics`。

## 本次更新 (2026-06-21) — 全文搜尋(BM25)

依相關性對文件語料排名。完整參考:[`docs/source/Zh/doc/new_features/v64_features_doc.rst`](../docs/source/Zh/doc/new_features/v64_features_doc.rst)。

- **`SearchIndex` / `search_documents` / `tokenize`**(`AC_search_documents`、`ac_search_documents`):`fuzzy` 是成對的,`skill_library` 以字母序比對子字串 —— 兩者都不會依相關性對語料排名。本功能補上以倒排索引、用 Okapi BM25(`k1=1.5`、`b=0.75`、`IDF = ln(1+(N−df+0.5)/(df+0.5))`)或 TF-IDF 排名的搜尋,因此罕見詞勝過常見詞、詞頻會飽和、長文件被正規化下調。增量 `add`/`remove`、可選停用詞、結果具決定性。純標準函式庫 `math`+`collections`+`re` —— 無需資料庫。

## 本次更新 (2026-06-21) — JSON Pointer、Patch 與 Merge Patch

定址、取差異並修補 JSON。完整參考:[`docs/source/Zh/doc/new_features/v63_features_doc.rst`](../docs/source/Zh/doc/new_features/v63_features_doc.rst)。

- **`resolve_pointer` / `make_patch` / `apply_patch` / `merge_patch` / `make_merge_patch`**(`AC_resolve_pointer`、`AC_apply_json_patch`、`AC_make_json_patch`、`AC_merge_patch`):`jsonpath` 是唯讀的,`approval` 比較整份產物 —— 沒有任何東西能定址單一位置、計算結構化差異或套用部分更新。本功能補上三個 IETF 原語 —— JSON Pointer(RFC 6901)、JSON Patch(RFC 6902,全六種操作,**原子**套用)、JSON Merge Patch(RFC 7386,`null` 刪除)—— 適用於設定漂移偵測、部分更新、HTTP PATCH 內容與 golden-master 差異。純標準函式庫 `json`+`copy`,以 RFC 測試向量驗證。

## 本次更新 (2026-06-21) — 用戶端速率限制

守在 API 配額之內。完整參考:[`docs/source/Zh/doc/new_features/v62_features_doc.rst`](../docs/source/Zh/doc/new_features/v62_features_doc.rst)。

- **`TokenBucket` / `SlidingWindowLimiter` / `throttle`**(`AC_rate_limit`、`ac_rate_limit`):`RetryPolicy`/`CircuitBreaker` 從失敗中復原,但沒有任何東西塑形呼叫的*速率*。本功能補上 token bucket(平滑速率 + 突發)、sliding-window 限制器(Cloudflare 的 O(1) 加權計數)以及前緣 throttle 裝飾器。每個限制器都接受可注入的 `clock`(`acquire` 另接受 `sleep`),因此在 CI 完全具決定性、沒有真正延遲。`AC_rate_limit` 以具名 bucket 閘控動作,回傳 `{acquired, tokens, wait}`。

## 本次更新 (2026-06-21) — JSON Web Token(JWT)

為你自動化的 API 簽發與驗證 bearer token。完整參考:[`docs/source/Zh/doc/new_features/v61_features_doc.rst`](../docs/source/Zh/doc/new_features/v61_features_doc.rst)。

- **`encode_jwt` / `decode_jwt` / `ClaimsPolicy`**(`AC_jwt_encode`、`AC_jwt_decode`):框架過去有 HMAC *檔案*簽章與綁定 ACME 的 RS256 JWS,卻沒有可簽發/驗證精簡 bearer JWT 的工具。本功能補上純標準函式庫的 HS256/384/512 編解碼器,含完整宣告驗證(`exp`/`nbf`/`aud`/`iss`、可注入時鐘),可直接接上 `http_request` 的 bearer 驗證。預設即安全:拒絕 `alg:none`、強制演算法允許清單(防混淆),並以 `hmac.compare_digest` 比對簽章。`AC_jwt_decode` 回傳 `{ok, claims}`,讓流程不必拋例外即可分支。

## 本次更新 (2026-06-21) — 授權政策閘門

標記不被允許的相依套件授權。完整參考:[`docs/source/Zh/doc/new_features/v60_features_doc.rst`](../docs/source/Zh/doc/new_features/v60_features_doc.rst)。

- **`evaluate_sbom` / `evaluate_license` / `normalize_spdx` / `license_findings_to_sarif`**(`AC_check_licenses`、`ac_check_licenses`):SBOM 記錄了每個相依套件的授權名稱卻從未*判斷*它。本功能把授權字串正規化為 SPDX id,以允許清單/拒絕清單(內建 `DEFAULT_COPYLEFT` 集合)評估,理解 SPDX 運算式(`OR` = 擇一、`AND` = 全部),再把違規橋接到 SARIF(`denied`→error、`unknown`→warning)。純標準函式庫、完全離線 —— 與 OSV 漏洞通道並列的授權合規通道。

## 本次更新 (2026-06-21) — OpenVEX 漏洞分級

抑制不影響你的漏洞。完整參考:[`docs/source/Zh/doc/new_features/v59_features_doc.rst`](../docs/source/Zh/doc/new_features/v59_features_doc.rst)。

- **`vex_statement` / `build_vex` / `apply_vex`**(`AC_apply_vex`、`ac_apply_vex`):OSV 掃描器會讓每個已知 CVE 一直出現 —— 沒有辦法記錄「我們查過了,這個不影響我們」。本功能撰寫 [OpenVEX](https://openvex.dev) 0.2.0 陳述並套用到掃描器的發現項目:`not_affected`/`fixed` **抑制**一項發現,`affected`/`under_investigation` **標註**它。陳述以漏洞 id *或*別名配對,並可限定產品;`not_affected` 需附理由或衝擊說明。純標準函式庫;可直接接在 `AC_scan_vulns` 之後。

## 本次更新 (2026-06-21) — 相依套件漏洞掃描(OSV)

以 SBOM 比對已知 CVE。完整參考:[`docs/source/Zh/doc/new_features/v58_features_doc.rst`](../docs/source/Zh/doc/new_features/v58_features_doc.rst)。

- **`scan_components` / `match_package` / `is_affected` / `findings_to_sarif`**(`AC_scan_vulns`、`ac_scan_vulns`):`build_sbom` 只會*盤點*相依套件,`to_sarif` 只會*匯出*發現項目 —— 從未真正**產生**漏洞發現項目。本功能以 SBOM 的 `(ecosystem, name, version)` 元件比對 [OSV](https://osv.dev) 諮詢資料庫(掃描 `introduced`/`fixed`/`last_affected` 範圍、PEP-503 名稱正規化、嚴重度對應 SARIF 等級),並把結果橋接到既有 SARIF 匯出器供 GitHub/Azure DevOps 程式碼掃描。諮詢資料庫以**資料注入**(離線、具決定性);線上 `osv.dev` 查詢為選用的 `fetcher` 接縫。純標準函式庫 `re`。

## 本次更新 (2026-06-21) — JSON Schema 驗證

以真正的 schema 驗證巢狀 JSON。完整參考:[`docs/source/Zh/doc/new_features/v57_features_doc.rst`](../docs/source/Zh/doc/new_features/v57_features_doc.rst)。

- **`validate_json` / `is_valid` / `assert_schema`**(`AC_validate_json`、`ac_validate_json`):框架過去只會*產生* JSON Schema,而 `data_quality` 是扁平的逐欄檢查器 —— 兩者都無法驗證巢狀的 API 請求/回應內容。本功能補上消費端:一個 JSON Schema(Draft 2020-12 子集)驗證器,將**每一個**違規以 `{path, keyword, message}` 回報(例如 `$.age maximum`)。涵蓋 `type`(含整數值浮點數的 `integer`)、`enum`/`const`、數字/字串界限、陣列與物件關鍵字、`allOf`/`anyOf`/`oneOf`/`not`、布林 schema 與本地 `$ref`。純標準函式庫 `re`;與 `json_query` 及 `http_request` 輔助函式搭配。

## 本次更新 (2026-06-20) — SARIF 2.1.0 發現項目匯出

統一掃描結果供 GitHub 程式碼掃描。完整參考:[`docs/source/Zh/doc/new_features/v56_features_doc.rst`](../docs/source/Zh/doc/new_features/v56_features_doc.rst)。

- **`to_sarif` / `write_sarif` / `make_finding` / `from_lint_issues` / `from_audit_findings`**(`AC_export_sarif`、`ac_export_sarif`):框架的發現項目產生器(action-lint、密鑰掃描、WCAG 稽核、guardrail)缺乏共通匯出。本功能建立 SARIF 2.1.0 文件(自動規則目錄 + 穩定 `partialFingerprints` 跨執行去重),供 GitHub/Azure DevOps 程式碼掃描以定位到行的警示匯入。純標準函式庫 `json`+`hashlib`;轉接器正規化既有 lint/audit 形狀。

## 本次更新 (2026-06-20) — 文字 PII 偵測與遮蔽

在文字洩漏前遮蔽 PII。完整參考:[`docs/source/Zh/doc/new_features/v55_features_doc.rst`](../docs/source/Zh/doc/new_features/v55_features_doc.rst)。

- **`detect_pii` / `redact_pii_text`**(`AC_detect_pii` / `AC_redact_pii`、`ac_*`):影像遮蔽已存在,但文字(OCR、剪貼簿、LLM I/O、日誌)無字串層級 PII 處理。本功能在純文字上偵測電子郵件/電話/SSN/信用卡/IPv4/IBAN 並以 `label`/`mask`/`partial`/`hash` 遮蔽。重疊區段會去重(卡號不會同時是電話);樣式無回溯風險。純標準函式庫 `re`+`hashlib`。

## 本次更新 (2026-06-20) — 自我修復定位器回寫

保存修正定位器,使修復不被遺忘。完整參考:[`docs/source/Zh/doc/new_features/v54_features_doc.rst`](../docs/source/Zh/doc/new_features/v54_features_doc.rst)。

- **`RepairStore` / `repair_from_heal`**(`AC_repair_record` / `AC_repair_resolved` / `AC_repair_pending` / `AC_repair_approve`、`ac_*`):執行期自我修復過去會**丟棄**修正後的位置,因此每次都重新修復。本功能記錄該次修復的修正定位器(座標/VLM 描述/方法),在 `confidence >= auto_threshold`(預設 0.9)時**自動套用**或排入可審查建議,`resolved(key)` 回傳已學到的修正供重用。封閉「修復→持久修正」迴圈;純標準函式庫、可完整測試。

## 本次更新 (2026-06-20) — DMN 式決策表

將分支外部化為可審查的規則表。完整參考:[`docs/source/Zh/doc/new_features/v53_features_doc.rst`](../docs/source/Zh/doc/new_features/v53_features_doc.rst)。

- **`evaluate_table` / `DecisionTable`**(`AC_decision_table`、`ac_decision_table`):以一列列的 `conditions -> outputs` 加命中政策(`UNIQUE`/`FIRST`/`PRIORITY`/`COLLECT`)取代巢狀 `AC_if_var` 鏈。儲存格條件為萬用字元 / 字面值 / `{op, value}`,使用執行器標準比較子(重用,不重複)。純標準函式庫、可完整測試;DMN 讓商業規則資料驅動的方式。

## 本次更新 (2026-06-20) — Saga / 補償回溯

後續步驟失敗時復原已完成步驟。完整參考:[`docs/source/Zh/doc/new_features/v52_features_doc.rst`](../docs/source/Zh/doc/new_features/v52_features_doc.rst)。

- **`Saga` / `run_saga`**(`AC_run_saga`、`ac_run_saga`):為每個步驟記錄補償動作;任何失敗時以 **LIFO** 順序對已完成步驟執行補償 —— 單一區塊的 `AC_try` 無法提供的持久性交易原語。前向動作/補償為可呼叫物件(或 JSON 動作清單),因此可在無副作用下完整單元測試;補償為盡力而為(失敗的復原會記錄,回溯繼續)。回傳 `{ok, completed, compensated, failed_step, error}`。

## 本次更新 (2026-06-20) — JSONPath 查詢

以萬用字元、遞迴、過濾查詢 API/DB JSON。完整參考:[`docs/source/Zh/doc/new_features/v51_features_doc.rst`](../docs/source/Zh/doc/new_features/v51_features_doc.rst)。

- **`json_query` / `json_query_one` / `json_extract`**(`AC_json_query` / `AC_json_extract`、`ac_*`):執行器的路徑走訪只會以 `.` 切分並索引 —— 本功能在已解析 JSON 上加入 JSONPath 子集(`$`、`.key`、`[n]`/`[-n]`、`*`/`[*]`、`..` 遞迴下降、`[?(@.k op v)]` 過濾),讓含陣列的 API/DB 回應易於擷取。`json_extract` 以 `{key: path}` 對應擷取成扁平 dict。純標準函式庫 `re`;這是 `AC_http_to_var` 與 DB-row 流程所缺的路徑引擎。

## 本次更新 (2026-06-20) — 多通道 Webhook 通知

通知 Teams/Discord/Slack/webhook。完整參考:[`docs/source/Zh/doc/new_features/v50_features_doc.rst`](../docs/source/Zh/doc/new_features/v50_features_doc.rst)。

- **`notify_webhook` / `WebhookChannel`**(`AC_notify_webhook`、`ac_notify_webhook`):`notify` 僅限桌面快顯、ChatOps 只內建 Slack —— 本功能可發送到 **Slack / Discord / Microsoft Teams / raw** webhook,組出對應傳輸的酬載(Slack 與 Teams MessageCard 用 `text`,Discord 用 `content`)並透過受出口守衛保護的 HTTP 用戶端 POST。`poster` 傳輸可注入(或 `set_default_poster`),因此發送在無網路下即可單元測試。

## 本次更新 (2026-06-20) — 對外 CloudEvents 發送器

將執行/自動化事件以 CloudEvents 發送。完整參考:[`docs/source/Zh/doc/new_features/v49_features_doc.rst`](../docs/source/Zh/doc/new_features/v49_features_doc.rst)。

- **`to_cloudevent` / `EventEmitter` / `post_cloudevent`**(`AC_emit_event`、`ac_emit_event`):本專案能接收 webhook 卻無法**發送**事件 —— 本功能將執行生命週期/斷言/失敗資料包進 CloudEvents 1.0(CNCF)信封,並可透過受出口守衛保護的 HTTP 用戶端 POST 出去(與 Knative、Azure Event Grid、iPaaS、一般 webhook 互通)。`sink`/`poster` 傳輸可注入,因此發送在無網路下即可單元測試。

## 本次更新 (2026-06-20) — 環境範圍的具型別資產儲存

依環境的具型別設定 + credential 參照。完整參考:[`docs/source/Zh/doc/new_features/v48_features_doc.rst`](../docs/source/Zh/doc/new_features/v48_features_doc.rst)。

- **`AssetStore` / `active_environment`**(`AC_set_asset` / `AC_get_asset` / `AC_list_assets`、`ac_*`):orchestrator 的「Assets/lockers」支柱 —— 集中管理、依環境(dev/staging/prod)而異且帶型別(`text`/`int`/`bool`/`credential`)的設定值。`get` 轉成宣告型別並退回 default 環境;`credential` 資產持有密鑰*參照*,由 `resolve` 透過注入解析器轉成真實值(僅限 Python,因此密鑰永不進入 `get`/executor 紀錄)。補足密鑰保險庫(僅密鑰)與 config-sync(整塊)的缺口。

## 本次更新 (2026-06-20) — 任務 / 流程探勘(自動化候選發現)

從錄製的動作日誌發現該自動化什麼。完整參考:[`docs/source/Zh/doc/new_features/v47_features_doc.rst`](../docs/source/Zh/doc/new_features/v47_features_doc.rst)。

- **`mine_action_log` / `find_repeated_sequences` / `directly_follows` / `rank_automation_candidates`**(`AC_mine_actions`、`ac_mine_actions`):探勘錄製的動作日誌中頻繁、可重複的指令 n-gram,建立 directly-follows 圖,並依 `count × length` 為自動化候選排名 —— 這是 AutoControl 一直在錄資料卻從未分析的 RPA「任務探勘」支柱。純標準函式庫;作用於既有動作清單結構;一個經常重現且橫跨多步的候選,是「抽成 skill」的強烈訊號。

## 本次更新 (2026-06-20) — 卡迴圈守衛(Agent Loop 進度偵測)

捕捉卡在無進展迴圈的 agent。完整參考:[`docs/source/Zh/doc/new_features/v46_features_doc.rst`](../docs/source/Zh/doc/new_features/v46_features_doc.rst)。

- **`LoopGuard` / `digest_result`**(`AC_loop_guard_observe` / `AC_loop_guard_reset`、`ac_*`):電腦操作最主要的失敗模式是 agent 重複一個無效果的動作 —— 而模型看不到自己的迴圈。`LoopGuard` 觀察 `(tool, args, result)` 串流並標記 `repeat`(相同呼叫 N 次)、`ping_pong`(A-B-A-B)與 `no_op`(觀察摘要不變),依執行長度由 `ok`→`warn`→`critical` 升級。與步數/時間預算及離線軌跡評估互補;純標準函式庫、具確定性。

## 本次更新 (2026-06-20) — 座標空間對映(模型網格 ⇄ 實體像素)

將電腦操作模型的點擊轉成真實像素。完整參考:[`docs/source/Zh/doc/new_features/v45_features_doc.rst`](../docs/source/Zh/doc/new_features/v45_features_doc.rst)。

- **`CoordinateSpace` / `xga_space` / `normalized_space` / `downscale_png`**(`AC_to_physical` / `AC_to_model`、`ac_*`):電腦操作/VLA 模型以固定網格點擊(Anthropic 縮小到 XGA;Gemini 回傳 1000×1000 網格),而非實體像素。本功能雙向對映(四捨五入 + 夾限),`xga_space` 保持長寬比且不放大,`downscale_png` 將截圖縮到模型輸入尺寸(Pillow,已是核心)。純算術對映 —— 無需模型/GPU 即可單元測試。

## 本次更新 (2026-06-20) — 語音指令路由器

以已辨識語音免手動觸發流程。完整參考:[`docs/source/Zh/doc/new_features/v44_features_doc.rst`](../docs/source/Zh/doc/new_features/v44_features_doc.rst)。

- **`VoiceRouter`**(`AC_voice_register` / `AC_voice_dispatch` / `AC_voice_list` / `AC_voice_clear`、`ac_*`):將語音觸發片語對應到 `AC_*` 動作清單;餵入已辨識文字即執行最接近的已註冊指令(片語比對重用模糊比對器,因此「save the file」會觸發「save file」)。**語音轉文字不在範圍內且可注入** —— 路由器接受文字與 `recognizer`/`runner` 可呼叫物件,因此路由在無音訊、無任何語音相依下完整單元測試(真實 Vosk/麥克風辨識器接入 `listen_once`)。

## 本次更新 (2026-06-20) — 區域設定感知的數字、貨幣與日期解析

解析在地化的數字/貨幣/日期。完整參考:[`docs/source/Zh/doc/new_features/v43_features_doc.rst`](../docs/source/Zh/doc/new_features/v43_features_doc.rst)。

- **`parse_decimal` / `parse_number` / `format_decimal` / `format_currency` / `format_date`**(`AC_parse_decimal` / `AC_parse_number` / `AC_format_decimal` / `AC_format_currency` / `AC_format_date`、`ac_*`):像 `"1.234,56"`(de_DE)這樣的 OCR/UI 文字會透過 **Babel** 的 CLDR 資料正確解析為 `1234.56`,值也能依區域設定格式化回去。`babel` 為選用 `[locale]` extra,採延遲匯入;功能測試以 `importorskip` 執行(wiring/facade 一律驗證)。

## 本次更新 (2026-06-20) — 感知雜湊影像去重

收合近乎相同的螢幕截圖。完整參考:[`docs/source/Zh/doc/new_features/v42_features_doc.rst`](../docs/source/Zh/doc/new_features/v42_features_doc.rst)。

- **`average_hash` / `dhash` / `hamming_distance` / `images_similar` / `dedupe_images`**(`AC_image_hash` / `AC_dedupe_images`、`ac_*`):感知雜湊將視覺相似的影像對應到接近的指紋,因此錄影或步驟報告中的近似重複畫面可依漢明距離分群並收合為一個代表。使用 **Pillow**(已是核心 —— 無額外相依);去重/比較邏輯為純 Python 且 `hasher` 可注入,因此分群在無任何影像下單元測試,實際 Pillow 路徑以 `importorskip` 測試。

## 本次更新 (2026-06-20) — S3 相容成品儲存

將執行成品推送到物件儲存。完整參考:[`docs/source/Zh/doc/new_features/v41_features_doc.rst`](../docs/source/Zh/doc/new_features/v41_features_doc.rst)。

- **`S3ArtifactStore`**(`AC_s3_upload` / `AC_s3_download` / `AC_s3_list` / `AC_s3_delete`、`ac_*`):對任何 S3 相容儲存桶(AWS S3、MinIO、R2)上傳/下載/列出/刪除報告、螢幕截圖與錄影。`boto3` 為**選用** `[s3]` extra,且 client **可注入**,因此儲存體邏輯(含 executor 路徑)以假 client 完整單元測試(無 boto3/網路);實際 AWS 路徑誠實標註為 CI 無法驗證。整個 API 相對於儲存體 `prefix`。模組層級的預設儲存體支撐這些指令。

## 本次更新 (2026-06-20) — 模糊字串比對與去重

穩健比對含雜訊的 OCR/UI 文字。完整參考:[`docs/source/Zh/doc/new_features/v40_features_doc.rst`](../docs/source/Zh/doc/new_features/v40_features_doc.rst)。

- **`fuzzy_ratio` / `fuzzy_best_match` / `fuzzy_matches` / `fuzzy_dedupe`**(`AC_fuzzy_ratio` / `AC_fuzzy_best_match` / `AC_fuzzy_dedupe`、`ac_*`):為相似度評分(0..1)、從清單挑最接近的候選,或收合近似重複 —— 讓流程可針對「*看起來像* Submit 的按鈕」動作,而非精確標籤。預設後端為標準函式庫 `difflib`(**無額外相依**);選用的 `[fuzzy]` extra 加入 `rapidfuzz` 以加速,兩者分數皆正規化。支援 `ignore_case` 與 `score_cutoff`。

## 本次更新 (2026-06-19) — 影片步驟疊加報告

將螢幕截圖加上字幕製成走查影片。完整參考:[`docs/source/Zh/doc/new_features/v39_features_doc.rst`](../docs/source/Zh/doc/new_features/v39_features_doc.rst)。

- **`write_step_video`**(`AC_write_step_video`、`ac_write_step_video`):將各步驟的螢幕截圖轉成可分享的影片,每個畫面停留數秒並燒入其字幕與通過/失敗色彩橫幅。組裝邏輯(`build_overlay_plan` / `render_overlay_frame`)透過可注入的 `loader`/`drawer`/`writer_factory` 掛鉤與 OpenCV 分離 —— 可用假物件單元測試、無 `cv2`/`numpy` 相依;真實路徑僅在缺少這些掛鉤時才延遲匯入 `cv2`。為 HTML/JSON 報告的視覺夥伴。

## 本次更新 (2026-06-19) — Agent 可觀測性(GenAI OpenTelemetry Spans)

LLM 執行的 OTel GenAI 慣例 spans。完整參考:[`docs/source/Zh/doc/new_features/v38_features_doc.rst`](../docs/source/Zh/doc/new_features/v38_features_doc.rst)。

- **`AgentTrace`**(`AC_trace_record` / `AC_trace_summary` / `AC_trace_export` / `AC_trace_reset`、`ac_*`):記錄的 span 其屬性遵循 OpenTelemetry **GenAI 語意慣例**(`gen_ai.operation.name`、`gen_ai.system`、`gen_ai.request.model`、`gen_ai.usage.input_tokens`/`output_tokens`、`gen_ai.tool.name`)與 `"{operation} {model}"` span 名稱。`to_otel()` 可送入 OTLP exporter;`summary()` 彙整 token 成本與延遲;`operation()` 情境管理器為即時區塊計時並標記錯誤。純標準函式庫(無 `opentelemetry` 相依)、可注入時鐘;與軌跡評估互補(在此記錄、在那裡評分)。

## 本次更新 (2026-06-19) — 合規控制報告(SOC2 / ISO 27001)

將治理證據對應到具名控制項。完整參考:[`docs/source/Zh/doc/new_features/v37_features_doc.rst`](../docs/source/Zh/doc/new_features/v37_features_doc.rst)。

- **`build_compliance_report`**(`AC_compliance_report`、`ac_compliance_report`):框架已內建稽核員關注的控制項 —— 出口允許清單、JIT 憑證租約、maker-checker 審批、密鑰掃描器、稽核記錄、CycloneDX SBOM。本功能將扁平的 `evidence` 對應表映射到 SOC2(CC6.1/CC6.3/CC6.8/CC7.3/CC8.1)與 ISO 27001(A.5.23/A.8.16/A.8.30)控制項,每項標記為 `satisfied`/`gap`/`not_assessed`,並輸出 JSON 或獨立 HTML 表格。治理套件的收尾 —— 為報告輔助,非認證。

## 本次更新 (2026-06-19) — Agent 軌跡評估

依評分標準為 agent 執行評分。完整參考:[`docs/source/Zh/doc/new_features/v36_features_doc.rst`](../docs/source/Zh/doc/new_features/v36_features_doc.rst)。

- **`evaluate_trajectory`**(`AC_evaluate_trajectory`、`ac_evaluate_trajectory`):依宣告式評分標準 —— `required_actions`(+`ordered`)、`forbidden_actions`、`max_steps`、`success_contains` —— 為一次記錄的軌跡(有序 `{action, args, observation}` 步驟)評分。回傳 `{passed, score, steps, checks}`,其中 `score` 為通過的適用檢查佔比,每個 `check` 精準指出被違反的期望。為 agent 回歸測試提供確定性、無相依的訊號;rubric 為純資料,可存於 JSON action 檔並經 MCP 傳遞。

## 本次更新 (2026-06-19) — 核准式測試(Golden-Master 基準)

將輸出鎖定到人工核准的基準。完整參考:[`docs/source/Zh/doc/new_features/v35_features_doc.rst`](../docs/source/Zh/doc/new_features/v35_features_doc.rst)。

- **`verify_artifact` / `approve_artifact`**(`AC_verify_artifact` / `AC_approve_artifact` / `AC_pending_artifacts`、`ac_*`):對*任何*產物(文字、JSON、OCR 輸出、螢幕截圖位元組)進行 golden-master / snapshot 測試。`verify_artifact` 將產出內容與 `<name>.approved.<ext>` 比對;不符或缺少基準會寫入 `<name>.received.<ext>` 供審查並失敗,`approve_artifact` 則將審查後的 received 檔晉升為基準。以與測試一起提交、受審查把關的基準補強逐像素比對;名稱會經過路徑穿越檢查。

## 本次更新 (2026-06-19) — 網路出口允許清單守衛

釘選自動化可連線的主機。完整參考:[`docs/source/Zh/doc/new_features/v34_features_doc.rst`](../docs/source/Zh/doc/new_features/v34_features_doc.rst)。

- **`EgressPolicy` / `set_egress_policy`**(`AC_egress_allow` / `AC_egress_check` / `AC_egress_reset`、`ac_*`):允許清單(預設拒絕)與/或拒絕清單,使用 `fnmatch` 主機萬用字元(`*.example.com`),由**每一次** `http_request` 諮詢(因此 `AC_http` 與所有以其為基礎的功能一次涵蓋)。被封鎖的主機會在 socket 開啟**之前**拋出 `EgressBlocked`。以 allow-all 模式啟動 —— 操作者鎖定前不改變任何行為。封閉無人值守自動化的資料外洩面。

## 本次更新 (2026-06-19) — 即時憑證租約

密鑰的零常駐權限。完整參考:[`docs/source/Zh/doc/new_features/v33_features_doc.rst`](../docs/source/Zh/doc/new_features/v33_features_doc.rst)。

- **`CredentialBroker`**(`AC_lease_secret` / `AC_lease_valid` / `AC_revoke_lease` / `AC_lease_active`、`ac_*`):使用者取得短效*租約*(綁定密鑰名稱 + 到期時間的 token);真正的值僅在 `redeem` 時、且僅在有效期間,透過可插拔解析器(已解鎖的 `SecretManager`、環境變數、vault)取得。密鑰值永不進入 executor/MCP 紀錄 —— executor/MCP/Builder 介面僅管理租約生命週期;`redeem` 是刻意設計的僅限 Python API 逃生門。時鐘與解析器皆可注入。

## 本次更新 (2026-06-19) — Maker-Checker 審批閘門

高風險步驟的職責分離。完整參考:[`docs/source/Zh/doc/new_features/v32_features_doc.rst`](../docs/source/Zh/doc/new_features/v32_features_doc.rst)。

- **`ApprovalGate`**(`AC_approval_request` / `AC_approval_approve` / `AC_approval_reject` / `AC_approval_status`、`ac_*`):由 *maker* 提出高風險動作並取得 token;*checker*(必須為**不同**主體)核准或駁回;只有在 `is_approved` 為真後動作才繼續。狀態為選用的共用 JSON 檔,讓派發器與人工審批者可分屬不同程序。純標準函式庫,SOC2 式四眼原則控制。

## 本次更新 (2026-06-19) — Plugin SDK

透過 entry points 註冊第三方 `AC_*` 指令。完整參考:[`docs/source/Zh/doc/new_features/v31_features_doc.rst`](../docs/source/Zh/doc/new_features/v31_features_doc.rst)。

- **`discover_plugins` / `load_plugins`**(`AC_list_plugins` / `AC_load_plugins`、`ac_*`):pip 套件以 `je_auto_control.commands` entry-point 群組宣告式註冊新執行器指令;AutoControl 於執行期探索並註冊(立即可用於 JSON 流程、socket server、排程器、MCP)。壞外掛會略過;為執行期路徑載入器的宣告式、具命名空間對應物。

## 本次更新 (2026-06-19) — MCP 結構化輸出

MCP 2025-06-18 結構化工具輸出。完整參考:[`docs/source/Zh/doc/new_features/v30_features_doc.rst`](../docs/source/Zh/doc/new_features/v30_features_doc.rst)。

- **`MCPTool(output_schema=...)`** — 工具可宣告 `outputSchema`;其 dict 結果會在 `tools/call` 回應以 `structuredContent` 回傳,讓用戶端/LLM 消費型別化、經 schema 驗證的物件而非重新解析文字。`to_descriptor()` 會在 `tools/list` 公告;非 dict 結果與未宣告 schema 的工具行為不變。`ac_validate_rows` 為首個採用。

## 本次更新 (2026-06-19) — 緩動拖曳

決定性的緩動拖曳。完整參考:[`docs/source/Zh/doc/new_features/v29_features_doc.rst`](../docs/source/Zh/doc/new_features/v29_features_doc.rst)。

- **`tween_points` / `tween_drag` / `easing_names`**(`AC_tween_drag`、`ac_tween_drag`):沿緩動曲線從 `start` 拖到 `end`(linear / ease_in_out_quad / ease_out_cubic / ease_in_cubic)——決定性、純數學路徑、測試可注入 sink;補足人性化抖動。

## 本次更新 (2026-06-19) — 流程文件(SOP)產生器

把動作清單轉成逐步 SOP。完整參考:[`docs/source/Zh/doc/new_features/v28_features_doc.rst`](../docs/source/Zh/doc/new_features/v28_features_doc.rst)。

- **`generate_sop` / `write_sop`**(`AC_generate_sop`、`ac_generate_sop`):把錄製/編寫的動作清單對應成編號、人類可讀步驟 + HTML 文件(UiPath Task-Capture 產出);內容 HTML 轉義,未知指令優雅降級。

## 本次更新 (2026-06-19) — 修復分析與機密掃描

兩項純標準庫的稽核/分析工具。完整參考:[`docs/source/Zh/doc/new_features/v27_features_doc.rst`](../docs/source/Zh/doc/new_features/v27_features_doc.rst)。

- **自我修復分析** — `analyze_heal_log` / `heal_stats`(`AC_heal_stats`、`ac_heal_stats`):把自我修復記錄彙總成 heal-rate、策略組合、fallback-rate、平均延遲與最脆弱定位器——在選擇器衰退失效前抓出來。
- **機密掃描** — `scan_secrets(data)`(`AC_scan_secrets`、`ac_scan_secrets`):標記 action JSON 中應改用 `${secrets.*}` 的寫死機密(依鍵名、值樣式或高熵);保險庫引用會略過、預覽遮罩。

## 本次更新 (2026-06-19) — CI 註解與剪貼簿歷史

兩項純標準庫工具。完整參考:[`docs/source/Zh/doc/new_features/v26_features_doc.rst`](../docs/source/Zh/doc/new_features/v26_features_doc.rst)。

- **CI 註解** — `emit_annotations(results)`(`AC_ci_annotations`、`ac_ci_annotations`):把結果 dict 轉成 GitHub Actions 工作流程命令(`::error file=...,line=...::msg`),讓失敗在 PR 行內顯示,免 reporter action。
- **剪貼簿歷史** — `ClipboardHistory` / `default_clipboard_history`(`AC_clip_history_capture`/`list`/`search`/`start`/`stop`、`ac_clip_history_*`):有上限、可搜尋、最新在前的複製文字環狀緩衝,含可選背景輪詢器。

## 本次更新 (2026-06-19) — 韌性原語

可重用的 retry 與斷路器原語。完整參考:[`docs/source/Zh/doc/new_features/v25_features_doc.rst`](../docs/source/Zh/doc/new_features/v25_features_doc.rst)。

- **RetryPolicy** — `RetryPolicy(...).run(fn)` / `retry_call(fn)`:在設定的例外上以指數退避重試(可注入 sleep)。(既有 `AC_retry` 流程指令已能對動作 body 重試;這是可重用的可呼叫包裝器。)
- **CircuitBreaker** — `CircuitBreaker` / `CircuitOpenError`(`AC_circuit_call`、`ac_circuit_call`):連續失敗 N 次後開啟、短路至重置逾時、再半開——避免重試風暴打掛已故障依賴。可注入 clock;`AC_circuit_call` 讓動作清單透過具名斷路器執行。

## 本次更新 (2026-06-19) — 計時輸入巨集

以時間保真度重播輸入 + 按住-放開 DSL,走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v24_features_doc.rst`](../docs/source/Zh/doc/new_features/v24_features_doc.rst)。

- **計時時間軸重播** — `replay_timeline(events, speed=...)`(`AC_replay_timeline`、`ac_replay_timeline`):遵守每個 `delta_ms` 間隔、依 `speed` 縮放且可夾限;op = move/click/scroll/press/release/key。
- **輸入序列 DSL** — `run_sequence(steps)`(`AC_input_sequence`、`ac_input_sequence`):宣告式按住-放開組合鍵 + `repeat`/`wait`。兩者皆可注入 sink+sleep 做決定性測試。

## 本次更新 (2026-06-19) — 語意螢幕狀態

像素差異的語意對應物,走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v23_features_doc.rst`](../docs/source/Zh/doc/new_features/v23_features_doc.rst)。

- **快照與差異** — `snapshot` / `diff_snapshots` / `snapshot_screen` / `screen_changed`(`AC_screen_snapshot` / `AC_screen_diff` / `AC_screen_changed`、`ac_*`):把 a11y 樹正規化為 `{role, name, bbox}`,回報**出現 / 消失 / 移動**並附人類可讀摘要——agent 驗證某步效果所需的回饋訊號(「Save 對話框出現了」)。
- **描述螢幕** — `describe_screen`(`AC_describe_screen`、`ac_describe_screen`):廉價的「我在哪」——各 role 計數 + 互動控制項標籤。

## 本次更新 (2026-06-19) — Set-of-Marks 疊圖

VLM 定位的標準格式,走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v22_features_doc.rst`](../docs/source/Zh/doc/new_features/v22_features_doc.rst)。

- **元素標號** — `mark_elements` / `render_marks` / `resolve_mark`(純函式 + Pillow):為可互動元素指派 `1..N`(含中心/role/text),在截圖上畫編號紅框,並把選到的編號對應回元素——讓 VLM 挑*編號*而非猜像素(直接強化既有 VLM locator)。
- **標號後點擊迴圈** — `mark_screen(render_path=...)` / `mark_click(n)`(`AC_mark_screen` / `AC_mark_click`、`ac_*`):為即時 a11y 樹標號(+可選疊圖截圖),把 marks+影像餵給模型,再點擊第 `n` 號。

## 本次更新 (2026-06-19) — 檢查點與續跑

長流程的耐久執行 + `py.typed` 標記,走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v21_features_doc.rst`](../docs/source/Zh/doc/new_features/v21_features_doc.rst)。

- **流程檢查點與續跑** — `run_resumable(actions, run_id=..., store=...)` / `CheckpointStore`(`AC_run_resumable` / `AC_checkpoint_status` / `AC_checkpoint_clear`、`ac_*`):每步後持久化 step-index + 變數;以相同 `run_id` 再執行時快轉略過已完成步驟並還原變數——在第 400 步當掉的流程會從 400 續跑,而非從 0。可抽換(預設 SQLite),完成後清除。
- **`py.typed` 標記** — 附帶 PEP 561 標記,讓 Mypy/Pyright/Pylance 在下游程式碼採用 AutoControl 的內嵌型別註記(此前型別化 API 對型別檢查器是隱形的)。

## 本次更新 (2026-06-19) — i18n / l10n 測試

三項可互相搭配的純標準庫國際化/在地化測試輔助工具,走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v20_features_doc.rst`](../docs/source/Zh/doc/new_features/v20_features_doc.rst)。

- **偽在地化** — `pseudo_localize` / `pseudo_localize_catalog`(`AC_pseudo_localize`、`ac_pseudo_localize`):為 UI 字串加重音與填充(保留佔位符、以 `⟦…⟧` 包覆),在真正翻譯前揪出寫死文字並對版面施壓。
- **文字溢位偵測** — `check_overflow(elements)`(`AC_check_overflow`、`ac_check_overflow`):標記估計寬度超過元件邊界的文字(在地化頭號 bug),由 AutoControl 既有讀取的 a11y 邊界計算。
- **目錄完整性** — `check_catalog(base, target)`(`AC_check_catalog`、`ac_check_catalog`):比對翻譯目錄的缺漏/多餘/空白鍵與佔位符不一致——防止空白 UI 的 CI 閘。

## 本次更新 (2026-06-19) — 資料品質

三項純標準庫的資料品質輔助工具(介於 `load_rows`/OCR 與下游輸入之間的閘),走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v19_features_doc.rst`](../docs/source/Zh/doc/new_features/v19_features_doc.rst)。

- **資料列 schema 驗證** — `validate_rows(rows, schema)`(`AC_validate_rows`、`ac_validate_rows`):宣告式逐欄規則(type/required/regex/min/max/min_len/max_len/allowed/unique);回傳 `{ok, valid, invalid, errors}`,在壞掉的抓取/OCR 資料汙染 ERP/表單前攔下。
- **欄位擷取** — `extract_fields(text, fields, patterns)`(`AC_extract_fields`、`ac_extract_fields`):具名 regex 預設(email/url/ipv4/phone/date_iso/amount/hashtag)+自訂 patterns,作用於自由文字 / OCR 文字塊。
- **資料列遮罩** — `mask_rows(rows, rules)`(`AC_mask_rows`、`ac_mask_rows`):匯出前遮罩欄位——`redact` / `hash`(SHA-256)/ `partial`(保留末 4 字);補足僅針對截圖的遮罩。

## 本次更新 (2026-06-19) — SBOM 與測試分片

來自安全與規模研究角度的兩項純標準庫維運工具,走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v18_features_doc.rst`](../docs/source/Zh/doc/new_features/v18_features_doc.rst)。

- **CycloneDX SBOM** — `build_sbom` / `write_sbom`(`AC_generate_sbom`、`ac_generate_sbom`):為供應鏈合規(歐盟 CRA / EO 14028)輸出 CycloneDX 1.6 相依 SBOM(name/version/purl/授權);`root` 限定某套件的封閉集,`extra_components` 可納入 action 檔。不需第三方相依。
- **時長感知套件分片** — `shard_flows` / `merge_results`(`AC_shard_suite` / `AC_merge_results`):依每個流程歷史時長把流程裝箱成 N 片(讓最慢的 worker 而非測試數量決定總時長),再把各分片報告合併為一份彙總。

## 本次更新 (2026-06-19) — 反應式觀察器

非阻塞的螢幕觀察器(SikuliX `observe` 模型),走完整五層(facade、`AC_*`、MCP、Script Builder)。完整參考:[`docs/source/Zh/doc/new_features/v17_features_doc.rst`](../docs/source/Zh/doc/new_features/v17_features_doc.rst)。

- **`ScreenObserver`**(`AC_observe_add` / `AC_observe_remove` / `AC_observe_list` / `AC_observe_poll` / `AC_observe_start` / `AC_observe_stop`、`ac_observe_*`):註冊監看,在影像/文字/像素的 **appear** / **vanish** / **change** 時觸發回呼或執行 action list——在主流程繼續的同時對對話框/進度/狀態做出反應。
- **為可測試而設計**——偵測是可注入的 `predicate`;轉換邏輯用 `poll_once()` 以合成值做單元測試。內建 `image_predicate` / `text_predicate` / `pixel_predicate` 包裝既有的 locate/OCR/pixel 輔助函式。

## 本次更新 (2026-06-19) — WCAG 2.2 稽核

無障礙稽核新增 WCAG 2.2 / EN 301 549 成功準則層,走完整五層(facade、`AC_*`、MCP、Script Builder)。完整參考:[`docs/source/Zh/doc/new_features/v16_features_doc.rst`](../docs/source/Zh/doc/new_features/v16_features_doc.rst)。

- **WCAG 標註符合度稽核** — `wcag_audit(level="AA")`(`AC_wcag_audit`、`ac_wcag_audit`):為每個缺陷標註 WCAG 成功準則編號/等級/影響(4.1.2、1.4.3、1.4.10),回傳含 `by_criterion`/`by_impact` 計數的符合度報告,依 A/AA/AAA 過濾——可對應 EN 301 549 作為 EAA 合規證據。
- **目標尺寸(SC 2.5.8)** — `audit_target_size(elements, min_px=24)`:WCAG 2.2 新規則,由元素 bounds 標記小於 24×24 px 的互動目標;`tag_issue` 可為任何既有稽核問題加上 SC 標註。

## 本次更新 (2026-06-19) — 記憶與決定性

由 agent/QA 研究輪找出的兩項純標準庫工具,走完整五層(facade、`AC_*`、MCP、Script Builder)。完整參考:[`docs/source/Zh/doc/new_features/v15_features_doc.rst`](../docs/source/Zh/doc/new_features/v15_features_doc.rst)。

- **Agent 情節記憶** — `AgentMemory`(`AC_memory_remember` / `AC_memory_recall` / `AC_memory_recent` / `AC_memory_forget` / `AC_memory_stats`、`ac_memory_*`):以 SQLite 儲存 `(目標 → 軌跡 → 結果)` 情節,依關鍵字召回過往經驗注入規劃器脈絡——跨執行學習,免向量相依。
- **決定性執行** — `DeterministicRun` / `seed_everything`(`AC_seed_everything`、`ac_seed_everything`):在 `with` 區塊內固定 RNG 種子並凍結 `time.time`(記錄選擇以便重現),消除時間/隨機造成的不穩定;`time.monotonic` 保持不變,逾時仍正常。

## 本次更新 (2026-06-19) — Office 讀寫

Excel/Word/PowerPoint 的 headless 讀寫,走完整五層(facade、`AC_*`、MCP、Script Builder)。可選 extra:`pip install je_auto_control[office]`。完整參考:[`docs/source/Zh/doc/new_features/v14_features_doc.rst`](../docs/source/Zh/doc/new_features/v14_features_doc.rst)。

- **Excel** — `read_workbook` / `write_workbook`(`AC_read_workbook` / `AC_write_workbook`、`ac_read_workbook` / `ac_write_workbook`):把 `.xlsx` 工作表讀成資料列字典(第一列為鍵)並寫回,不需 GUI。
- **Word** — `read_document` / `write_document`(`AC_read_document` / `AC_write_document`):讀寫 `.docx` 段落。
- **PowerPoint** — `read_presentation` / `write_presentation`(`AC_read_presentation` / `AC_write_presentation`):讀取每張投影片文字;以 `{title, body:[...]}` 寫入投影片。

背後函式庫(`openpyxl`/`python-docx`/`python-pptx`)為可選——缺少時每個呼叫會丟出清楚錯誤,且 `import je_auto_control` 不會載入它們。

## 本次更新 (2026-06-19) — Agent 工具組

三項供 LLM / agent 驅動自動化使用的純標準庫工具,走完整五層(facade、`AC_*`、MCP、Script Builder)。完整參考:[`docs/source/Zh/doc/new_features/v13_features_doc.rst`](../docs/source/Zh/doc/new_features/v13_features_doc.rst)。

- **技能 / playbook 庫** — `SkillLibrary`(`AC_skill_save` / `AC_skill_run` / `AC_skill_list` / `AC_skill_remove` / `AC_skill_search`、`ac_skill_*`):把具名、可重用的動作序列存到磁碟,依名稱/說明/標籤搜尋,並跨執行重播——記憶體內巨集的持久化對應物。
- **Prompt-injection 防禦閘** — `assess_text` / `scan_text` / `redact_text`(`AC_guard_text`、`ac_guard_text`):在把不可信的螢幕/OCR 文字餵給 LLM 前,掃描注入樣式(指令覆寫、系統提示外洩、jailbreak/聊天樣板標記…);回傳 `{suspicious, score, findings, redacted}`。
- **A2A agent card** — `build_agent_card` / `write_agent_card`(`AC_agent_card`、`ac_agent_card`):發佈 A2A agent card,讓其他 agent 把 AutoControl 當成 GUI 自動化夥伴發現並呼叫。

## 本次更新 (2026-06-19) — 編寫與除錯

兩項純標準庫的編寫期工具,走完整五層(facade、`AC_*`、MCP、Script Builder)。完整參考:[`docs/source/Zh/doc/new_features/v12_features_doc.rst`](../docs/source/Zh/doc/new_features/v12_features_doc.rst)。

- **元素庫** — `ElementRepository`(`AC_element_save` / `AC_element_find` / `AC_element_click` / `AC_element_remove` / `AC_element_list`、`ac_element_*`):把原生 UI 定位器以友善名稱存起來(object repository)重用——用 `repo.click("login.submit")` 取代到處重複 name/role;UI 變動只需改一處。
- **步進除錯器 / 追蹤器** — `FlowDebugger`(中斷點、`step`/`continue_`/`run_to_end`、即時 `variables()`)與 `trace_actions`(`AC_debug_trace`、`ac_debug_trace`):把動作清單一次跑一個指令、變數跨步保留,或取得每步 `{index, command, result}` 追蹤(用 `dry_run` 只規劃不執行)。

## 本次更新 (2026-06-19) — 測試與工具三件套

三項純標準庫的生產力工具,走完整五層(facade、`AC_*`、MCP、Script Builder)。完整參考:[`docs/source/Zh/doc/new_features/v11_features_doc.rst`](../docs/source/Zh/doc/new_features/v11_features_doc.rst)。

- **合成測試資料** — `generate_rows(schema, count, seed=...)` / `write_dataset`(`AC_generate_data`、`ac_generate_data`):產生可重現的假資料列(name/email/phone/int/choice/date…),驅動資料驅動執行而不需真實 PII;不需 Faker。
- **MCP registry 清單** — `write_server_manifest("server.json", include_tools=True)`(`AC_mcp_manifest`、`ac_mcp_manifest`):產生符合 registry 規範的 `server.json`,讓 MCP agent/IDE 能發現此伺服器。
- **風險導向測試選擇** — `rank_flows` / `select_flows`(`AC_rank_tests` / `AC_select_tests`):依最近失敗、不穩定、陳舊與從未跑過,從 run history 排序流程;先跑最高風險或只跑前 k 個。

## 本次更新 (2026-06-19) — 交易式工作佇列

把 AutoControl 從「跑腳本」升級成「跑機器人」。以 SQLite 為底的工作佇列實作生產級 RPA dispatcher/performer:入列項目、一次處理一項、具每項狀態/去重/重試,使上千項執行能**當機後續跑**且可平行化。純標準庫、走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v10_features_doc.rst`](../docs/source/Zh/doc/new_features/v10_features_doc.rst)。

- **Dispatcher/performer** — `WorkQueue.add()` 入列(依 reference 去重);`get_next()` 原子認領最舊項;`complete()` / `fail()` 記錄結果。`AC_queue_add` / `AC_queue_next` / `AC_queue_complete` / `AC_queue_fail` / `AC_queue_stats`。
- **失敗語意** — application 錯誤重試至 `max_retries`;**business** 錯誤(`BusinessError` / `kind="business"`)永不重試。`stats()` 給各狀態計數供儀表板。

## 本次更新 (2026-06-19) — 無人值守可靠性

三個無人值守/登入自動化的社群痛點修復,皆 headless 且走完整五層。完整參考:[`docs/source/Zh/doc/new_features/v9_features_doc.rst`](../docs/source/Zh/doc/new_features/v9_features_doc.rst)。

- **2FA 的 OTP / TOTP** — `generate_totp` / `verify_totp`(`AC_otp_to_var`、`ac_generate_otp`):從 base32 secret 產生當下 6 碼,填進登入表單(重用遠端桌面 TOTP 引擎)。
- **原生檔案對話框** — `handle_file_dialog`(`AC_handle_file_dialog`):等 OS 開啟/儲存/資料夾對話框、輸入路徑、確認,一次完成,driver 可注入。
- **鎖定工作階段守衛** — `ensure_interactive_session` / `is_session_locked`(`AC_assert_session_active`):工作站鎖定/斷線時清楚失敗,而非送出幽靈點擊。

## 本次更新 (2026-06-19) — 彈窗看門狗

無人值守自動化失敗的第一大主因,是腳本沒寫到的未預期對話框(UAC、「工作階段過期」、Windows Update、modal)。彈窗看門狗以並行守衛執行緒監看註冊 pattern,獨立於主流程把它們關掉。由社群痛點研究指出為無人值守頭號失敗主因;走完整五層(facade、`AC_*`、MCP、Script Builder),完全 headless。完整參考:[`docs/source/Zh/doc/new_features/v8_features_doc.rst`](../docs/source/Zh/doc/new_features/v8_features_doc.rst)。

- **自動關閉彈窗** — `default_popup_watchdog.add_window_rule(title, action="close")` 後 `.start()`(`AC_watchdog_add` / `AC_watchdog_start` / `AC_watchdog_stop` / `AC_watchdog_list`):視窗出現時關閉它或按鍵(`enter`/`esc`)。
- **自訂規則** — `PopupWatchdog` / `WatchdogRule` 把任意偵測器(圖/a11y/文字)配對關閉器;壞規則只記錄並略過,絕不讓守衛迴圈停擺。

## 本次更新 (2026-06-19) — 原生 UI 控制

物件級桌面自動化:透過 OS 無障礙 API(以 name / role / app / **AutomationId** 定位)讀取與操作原生控制項,而非點像素或 OCR——對原生 app 可靠得多。無障礙層先前只能 list/find/click,現在還能操作。走完整五層(facade、`AC_*`、MCP、Script Builder),提供 Windows UIAutomation 後端;不支援的後端會拋清楚錯誤。完整參考:[`docs/source/Zh/doc/new_features/v7_features_doc.rst`](../docs/source/Zh/doc/new_features/v7_features_doc.rst)。

- **讀取 / 設定值** — `control_get_value` / `control_set_value`(`AC_control_get_value` / `AC_control_set_value`):讀 textbox/combo 值(不用 OCR),一次設定值(不必逐鍵輸入)。
- **呼叫 / 切換** — `control_invoke` / `control_toggle`(`AC_control_invoke` / `AC_control_toggle`):透過控制模式按按鈕或切換核取方塊。
- **讀取表格/清單** — `read_control_table`(`AC_read_table`):把 grid/list/table 控制項抓成逐列儲存格字串——不用 OCR 的桌面資料擷取。
- 以 `name` / `role` / `app_name` / `automation_id`(Windows 穩定識別碼)定位,版面/在地化改變也不壞。

## 本次更新 (2026-06-19)

兩個早已存在、卻沒接上其餘各層的 headless 核心,現在成為一級功能。兩者都新增 facade re-export、`AC_*` 執行器指令、MCP 工具與 Script Builder 項目,並有 headless 測試。完整參考:
[`docs/source/Zh/doc/new_features/v6_features_doc.rst`](../docs/source/Zh/doc/new_features/v6_features_doc.rst)。

- **視覺回歸(黃金影像)** — `take_golden` / `compare_to_golden`(`AC_take_golden` / `AC_assert_visual`):擷取基準截圖,畫面偏離超過像素容差時判失敗,並輸出標示差異圖與遮罩區域。`AC_assert_visual` 首跑會自動建立基準。純 PIL。
- **有限狀態機** — `run_state_machine`(`AC_run_state_machine`):把腳本當成宣告式 `{initial, states}` spec 驅動,`on_enter` 動作經執行器執行,transition 依 `after` / `if_var_eq` / predicate 觸發,並以 `max_steps` / `global_timeout_s` 限制。

## 本次更新 (2026-06-18)

八項 headless 能力,補齊腳本化、整合與 CI 情境:真正的命令列介面、把錄製轉成程式碼,以及一級的 HTTP / SQL / Email / PDF / 等待步驟。每項都附帶 headless API、`AC_*` 執行器指令、MCP 工具與視覺化腳本建構器項目,並有 headless 測試(網路 / SMTP / PDF 後端皆注入,不碰外部系統)。完整參考頁:
[`docs/source/Zh/doc/new_features/v5_features_doc.rst`](../docs/source/Zh/doc/new_features/v5_features_doc.rst)。

**命令列介面**
- **`je_auto_control` console script** — 在 shell／CI 執行與檢查動作檔:`run`(含 `--var`、`--dry-run`)、`validate`(別名 `lint`)、`list-commands`、`fmt`、`record`、`codegen`、`version`。

**程式碼產生**
- **錄製 → 程式碼** — `generate_code` / `generate_code_file`(`AC_generate_code`、`je_auto_control codegen`):把錄製或動作檔轉成 pytest／獨立 Python／Robot 腳本。預設 `calls` 風格產生可讀的 `ac.<fn>(...)`,流程控制退回 `ac.execute_action([...])`。

**整合**
- **HTTP / API** — `http_request`(`AC_http_request`):method、headers、JSON／原始 body、basic／bearer 認證、明確逾時;非 2xx 回傳而非丟例外。`AC_http_to_var` 現共用此客戶端,可送 body。
- **SQL** — `query_sqlite`(`AC_sql_to_var` / `AC_assert_db`):唯讀、參數綁定的 SQLite 查詢,存入變數或做純量斷言。
- **Email(SMTP)** — `send_email`(`AC_send_email`):標準庫 SMTP,預設 TLS(STARTTLS／SSL、已驗證憑證),支援附件與多收件人。
- **PDF** — `extract_pdf_text` / `pdf_metadata` / `assert_pdf_text`(`AC_pdf_to_var` / `AC_assert_pdf_text`):文字抽取與內容斷言,後端為可選 `pypdf`(`pip install je_auto_control[pdf]`)。

**智慧等待**
- **等待檔案** — `wait_until_file`(`AC_wait_for_file`):等到檔案存在且大小停止增長(下載寫完)。
- **等待 TCP 連接埠** — `wait_until_port`(`AC_wait_for_port`):等到 `host:port` 可連線(與 `launch_process` 互補)。
- **等待行程** — `wait_until_process`(`AC_wait_for_process`):等到行程出現或結束(與 `launch_process` / `kill_process` 互補;需 psutil)。

**安全性** — HTTP／SMTP 強制 http/https 或已驗證 TLS 與明確逾時;SQL 唯讀且參數綁定;檔案路徑 I/O 前以 `realpath` 解析。

## 本次更新 (2026-06-17)

新增 30+ 個自動化原語，涵蓋輸入擬真、視覺、流程控制、觸發器、視窗管理與檔案安全，
另加「可還原刪除（資源回收桶）」與「編輯器 Undo」。每個都附帶 headless API、`AC_*`
執行器指令，以及視覺化腳本建構器項目；視覺與視窗功能的 geometry / IO 操作皆可注入，
邏輯完全單元測試。完整參考頁：
[`docs/source/Eng/doc/new_features/v4_features_doc.rst`](../docs/source/Eng/doc/new_features/v4_features_doc.rst)。

**擬人化輸入**
- **擬人化滑鼠移動** — `move_mouse_humanized`：eased bezier 曲線 + overshoot + jitter，seed 可重現（`AC_human_move`）。
- **擬人化打字** — `type_text_humanized`：每字隨機微延遲 + 偶爾停頓，seed 可重現（`AC_human_type`）。

**視覺**
- **VLM 自然語言斷言** — `assert_by_description`：用 VLM 判斷畫面是否符合描述（`AC_assert_vlm`）。
- **捲動找元素** — `scroll_until_visible`：往某方向捲動直到圖／文字出現（`AC_scroll_to_find`）。
- **區域顏色統計** — `region_color_stats`：平均色 + 主色 + 占比（`AC_region_color_stats`）。
- **讀 QR code** — `read_qr_codes`：OpenCV QRCodeDetector 從螢幕區域解 QR（`AC_read_qr`）。

**流程控制與變數**
- **可重用巨集** — `AC_define_macro` / `AC_call_macro`：具名、帶參數的動作子程序，`${arg}` 綁定。
- **同進程平行** — `AC_parallel`：多分支並行，各自獨立 executor，變數不互相 race。
- **效能預算斷言** — `assert_duration` / `AC_assert_duration`：超過毫秒預算就判失敗。
- **讀進變數** — `AC_ocr_to_var`、`AC_shell_to_var`、`AC_read_file_to_var`、`AC_http_to_var`（body 或 dotted JSON path）、`AC_now_to_var`（strftime）、`AC_random_to_var`（seeded）。
- **變數轉換** — `AC_transform_var`：upper／lower／strip／title／replace／regex 取出／slice。
- **斷言變數** — `assert_variable` / `AC_assert_var`：eq／ne／lt／gt／contains／regex。

**觸發器與智慧等待**
- **複合觸發器** — `AllOfTrigger` / `AnyOfTrigger` / `SequenceTrigger`：布林 AND／OR／順序組合任何現有觸發器。
- **Cron 觸發器** — `CronTrigger`：五欄 cron 排程，每分鐘最多一次，可與布林觸發器組合。
- **更多智慧等待** — `wait_until_clipboard_changes`（`AC_wait_clipboard_change`）、`wait_until_window_closed`（`AC_wait_window_closed`）。

**視窗管理**
- **單一視窗截圖** — `capture_window`：依標題截出該視窗（`AC_capture_window`）。
- **版面存／還原** — `save_window_layout` / `restore_window_layout`：快照所有視窗位置 → JSON → 一鍵還原。
- **貼齊／分割** — `snap_window`：左／右半、四角、最大化（`AC_snap_window`）。

**檔案安全**
- **動作檔簽章** — `sign_action_file` / `verify_action_file`（HMAC-SHA256）；`execute_files` 可在 `JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` 下強制驗章。
- **動作檔加密** — `encrypt_action_file` / `decrypt_action_file`（Fernet）。
- **可還原刪除** — `move_to_trash`：送進作業系統資源回收桶（`AC_move_to_trash`）。

**報告與通知**
- **截圖標註** — `annotate_screenshot`：畫帶標籤方框／高亮／箭頭／文字（`AC_annotate_screenshot`）。
- **桌面通知** — `notify`：跨平台 toast，injection-safe（`AC_notify`）。

**GUI**
- **錄製編輯器 Undo** — 每個編輯都快照；**Ctrl+Z** 與 Undo 按鈕還原。
- **觸發器頁** — 「Combine selected」把選取的觸發器組成複合；新增 **Cron** 型別。
- **斷言頁** — 新增 **VLM** 斷言型別。
- 所有新 `AC_*` 指令都在視覺化 **腳本建構器** 可用。

**修正** — 修了 PySide6 6.11.1 上 USB 授權彈窗的 `Q_ARG(object)` crash、8 個 stale／壞掉的測試、2 個遺失例外鏈，並把 13 個函式拉回 CC≤10。

## 本次更新 (2026-06)

新增 9 個功能，把自動化原語升級成一套完整的 **QA / 測試框架**：驗證畫面狀態、
用資料驅動腳本、偵測並隔離不穩定測試、執行計分套件、輸出 CI 原生報告、
稽核無障礙 / i18n、跨裝置矩陣並行執行，以及對音訊 / 影片做斷言。
每個功能都遵循框架既有模式：headless Python API、`AC_*` executor 命令、
`ac_*` MCP 工具，以及 Qt GUI 分頁。完整參考頁面：
[`docs/source/Zh/doc/new_features/v3_features_doc.rst`](../docs/source/Zh/doc/new_features/v3_features_doc.rst)。

**斷言**
- **斷言 DSL** — 驗證畫面狀態而不只是操作：`assert_text`（OCR，`regex` + `present=False` 斷言不存在）、`assert_image`、`assert_pixel`、`assert_window`、`assert_clipboard`（`equals` / `contains` / `regex`，`present=False` 可確認機密已清除）、`assert_process`（指定名稱的程序是否執行中，透過 psutil）。回傳 `AssertionResult`，不符時拋出 `AutoControlAssertionException`，可選失敗截圖（`AC_assert_text / _image / _pixel / _window / _clipboard / _process`）。
- **畫面外斷言** — `assert_file`（檔案存在 / 子字串 / SHA-256 / 最小大小，驗證下載或匯出結果）與 `assert_http`（http/https 端點回傳狀態碼 + 可選內文，一律帶明確 timeout）。兩者把 DSL 延伸到畫面之外，並能接到下方的組合器（`AC_assert_file / AC_assert_http`）。
- **斷言組合器** — `assert_all([...specs])` 以*軟斷言*方式跑完整批（逐一檢查、收齊所有失敗才拋出）並回傳 `GroupAssertionResult`；`assert_any([...specs])` 是 OR 互補（任一通過即通過、短路 — 例如登入成功對話框*或*重新導向其一出現即可）；`assert_eventually(spec, timeout, interval)` 重試單一宣告式 spec 直到通過或逾時（例如輪詢健康檢查端點直到回傳 200，或等待下載檔出現）。皆以 spec 驅動（`{"kind": "text", "text": "Saved"}`、`{"kind": "http", "url": "..."}`），在 Python、JSON、MCP 中行為一致,涵蓋全部斷言種類 — text/image/pixel/window/clipboard/process/file/http（`AC_assert_all / AC_assert_any / AC_assert_eventually`）。
- **媒體斷言** — `assert_audio_activity`（錄音 + RMS 門檻判斷有聲 / 靜音）與 `assert_video_changes`（影片區段相鄰影格平均差異判斷動態 / 靜止）；純數值核心，`sounddevice` / OpenCV 延遲載入（`AC_assert_audio / AC_assert_video_changes`）。

**資料驅動執行**
- **資料來源** — `load_rows` 支援 CSV / JSON / SQLite / Excel / 內嵌；`AC_for_each_row` 區塊命令每列執行一次 body，欄位以 `${row.column}` 取用。SQLite 僅允許單句唯讀 `SELECT`/`WITH`，路徑經 `realpath` 驗證。`${var}` 插值現在支援點號路徑（dict 鍵 / list 索引）並保留型別（`AC_load_data`）。

**不穩定偵測與隔離**
- **不穩定報告** — 從執行歷史以通過↔失敗翻轉率評分間歇性失敗，依 script / source 分組（`AC_flaky_report`）。
- **隔離區** — 套件執行器會遵守的持久化（0600）跳過清單；`auto_quarantine_from_flakiness` 依翻轉率門檻自動填入（`AC_quarantine_add / _remove / _list / _clear / _auto`）。

**套件執行器 + CI 報告**
- **QA 套件編排** — `run_suite` 把 action list 變成具 setup / teardown、標籤與資料驅動展開的計分案例；斷言失敗 → failed、其他例外 → error、被隔離 → skipped（`AC_run_suite`）。
- **JUnit / Allure 報告** — `write_junit_xml` + `write_allure_results`（或 `AC_run_suite` 的 `junit_path` / `allure_dir`），輸出 Jenkins / GitHub Actions / GitLab CI / Allure 原生解析的報告。

**稽核、矩陣、媒體**
- **無障礙 / i18n 稽核** — 反向利用 a11y 樹 + OCR，找出缺漏的可存取名稱、WCAG 對比度不足與省略號截斷字串（`AC_audit_accessibility / AC_audit_contrast`）。
- **行動裝置矩陣** — 將單一 action list 並行分發到多台 Android / iOS 裝置，每台獨立 executor，透過 `${device.*}` 鎖定當前裝置；逐裝置通過 / 失敗，失敗互相隔離（`AC_run_device_matrix`）。

## 本次更新 (2026-05)

新增 27 個功能，涵蓋更聰明的定位器、更深的 IDE / 維運工具、
四個新平台後端（Wayland、Wayland-libei、Android widget tree、iOS）、
螢幕截圖 PII 遮罩，以及通用的 plan-execute-verify agent 迴圈。
每個功能都遵循框架既有模式：headless Python API、`AC_*` executor 命令、
`ac_*` MCP 工具，以及（適用時）Qt GUI 分頁。完整參考頁面：
[`docs/source/Zh/doc/new_features/v2_features_doc.rst`](../docs/source/Zh/doc/new_features/v2_features_doc.rst)。

**定位器與選擇器智慧化**
- **自我修復定位器** — `image_template → VLM` 後備並寫入 JSON-lines 稽核記錄（`AC_self_heal_locate / _click`）。
- **錨點定位器** — 依空間關係（`above` / `below` / `left_of` / `right_of` / `near`）找到目標；錨點與目標可使用不同 backend（image / OCR / VLM / a11y）。
- **結構化 OCR** — 把原始 OCR match 聚合為 rows、tables、`label:value` 表單欄位（`AC_ocr_read_structure`）。
- **智慧等待** — `wait_until_screen_stable`、`wait_until_pixel_changes`、`wait_until_region_idle`：用 frame-diff 取代 `time.sleep`。
- **A/B 定位器框架** — 並行跑 N 個策略，依持久化的歷史成績推薦最佳。

**維運與觀察性**
- **LLM 成本遙測** — 每次呼叫的 token / USD 紀錄，按天 / 模型 / 提供者彙總（`record_llm_call`、`summarise_llm_costs`）。
- **追蹤重播 UI** — 在現有 time-travel 錄影上拖曳時間軸並逐步顯示動作。
- **失敗 → 工單自動化** — 排程／觸發器／REST 任務失敗時自動分送 Jira / Linear / GitHub Issues。
- **容器化 CI 模板** — GitHub Actions + GitLab CI workflow：建鏡像、跑 headless pytest（Xvfb 容器內）、smoke-test REST entrypoint；另含 XFCE+x11vnc Dockerfile 變體。
- **跨主機 DAG 編排** — 跨 local + admin-console 已註冊主機並行執行，失敗時下游 cascade 為 `skipped`（`run_dag`、`AC_run_dag`）。
- **多 viewer 名單** — 為遠端桌面提供控制者 / 觀察者角色，純 Python `PresenceRegistry` 獨立於 aiortc。

**代理與整合**
- **Computer-use 高階 API** — `run_computer_use(goal, ...)` 封裝 `ComputerUseAgentBackend` + `AgentLoop`；自動偵測螢幕大小；以 `max_steps` / `wall_seconds` 為預算。
- **通用 agent 迴圈 JSON / MCP 接點** — `AC_run_agent` / `ac_run_agent` 把閉環 `AgentLoop`（規劃 → 執行 → 驗證 → 重試）開放給 JSON action 與 MCP 客戶端，支援 Anthropic / OpenAI 兩種 backend；既有的 Anthropic 原生 Computer-Use 路徑仍透過 `AC_computer_use` 提供。
- **WebRunner 便利命令** — 在既有 `je_web_runner` 橋接之上的 `web_open` / `web_quit` / `web_screenshot` / `web_current_url`；同步以 `AC_web_*`、`ac_web_*` 暴露。
- **Chat-ops 機器人** — 傳輸層中立的 `CommandRouter` + Slack polling adapter。內建命令：`/help`、`/scripts`、`/run`、`/screenshot`、`/status`。RBAC 透過 `required_role`。

**隱私與安全**
- **截圖 PII 遮罩** — `RedactionEngine` 內建偵測：email / credit card / SSN / 電話（regex 比對呼叫端提供的 OCR token）以及 accessibility tree 標記的 secure-text 欄位；可指定強制模糊區域。預設政策透過環境變數 `JE_AUTOCONTROL_REDACTION=off|moderate|strict` 控制。執行器命令 `AC_redact_screenshot` 與 MCP `ac_redact_screenshot` 都已串接。

**平台覆蓋**
- **Wayland CLI 後端** — `wtype` / `ydotool` / `grim`，依 `XDG_SESSION_TYPE` 自動偵測，CLI 工具未裝時回退到 X11 (XWayland)；可用 `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11|wayland|auto` 覆寫。
- **Wayland libei 原生後端** — 對 `libei.so.*` 的 ctypes 綁定，繞過 CLI shim 取得微秒級延遲；以 `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei|cli|auto` 啟用，預設在 libei 可載入時用 libei。
- **macOS Accessibility 強化** — 遞迴 `dump_accessibility_tree()` 與 polling `AccessibilityRecorder`，捕捉 focus / bounds 事件。
- **Android — adb shell 原語** — `AC_android_tap/swipe/key/text/screenshot` 直接透過 `adb` 驅動任何 USB / Wi-Fi adb 連線的手機，不需要常駐 daemon。
- **Android — uiautomator2 widget tree** — `AC_android_find_element/click_element/dump_hierarchy` 在 adb 路徑之上加上 selector（`text` / `resource_id` / `description` / `class_name`）查找與即時 XML hierarchy dump。
- **iOS — WebDriverAgent / XCUITest** — 新的 `je_auto_control.ios.*` 命名空間：`tap`、`swipe`、`long_press`、`type_text`、`press_key`、`screenshot`、`screen_size`、`find_element` / `click_element`（XCUITest selector：`name`、`class_name`、`predicate`）、`dump_source`。新增七個 `AC_ios_*` executor 命令與對應 `ac_ios_*` MCP 工具。`facebook-wda` 為可選 pip 相依、懶載入，非 macOS 主機 import 仍可成功。

**開發者體驗**
- **autocontrol-lsp 完整化** — 追蹤 `didOpen` / `didChange` / `didClose`、發佈 JSON 與未知 `AC_*` 命令的 diagnostics、由即時的 executor 表產生 signature help。
- **`.pyi` stub 產生器** — `python -m je_auto_control.utils.stubs.generator je_auto_control/actions.pyi` 寫出 IDE 端 stub 檔，所有 `AC_*` 命令在 IDE 內可 autocomplete 並顯示參數提示。
- **VS Code 擴充** — 內建擴充新增 `AutoControl: Run / Screenshot / Preview` 命令，直接打本機 REST API。
- **瀏覽器擴充錄製器** — `browser-extension/` 下的 Manifest V3 擴充：捕捉分頁的點擊、輸入、導航與表單提交，匯出成 `AC_web_*` / `WR_*` JSON。
- **pytest plugin + Gherkin BDD** — `pytest11` entry point 自動載入；`@pytest.mark.autocontrol` 開啟失敗自動截圖；`bdd_steps.register_pytest_bdd_steps(pytest_bdd)` 一次把 `Given/When/Then` 對應到每一個 `AC_*` verb。
- **視覺流程編輯器** — node-based 視圖與既有 list-based Script Builder 使用同一份 JSON 格式，互相相容。

---

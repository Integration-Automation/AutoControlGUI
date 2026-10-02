# 跨平台自動化與 GUI 改版設計

狀態：設計已核准；本文件描述預定行為，不代表功能已實作。

## 1. 目標與範圍

依根目錄 `Progress.md` 的未完成項目與維護者已填寫的 `[Answer]`，完成下列工作：

1. 重新設計 UI，重寫並優化 GUI。
2. 修正 Wayland 後端、資源管理與可用性；有問題的函式庫以修正、替代後端或隔離方式處理。
3. 解決跨機器設定、檔案、工作狀態與遠端連線不同步的問題。
4. 補強全套 mypy 檢查。
5. 補齊 iOS、Android 的自動化功能與所有交付介面。
6. MCP 採取逐步揭露，降低首次載入與每次互動的 schema 成本。
7. 讓自愈定位器的改動可透過固定資料集與真實執行結果量測。
8. 從動作日誌接上 codegen，產生可審閱的候選腳本。
9. 補齊可執行範例、完整設定說明、API 文件與疑難排解。

成功條件是實際功能、相容性測試、平台測試與文件一致。能力受作業系統或授權限制時，
必須提供可用的替代流程與具體原因，不能回傳假成功、假座標或以跳過測試宣稱支援。

這是多個子專案；各階段各自維持可用版本與獨立提交。既有公開 import、`AC_*` 名稱、
舊式 CLI 與跨專案契約沿用，必要的行為變更按照 `Progress.md` 已核准的決策遷移。

## 2. 已確認的現況

| 領域 | 原始碼證據 | 改版要處理的差距 |
| --- | --- | --- |
| GUI | `gui/main_widget.py` 在建構時匯入及建立全部面板；`main_window.py` 使用分頁與 qt-material | 首次啟動成本、導航、工作執行緒與關閉生命週期 |
| Wayland | `linux_wayland/libei.py` 依交握狀態釋放資源；`listener.py`、`record.py` 為受限實作 | 半開交握 crash 迴避、取消授權、裝置暫停與重連、錄製與停止機制 |
| 設定同步 | `utils/config_sync/client.py` 執行 fetch → merge → 無條件 push | 並行更新、離線重送、時鐘偏差、刪除項目過期與衝突可見性 |
| 同步 server | `utils/remote_desktop/signaling_server.py::_ConfigStore` 使用記憶體 dict | 重啟資料遺失、持久化與原子版本檢查 |
| 遠端連線 | `utils/remote_desktop/registry.py` 每 transport 共用 host/viewer 槽位 | 面板互相中斷、過期回呼、連線所有權 |
| 型別 | `test/verify/typing_contract_verify.py` 檢查三個目標；豁免清單為空 | 未標註函式、泛用容器與第三方 `Any` 邊界的檢查深度 |
| 行動裝置 | `android/` 提供 ADB、UIAutomator；`ios/` 提供 WDA、基本輸入與定位 | 能力一致性、裝置隔離、生命週期、GUI 與文件完整度 |
| MCP | `utils/mcp_server/server.py::_handle_tools_list` 回傳整份 registry descriptor | 首次 schema 體積、搜尋、依 session 揭露與權限一致性 |
| 自愈 | `utils/self_healing/{locator,heal_log}.py` 記錄 image/VLM/miss 與耗時 | 定位版本、結果驗證、資料集評估、品質與成本比較 |
| codegen | `utils/codegen/codegen.py` 接收動作清單；支援 pytest/python/robot | 結構化日誌轉換、步驟來源、秘密遮罩、候選預覽與驗證 |

2026-10-02 本機執行 `.venv/Scripts/python.exe test/verify/typing_contract_verify.py`：
win32、linux、darwin 均為 0 個錯誤模組。這只能證明現有設定通過，不能推論所有函式已嚴格標註。

`Progress.md` 已有使用者修改；實作與提交只處理本階段內容，保留原有決策。
`config_sync/__init__.py` 所稱尚無 `/config` endpoint 與實際 server 不一致，隨同步階段修正。

## 3. 改版方式

採用分階段替換：保留 headless 核心與公開契約，重寫 GUI shell、平台縫與確定有缺陷的模組。
測試與量測先建立基準，再替換實作。所有新功能同時交付 Python API、executor、GUI、
必要的 CLI/MCP 介面與使用文件。

整套一次重寫會讓既有後端與契約難以驗證；只換配色則無法處理同步、生命週期與平台問題。
分階段替換能逐步驗證每個子系統，並讓 GUI 在核心功能成熟後接上統一能力資訊。

### 3.1 共用能力與執行邊界

以型別化的能力描述表示 available、needs_permission、needs_dependency、unsupported 與原因。
探測不自動要求權限、不開啟裝置控制；真正的操作才建立 session。
GUI、executor 與 MCP 使用同一份資訊，並共享參數驗證及錯誤型別。

每個頂層執行、裝置、遠端連線與背景工作有自己的 context，包含 run/session/device ID、
取消訊號與變數範圍。context 以明確參數或受控邊界傳遞，不以另一個全域可變 singleton 代替。
例外繼承框架的 `AutoControlException`；結果不把「未取得能力」編碼成成功。

### 3.2 UI 與 GUI

桌面工具保留 PySide6，主介面改為可搜尋的左側功能導航、中間工作區、右側可收合的執行詳情。
導航分成錄製／腳本、定位／檢查、裝置／遠端、執行／報告、設定／診斷。
預設入口呈現錄製、腳本與遠端連線。功能以 factory 延遲匯入、第一次開啟才建立，
關閉時釋放 worker、session 與訂閱。保留舊的分頁識別碼及 show/hide/list 相容入口。

使用一致的間距、字級、焦點狀態、空白狀態、錯誤提示、淺色與深色主題。
支援視窗縮放、混合 DPI、多螢幕、鍵盤導航與動態語系；依現有語系目錄同步所有新增字串。
一般面板的操作仍由 Actions 選單提供，符合專案既有規範；Script Builder 與 Remote Desktop
保留互動操作。背景工作顯示進度與取消結果。

檔案、網路、ADB/WDA、OCR/VLM、腳本執行與同步移到 worker。worker 僅回傳資料，
UI 更新透過 Qt signal。關閉畫面不能留下 callback 存取已銷毀的 Qt 物件。

先量測冷啟動、開啟面板、記憶體、事件迴圈延遲與關閉耗時；同一台機器、相同依賴與
相同 workload 比較。效能門檻在取得基準後記入 benchmark 設定，不能用未量測的數字宣稱改善。

### 3.3 Wayland 與函式庫問題

輸入控制優先使用 RemoteDesktop portal 的授權 session 與 libei；ydotool 是明確配置的替代。
擷取共用 ScreenCast/PipeWire 或已有可用的擷取後端，所有路徑遵守同一座標與螢幕原點契約。
backend 選擇、授權取消、權限撤銷、compositor 重啟、裝置移除、鍵盤布局與按鍵釋放都要可觀察。
XWayland 的能力必須按照實際覆蓋範圍呈現。

先以 `docker/libei_verify.py`、`docker/eis_verify.py` 重現目前 crash 狀態，並修正與程式不符的
進度敘述。修 ctypes 原型、fd 擁有權與狀態機；若原生函式庫在合法清理仍會崩潰，
將 session 放入專用 helper process，使用有界、可取消的 IPC，讓作業系統回收該 helper 的資源。
先量測 IPC 對輸入延遲的影響，並驗證 helper crash、啟動失敗與主程式退出。
禁止在 GUI 主行程呼叫已知會 SIGSEGV 的清理來取代現有迴避。

動作記錄分為 executor 已執行動作與實體輸入。前者在所有後端提供一致的結構化日誌。
後者在 Wayland 採取實際可用、需要明確配置的裝置事件讀取替代，並排除自己注入的事件。
InputCapture 的觸發與啟用由 compositor 決定，不能當成任意時間啟動的一般全域錄製器。
提供 GUI 停止控制與受支援的 GlobalShortcuts 路徑；權限不足時明確提示可用停止方法。

依序驗證現有 wlroots 測試環境、GNOME、KDE；授權允許與拒絕、不同 portal 版本與
libei 支援版本均需留下測試報告。只通過 fake backend 不能把該功能標示為實機驗證。

### 3.4 跨機器同步

同步範圍包括腳本與引用資產、定位器、快捷鍵、觸發器、通訊錄，以及需要同步的工作設定。
機器專屬路徑、認證秘密、裝置連線與暫存授權資訊保留在本機；腳本的秘密以參照表示。
「同步」不自動執行同步過來的腳本或啟用觸發器。

server 使用 SQLite 持久化 user bucket 與修訂版；在同一交易比較 base revision 並寫入。
client push 帶 base revision，落後回覆 conflict，重新 fetch、merge 並有限次重試。
成功回傳 committed revision；網路中斷與不確定成功使用 operation ID 去重。
舊 client 的無條件寫入只在明確相容模式開啟；新的 GUI 顯示 server 是否具備競爭保護。

每筆變更有 origin device、operation ID 與因果版本資訊。不同 entry 的更新自動合併；
同一 entry 的並行變更保留兩份資料與衝突供選擇，不依本機 wall clock 靜默覆寫。
刪除使用版本化 tombstone；回收依已知裝置確認版本，離線裝置過期後必須完整重同步，
不能單靠經過幾天就丟棄 tombstone 而使刪除內容復活。

本機 outbox 持久化、退避重送；每個帳號與 endpoint 隔離。GUI 顯示 pending、syncing、
synced、conflict、offline 與 last successful revision。資產以內容 hash 驗證，暫存後原子替換，
避免只同步到腳本而缺少樣板。既有 folder mirror 與 clipboard sync 分開驗證，
避免循環傳送、部分檔案、不同原點與斷線重連造成假同步。

遠端 registry 增加 session ID 與 owner，狀態與斷線指定 session。
省略 session 的既有 `AC_remote_*` 指令仍操作腳本的預設 session；GUI 面板各自持有自己的 session。
替換或結束 session 發出通知，過期 frame/error callback 依 session ID 丟棄。

### 3.5 Android 與 iOS

保留已有 ADB、UIAutomator、WDA 的延遲匯入，建立共用 device context 與能力契約。
每台裝置的連線、session、取消與重試互相隔離，平行執行不可修改預設 singleton 指向。

| 功能組 | Android 實作路徑 | iOS 實作路徑 |
| --- | --- | --- |
| 裝置與 session | ADB 探測、授權狀態、UIAutomator session | WDA endpoint 探測、session 建立與關閉 |
| 輸入與手勢 | tap、長按、swipe、drag、pinch、Unicode 輸入、按鍵 | WDA 對應輸入、手勢、文字與受支援按鍵 |
| 畫面與定位 | 截圖、原點／尺寸／旋轉、UI tree、OCR、樣板、VLM、自愈 | 相同 headless pipeline，適配 WDA point/pixel 座標 |
| App 與等待 | 啟動、停止、狀態、等待元素、alert | WDA App 狀態、啟動／終止、等待與 alert |
| 擴充裝置功能 | 安裝、檔案、剪貼簿、錄影等逐項 capability | WDA 不提供的項目以可配置的受支援 adapter 補足 |
| 工作與報告 | device matrix、結構化日誌、codegen、run history | 相同 context 與資料格式 |

「所有功能」逐項對照 executor、Script Builder、MCP 與文件矩陣，不能只新增 SDK wrapper。
桌面視窗管理、COM、USB 主機等不具行動平台對應語意的功能，需在矩陣列出替代或限制。
iOS 擴充以現有 WDA 能力為基礎；確需安裝／檔案等額外服務時使用可選 adapter，
不以 ADB shell 的形式假設 iOS 可執行相同操作。
實機建置與簽章需求按選定 backend 寫入文件；本機 Windows 可連遠端 WDA，
但不以此宣稱已在 Windows 本機完成 Xcode 建置與實機驗證。

### 3.6 MCP 逐步揭露

保留完整 registry 作為單一工具定義來源，另加 typed 搜尋索引與 session 可見工具集。
漸進模式先提供狀態、工具搜尋與啟用工具，搜尋預設僅回傳名稱、簡短說明與能力需求；
需要時取得單一工具的完整 schema，啟用後才加入該 session 的 `tools/list`。
完整模式保留既有使用方式；文件與啟動設定明確提供兩種模式。

啟用、停用與插件變更發出 `notifications/tools/list_changed`。tools/list 使用不透明 cursor
與穩定 snapshot；舊 cursor、已刪除 plugin、重複啟用與 session 關閉有一致處理。
HTTP session 之間不能共享揭露狀態，stdio server 有自己的 session。
對無法即時更新清單的 client，提供設定好的靜態能力 profile。

工具搜尋、schema 取得、啟用與呼叫都套用同一 read-only、root、env allowlist 與權限規則。
漸進揭露不取代授權，也不新增可繞過驗證的通用 executor 工具。
`AC_run_agent` 維持 `Progress.md` 的「不改」決策；本階段的 MCP 改版不暗中縮減其工具集合。
量測 descriptor 數、JSON bytes、首次交握與搜尋／啟用耗時，並以完整模式作比較。

### 3.7 自愈定位器量測

保留舊 HealEvent 的讀取相容性，加入 schema version、run/step/locator ID、locator version、
選用策略、frame hash、候選座標、各策略耗時、backend/model 與成本資料。
完整修正 `screen_region` 在 image 與 VLM 兩條路徑的語意與座標換算。

定位成功與操作成功分別記錄。沒有 ground truth 或操作後的驗證不能算正確命中。
固定資料集提供畫面、目標 box、原點／縮放與期望 miss；受控 replay 比較相同輸入的版本。
報告包含 image hit、fallback、miss、正確率、false-positive、恢復成功率、p50/p95 延遲及
有資料時的模型成本。每個比率附分子、分母；未標註項目顯示 unknown，不算成正確樣本。

回歸資料集與 thresholds 進版控，結果輸出 JSON 與可分享報告。
GUI 顯示版本比較、失敗案例與原始步驟；headless 與 MCP 產生同一份報告。
樣板修改產生候選版本，可預覽、驗證與回復；不直接用未驗證 VLM 座標覆寫舊定位器。

### 3.8 動作日誌與 codegen

定義 append-only JSONL 日誌：schema version、run/step/parent ID、device/session、順序、
command、可序列化參數、起訖、status、錯誤與可引用 artifact。
在 executor 的動作邊界記錄，GUI、CLI、REST、MCP 走同一條路。
秘密在寫入前轉成 secret reference 或遮罩；未知 payload、不可重播參數與缺失來源明確標記。

日誌 importer 驗證版本、順序與 command schema，按 run 選擇步驟並保留來源索引。
保留 loop/branch/parallel 的階層；無法還原控制流程時產生明確標示的已觀察路徑候選，
不可憑空恢復沒有執行的分支。
失敗、重試與補救步驟提供明確選取規則，不能把執行結果誤當輸入參數。

轉換後呼叫現有 `generate_code`，交付 Python、pytest、Robot 候選與 provenance manifest。
靜態解析、command 驗證與無副作用 dry-run 後，GUI 提供 diff/預覽與匯入 Script Builder。
產碼不自動執行；真正 replay 是獨立操作。
不使用 eval 或執行文字 log 的 repr，任意文字 log 僅在能可靠解析的格式下支援。

### 3.9 型別、文件與範例

保留三目標 mypy 與空豁免清單。新寫／重寫模組啟用完整函式標註、型別化容器與 Protocol；
逐步把 SDK `Any` 限縮於 adapter，優先 GUI worker、同步 wire payload、device、MCP 與日誌。
另外驗證已安裝 GUI 等 extras 的型別環境；不以全域 skip/ignore_errors 隱藏新版 SDK 的不相容。
對 Python 3.10 無法解析的新型別語法維持必要的特定相依邊界，並記錄理由。

每個新流程都有最小可執行範例與整合範例，包含 GUI 對應操作、無 GUI 使用、權限配置、
錯誤處理與結果。範例支援 validate/dry-run；需要實機的執行條件與指令明列。
包含 Wayland 診斷／授權、兩台機器同步、Android/iOS、多裝置平行、自愈版本比較、
日誌轉腳本、MCP 漸進模式與舊 client 相容模式。

同步更新三語 README、Sphinx 英文／中文、API lifecycle、capability matrix、CHANGELOG、
`architecture.md`、`architecture_explore.md`、examples 索引與 measured counts。
未完成工作留在 `Progress.md`；完成後才移入 `docs/updates/`。

## 4. 沿用 Progress.md 決策

| 原有項目 | 實作契約 |
| --- | --- |
| 簽章 | 簽章金鑰與執行權限分離；執行端不能取得預設簽章能力 |
| USB request/reply | 加 request ID；遲到回覆不能完成新的請求；舊 peer 無 ID 時需安全處理逾時歧義 |
| 執行變數 | 每次頂層執行使用新的 VariableScope；巢狀與平行任務繼承正確 context |
| 舊式 CLI | 動作失敗回 exit 1，維持既有旗標與跨專案契約 |
| MCP registry 名稱 | `io.github.integration-automation/autocontrol`，同步修正專案 URL |
| pytest11 | 頂層精簡 plugin；舊套件 import 路徑 re-export；重裝與 coverage 前提一起修正 |
| cryptography | 下限提升至已核准的 50；可選能力明確診斷，不能以不安全版本換 wheel |
| Viewer 收檔 | 預設下載根目錄與相對路徑，拒絕越界；文件與範例遷移 |
| AC_run_agent | 保持預設工具集決策，不加入未核准的工具縮減 |
| MCP 路徑 | 同時支援配置根目錄與 roots/list；不預設啟用唯讀限制 |
| Windows DPI | 換成 per-monitor v2，檢查 Jeffrey_RPA 使用端與混合 DPI 座標 |
| 遠端 registry | GUI 與 AC/MCP session 語意一起修正 |

其他尚未完成項目也納入實作：macOS 最小化還原、Windows 副螢幕擷取、Retina 多螢幕、
輸入 wrapper 修正、agent 截圖歷史壓縮、arm64 可選相依、Python 3.10 USB ACL 間歇 crash。
agent API 與原生依賴版本在實作時查核官方文件，不能只依進度檔中的版本或 API 名稱猜測。
Computer-use 預設切換須有真實 API 驗證才落地。

RBAC 與強制簽章的舊部署過渡仍需細化；建議以明確 opt-in 的 UserStore 配置啟用角色，
沒有配置時保留既有共用 token。角色到 route/tool 的對應由能力分類產生，稽核帶 user_id。
本設計審閱時需確認這個尚未有 `[Answer]` 的預設方案。

## 5. 實作順序與驗收

| 階段 | 工作 | 必須通過的驗收 |
| --- | --- | --- |
| A | 基準、契約、已核准 Progress 修正 | 失敗重現、契約測試、pytest/plugin/CLI/簽章/USB 回覆隔離 |
| B | 日誌、自愈量測、codegen | 固定 frame 的前後比較；遮罩後日誌可轉碼；mock replay 與來源一致 |
| C | 持久同步、衝突與遠端 session | server 重啟、雙 client 並寫、斷線重送、刪除不復活、面板互不誤斷 |
| D | Wayland 與有問題的依賴 | 真實 EI peer、半開交握退出、授權允許／取消、裝置暫停／移除與資源界線 |
| E | 行動平台 | 多裝置隔離、Unicode、旋轉與 point/pixel、所有交付介面與實機案例 |
| F | GUI 重寫 | 全功能可達、延遲建立、無 UI 執行緒 I/O、取消／關閉、DPI／鍵盤／語系 |
| G | MCP 漸進模式 | 首次 schema 減少、搜尋／啟用、session 隔離、唯讀／root／plugin／cursor 相容 |
| H | 型別深化與總驗收 | 各階段同步深化型別；完整回歸、文件建置、範例 validate、矩陣一致 |

每階段都同步交付型別、GUI/CLI/MCP 入口與文件；H 是整合驗收，不把文件延至最後才補。
新的檔案遵守 750 行上限；重寫已超限模組先拆清楚的責任邊界。

單元測試使用可控 clock、frame、network、device 與 session，不驅動使用者桌面。
整合驗證覆蓋 Python 3.10–3.14 與既有 Windows/Linux/macOS CI。
coverage 沿用 `coverage run -m pytest` 與現有 floor；pytest11 改動後重新量測而不放寬 floor。
GUI 測試另驗證真實 Qt 生命週期；headless import 維持 Qt-free 與 optional dependency lazy。

實機結果附 backend、版本、輸入資料與限制。無法在本機驗證的平台可交付測試腳本與 CI job，
但該項保留待驗證狀態。任何修正都需證明先前錯誤已不再出現，不能只宣稱新增了測試。

## 6. 跨專案與環境

Jeffrey_RPA 使用這個工作樹的 editable install。動到它正在執行的輸入、截圖與座標模組前，
先確認 batch/bot 狀態；必要時以隔離 checkout 開發，不停止或改寫其正式批次。
下游驗證使用 `D:/Codes/AI_CONTEXT.md` 指定的 `test_gui_facade.py`、`test_gui_control.py`，
WebRunner 相關驗證另按其契約處理。不得把 `test_je_facade.py` 當成 AutoControl 契約唯一證據。
修改其他 repo 或安裝相依時按實際檔案／網路權限處理。

提交按階段只 stage 本階段檔案。發佈、推送或合併遵照專案分支流程，
不能讓尚未完成的平台改版以完成狀態進入發佈流程。

## 7. 官方參考

- [XDG RemoteDesktop](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)：session、ScreenCast 共用與 ConnectToEIS。
- [XDG InputCapture](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.InputCapture.html)：compositor 啟動、pointer barrier、裝置能力與版本探測。
- [MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)：tools/list、分頁與 listChanged；實作保持 server 目前協商版本的語意。
- [Android ADB](https://developer.android.com/tools/adb)：裝置指定、連線與 shell 工具的邊界。
- [Appium XCUITest capabilities](https://appium.github.io/appium-xcuitest-driver/latest/reference/capabilities/)：WDA 與可選擴充的設定及建置需求。

以上限制據官方文件；分階段替換、同步版本、GUI 布局與日誌格式是本專案提出的設計選擇。

# Progress

## Agent 電腦接管與任務自動化

`WIP` — **依使用者恢復要求繼續交付；個別原生／真機／24 小時驗收仍暫緩。**
個別原生／真機／24 小時驗收也維持暫緩，不能因恢復一般開發而一併啟動。
完整交付契約：`docs/superpowers/plans/2026-10-23-agent-runtime.md`。
以下僅列未完成的實作、設定與驗證步驟；本批收尾不代表 P0–P9 全部完成。
功能開發位置：`D:\Codes\AutoControlGUI\.worktrees\agent-runtime`，分支 `feat/agent-task-runtime`；
WebRunner 對應位置：`D:\Codes\WebRunner\.worktrees\agent-managed`，分支 `feat/managed-browser-sessions`。
正式工作樹尚待整合；恢復時先核對兩個功能工作樹與本清單，勿直接在正式環境續跑。
接續完成第 5 組 browser／remote reader 與第 6 組跨主機成果移交，
並核對第 4 組真實裝置控制／擷取來源、其餘實作及第 8 組交付核對。

1. **P4：瀏覽器與正式環境接合**
   - 選定正式服務專用 helper Python、AutoControl／WebRunner 套件版本與受管 Chromium 安裝；
     以已審閱的主機 profile 明列工具、來源與產物根目錄，再驗證正式服務載入該環境。
     隔離環境的依賴診斷不能代替實際瀏覽器啟動／原生證據。
   - 核對既有瀏覽器呼叫者各自的環境是否已安裝相容 `je_web_runner`。舊 bridge 依賴呼叫環境的
     SDK，不會自動使用受管 helper；缺套件時應保留明確失敗，不能退回其他瀏覽器引擎。
   - 正式變更前仍須安排主工作樹、既有 Jeffrey_RPA 批次與服務的部署／回復步驟；不能直接將
     功能工作樹當作已部署版本，也不能替換共用 `.venv` 或自動重啟正式服務。
   - 瀏覽器統一使用 WebRunner（`je_web_runner`），來源 `D:\Codes\WebRunner`。
     真實頁面驗收尚缺登入狀態、目前頁面身分、表單讀回、獨立 DOM 完成條件、來源限制、
     上／下載權限與摘要、非預期視窗／對話框、逾時／取消及 session 清理證據。

2. **P4／P2：四條流程的實際應用驗收**
   - 查詢／下載／歸檔：真實來源、完整下載、命名衝突、取消、摘要與獨立檔案清單驗證。
   - CSV／Excel 批次填表：資料驗證、逐筆新紀錄切換、讀回、提交前舊確認值拒絕、成功／失敗／
     待確認清單與中斷後人工審閱。
   - 跨應用欄位轉移：來源擷取、轉換、指定目的地填入、提交／儲存及獨立成果確認。
   - 工作區準備：指定程式／文件、視窗排列、就緒檢查、未知對話框與未儲存內容暫停。
   - 覆蓋外部 agent、本機模型及固定 skill 的完整路徑；模型停止或舊收據不能取代完成證據。

3. **P1／P7：跨平台桌面與真人接回**
   - Windows：補跨任務／helper 世代的持續真人活動及閒置來源，再驗證注入事件排除、鎖定、
     真人接回、明確恢復與閒置 60 秒條件。原生 HWND／PID、遮擋、縮放與輸入清理仍缺實測。
   - macOS、X11、Wayland：實作可信真人活動來源，接合授權／鎖定／閒置判定、觀察目標身分、
     視窗範圍輸入及自有 helper 隔離；補非 Windows 對話框／未儲存 gate。
     目前不能解除不支援平台的共用桌面拒絕保護。
   - Wayland 接既有改版 D1／D2：portal session 關閉／恢復、compositor 重啟、觀察擁有者 context、
     helper／半開交握回收與取消／停止生命週期，避免兩條實作各自接管相同原生資源。
   - 驗證相同實體桌面在不同 profile、資料庫、服務及 DAG 節點間仍只有一位輸入擁有者；
     未知 worker／按住輸入／清理失敗時不得移交或竊取租約。

4. **P7：Android／iOS 受管裝置**
   - 為 `utils/agent_runtime/android_adapter.py` 實作並審閱真實 `AndroidControlProvider`／
     `AndroidCommandLease` 來源；須有裝置端執行機制，在真人接回、取消／逾時後阻止舊寫入，
     並提供逐命令 ID／boot／epoch 相符的輸入釋放、遠端佇列清空與舊 writer 退出證據。
     主機 lock／context manager、結束本機 ADB helper、shell 返回或 Android 階段都不能替代。
     補可信真人活動、已按下輸入、閒置條件與全域監看器的即時審閱；沒有來源時保持拒絕就緒。
     提案／證據的 `input_authorized=false` 不得當作批准，只有完整前置拒絕證明此命令未呼叫輸入；
     返回／後置拒絕仍不授權重試或清除未知 journal。
     WDA 還須實作 `RemoteDeviceAdapter` 與同等來源；真實 provider／SDK 契約確認後才接
     `target_config.py`／`target_factory.py`。內部橋接與模擬裝置都不代表已可正式受管執行。
     在實際 SDK 重驗合併焦點擷取的六種順序／重複拒絕、原期限、ACK 前拒絕、begin 後取消／逾時、
     錯誤裝置／世代、撤權、真人接回，並確認原生診斷仍不含敏感參數；
     亦須驗證唯讀路徑禁止輸入與清理失敗隔離；不得重播、更換 helper 繞過或代送桌面釋放事件。
     數字 transport ID、shell-v2 的退出碼或本機 socket 結束都不足以證明裝置／輸入安全。
     為 `android_hierarchy.AndroidHierarchyReader` 接入真實、限 app／window 的來源與安全文字授權，
     核對 SDK／服務的身分、完整度、生命週期與不干擾其他無障礙擁有者的契約；不可直接貼上
     要求的 snapshot 當作來源證明，也不能默用會建立 UiAutomation 的 dump CLI 或重啟服務。
     無 reader 的 metadata、遮罩值、部分文字及 SDK import 成功均不能宣稱完整畫面／原生可用。
     補受保護輸入欄位值的有限比較／獨立驗證、豐富欄位狀態條件、Unicode／IME，以及旋轉／縮放／
     多顯示器、版本／OEM 格式核對；不能把有限 ASCII／現有單視窗解析當作完整裝置輸入支援。
   - 為 ADB／WDA 各自建立可信的實體裝置識別、舊 writer 退出與清理／世代證據來源；核對真實
     SDK 契約，證明新世代能使所有舊指令失效且不重播。沒有可信來源時維持拒絕恢復。
   - 部署時明定每台裝置唯一的權威服務與受保護資源位置。預設使用者目錄內的 OS lock 只協調
     同帳號的本機程序；跨作業系統帳號／主機須共用可信協調端，不能各自取得同一裝置。
   - 將現有 ACK／耐久 journal／未知副作用隔離測試延伸到實際 SDK 的重連、重試、app scope、
     跨資料庫競爭、權限撤銷及主機崩潰路徑；SDK 模擬通過後仍須另排解除暫緩的真機驗收。
   - 建立以裝置及 app 身分固定的主機 profile、有限工具集與 scope；接既有 ADB／WebDriverAgent
     路徑，不把任意 shell、主機或執行參數交給模型。
     接合前核對 SDK 的實際裝置身分、重連／重試與清理契約；ADB 不得誤啟動或終止共用 daemon，
     亦需遮蔽逾時／例外中的命令參數。WDA 未提供的世代／閒置保證不可自行假定。
   - 接合觀察版本、元素參照、app／裝置身分、敏感內容遮罩、動作後讀回與完成驗證。
   - 以實體裝置身分協調互斥，處理斷線、app 切換、連線／helper 世代及權限撤銷。
   - 遠端動作逾時或 ACK 遺失須保存未知副作用；本機 helper 結束不等於裝置停止。
     補清理確證、資源隔離／保留及具證據的人工恢復後，才可允許另一任務接管。
   - 加入服務／API／AC／MCP／REST／CLI／Builder／薄 GUI、能力診斷與無真機回歸，
     最後才安排已解除暫緩限制的真機驗收。

5. **P5／P9：中斷狀態恢復與技能驗收**
   - 設計登入／暫存欄位／視窗狀態的安全恢復策略；不能以歷史前綴證明新 session 的當前狀態。
   - 將經審閱的新任務流程延伸至實際登入／欄位／視窗狀態重建與四條應用流程驗收；為舊 capture／
     指標步驟提供可信新來源與語義轉換，不能把舊索引／座標或歷史欄位值直接移入新 session。
   - 補實際應用的語義錄製、參數化、候選修復、驗證 trial、人工接受／版本發布及執行中固定版本
     的完整驗收；持續拒絕沒有完整動作確認或獨立完成證據的試跑，不能僅憑舊收據發布。
   - 將唯讀完成審閱／驗證／發布延伸至 browser／remote target：補可信唯讀 reader，來源副作用與
     當前獨立條件須分別核對；缺少原瀏覽器 context 時不可新開頁面當作舊狀態，亦不可回退普通
     可操作 helper、重做最後動作或解除未知隔離來完成認證。原生／真機能力與驗收仍須分開確認。
   - 針對新增平台／裝置及恢復路徑重驗服務重啟、WorkQueue 去重、事件／排程重新授權、
     journal／history／產物關聯及 30 天保留／清理，不擴大既有權限。

6. **P8：多 agent／多機的剩餘接合**
   - 逐條稽核規劃、執行及驗證的權限邊界：規劃產生有限提案，執行重新授權，完成由獨立條件
     判定；補必要的角色／跨節點證據與提示注入回歸。
   - 為實際主機配置受保護的 runtime 端點、背景派送、主機憑證與相容完成契約；明確記錄遠端
     目錄／目標設定、部署／回復方法。受管任務 DAG 不會自動部署遠端服務。
   - 設計跨主機成果移交：明列讀寫權限、來源身分、摘要與目的地發布，不能以本機路徑當遠端
     檔案證據，不能轉送本機 principal／使用者資料庫路徑／來源 witness。
     須包含遠端任務證據的保留／移交契約；來源端保留未決批次不能自動延長目的端的 30 天保留期，
     目的端證據到期或失聯須維持不可採認，不能以來源端協調收據取代獨立完成證據。
   - 實際多機驗證斷線／晚到回覆、主機重啟、憑證撤銷／變更、協調端中斷及同資源序列／
     獨立資源並行；未知清理不得讓下游成功或搶走遠端控制權。

7. **P3／P6／P7：能力、模型及共用介面驗證**
   - 補桌面權限、平台／裝置連線、來源／目標就緒與原生證據的診斷；區分未支援、缺依賴、
     未授權、未探測、未記錄與實測成功，不把 Python 套件匯入成功當原生可用。
   - 為自訂／外部 target 補經審閱的語義觀察與遮罩覆蓋契約；沒有能力旗標的舊 target 仍沿用
     既有判定，不能因此宣稱已證明完整畫面或遮罩內容的不存在。深化部分證據的計數／狀態／
     變動判定與受保護欄位比較，目前缺少充分證據時仍為未知。
   - 在明確配置且已安裝的本機 Ollama 工具／視覺模型上補端到端證據：模型不符、拒絕連線、
     逾時、取消、預算與完成驗證；不可自動下載或切換外部服務。
   - 新增／深化功能須同步公開 API、命令目錄、MCP／REST／CLI／Builder、薄 GUI Actions 及語系，
     並重驗匿名／具名權限、來源限制、GUI 關閉／重開、服務獨立生命週期與跨 session 隔離。

8. **P0–P9 最終交付核對與檢查**
   - 每條交付契約整理實作、無頭回歸與原生／真機證據對照；補新平台／多機／恢復情境的漏洞，
     區分已實作、尚缺實作與只缺實測，不能用模擬目標取代原生驗收。
   - 於最後固定提交重跑完整 headless 與 `coverage run -m pytest`、跨功能／故障恢復回歸；
     目前較早固定版本的全套證據不能冒充最新工作樹結果。
     `WIP`：完整套件曾在 `test_dag_managed_loopback.py::test_distinct_targets_run_concurrently_with_destination_verification`
     偶發提交 HTTP 409，另一節點等待後限流；該次為 5,391 passed／17 skipped／1 failed。
     單獨 20 次與整檔 60 次回歸均未重現；仍須取得最初拒絕原因，不能以後續通過宣稱已修復。
     `WIP`：第 71 階段全套在
     `test_agent_completion_handoff_security.py::test_matching_grant_digest_cannot_make_invalid_private_renewal_authoritative[completion_task-named_dag]`
     的 fixture 首次 `observe` 發生 `native helper bootstrap deadline exhausted`；
     該次為 15,235 passed／77 skipped／1 setup error，案例本體未執行。
     須收集自有 helper 啟動時間與逾時前堆疊以釐清原因；不放寬 15 秒期限、不重試或略過錯誤，
     單獨重跑通過與後續全套通過都不能代表此啟動問題已修復。
     `WIP`：pytest 的 atexit `cleanup_dead_symlinks` 對共用暫存連結
     `C:\Users\USER\AppData\Local\Temp\pytest-of-USER\pytest-current` 發生
     `PermissionError: [WinError 5]`；已核對為目錄符號連結，讀取連結目標亦遭相同錯誤。
     仍須查明權限／生命週期及清理契約，避免影響其他 pytest 執行者。不直接刪除共用連結或
     修改共用 `.venv`；測試本體退出碼 0 不代表暫存清理已修復。
   - 重跑三平台型別、Ruff／Bandit、檔案／函式／複雜度及文件計數，檢查新增 lint 問題；
     AutoControl 全套 Pylint 仍有既有問題，不能把局部模組通過當全套零問題。
     WebRunner 既有全套 mypy／flake8／嚴格 Sphinx 債務見其 `Progress.md` #23，不能標示全綠。
   - 完成最終 wheel／隔離安裝／依賴一致性、嚴格文件建置，以及三語 README、Sphinx、架構、
     範例與公開契約一致性核對；避免舊說明把已支援的 browser profile 說成不支援。
     初次隔離安裝驗證留下的自有暫存目錄
     `C:\Users\USER\AppData\Local\Temp\autocontrol-wheel-stage72-mbpvem9h` 尚未清理；
     刪除操作遭自動審核拒絕（僅回覆 `blocked by policy`），保持原樣，不改用其他工具繞過。
   - 功能分支到正式環境的整合／部署仍未執行；正式工作樹與既有批次須保持可回復。

**仍暫緩的驗收**：原生桌面、實際瀏覽器與 Android／iOS 真機驗收；WebRunner `Progress.md` #20
的原生雙向 bridge 驗收，以及 #21 的完整 24 小時驗收。只有使用者明確恢復後才可啟動，24 小時
驗收須用新的 attempt 目錄與固定來源，短測／中斷紀錄不能代替完整結果。
**範圍限制**：不新增付費依賴及收費功能；保持瀏覽器統一走 `je_web_runner`。
本輪執行全程背景，不切換前景、不移動使用者滑鼠或注入桌面輸入。Tripo 使用專用持久登入設定檔、
螢幕外瀏覽器及 DOM 操作；AutoControlGUI 僅作必要唯讀觀測。登入狀態與 DOM 結果須分別驗證。

## 跨平台與 GUI 全面改版

`TODO` — 重設 UI、重寫並優化 GUI、修正 Wayland 與函式庫問題、跨機器同步、
深化全套 mypy、補齊 iOS／Android、自愈定位器量測、動作日誌 codegen、
完整範例與文件。涉及 `gui/`、`linux_wayland/`、`android/`、`ios/`、
`utils/{config_sync,remote_desktop,mcp_server,self_healing,codegen,executor}/` 與型別／文件驗證。
核准設計：[跨平台自動化與 GUI 改版](docs/superpowers/specs/2026-10-02-platform-gui-modernization-design.md)。
實作計畫：[分階段交付計畫](docs/superpowers/plans/2026-10-02-modernization-index.md)，待審閱。
現有 `[Answer]` 決策沿用。

`TODO` — 真機與付費 API 驗收暫緩，待明確恢復後執行；其餘目前缺環境的實驗先略過，相關項目保留未驗證。

`WIP` — 改版仍缺以下內容；原生平台與正式環境驗收缺口另列於後。
計畫 D1 仍缺 portal session 關閉／恢復、compositor 重啟的狀態與原生驗收、
擷取結果與擁有者 context 的接合，以及原生 session 的重試／取消／停止控制。
D2 仍缺 helper 隔離與半開交握資源回收；D3 的錄製／全域停止／Windows 原生崩潰證據仍缺，詳見計畫與下方生命週期待辦。
計畫 E（Android／iOS）、H（型別深化與總驗收）尚未開始。F 還缺：

- **Remote Desktop 與 Script Builder 仍在啟動時建立**（預設開啟），啟動時間 2.6–2.7 秒裡大半是它們與門面匯入。
- **F1 的遺留面板釋放**：擁有者直接建立的核心表單與 Remote Desktop 在關閉時仍保留 widget；需隨 F3 遷移直接控制項引用、執行中工作與連線生命週期，再啟用銷毀。
- **F2 其餘**：計畫指定的 `WorkspaceShell` 介面、右側可收合詳情，以及各面板的空白／錯誤／permission states 還沒全面交付。
- **F3** 還缺共用 `TaskController` 接入其餘面板、backend timeout／cancel 傳遞與關閉生命週期遷移，
  以及 `webrtc_panel.py` 的 dialog／worker／session 拆分。
- **F4**（啟動／記憶體基準、mixed-DPI、功能對等測試）尚未開始。
- **F3 Windows 原生釋放驗收**：`test/unit_test/headless/test_remote_desktop_host_id.py` 的 freed-thread-state abort 尚缺 Windows 原生堆疊與獨立根因確認。

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
行數以 `len(text.splitlines())` 量測；檔案縮短時，上限跟著往下走。
**這張表現在有測試在守**：`test/unit_test/headless/test_file_length_budget.py` 比對本表與樹，
超標未列、列上的檔案變長、或已經縮到線內卻還留著的列，都會紅。

| 檔案 | 行數 | 為何還沒拆 |
| --- | ---: | --- |
| `utils/mcp_server/tools/_handlers_executor_bridge.py` | 1,429 | 純委派函式（函式內匯入後立即轉呼叫，沒有分支），不適用 flat data tables 豁免。需先定義領域邊界再拆分。 |
| `gui/remote_desktop/webrtc_panel.py` | 2,488 | 單一 Qt 面板,但已含連線、監視器選擇、頻寬自適應、麥克風、錄影五組互動狀態。應拆成 panel + 各控制器。 |
| `utils/accessibility/backends/windows_backend.py` | 805 | 剩餘 UIA COM 生命週期管理仍需保留 `CoInitialize`／介面釋放的配對；拆分前須建立這些配對的回歸。 |

**本質豁免（flat data tables）**：`utils/mcp_server/tools/_factories.py`、
`utils/executor/action_executor.py`、`gui/script_builder/command_schema.py`、
`je_auto_control/__init__.py` 與
`gui/language_wrapper/{english,japanese,traditional_chinese,simplified_chinese}.py` 語系字串表。

## Windows arm64:裝得起來了，但少了影像與加密

`TODO` — 上游仍未發 wheel（`opencv-python`、`cryptography`），但安裝本身不再是卡點

### 還沒有答案的：Windows arm64 上這些功能不能用

裝得起來不等於功能齊。該平台上以下四組會拋帶提示的錯誤，而不是默默失效：

| 功能 | 缺的是 | 錯誤形式 |
| --- | --- | --- |
| 影像比對、截圖轉 BGR、螢幕錄影 | `opencv-python`／`je_open_cv` | `utils/cv2_utils/optional.py` 的 `require_cv2()`／`require_je_open_cv()` 拋 `RuntimeError` |
| 動作檔加密與 Ed25519 簽章（`action_signing`） | `cryptography` | 拋 `CryptographyUnavailableError`（也是 `RuntimeError`；HMAC 簽章不受影響） |
| 秘密金庫（`${secrets.NAME}`） | `cryptography` | 同上 |
| ACME／TLS 發證、加密錄影 | `cryptography` | 模組層 `ImportError` 轉述（照 `webrtc_transport` 慣例） |

`BLOCKED` — 仍需相容的上游 wheel：`opencv-python>=4.8,<6`、
`cryptography>=50.0.0` 與 `aiortc` 的傳遞相依 `google-crc32c`。
不能為相容性降低 cryptography 安全下限。上游提供相容版本後，需重驗安裝與功能，
再移除 `pyproject.toml` 中相應平台標記並同步更新
`test/unit_test/headless/test_arm64_dependency_markers.py`。

重驗指令（不需要 arm64 機器，也不需要 runner）：

```bash
pip install --dry-run --only-binary=:all: --platform win_arm64 --python-version 3.12 --target /tmp/probe 'opencv-python>=4.8,<6' 'cryptography>=50.0.0'
```

重驗通過後，需調整相應環境標記與 `test_arm64_dependency_markers.py`，保留安全下限。

注意一個驗證上的陷阱：**`pip --platform` 不會換掉 marker 的評估環境**，
它只影響 wheel 相容性標籤，所以拿本機做 `--dry-run` **驗不到標記的效果**（兩個
套件依舊會被要求）。能驗的是兩件事：直接評估 marker（上面那支測試在做的），
以及 `windows-11-arm` 那一格自己綠。

## Wayland 生命週期與驗收

`TODO` — 下列上游行為與原生桌面互動仍需驗證。

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

---

## 輸入、視窗與擷取修正：還沒在真的桌面與 Jeffrey_RPA 上驗過

`TODO` — 原生桌面與正式批次升級前的行為驗收暫緩。

- **正式批次升級前的桌面行為驗收**：需核對 `_gui_control.py` 對下列行為的實際依賴：
  `write()` 大寫與 `is_shift` 在 Windows／X11 生效、`"\r\n"` 只按一次 Enter、`mouse_scroll` 預設方向改為 `scroll_up`
  （X11／Wayland 上 `mouse_scroll(3)` 由往下變往上）、小數座標四捨五入、`focus_window` 在 Windows 沒拿到前景會丟例外、
  `list_windows` 不再列出 DWM cloak 與零面積視窗、`post_key` 對可列印字元只送 `WM_CHAR`。
- **混合 DPI 座標與樣板**：需實測各螢幕上的舊版座標、`screen_region`、視窗版面與樣板，
  包含縮放不同的副螢幕、負原點與多螢幕排列；必要時重新錄製，不能以推導代替驗收。
- **舊版存的視窗版面檔要重存**：`save_window_layout` 改存 `GetWindowRect`，舊檔還原會偏右 7 px、縮小 14×7 px。
- **真的 Win32 行為沒有實測**：`post_key` 在真的編輯框是否只出現一個字、DWM cloak 過濾掉的是哪些視窗、
  `MoveWindow` 對最大化視窗與另一個 DPI 的螢幕是否能原樣還原，都只用假的 `user32` 驗過。
- **X11／Wayland**：大寫與 Shift 標點的判斷假設 `keysym_to_keycode` 把大寫字母對到小寫的 keycode，沒有對著 X server 跑過。

**還沒決定的小事**：Windows 鍵表沒有 `slash` 這個名字。`plus`／`minus`／`comma`／`period` 與 `oem_1`…`oem_8` 都有，
但鍵表的註解刻意不替 `oem_*` 取好讀的別名，因為它們隨鍵盤配置而變（`oem_2` 只有在美式配置上是 `/`）。
要加的話是 `wrapper/_platform_windows.py` 的 `keyboard_key_aliases` 一行。

---

## macOS 的修正：CI 驗到一半，其餘要一台真的 Mac

`TODO` — 要一台真的 Mac（Retina，最好接第二個螢幕）

還沒驗的：

- **應用程式是否把 `click_mouse(clicks=2)` 認成雙擊**：只確認了欄位的值，沒有對真的應用程式送事件。
- **`grab_logical`**（`utils/monitor_layout/macos_frame.py`，點座標、逐螢幕擷取後拼接）完全沒在 macOS 跑過。三個假設要實機確認：
  `screencapture -R` 接受含負值的全域點座標、Pillow 的 `scale_down=True` 給出點尺寸的影像、`CGDisplayBounds` 與 Quartz 滑鼠事件同一個座標空間。
  每一格要為每個螢幕各開一次 `screencapture`。CI 的 runner 是 1x 單螢幕，測不到 Retina 與副螢幕。
- **`list_windows` 在真的桌面上的成本與誤列**：沒加 AX 逾時，沒回應的 app 會拖慢列出；同一行程裡與最小化視窗同原點或同標題的螢幕外輔助視窗可能被誤列。

---

## 這一輪修正留下的後續

`TODO` — 下列整合、安全與平台驗證仍未完成。

- **Intel Mac 安裝要編譯 `cryptography`**：下限拉到 50 之後 `macosx_10_9_x86_64` 沒有 wheel（探測：最新只到 48.0.1），
  `pip install je_auto_control` 在 Intel Mac 需要 Rust 工具鏈。沒有在 Intel Mac 上實際編過。
- **簽章分離擋不住能寫檔的人**：能執行寫檔指令（shell、檔案類指令）的人仍能換掉公鑰檔本身，保護那個檔是作業系統權限的事；
  私鑰是未加密的 PEM（0600，Windows 上沒驗權限位元），沒有通行碼選項；遷移模式開著時 HMAC 簽章會被接受。
  強制簽章經 socket／REST／MCP 的端到端沒有跑過，覆蓋的是共用的 `read_executable_action_json` 與指令本身。
- **RBAC**（`JE_AUTOCONTROL_RBAC_USERS`，預設關閉）：
  - 使用者只能用 Python 管（`UserStore.add_user/set_role/rotate_token/remove_user`），沒有 `AC_*`、CLI 或 GUI；`Capability.MANAGE_USERS` 因此沒有任何路由或工具對應。
  - viewer 的其餘影像檔案型、mobile 與外掛唯讀工具仍需全面盤點 capability；自製工具仍依提示採預設分類。
  - 沒對真的 client（Claude Desktop、VS Code、內建 dashboard）試過；SSE、無狀態與 `subscriptions/listen` 路徑、TLS 加 RBAC 沒有測試。
- **MCP 路徑根目錄**（`JE_AUTOCONTROL_MCP_PATH_ROOTS`，預設關閉）管不到的參數：執行動作清單的工具、
  有時才是路徑的參數（`ac_open_path`／`ac_plan_open`／`ac_file_association`／`ac_act_in_view` 的 `target`，`ac_launch_process`／`ac_shell` 的 `argv`／`command`）、
  `ac_handle_file_dialog` 的 `path`、自由格式物件裡的路徑（`ac_run_suite` 的 `spec`、`ac_run_dag` 的 `definition`、`ac_assert_all` 的 `specs`）、沒標註的外掛工具。
  檔案 symlink 的跳脫在這台機器上建不出來（只跑了目錄 junction）；POSIX 的 `:` 分隔與 `~` 沒在 Linux／macOS 跑。
  `roots/list` 來的根目錄要另外開 `JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT` 才算數——這是實作時定的，請維護者確認。
- **USB passthrough**：client 仍在 `reply_timeout_s`（10 秒）放棄，即使呼叫端要的 `timeout_ms` 更長（host 接受到 60 秒）；
  對新 host 逾時已經無害，對舊 host 正常使用就會進入「需重連」。通道層的 ERROR（passthrough 關閉、bad frame、host 沒有 session）在 session 之前送出、不帶請求編號，
  呼叫仍是等到逾時。沒對真的舊版 host、真的 WebRTC 通道或真的 USB 裝置跑過。
- **變數範圍**：free-threaded 原生執行緒繼承與同時存取範圍的行為尚未實測。
- **遠端桌面的擁有者模型**：Quick Connect 沒有狀態列，它的連線被取代時視窗只是關掉；主機的 Stop 會停任何擁有者開的 host（刻意的）；
  只用假的 viewer／host 測過，真的 viewer 被擠掉時會不會觸發 `on_error` 而多跳一個警告框，沒看過。
- **套件閘門**：`execute_action` 會先驗完所有指令名稱才執行，所以「載入套件」與「用它的指令」寫在同一份清單裡會以 unknown command 失敗，與閘門無關（既有限制）。
  repo 根目錄的舊範例 `AutoControl/keyword/keyword1.json` 載入 `time`，現在預設會被拒絕。
- **`pytest --cov` 沒有重新量過**：進入點搬到 `je_auto_control_pytest` 之後，它是否還少算，未知；規則仍是 `coverage run -m pytest`。
- **快到 750 行上限的檔案**：`utils/usb/passthrough/viewer_client.py`（748）、`gui/remote_desktop/connection_screen.py`（729）、
  `utils/mcp_server/server.py`（734）、`utils/mcp_server/http_transport.py`（727）、`utils/agent/backends/anthropic_computer_use.py`（723）——下一次要加東西就得先拆。

---

## Computer use 的預設還是 beta 的 `computer_20251124`

`TODO` — 在 `claude-opus-5`（兩種形式都接受）上實測 GA toolset 後，把它設成所有模型的預設

驗收入口：`utils/agent/backends/anthropic_computer_use.py` 與 `_computer_toolset.py`。
需驗證多呼叫回覆、toolset 名稱、截圖尺寸、座標換算與 zoom；未取得真實 API 證據前，
其他模型的預設切換仍待完成。

---

## libei 半開交握的資源隔離尚未完成

`TODO` — D2 helper 隔離；不能直接移除 `linux_wayland/libei.py::_teardown` 的半開保護。

需依 D2 計畫把原生配置、portal／交握、事件送出與 teardown 放進擁有的 helper，
補上有界 IPC、request ID、逾時與取消，以及 parent close／reap。
半開交握失敗仍會留下 context／fd；直接重複建立 backend 可能重複累積，
需驗證 helper 結束後資源可回收，且取消不影響其他擁有者。
`docker/libei_verify.py` 與 `docker/eis_verify.py` 保留原生故障／成功邊界檢查；
裝置暫停與序號回讀、真實合成器權限流程仍待對應環境驗證。

---

## Agent 的歷史壓縮還沒對真的 API 跑過

`TODO` — 需要付費實機跑一次多步驟任務；離線測試只驗得到請求的形狀

需驗證 `utils/agent/backends/anthropic.py`、`anthropic_computer_use.py` 的 beta／GA 路徑，
以及 OpenAI 歷史剪裁在真實 API 上的行為：

- 重開的歷史在強制 thinking 綁定的帳號（Opus 5.5／Fable 5.1）上是否被接受。
- 模型只憑摘要能不能接著做——上限是 3，大約每 3 張截圖就壓縮一次，摘要最多列最新 60 個動作、每個截到 240 字元。
- 真的桌面 PNG 的請求大小離 32 MB 多遠。
- 兩個後端都沒送 `cache_control`，所以現在本來就沒有 prompt cache；要開的話是另一個請求形狀的改動。

---

## `test_usb_acl_prompt.py` 讓 Python 3.10 的 headless 測試間歇 segfault

`TODO` — `test/unit_test/headless/test_usb_acl_prompt.py::test_bridge_remember_persists_acl_rule`
在 Python 3.10 的 Linux／macOS `coverage run -m pytest` 中仍有間歇 SIGSEGV（exit 139）紀錄。
需在對應環境開啟 `faulthandler` 重跑並定位原生呼叫；單次重跑通過不足以證明已修復。

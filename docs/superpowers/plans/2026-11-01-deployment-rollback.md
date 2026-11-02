# Agent runtime 正式環境部署與回復計畫（P4／P8）

狀態：**計畫，未執行**。本文件只列步驟與檢查，不授權任何部署動作；每一節的「待決定」需維護者
明確批准後才能進行。交付契約見 `2026-10-23-agent-runtime.md`，未完成項目見 `Progress.md` 第 1、6 項。

## 1. 現況（2026-11-01 實測）

| 元件 | 位置 | 誰在使用 | 部署的意義 |
| --- | --- | --- | --- |
| AutoControl 主工作樹 | `D:\Codes\AutoControlGUI`，本機 `dev` | Jeffrey_RPA 以 editable install 直接載入；`pytest11` 也從這裡載入 | 主工作樹的檔案一變就等於部署到 Jeffrey_RPA |
| 功能工作樹 | `.worktrees\agent-runtime`，`feat/agent-task-runtime` | 只有開發 | 遠端 `dev` 由這裡推送；主工作樹本機 `dev` 目前落後 |
| 遠端 `dev` | GitHub | `dev.yml` 測試通過後發布 `je_auto_control_dev` | 發布套件，不改任何本機環境 |
| 共用 `.venv` | `D:\Codes\AutoControlGUI\.venv` | 主工作樹、測試、其他工具 | 不得替換；依賴變更須先比對 |
| Jeffrey_RPA 批次 | `D:\Codes\Jeffrey_RPA` | Discord bot、`webrunner_novelai.py` 等長時間程序 | 執行中不得改它載入的模組 |
| Agent runtime 服務 | 每位使用者明確啟動的隱藏本機程序；`agent_runtime.json` | GUI／API／AC／MCP／REST／CLI | 程式更新後要停止再重新明確啟動 |
| 瀏覽器 helper | 目前沒有正式 helper Python；stage104 有隔離候選 | 受管 browser target | 需要選定專用直譯器與套件鎖 |
| 受管 Chromium | 尚未安裝正式版本 | WebRunner 專用持久登入設定檔 | 需要選定版本與安裝位置 |

主工作樹另有其他 session 尚未提交的修改（例如 `Progress.md`）；部署前必須先處理，不能 `git stash`
（stash 堆疊與所有工作樹共用），也不能覆蓋他人的未提交工作。

## 2. 部署前檢查（每次都做，任一不符就停止）

1. **來源固定**：記下要部署的提交雜湊 `T` 與目前主工作樹的提交雜湊 `P`（回復目標）；
   `dev.yml` 對 `T` 的四個方格全部通過。只看版本號不算數。
2. **Jeffrey_RPA 未在執行**：讀 `D:\Codes\Jeffrey_RPA\webrunner.pid` 的數字，用
   `Get-CimInstance Win32_Process -Filter "ProcessId=<pid>"` 確認程序不存在（或已由維護者停止），
   並比對 `webrunner.log` 的最後寫入時間。執行中就停止，不嘗試「趁空檔」部署。
3. **沒有進行中的受管任務**：`agent-task list` 沒有 running／pausing／cancelling 任務；
   `agent-task readiness` 的結果存檔，作為部署前後比對基準。
4. **主工作樹乾淨**：`git status` 只剩已知的未追蹤檔；其他 session 的未提交修改已由其擁有者提交或確認可保留。
   通知同儕 session 部署時間。
5. **依賴差異**：比對 `T` 與 `P` 的 `pyproject.toml`、`dev.toml`；若依賴有變，先列出共用 `.venv`
   要變動的套件與版本，經批准後才安裝（依 2026-10-26 指示：安裝前比對已安裝版本、來源與待安裝內容）。
6. **私有根與資料庫相容**：記錄 agent runtime 使用者目錄下任務資料庫、證據快取與私有根的位置與雜湊；
   部署新版本不搬移、不刪除它們。

## 3. 部署步驟：主工作樹（AutoControl 本身）

1. 完成第 2 節全部檢查。
2. `agent-task stop` 停止服務；有活動中的輸入擁有者時服務會拒絕關閉，此時停止並回報，不強制結束。
3. 主工作樹 `git merge --ff-only <T>`（只允許快轉；不能快轉代表本機有分歧，停止並回報）。
4. 驗證：
   - `import je_auto_control` 不載入 PySide6；
   - 在 Jeffrey_RPA 根目錄執行
     `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test/test_je_facade.py`（唯讀）；
   - `agent-task readiness` 與部署前的存檔比對，差異須能由 `T` 的變更解釋。
5. 需要服務時才由使用者明確 `agent-task start`；部署本身不自動啟動服務。
6. 在 `docs/updates/` 記錄 `T`、`P`、檢查結果與驗證輸出。

## 4. 回復步驟：主工作樹

1. 先停止服務並取得輸入退場確證（`agent-task stop` 成功；沒有活動輸入擁有者）。
2. **不重播、不清除**：不明結果的 journal 與隔離中的任務保持原樣，不能為了回復而重播已送出的副作用。
3. 新版建立、舊版不認識的私有檔案（例如新版私有根下的快取）必須從舊版會掃描的任務根目錄中排除；
   舊版不能沿用新版的資料庫或快取。若無法證明舊版不會讀到它們，停止並交維護者審閱，不直接回復。
4. 主工作樹回到 `P`。這一步會改寫工作樹檔案，所以先確認沒有他人的未提交修改（同第 2 節第 4 點）。
   **待決定**：回復方式由維護者選定，例如把本機 `dev` 重設到 `P`，或建立指向 `P` 的回復分支並切換過去；
   兩者都不能遺失未提交的工作。
5. 重跑第 3 節第 4 點的驗證，並比對來源／成品雜湊與 `P` 一致。

## 5. 瀏覽器 helper 與受管 Chromium（P4）

**待決定**（維護者）：
- helper 專用 Python 的位置與版本（不得使用共用 `.venv`）；
- AutoControl／WebRunner 套件版本（以雜湊鎖固定，例：stage104 的隔離候選與其套件鎖）；
- 受管 Chromium 的版本與安裝位置；
- 主機 profile：允許的工具、來源、產物根目錄。

步驟（批准後）：
1. 在全新目錄建立 helper 直譯器，依鎖安裝並逐檔比對 wheel／sdist 與安裝結果的雜湊。
2. 以 `AC_agent_target` 註冊瀏覽器 profile（`helper_python` 指向該直譯器），`agent-task target probe`
   只檢查依賴，不啟動瀏覽器。
3. 依 Progress 第 1 項完成真實頁面驗收前，profile 保持停用；Python 依賴與介面通過不能代替受管 Chromium、
   實際登入／頁面與原生證據。
4. 回復：停用 profile、保留 helper 目錄供審閱；不刪除登入設定檔。

既有瀏覽器呼叫者（舊 bridge）依賴各自呼叫環境的 `je_web_runner`，不會自動改用受管 helper；
缺套件時保留明確失敗，不退回其他瀏覽器引擎。

## 6. 多主機（P8）

**待決定**（維護者）：參與的主機、每台的 runtime 目錄與受保護端點、主機憑證的發放與撤銷方式、
每台主機唯一的權威服務與受保護資源位置。

步驟（批准後）：
1. 每台主機各自依第 2～3 節部署；受管任務 DAG **不會**自動部署遠端服務。
2. 在協調端以 `AC_admin_*`／主機名冊登記遠端主機；只轉送受審閱的工作，不轉送本機權限。
3. 依 Progress 第 6 項做兩／三主機故障矩陣（斷線、晚回覆、重啟、憑證撤銷、協調端中斷）。
4. 回復：先在協調端停用主機，再於各主機依第 4 節回復；未知清理不得讓下游成功或移交遠端控制權。

## 7. 本計畫不做的事

- 不替換共用 `.venv`、不自動重啟正式服務、不在 Jeffrey_RPA 執行中改動它載入的模組。
- 不把功能工作樹當作已部署版本；部署只以主工作樹快轉到經 CI 驗證的提交為準。
- 不啟動暫緩中的原生桌面、實際瀏覽器、真機或 24 小時驗收。

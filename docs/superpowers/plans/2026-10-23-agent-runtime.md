# Agent 電腦接管與任務自動化交付契約

## 已確認需求

全平台、遠端多機、外部與內建 agent；範圍內自主執行，預授權排程/事件可自動啟動。
新增流程使用本機或自架資源，不新增付費依賴及收費功能。正式批次工作樹不直接修改。
本輪開發／工具／驗證全程背景，不切換前景、不移動使用者滑鼠、不注入桌面鍵盤／滑鼠輸入。
Tripo 網頁操作使用 je_web_runner 的專用持久登入設定檔、螢幕外瀏覽器與 DOM；AutoControlGUI
僅作必要唯讀觀測。除非使用者明確要求，不顯示登入視窗；DOM 結果、前景／滑鼠觀測與登入狀態分別核實。

既有及新增的瀏覽器自動化統一由 WebRunner（套件名稱 `je_web_runner`）提供；本機開發來源為
`D:\Codes\WebRunner`。AutoControlGUI 沿用其 API／橋接，不另建獨立的瀏覽器自動化引擎。

## 交付順序

| 階段 | 契約 |
| --- | --- |
| P0 | 共用 raw-result 分派、授權、取消、journal、交集式巢狀 guard。 |
| P1 | 每個互動桌面/裝置一個輸入擁有者，舊世代拒絕；人工接回、暫停/取消、清理後移交。 |
| P2 | 有版本的觀察、目標身分、動作後驗證；完成只由明確條件判定；未知不成功。 |
| P3 | Ollama 本機 HTTP 工具/視覺 adapter，明確指定已安裝模型；不下載、不切外部服務。 |
| P4 | 應用與視窗、檔案、瀏覽器、表單、文件、剪貼簿、已知對話框；四條完整流程。 |
| P5 | SQLite 狀態、WorkQueue 派送、journal/history 連結、逐筆恢復、事件去重與重新授權。 |
| P6 | 服務共用 GUI/API/AC/MCP/REST/CLI；Actions menu；session 隔離；關閉視圖不取消服務任務。 |
| P7 | Windows、macOS、X11、Wayland、Android、iOS；接既有 D/E，能力明確標示、原生證據分列。 |
| P8 | 規劃/執行/驗證角色；同桌面輸入序列化，不同裝置或資料工作可並行；遠端沿用 DAG。 |
| P9 | 語義錄製、參數化、版本化技能；修復候選驗證/接受後發布，執行中版本固定。 |

## 核心介面

`AgentTaskSpec` 包含 goal、inputs、mode、target、allowed tools、roots、success criteria 與 budgets。
`AgentObservation` 的索引只在 observation ID 內有效，附時間與幾何；狀態變更後重新觀察。
`AgentActionResult` 區分已確認與不明副作用；`AgentTaskResult` 包含完成條件報告與產物。

公開操作：submit/get/list/pause/resume/cancel/observe/act/finish_agent_task。
同步提供 AC_agent_task_*、MCP、REST、CLI agent-task 與薄 GUI。
單一主機 service 協調受管工作；匯入時不啟動服務或取得原生權限。

狀態：queued/running/pausing/paused/waiting_user/recovering/verifying/cancelling/
succeeded/failed/cancelled/timed_out。恢復先授權與觀察，絕不盲目重播已送出但結果不明的副作用。

## 首批流程

1. 查詢、下載、完成檢查、命名歸檔及檔案清單。
2. CSV/Excel 驗證、逐筆填表、讀回、成功/失敗/待確認清單。
3. 跨應用欄位擷取、轉換、填入、儲存驗證及成果。
4. 指定程式/文件啟動、視窗排列、就緒檢查；未儲存內容暫停。

## 不變式與預設

模型停止不代表成功。所有新任務須具完成條件。外部資料不能擴大授權。
一般工具集不含任意 shell、套件載入或遞迴 agent；授權撤銷立即阻止下一動作。
預設 25 步/300 秒/兩次暫時重試；自動啟動需已解鎖與閒置 60 秒。
真人接回後明確恢復。影像預設只在記憶體，產物遮罩後才可持久化。
任務保留 30 天；不擁有的 journal 不隨任務清除。GUI 關閉只解除視圖訂閱。
控制權只保證參與 runtime 的受管工作，不宣稱為任意行程沙箱。

## 驗證

每階段先以 fake/固定畫面重現缺口，再實作與回歸；測試不操作使用者桌面。
涵蓋多行程競爭/失效 worker/取消、過期觀察/座標、假完成、送出前後崩潰與未知結果、
權限撤銷/巢狀繞過/提示注入、模型錯誤、GUI 釋放與四條完整流程。
原生桌面/真機驗收仍暫緩，未有證據的能力保持未驗證。
每階段更新型別、三語 README、Sphinx、架構、Progress、updates 與相容性紀錄，逐檔提交。

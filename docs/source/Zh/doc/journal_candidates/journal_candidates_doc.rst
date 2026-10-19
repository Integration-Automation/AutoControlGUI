從日誌產生候選腳本
==================

從明確選取的一次結構化動作日誌執行，產生可審閱的 Python、pytest 或 Robot 候選。
產碼不重播動作、不截圖，也不呼叫模型。靜態檢查成功與原生操作是否成功、外部相依是否可用分開呈現。

Python API
----------

實驗性 API 回傳 ``CandidateScript``，包含 ``code``、``actions``、``manifest``、
``warnings`` 與 ``observed_path_only``；``to_dict()`` 回傳獨立的 JSON 審閱資料::

    from pathlib import Path
    from je_auto_control import generate_candidate_from_log, write_candidate_archive

    candidate = generate_candidate_from_log(
        Path("run.jsonl"), run_id="selected-run",
        target="pytest", style="actions",
    )
    print(candidate.manifest["source_sha256"])
    print(candidate.warnings)
    write_candidate_archive(candidate, "candidate-review.zip")

``target`` 支援 ``pytest``（預設）、``python``、``robot``；``style`` 支援
``actions``（預設）與 ``calls``。兩個函式均可選填 ``observer``、``path_policy``。
``run_id`` 必須是明確的非空字串，不自動猜測執行。無效來源或生命週期資料會拋出
``CandidateGenerationError``；檔案與路徑政策錯誤正常傳遞。

``python -m examples.journal_candidates`` 只使用合成觀察與暫存檔案，驗證三種目標。

選取規則與忠實度
----------------

所有候選均為 ``observed_path_only=True``。日誌能證明已觀察資料，不能證明整個預期流程、
未來分支或外部狀態。

* 整份有界快照均驗證 wire schema、重複 JSON key 與追加順序，再針對所選 run 檢查生命週期與命令。
  開始／完成輸入變更、重複完成、parent 循環或無效涵蓋範圍均拒絕。
  尚未提交的最後片段會忽略並明確標示。
* 開始／完成快照整合為一次呼叫。只提出已成功完成的根步驟；失敗、取消、跳過、乾跑與
  未完成根步驟會連同子步驟排除。只有完成紀錄時會標示來源不完整。
* 有效的已記錄 loop／branch／parallel／retry 輸入保持原樣，觀察到的子步驟由父來源涵蓋，
  不重複展開迭代或嘗試。只有來源比對能證明時才列出重試邊界，否則保持未知。
  原始已記錄來源可包含未執行的分支輸入，但不捏造其他分支。
* 順序控制來源不足時，成功的已觀察子步驟可形成有明確標記的已觀察路徑，manifest 仍保留
  parent 與排除資訊。平行來源不足則排除整個子樹，不能以追加順序推造並行重播排程。
* 未知命令、遮罩／不支援輸入、無效命令簽名會保留排除原因；執行結果不會變成輸入參數。
  沒有可重播動作時，產物會明確失敗，不會產生空白而通過的測試。

原始位置／關鍵字參數形狀與安全的平行分支 JSON 字串保持原樣；只有驗證會解析其結構。
``${secrets.name}``／``secret://name`` 等未解析參照可保留。
日誌寫入前會檢查已編碼分支、遮罩已知解析後的輸入字串與動態 key，並記錄不可重播原因。
Importer 也會清理外部輸入，不會求值任意文字日誌或 repr。

驗證與來源清單
--------------

Manifest 包含來源 SHA-256、所選 run、實際來源行號／追加序號、生命週期／parent／status、
提出與排除方式、重試邊界、程式／動作雜湊、目標／風格與驗證範圍。
雜湊是內容身分，不是數位簽章；若讀取後來源變更，仍代表實際消費的位元組快照。

命令檢查涵蓋目前命令名稱、巢狀結構、必要參數與呼叫簽名。Python／pytest 通過 AST 解析；
Robot 使用既有 renderer 並解析內嵌 Python expression 的 AST，並不代表執行過 Robot。
真正的 executor 乾跑路徑會暫時解除外層日誌擷取，不派送 callable，也不解析秘密參照。
動態輸入與原生結果保持待驗證。

審閱內容會封存，事後變更動作或 manifest 時，匯出／匯入均拒絕。
若目前秘密遮罩會改變產物程式，會明確報錯，不回傳語法已毀損卻標示驗證通過的程式。

來源上限 64 MiB，單筆 8 MiB、最多 100,000 紀錄／10,000 個所選步驟，parent 深度最多 64。
候選驗證最多 10,000 個動作節點與 32 層結構化控制。
JSON 審閱包與 ZIP 未壓縮內容各有 16 MiB 上限。
GUI 每個檢視最多顯示 200,000 字元並標示截斷，快取中的完整審閱資料仍保留。

CLI、命令與匯出
------------------------

日誌模式在 stdout 輸出完整 JSON 審閱資料::

    je_auto_control codegen --from-log run.jsonl --run-id selected-run
    je_auto_control codegen --from-log run.jsonl --run-id selected-run --target robot -o review.zip

日誌模式的 ``-o`` 要求 ``.zip``。單一原子 ZIP 包含 ``candidate.py`` 或
``candidate.robot``、``actions.json``、``manifest.json``、``README.txt``；可整份替換既有 ZIP。
``--name``／``--failure-bundle`` 供舊動作檔模式使用，該模式仍預設 calls 風格並輸出程式文字。

``AC_generate_candidate_from_log``、MCP ``ac_generate_candidate_from_log`` 接受 ``path``、
``run_id`` 與可選的 ``target``、``style``、``output`` （ZIP）；Script Builder 也提供這些欄位。
MCP 具進度與合作式取消，不回傳部分候選。即使不匯出，私有日誌存取也要求 drive 權限。
來源／目的地遵守目前、client 與外層根目錄，進度通知前後均重查。
原子匯出前取消會阻止替換，完成匯出後不再以取消 callback 改標成功結果。

GUI 審閱與匯入
--------------

Recording Editor 或 Script Builder 的 **動作 → 審閱日誌候選腳本** 會開啟有擁有者的背景審閱視窗。
選取日誌／run，使用視窗的 **動作 → 產生並驗證**，檢視程式、與目前動作的差異、來源與警告。
變更輸入會清除舊候選，關閉視窗或編輯器則取消工作並丟棄過期結果；四種介面語言均支援。

從 Builder 開啟時，**匯入 Script Builder** 會明確替換編輯資料，並在儲存的 JSON metadata 保留來源；
不會呼叫 Run。若差異基準建立後編輯器有變更，匯入會拒絕，必須針對新基準重新開啟審閱。
Recording Editor 提供審閱／匯出，匯入則由 Builder 所擁有的視窗提供。
匯出使用已審閱快照並重查目前路徑與權限。真機與付費 API 驗收仍暫緩。

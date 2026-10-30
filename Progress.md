# Progress

## Agent 電腦接管與任務自動化

`WIP` — **依使用者恢復目標繼續交付；個別原生／真機／24 小時驗收仍暫緩。**
個別原生／真機／24 小時驗收也維持暫緩，不能因恢復一般開發而一併啟動。
完整交付契約：`docs/superpowers/plans/2026-10-23-agent-runtime.md`。
以下僅列未完成的實作、設定與驗證步驟；本批收尾不代表 P0–P9 全部完成。
目前驗證紀錄：docs/updates/2026-10-e.md #U-20261030-40；原40項與暫緩驗收仍未結案。
功能開發位置：`D:\Codes\AutoControlGUI\.worktrees\agent-runtime`，分支 `feat/agent-task-runtime`；
WebRunner 對應位置：`D:\Codes\WebRunner\.worktrees\agent-managed`，分支 `feat/managed-browser-sessions`。
正式工作樹尚待整合；恢復時先核對兩個功能工作樹與本清單，勿直接在正式環境續跑。
接續第 5 組 browser／remote reader、第 3 組非 Windows helper 與第 6 組跨主機剩餘驗證，
並核對第 4 組裝置來源及第 8 組正式交付。

1. **P4：瀏覽器與正式環境接合**
   - 選定正式服務專用 helper Python、AutoControl／WebRunner 套件版本與受管 Chromium 安裝；
     以已審閱的主機 profile 明列工具、來源與產物根目錄，再驗證正式服務載入該環境。
     隔離候選、固定套件鎖、實際標準 helper IPC 與逐檔比對見 stage104；仍須選定穩定路徑、
     審閱實際工具／來源／根目錄並安排部署，不能直接採用暫存候選或宣稱瀏覽器已啟動。
     Python 相依與介面驗證不能代替受管 Chromium、實際登入／頁面及原生證據。

   - 核對既有瀏覽器呼叫者各自的環境是否已安裝相容 `je_web_runner`。舊 bridge 依賴呼叫環境的
     SDK，不會自動使用受管 helper；缺套件時應保留明確失敗，不能退回其他瀏覽器引擎。
   - 正式變更前仍須安排主工作樹、既有 Jeffrey_RPA 批次與服務的部署／回復步驟；不能直接將
     功能工作樹當作已部署版本，也不能替換共用 `.venv` 或自動重啟正式服務。
     舊版回復須先取得輸入退場確證，審閱相符的升級前狀態及原位置，並從全部舊版任務根目錄
     排除留存的新版私有檔案；不能讓不識別新私有根的舊程式沿用新版資料庫／快取。
     須比對來源／成品雜湊，不能只看相同版本號；保留不明 journal，不重播副作用。
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
   - Windows：實測持續來源的注入事件排除、鎖定、
     真人接回、明確恢復與閒置 60 秒條件。原生 HWND／PID、遮擋、縮放與輸入清理仍缺實測。
     原生驗收解除暫緩前，仍缺 Raw Input 實體／注入／觸控涵蓋、
     真實本機 console／鎖定轉換、來源／helper 崩潰與輸入清理的實測證據，
     不可用虛擬來源、受控原生後端或局部 IPC 成功取代。
     歷史固定版本的 DAG 同目標提交 HTTP409 原因仍未明；後續完整執行沒有拒絕回應
     不構成該次原因已修復。保留 stage117 原始失敗及後續實際拒絕內容的追查，
     不放寬既有提交／等待／清理期限，也不重播已完成效果。
   - macOS、X11、Wayland：實作可信真人活動來源，接合授權／鎖定／閒置判定、觀察目標身分、
     視窗範圍輸入及自有 helper 隔離；補非 Windows 對話框／未儲存 gate。
     目前不能解除不支援平台的共用桌面拒絕保護。
     Linux helper 仍須將 presence_channel_linux transport 接入自有 helper 啟動與可信 endpoint 傳遞，
     補預期 helper 程序政策、既有 presence challenge／lease 與真正登入／seat／鎖定／真人活動來源；
     核對實際 helper 世代、故障退場與完整應用接合，不能以獨立元件 IPC 取代這些證據。
     程序／逐訊息身分及受保護路徑不代表桌面權限，也不能隔離同 UID／特權敵對程序；
     使用者空間有界等待不能冒稱核心 syscall 的硬即時完成，未知清理仍不得移交控制權。
     POSIX 本機 channel 已在 SIGCHLD 被忽略時拒絕啟動，且只在未回收的 leader 仍保有群組 ID
     時才送出 killpg；leader 已被他處回收時拒絕送訊號並保留未 retired（stage147，WSL 實測）。
     仍缺：以 setsid 等方式離開群組的後代無法由本機 channel 觸及，送出訊號、主程序退出或單次
     錯誤碼均不足以證明全部後代已退出，須靠 owner 服務的 cgroup 退場；涵蓋既有環境探測、
     桌面／瀏覽器及遠端 helper 呼叫者的實際驗收亦仍待執行。
     正式繫結仍須核實取消發生於 native spawn 期間的所有權、失敗清理、群組與逸出後代退場，
     並補受支援版本／架構驗證；隔離原型與直接子程序驗收不等於正式 helper 已接合，安裝前仍須比對。
     不得把原始逾時改稱 registry 死鎖，也不得放寬原始 10 秒期限或改動跳過政策。
     presence_worker 仍須接合 Linux source／pipe／security，處理真正登入、seat、鎖定與活動來源；
     已安裝固定模組的未支援回覆及正常 EOF 退場不能證明實體來源或完整後代退場。
     不得替換空白 initializer 或偽裝 Wayland session 取代完整應用驗證。
     獨立 owner 核心仍須完成每筆記錄的啟動、取消、句柄發布、執行緒回收與服務端持續所有權；
     失敗 clone 的輸出暫存值不得當成擁有的 fd，晚到成功必須接管後清理，啟動確認遺失亦不得漏失。
     須涵蓋建立執行緒回傳前 worker 已完成、建立失敗、記憶體配置失敗、失去通知及句柄重用。
     每個 nested helper 仍須獨立受保護子樹；關閉來源保留 broker 與 sibling，關閉父程序則等待
     所有後代啟動解決、子樹清空與精確目錄移除。mkdir 成功但 open 失敗仍須保有清理責任。
     stage150 已在 WSL distro 內以 root 佈建並執行受保護驗收（連續三次 13 項全過）：payload
     帳號無能力且無法遷出、以 setsid／雙重 fork 逃離的後代仍被 cgroup 收回、guardian 與服務
     崩潰後冷復原收回孤兒程序；並行 session 互不影響，受保護父程序也能以 fd 4 授權開啟子 lease
     並在其容器內啟動子 helper；START 後立即關閉的競態循環皆退場且無殘留（連續三次 18 項全過）。
     仍須核實 clone 瞬間的確定性取消、多層
     nested 與其他核心／發行版；單一 distro 的結果不代表所有部署。
     stage138 已於隔離 staging 實作 native_service（guardian 授權握手、逐封包 sender 驗證、
     lease 發行／關閉、scope owner 生命週期與 drain），但僅有 peer/lease 證據；正向 bootstrap
     未執行（此環境無服務擁有的 delegated cgroup2）。獨立審查的發現已全數回應（nested 授權、
     子程序 fd／訊號／能力設定、namespace、START 重驗、服務入口）。stage139 已讓 nested
     capability 經 worker 私有 bootstrap pipe（fd 4）只交付給該紀錄自己的子程序，並以 fixture
     驗證；受保護路徑「payload 發布後才交付」仍未實際執行。stage141 已加入 worker 擁有的應用程式中繼（fd 0／fd 1、各 64 KiB、
     OP_WRITE／OP_READ），以 fixture 子程序與閘門下的紀錄驗證；stage142 加入 OP_OBSERVE，並以
     _Static_assert 固定 C 與 Python 兩側的封包配置。guardian 有持久 journal（stage144）與程序
     （stage145）；stage149 改由 guardian 擁有 listener、驗證 client 的帳號與 namespace 後才把
     連線交給服務（依 2026-10-29 決定）。stage150 依實測修正 cgroup 配置（委派者只能在共同祖先
     的 cgroup.procs 可寫時搬移程序：epoch-N 為委派根、service-N 為 root 擁有的葉節點、records
     為授權給服務的錨點），服務以 guardian 給予的 ambient CAP_SETUID／SETGID／SETPCAP 執行，並在
     WSL 完成受保護端到端驗收（實際 client、受保護 payload、RETIRED 回報、未列帳號被拒、冷復原）。
     正式入口在安裝版本仍維持關閉，開啟前仍須獨立審查；僅 `NO_PROTECTED_ACCEPTANCE` 驗收建置
     開啟。
     位置：`.worktrees/agent-tools/stage138/`（todo.md、review.md）、`stage139/`、`stage141/`
     至 `stage150/`。
     OwnedChannel 的 close 已不再等待 request 鎖，另一執行緒可中止等待中的請求，close 開始後
     不再交付任何回覆（含已排入佇列者）。`helper_owner_linux.py` 以相同介面經 owner 服務運作
     （每個 channel 一條連線與 lease、OPEN／START 以固定 nonce／request ID 重送、依 nonce
     略過過期回覆、close 只等待單一呼叫並在服務觀察到 helper 結束後才標記 retired）；已在 WSL
     對實際 C 服務端到端執行（僅 acceptance build 以未受保護的 fixture 紀錄代替閘門後的受保護
     啟動，因此 close 正確地拒絕宣稱 retired）。nested helper 已能讀取 fd 4 並以 OPEN_CHILD 開啟
     子 lease（stage146，對實際服務只觀察到閘門下的拒絕）；presence broker 的入口尚未呼叫讀取。
     5 類呼叫者已改經 `owned_channel` 取得 channel：
     Linux 若有主機安裝的 root 擁有綁定檔，只能經服務啟動清單中完全相符的 argv，不退回本機程序。
     已決定（2026-10-29）：Linux 無綁定時繼續以本機 channel 執行 helper，runtime status 回報
     not_configured。presence broker 目前只有 Windows 版本，nested grant 待 Linux presence 來源
     存在後接合。parent_watch、輸入 journal／lease 與本機 pipe 執行緒退場仍須接合。
     owner 服務原始碼依 2026-10-29 決定已進入 `native/owner_service/`（src、manifest 範本、build.sh、
     tests 與兩個驗收執行器，不進 wheel），每個 client 帳號的 lease 配額已實作。
     現況：經二十五輪獨立審查（處理紀錄見 docs/updates/2026-10-e.md，U-20261029-23 起），第二十三輪
     審查 U-20261030-36 未發現 MAJOR 或 MINOR；第二十四輪審查 U-20261030-38（補齊先前延後的測試與
     載入檢查）與第二十五輪審查 U-20261030-39 亦未發現 MAJOR 或 MINOR，其 NOTE 分別於 U-20261030-39、
     U-20261030-40 處理。正式閘門另因下列項目關閉。
     驅動桌面／瀏覽器的 helper 一律以本機程序執行，owner 服務只承載不需顯示的 helper（探測、遠端裝置）；
     遠端 helper 與實體裝置的通訊屬暫緩的實體裝置驗收。
     已知限制（服務 README 已列）：payload 檔案只在別的本機使用者配合時可能逃過一次清除（放在該 ID 的
     目錄裡且超過延後上限、或在走訪中被即時改名到走訪後方）；逃過的只是資料，不帶身分（不能設 set-ID）。
     徹底消除需讓 payload 使用私有 /tmp、/var/tmp、/dev/shm，屬另一項設計。
     已知限制（未寫進服務 README）：清除只依使用者 ID 判斷，隔離區保留其他 ID 擁有的內容；NSS 服務中斷
     而回報 ENOENT 時，manifest 的 payload ID 會被當成「未配置」；同一檔案系統上的 bind mount 只在清除
     自己的 namespace 中卸下。
     TODO：已安裝主機驗收須確認主機需求：journald SplitMode=none 或不保存、core_pattern 為檔案／
     systemd-coredump／apport、mount API 未被擋或 /dev/mqueue 為本 IPC namespace 的 mqueue、所有 payload
     可寫目錄皆為清除根目錄。guardian 只對未知的 pipe／socket 或讀不到的 core_pattern 警告，並記錄存在
     但打不開或不受信任的清除根目錄，其餘不檢查。
     TODO：其他架構／libc／核心的相容性驗證、
     安裝內容比對、實際已安裝主機的執行驗收才能開啟正式閘門；不能匯入時下載
     或暗中部署服務。
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
   - browser 仍須完成實際登入／欄位／視窗狀態重建、原 helper／SDK context 的完成讀回、
     永久輸入／網路退休與技能的真實應用驗收；受控模擬頁面／IPC 證據不能取代原生驗收。
     remote 完成審閱／驗證／技能發布仍缺真實 SDK／裝置世代、永久唯讀來源、清理確證與
     舊 writer 結束證據；接入既有私有完成預覽／建立／執行與 API／GUI，不以旗標、另開 reader、
     舊動作收據或重播輸入替代。網路結束後的即時 DOM 不能當作新伺服器回應；未知隔離不可解除。

   - 針對新增平台／裝置及恢復路徑重驗服務重啟、WorkQueue 去重、事件／排程重新授權、
     journal／history／產物關聯及 30 天保留／清理，不擴大既有權限。

6. **P8：多 agent／多機的剩餘接合**
   - 逐條稽核規劃、執行及驗證的權限邊界：規劃產生有限提案，執行重新授權，完成由獨立條件
     判定；補必要的角色／跨節點證據與提示注入回歸。
   - 為實際主機配置受保護的 runtime 端點、背景派送、主機憑證與相容完成契約；明確記錄遠端
     目錄／目標設定、部署／回復方法。受管任務 DAG 不會自動部署遠端服務。
   - 跨主機成果移交仍須完成實際受保護端點、跨實體主機與正式環境交付；
     各有限來源／接收／採認案例的
     驗證不能取代實際遠端部署及目前來源／接收端的應用狀態證據。
     核對讀寫權限、當前來源／接收身分、原始提交與私有完成授權、摘要及目的端發布；
     本機路徑、匯入收據或協調端摘要不得冒充遠端檔案／完成證據，也不得轉送本機權限。
     核對兩／三主機故障矩陣：原 host／token／帳戶／origin 變更或撤銷、來源到期、讀者同意、
     冷重啟與晚回覆、發布／取消交錯、舊派送 schema、多次續行 origin、精確產生者退出、
     未知暫存與清理失敗、未決批次、配額回收及重啟後仍固定的來源／目的端／證據期限。
     保留原有本機 DAG admission／憑證與跨程序 host binding 核對；實際本機祖先不能因 wire grant
     省略、變更 tags 或補造提交列而繞過。standalone 與真正遠端節點沿各自實際接受憑證處理。
     技能契約須核實來源主機的真實動作、原 trial／版本及當前權限；規範未要求補造協調端外國任務。
     歷史 D 磁碟 2／3 秒協調與 HTTP 準備逾時的原因／部署影響仍須追查；C 預設暫存的完整成功
     不代表所有磁碟上的相同期限均已根治。舊失敗與階段觀測保留於本次月誌及 stage74–104。
     真正受保護端點、跨實體主機與正式環境驗收仍依第29／31項完成；不得直接部署功能工作樹。

   - 實際多機驗證斷線／晚到回覆、主機重啟、憑證撤銷／變更、協調端中斷及同資源序列／
     獨立資源並行；未知清理不得讓下游成功或搶走遠端控制權。

7. **P3／P6／P7：能力、模型及共用介面驗證**
   - 補桌面權限、平台／裝置連線、來源／目標就緒與原生證據的診斷；區分未支援、缺依賴、
     未授權、未探測、未記錄與實測成功，不把 Python 套件匯入成功當原生可用。
     runtime status 已加入 helper 程序擁有方式（helper_containment，native_evidence 固定
     not_recorded）；桌面權限、裝置連線與來源／目標就緒的診斷仍缺。
   - 為自訂／外部 target 補經審閱的語義觀察與遮罩覆蓋契約；沒有能力旗標的舊 target 仍沿用
     既有判定，不能因此宣稱已證明完整畫面或遮罩內容的不存在。深化部分證據的計數／狀態／
     變動判定與受保護欄位比較，目前缺少充分證據時仍為未知。
   - 本機 Ollama 模型／端點尚未設定（使用者2026-10-28確認）；待明確配置已安裝的
     工具／視覺模型與本機端點後，補模型不符、拒絕連線、逾時、取消、預算與完成驗證的
     端到端證據；不可自動下載或切換外部服務。
   - 新增／深化功能須同步公開 API、命令目錄、MCP／REST／CLI／Builder、薄 GUI Actions 及語系，
     並重驗匿名／具名權限、來源限制、GUI 關閉／重開、服務獨立生命週期與跨 session 隔離。

8. **P0–P9 最終交付核對與檢查**
   - 每條交付契約整理實作、無頭回歸與原生／真機證據對照；補新平台／多機／恢復情境的漏洞，
     區分已實作、尚缺實作與只缺實測，不能用模擬目標取代原生驗收。
     歷史證據檔不自動認領或刪除。

   - 於整份規範最後固定提交重跑完整 headless 與 coverage run -m pytest、跨功能／故障恢復回歸；
     後續平台／恢復修正亦須納入完整 coverage 及新成品逐檔比對；
     後續修正不得沿用較早提交的完整驗證；來源、測試、設定與文件須重新固定並核實。
     目前功能工作樹完整成功的來源範圍與133項跳過原因見本次月誌，不能替代尚缺的原生／裝置驗收。
     歷史原因仍須追查：stage74 的管理員 host binding 與 retention uncertain／phase 前置失敗；
     stage85 的 default_connection_discovery_change、expired_origin_can_be_replaced_only_for_never_dispatched_scoped_work
     及 retention queued_child／executing／fresh_delivery；stage88–93 的3秒來源匯出／匯入準備逾時。
     C／D 儲存尾延遲對照不構成所有磁碟的根治；保留原始失敗與收據、逐案確認實際耗時／未知狀態，
     不放寬2／3／15秒期限、不改 WAL／耐久性、不重播已完成效果、不以局部通過抵銷舊失敗。
     test_dag_managed_loopback 的完整執行曾遇提交 HTTP409／限流，尚缺最初拒絕原因；
     stage71 matching_grant_digest 的首次 observe 曾耗盡15秒 bootstrap，仍缺啟動堆疊／耗時原因。
     共用 pytest-current 的 WinError5 權限／生命週期問題仍未修復；不得刪除共用連結、改共用環境
     或將自有新 basetemp 成功視為清理問題已消失。原始計數與檔案位置已保留於本次月誌。

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
**安裝前比對（使用者 2026-10-26 指示）**：任何安裝／升級前，先核對本紀錄與當前工作樹／
環境，並比對已安裝版本、依賴、來源及待安裝內容；把差異與預期變更寫入紀錄後再處理安裝。
本專案封裝還須比對來源提交、wheel／sdist 內容與檔案雜湊；安裝後再核實實際來源及依賴一致性。
這項要求不授權變更共用環境、付費依賴或正式部署；本輪僅在全新自有 C 暫存目錄
隔離安裝已逐項比對的套件。正式工作樹、共用環境、服務與瀏覽器均未變更。
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
`je_auto_control/__init__.py`、`je_auto_control/_export_bindings.py`（產生的公開名稱來源查表）與
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

# 程式審核：AutoControlGUI

## 審核者

審核者＝工作區程式審核；日期＝2026-10-22；對象＝`AutoControlGUI`（`je_auto_control`）；結論＝有條件通過。

## 審核規範

共通規範在工作區 repo [JE-Chen/Codes](https://github.com/JE-Chen/Codes) 的 `docs/code-review-standard.md`。下面留下 2026-10-22 這次審核所用的條款，讓審核紀錄的依據對得上那一次。之後的審核以工作區那份為準。本專案更嚴的條款仍以本節與本專案的 `CLAUDE.md` 為準。

1. 設計：分層為進入點 → `utils/executor/` → `utils/` → `wrapper/` → 單一 OS backend；新能力須同時有 headless API、外觀匯出、`AC_*` 與薄 GUI。
2. 可讀性：依 `CLAUDE.md` 從嚴。循環複雜度 ≤ 10、認知複雜度 ≤ 15、函式 ≤ 75 行、參數 ≤ 7、巢狀 ≤ 4、檔案 ≤ 750 行（flat data table 與 `Progress.md` 豁免除外）、每行 ≤ 120。
3. 錯誤處理：框架錯誤須衍生自 `AutoControlException`；邊界失敗要明確拋出；寬 `except` 須就地註明原因，禁止裸 `except:`。
4. 死碼：不把已接上的命令、保留的相容進入點或有意留下的拒絕路徑當成死碼。
5. 型別與 docstring：公開模組、類別、函式要有一行摘要與型別；本次只在熱點路徑上看。
6. 安全：套件閘門、`eval`／`exec`、`shell=True`、`pickle`、`verify=False`、日誌是否寫出祕密、`AC_*` 如何吃外部字串。有白名單且無法繞過的執行器不當成缺陷。不建議改名既有 CLI 旗標。
7. 測試：只看熱點旁的測試意圖與文件所引的契約測試是否對得上實作；本輪不執行測試。
8. 效能：只記會在熱點上放大成本或把祕密留在行程裡的行為，不展開全套件。
9. §6：不改 `architecture.md` §6 所列之 CLI 旗標、外觀名稱、executor API 與 WebRunner 拒絕的命令名。
10. 文件同步：`architecture.md` 的分層、進入點與安全約束須與套件原始碼一致。

嚴重度：缺陷＝會讓閘門、命令或祕密邊界失真；建議＝應改但無立即損害；備註＝已核對、不構成問題。通過＝無未關閉缺陷；有條件通過＝無立即損害；需修正＝有會立即損害的未關閉缺陷。

## 審核紀錄

### 方法

抽樣範圍是 `je_auto_control/` 底下的 `.py`。排除 `test/`、`build/`、文件產物、`__pycache__`、`autocontrol-lsp/node_modules`、`exe`。沒有整份讀 `architecture_explore.md`；`Progress.md` 只讀前 60 行。`architecture.md` 讀了分層、進入點與 §6，並核對 §7 的套件閘門句。`CLAUDE.md` 只讀編碼標準、長度上限與安全相關段。

在套件 `.py` 搜尋 `eval(`、`exec(`、`shell=True`、`pickle`、`verify=False`、裸 `except:`。`eval(`、`pickle`、`verify=False`、裸 `except:` 無命中。`exec(` 皆為 Qt 事件迴圈。`shell=True` 只出現在「不使用 shell」的註解，以及 `still_run_shell` 旗標。

深讀：`utils/package_manager/package_manager_class.py`、`utils/shell_process/shell_exec.py`、`utils/executor/flow_data_commands.py`（shell 段）、`utils/start_exe/start_another_process.py`、`utils/logging/secret_scope.py`、`utils/logging/logging_instance.py`、`utils/mcp_server/tools/_handlers_system.py`（行程與 shell）、`utils/plugin_sdk/plugin_sdk.py` 與 `utils/plugin_loader/plugin_loader.py`。對照了 executor 派遣、插值、動作遮罩、RBAC、socket 預設綁定與 `architecture.md` §7。

### 發現

#### CR-01 · 缺陷 · shell 輸出在祕密遮罩結束後才寫入日誌

位置：`je_auto_control/utils/shell_process/shell_exec.py:172`、`je_auto_control/utils/shell_process/shell_exec.py:253`、`je_auto_control/utils/executor/action_executor.py:8270`、`je_auto_control/utils/logging/secret_scope.py:69`

說明：`AC_shell_command` 走全域 `default_shell_manager`。子行程的 stdout／stderr 只進佇列，不在當下寫日誌。`exec_shell` 在啟動新行程之前呼叫 `exit_program`，由 `log_and_clear_queue` 把上一輪佇列整行送進 `autocontrol_logger`。`execute_action` 的 `secret_log_scope` 在該次回傳時 `close()`，遮罩清空；`SecretLogFilter` 在沒有作用中的 scope 時原樣放行。因此上一輪 shell 若印出已由 `${secrets.*}` 解析的值，下一次 shell（另一次執行、且該次啟動前未再次記住同一個值）會把明文寫進日誌檔。命令列本身有 `program_of`，這段補不上輸出佇列。

依據：安全（記錄不得寫出已納入執行期遮罩的祕密）；`architecture.md` 所述執行期遮罩須涵蓋錯誤處理與持久診斷。此路徑把明文留到遮罩生命週期之外。

狀態：未關閉。

建議：在 scope `close()` 之前，用當時仍有效的遮罩把佇列刷成日誌或改成已遮罩文字。讀取執行緒入列時也要遮罩，避免 `close()` 之後才讀到的行恢復明文。不要只依賴下一次 `exec_shell`。

#### CR-02 · 建議 · 架構文件仍寫未設定時任何套件都會載入

位置：`architecture.md:562`；實作在 `je_auto_control/utils/package_manager/package_manager_class.py:52`、`je_auto_control/utils/package_manager/package_manager_class.py:82`

說明：§7 寫未設定時任何套件會載入並發出 `DeprecationWarning`（workspace X-12）。實作預設 `allow_arbitrary_packages` 為 `False`，允許清單只來自行程建立時的 `JE_AUTOCONTROL_ALLOWED_PACKAGES`。`AC_add_package_to_executor` 與 `AC_add_package_to_callback_executor` 在 `import` 前呼叫 `_check_allowed`；不在清單上就拋 `AutoControlExecuteActionException`，不會匯入。`allow_packages` 與 `set_allow_arbitrary_packages` 不是 `AC_*`。名稱須符合點分模組正則，子模組比對是 `allowed + "."`，動作檔不能自己打開閘門。

依據：文件同步；安全契約若與程式相反，之後可能把已收緊的預設改回開放。

狀態：未關閉。

建議：把該句改成預設拒絕，並寫明環境變數、`je_auto_control run --allow-package` 與 Python API 三個顯式開口。不要新增或改名 CLI 旗標。

沒有第三則。下列項目看過，不構成缺陷。

### 總評

套件閘門、命令名稱檢查、shell 參數形式與祕密遮罩的主路徑是收斂的，沒有看到可繞過白名單的 `eval`／`exec` 或 `shell=True`。唯一未關閉缺陷是 shell 輸出延後寫日誌，發生在本機日誌、且要等下一次 shell 啟動；它不打開套件閘門，也不讓外部字串變成任意 Python。因此不是需修正。文件有一則過時的安全描述，程式比文件嚴。

### 已核對

- `eval(`、`pickle`、`verify=False`、裸 `except:`：套件 `.py` 無命中。`exec(` 為 Qt `dialog`／`app` 的事件迴圈。
- `shell=True`：無實際呼叫。`AC_shell_command`、`AC_shell_to_var`、`ac_shell` 都以 `shell=False` 啟動。list 在 Windows 上對 `.bat`／`.cmd` 的 cmd 元字元有 `refuse_batch_metacharacters`；字串命令列依註解刻意不套用該檢查，因為它就是呼叫端的命令列，不是被繞過的白名單。
- `AC_execute_process` 只把 `resolve()` 後的單一路徑放進 argv，避免 `shlex` 拆開含空白的路徑。
- `ac_launch_process` 未呼叫 batch 檢查，但該 MCP 工具本來就接受呼叫端給的任意 argv，且標成破壞性操作；不是白名單繞過。
- `AC_*` 外部字串：`validate_actions` 先拒絕未知命令；`_execute_event` 只從 `event_dict` 取可呼叫物件，dict 用關鍵字、list 用位置參數。`${var}`／`${secrets.*}` 在執行當下插值；祕密經 `remember_secret`。沒有把命令名字串送進 `eval`。
- 代理程式：`require_offered` 拒絕未提供的工具名，補上先前 `only=[...]` 擋不住 `AC_shell_command` 的缺口。
- 外掛：`AC_load_plugins` 只傳 group；`plugin_sdk` 只載入 `je_auto_control.commands`。目錄載入會 `realpath` 並拒絕解析到目錄外的 symlink。檔案外掛會執行該 `.py`，模組註解已將此訂為信任目錄，且 RBAC 把 `AC_load_plugins` 放在 hosts。
- 狀態機 `_guard_eval` 只跑 `after`、`if_var_eq`、`if_image_found` 與可呼叫的 `predicate`；JSON 字串 predicate 會拒絕。
- 產生程式碼：非識別字的參數鍵改走 `execute_action` 字面量，不直接拼進關鍵字引數。
- TLS：`verify=False` 無命中。`ssl.CERT_NONE` 只在遠端桌面 Viewer 的 opt-in self-signed 路徑，預設仍是 `CERT_REQUIRED` 且檢查主機名。
- 綁定：TCP 與 REST 預設 `127.0.0.1`。
- 日誌主路徑：執行清單先 `redact_actions`；logger 有 `SecretLogFilter`；vault 欄位與敏感參數名會遮。CR-01 是這套遮罩沒蓋到的延遲佇列。
- §6：本輪沒有建議改 CLI 旗標、外觀名稱或 WebRunner 所拒絕的命令名。

### 未涵蓋

未逐行審約 20 萬行，未跑測試、lint、bandit 或 radon，未啟動 GUI，未匯入套件。未審 `test/`、`docker/`、`scripts/`、`autocontrol-lsp/`、瀏覽器擴充與 exe。GUI 只抽到遠端桌面的憑證開關。`Progress.md` 750 行豁免表只讀到前 60 行，未逐檔對長度。HTTP／ACME、webhook 與 journal 只沿架構與呼叫點確認有遮罩鉤子，沒有全讀。

### 本專案加嚴

長度與複雜度用 `CLAUDE.md`：循環 ≤ 10、認知 ≤ 15、函式 ≤ 75、參數 ≤ 7、巢狀 ≤ 4、行 ≤ 120、檔案 ≤ 750。本輪熱點函式沒有量到超過這些上限的新缺陷；`action_executor.py` 在 `Progress.md` 開頭列為 flat data table，未把它的行數當缺陷。寬 `except` 在套件閘門與外掛載入處有 `# reason:`，不是裸 `except:`。

### 結論

有條件通過。發現 2 則：未關閉缺陷 1（CR-01，無立即的閘門或遠端損害）、建議 1（CR-02）。沒有需立刻擋下整合的執行路徑繞過。

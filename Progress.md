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

## [WIP] `utils/url_canon/` 尚未完成三面交付

RFC 3986 URL 正規化模組已有無頭核心與測試，但不符合 CLAUDE.md 的交付規則，目前只能從
Python 直接匯入子模組使用。

- **已完成**：`je_auto_control/utils/url_canon/url_canon.py`（117 行，
  `canonicalize_url`／`normalize_url`／`urls_equal`／`parse_query`／`build_query`）；
  `test/unit_test/headless/test_url_canon_batch.py`
- **缺**：
  1. 門面再匯出 — 五個公開函式都不在 `je_auto_control.__all__` 裡
  2. `AC_*` 指令 — 執行器沒有對應命令（現有的 `AC_next_url`／`AC_web_current_url` 是分頁與
     WebRunner 用途，無關）
  3. GUI 介面 — 沒有分頁或既有分頁的操作入口
  4. `architecture_explore.md` §5.4.11 沒有這個套件的列
- **另外**：兩個檔案都還是 untracked，尚未進版控

---

## [TODO] headless 全套件跑到 `test_usb_acl_prompt.py` 會讓直譯器整個掛掉

`python -m pytest test/unit_test/headless` 跑到約 87%（`test_usb_acl_prompt.py` 的第三個
測試附近）時，行程**沒有 traceback、沒有結尾摘要就直接結束** —— 是原生層的崩潰，不是測試
失敗。單獨跑 `pytest test/unit_test/headless/test_usb_acl_prompt.py` 九個測試全過，所以是
跨檔案累積出來的狀態（COM／執行緒／原生資源）才觸發。

- **影響**：CI 那一關實際上跑不完，後面約 500 個測試從來沒有被執行過，而輸出看起來只是
  「中斷了」，不會紅燈得很明顯
- **與新功能無關**：把 2026-08-15 的 Unicode／OCR／DPI 變更 stash 掉之後，同一個位置一樣
  崩潰，所以是既有問題
- **繞法**：`--ignore test/unit_test/headless/test_usb_acl_prompt.py` 之後全套 4,300 通過
- **下一步**：用 `-p no:randomly` 固定順序後二分找出前置的加害者測試（優先看會開 COM、
  起執行緒或掛 hook 的那幾支）

---

## [DECIDE] 文件數字漂移要不要設 CI 守門

CLAUDE.md 現在要求每次變更同步更新 `architecture_explore.md`，README 三份也引用同一批數字
（指令數 754、子套件數 306、GUI 分頁 48、MCP 工具 660、範例 27），但**沒有任何機制強制**，
純靠人與 agent 自律。

- **提案**：加一個 headless 測試，實測 `known_commands()`、`__all__`、`_add_tab` 數量、
  `build_default_tool_registry()`、`examples/` 檔數，與文件中的數字比對，不一致就紅燈 —
  作法比照既有的 `test/unit_test/headless/test_actions_menu_gui.py`
- **代價**：文件與程式碼必須同一個 commit 更新，否則 CI 會擋
- **待決**：要不要做；若要，是硬性失敗還是只發警告

---

## [DECIDE] README 精簡後移除的深度內容是否部分回收

README 由 1,471 行重寫為 267 行（三語同步），移除約 30 段 Quick Start 程式範例與
45 條發佈說明式的功能敘述。

- 發佈說明類內容 `WHATS_NEW.md` 已有完整記錄，範例由 `examples/` 的 27 個可執行腳本承接
- **待決**：是否要把其中特定段落搬回 README，例如遠端桌面的線路協定說明
  （HMAC 握手、JPEG 影格廣播、輸入允許清單）——那段在 `examples/04_remote_desktop.py`
  與 readthedocs 都沒有等價敘述

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

## [TODO] 還有六個測試檔呼叫 `deleteLater()` 而沒有沖掉

`deleteLater()` 要有事件迴圈在跑才會生效。測試模組通常不跑事件迴圈，於是物件（連同它
建構時起的輔助執行緒與計時器）會一路活到後面某個**會**推事件的測試，然後在那支不相干的
測試裡被銷毀。`test_admin_console_thumbnails_gui.py` 就是這樣讓整個直譯器以
`__fastfail`（rc 3221226505）死掉的，已修；同一個模式還留在：

- `test/unit_test/headless/test_r3_gui_main_window.py`（2 處）
- `test/unit_test/headless/test_r3_gui_thread_marshal.py`（3 處）
- `test/unit_test/headless/test_remote_desktop_cursor.py`（1 處）
- `test/unit_test/headless/test_remote_desktop_quick_connect.py`（9 處）
- `test/unit_test/headless/test_usb_passthrough_panel.py`（8 處）

- **現況**：套件目前全綠（4,364 passed／19 skipped，打亂順序重跑亦同），所以這幾處還沒
  咬人，但差一次順序或新測試就可能再炸一次，而且崩潰時沒有 traceback、`faulthandler`
  也攔不到，極難查。
- **做法**：比照已修的那支，收尾補
  `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` + `processEvents()`。
  規則已寫進 `CLAUDE.md` §Testing。
- **另一個選項**：改在 `test/unit_test/headless/conftest.py` 放一個 autouse fixture 統一沖，
  一處到位，但目前整個 `test/` 底下還沒有任何 `conftest.py`，等於新增結構，要先拍板。

---

## [DECIDE] `windows/listener/` 兩個模組已無呼叫端

`win32_keyboard_listener.py`（118 行）與 `win32_mouse_listener.py`（127 行）在
`je_auto_control/` 與 `test/` 底下**沒有任何引用**——錄製改走
`record/win32_input_hook.py` 之後就沒人用了。

- **待決**：兩者都是公開類別，刪掉算破壞性變更。要刪（下一個主版本）、標記
  deprecated，還是就留著？
- 在 `architecture_explore.md` 的 Windows 後端表已標注「已無任何呼叫端」。

---

## [TODO] `windows_backend.py` 915 行，超過 750 行上限

`je_auto_control/utils/accessibility/backends/windows_backend.py` 目前 915 行，超出
`CLAUDE.md` §Limits 的 750 行。拆出 `windows_query.py`（170）與 `windows_state.py`（98）之後
仍然超標——這個檔在拆之前就已經是 772 行，後續補視窗限定搜尋與控制項模式又長回來。

- **注意**：目前**沒有任何 CI job 在檢查行數與複雜度**（`quality.yml` 只有 ruff 與 bandit），
  所以這條上限實際上靠自律；`action_executor.py` 8,021 行、`_factories.py` 8,866 行同樣超標。
- **待決**：是要真的拆這個檔、把上限改成符合現況的數字，還是把這條規則的適用範圍寫清楚。

---

## [DECIDE] 文件數字漂移要不要設 CI 守門

CLAUDE.md 現在要求每次變更同步更新 `architecture_explore.md`，README 三份也引用同一批數字
（指令數、子套件數、GUI 分頁、MCP 工具、範例數），但**沒有任何機制強制**，純靠人與 agent 自律。

- **已經發生過**：`url_canon` 佈線那次加了 3 個指令與 3 個 MCP 工具，`architecture_explore.md`
  與三份 README 的數字全部沒跟著改（758／664 對實際的 761／667），`CLAUDE.md` 的子套件數也
  停在 306 對實際的 308。是事後對數字才抓到的，不是任何檢查擋下來的。
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

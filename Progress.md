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

## [DECIDE] `utils/clipboard/` 有兩份同名但不同簽章的圖片 API

同一個子套件裡有兩個 `get_clipboard_image` / `set_clipboard_image`：

- `clipboard/clipboard.py`：`set_clipboard_image(png_bytes: bytes)`，跨平台
  （Windows／macOS／Linux）。呼叫端是 `gui/remote_desktop/viewer_panel.py`。
- `clipboard/clipboard_image.py`：`set_clipboard_image(image_path: str)`，寫入
  只支援 Windows。呼叫端是 MCP 的 `ac_set_clipboard_image`。

兩邊都有真實呼叫端，所以不能單方面刪掉任何一份。名字一樣、參數型別卻一個是 bytes
一個是路徑，`from ... import set_clipboard_image` 匯錯來源會在執行期才炸。

- **另外**：兩份都**沒有**從 `utils/clipboard/__init__.py` 或門面匯出
  （`__init__.py` 的 `__all__` 只有 `get_clipboard` / `set_clipboard`），也沒有
  `AC_*` 指令，等於只有 MCP 與 GUI 走得到，`execute_action` 走不到。
- **待決**：合併成一支（例如同時吃 bytes 與路徑）並補上門面匯出與 `AC_*` 指令，
  還是明確拆成兩個不同名字。

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

## [TODO] 文件數字守門還沒涵蓋 GUI 分頁數

`test/unit_test/headless/test_doc_counts.py` 已經擋住指令數、MCP 工具數、`utils/`
子套件數與 `examples/` 檔數（16 處引用，硬性失敗）。**還缺 GUI 分頁數（README 三份都寫
48）**：要數 `_add_tab` 得先建 `AutoControlGUIWidget`，也就是要 Qt，而這一包是無頭套件。

- **做法**：比照 `test_actions_menu_gui.py`，丟到子行程用 offscreen 平台跑起來數，
  結尾 `os._exit(0)` 跳過 Qt 收尾。
- **成本**：那支探針啟動一次要好幾秒，只為了一個數字。也可以接受這個數字不設守門，
  但要明講。

---

## [DECIDE] README 精簡後移除的深度內容是否部分回收

README 由 1,471 行重寫為 267 行（三語同步），移除約 30 段 Quick Start 程式範例與
45 條發佈說明式的功能敘述。

- 發佈說明類內容 `WHATS_NEW.md` 已有完整記錄，範例由 `examples/` 的 27 個可執行腳本承接
- **待決**：是否要把其中特定段落搬回 README，例如遠端桌面的線路協定說明
  （HMAC 握手、JPEG 影格廣播、輸入允許清單）——那段在 `examples/04_remote_desktop.py`
  與 readthedocs 都沒有等價敘述

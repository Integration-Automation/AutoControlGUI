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

## [TODO] `windows_backend.py` 915 行，超過 750 行上限

`je_auto_control/utils/accessibility/backends/windows_backend.py` 目前 915 行，超出
`CLAUDE.md` §Limits 的 750 行。拆出 `windows_query.py`（170）與 `windows_state.py`（98）之後
仍然超標——這個檔在拆之前就已經是 772 行，後續補視窗限定搜尋與控制項模式又長回來。

- **注意**：目前**沒有任何 CI job 在檢查行數與複雜度**（`quality.yml` 只有 ruff 與 bandit），
  所以這條上限實際上靠自律；`action_executor.py` 8,021 行、`_factories.py` 8,866 行同樣超標。
- **待決**：是要真的拆這個檔、把上限改成符合現況的數字，還是把這條規則的適用範圍寫清楚。

---

（目前沒有其他待辦。）

# 跨平台與 GUI 改版實作計畫

狀態：設計已核准；以下實作計畫待審閱，產品實作尚未開始。

設計：[2026-10-02-platform-gui-modernization-design.md](../specs/2026-10-02-platform-gui-modernization-design.md)。

## 執行方式

建議直接在本次工作中逐 task 實作，依 `superpowers:executing-plans` 執行。
每個 task 做失敗重現、修正、驗證與獨立提交；依賴未完成不能跳過。
可獨立審閱的完成階段交付後，繼續下一階段，直到全範圍完成或遇到必須由外部提供的條件。

隔離開發依實際執行中模組判斷，尤其 Jeffrey_RPA 使用 editable 工作樹。
不能先把尚未驗證的改版放進正在執行的正式流程；也不能停掉使用者批次來迴避問題。

## 子計畫

| 順序 | 可審閱實作計畫 | 交付 |
| --- | --- | --- |
| A | [A：既有決策與執行契約](2026-10-02-a-contracts.md) | 完成已核准的 Progress 修正，建立之後改版不能破壞的執行邊界。 |
| B | [B：動作日誌、自愈量測與候選腳本](2026-10-02-b-journal-healing-codegen.md) | 讓動作來源可追溯、自愈版本可比較，並從日誌產生可驗證的候選腳本。 |
| C | [C：持久化同步與遠端 session](2026-10-02-c-sync-sessions.md) | 讓多機設定在重啟、離線及並行更新後仍一致，並隔離遠端連線所有權。 |
| D | [D：Wayland 與原生依賴可靠性](2026-10-02-d-wayland-dependencies.md) | 修正 Wayland 生命周期，提供可測替代後端及正確的能力診斷。 |
| E | [E：Android 與 iOS 功能完整化](2026-10-02-e-mobile.md) | 補齊行動自動化功能並提供隔離的多裝置工作流程。 |
| F | [F：GUI 重寫與效能](2026-10-02-f-gui.md) | 提供一致、可搜尋、延遲建立與可取消的桌面自動化工作區。 |
| G | [G：MCP 逐步揭露](2026-10-02-g-mcp.md) | 依 session 搜尋與揭露必要工具，降低 schema 體積且維持權限與協定相容。 |
| H | [H：型別深化、完整文件與總驗收](2026-10-02-h-typing-docs-validation.md) | 驗證全套型別契約、所有新流程文件與平台功能矩陣一致。 |

## 需求覆蓋

- 原有 Progress 已核准決策：A1–A14，遠端 session 在 C4；RBAC 在 A10 使用核准設計預設。
- Wayland 與函式庫：D1–D3，座標與原生平台契約 A8/A12–A14，安全相依 A11。
- 跨機器不同步：C1–C4，file/clipboard 循環與資產完整性 C3。
- UI 與 GUI 重寫／最佳化：F1–F4；各新能力同步交付面板，最後接入新 shell。
- mypy：所有 task 與 H1；既有三目標檢查基準為 0 錯誤模組。
- iOS／Android：E1–E4；能力矩陣 H2，實機與平台證據 H3。
- MCP 逐步揭露：G1–G3；root/RBAC 沿用 A6/A10。
- 自愈可量測：B2；錄影與對應 frame 來源 B1/E2。
- 動作日誌 codegen：B1、B3。
- 完整範例與文件：每個 task 同步交付，H2–H3 做全套校對與建置。
- 原有未完成項目：A8/A9、D2/D3 與 H3；未有真實 API／實機證據時保持待驗證。

## 整體驗證命令

```powershell
& '.venv/Scripts/python.exe' -m ruff check je_auto_control/ je_auto_control_pytest.py
& '.venv/Scripts/python.exe' test/verify/typing_contract_verify.py
& '.venv/Scripts/python.exe' test/unit_test/headless/test_doc_line_counts.py --fix
& '.venv/Scripts/python.exe' -m coverage run -m pytest --timeout=120
& '.venv/Scripts/python.exe' -m coverage report
& '.venv/Scripts/python.exe' -m build
```

依專案規範再執行 bandit、pylint、radon；Sphinx 英文與中文各自建置。
平台測試要分開列出實測／未測項，CI artifact 保留對應版本與執行條件。
新增頂層 pytest plugin 後須重新安裝本專案讓 entry point 生效。

## 狀態追蹤

進度只記未完成的工作；完成項目移至 docs/updates，設計／計畫不是已完成功能的證據。
現有 Progress 的使用者決策修改仍保留，提交只納入本階段內容。

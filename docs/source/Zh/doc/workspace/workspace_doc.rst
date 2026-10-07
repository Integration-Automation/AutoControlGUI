GUI 工作區
==========

延遲建立面板
------------

啟動只開啟錄製、Script Builder 與遠端桌面。View → Tabs 保留完整 50 個功能 key；
其他模組／widget 首次開啟才匯入／建立。動作 metadata 不建立面板，handler
於建立後綁定；缺少選用套件會顯示恢復說明，功能仍可搜尋及開啟。

``AutoControlGUIWidget`` 既有匯入及 show/hide/list/core methods 保持相容。
``hide_tab`` 保留輸入內容；分頁關閉鈕或 ``close_tab`` 釋放／刪除面板及訂閱。
重開已關閉面板會以相同 key 建立新 widget。目錄順序及
key/title/visible/category 欄位保留。語言／引擎更新只處理已建立面板。
GUI factory、open、close 在 GUI 執行緒執行；``gui.tab_registry`` metadata
可在不匯入 Qt 或建立功能的情況下讀取。

Offscreen 測試明確開啟所有功能稽核 Actions，並驗證未開啟功能不匯入、
隱藏／重開的身分及延遲刪除後的訂閱回收。此證據不代表實體輸入或原生狀態恢復。

導航與呈現
----------

左側導航搜尋全部功能 key、目前翻譯與英文別名，不執行 factory。Ctrl+K 選取搜尋，
Enter 開啟第一個符合項目，Down 移至結果樹。操作仍透過既有 Actions 選單執行。
中央工作區重用 registry 擁有者並保留分頁輸入；右側詳情顯示明確回報的空白、
就緒、執行中、錯誤、權限、相依套件及不支援狀態，以及原因、復原方式與進度。
就緒描述工作區，不代表原生權限已驗證；工作取消整合由 F3 接續。

Ctrl+Shift+D 或 View 切換詳情，寬度小於 900 邏輯像素時預設收合；明確切換可覆寫
此預設。640×480 的寬內容可捲動操作。View → 主題切換深色／淺色，字級使用系統
字型；四種語言切換保留搜尋、目前識別及既有輸入，相依套件復原提示也會更新。
原生 Qt 圖示及焦點外框不需新圖片／主題套件。
``benchmarks/gui_workspace_capture.py`` 產生實際 Qt offscreen 截圖；平台找不到字型
時可用 ``--font`` 載入已安裝字型。Windows／Python／PySide／布局報告位於
``benchmarks/results/gui-workspace-f2``；原生多螢幕 DPI 留在 H3 驗收。

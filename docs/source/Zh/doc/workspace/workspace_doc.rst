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

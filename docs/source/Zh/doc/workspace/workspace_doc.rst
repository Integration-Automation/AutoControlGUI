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
就緒描述工作區，不代表原生權限已驗證；工作取消遵循下列生命周期。

Ctrl+Shift+D 或 View 切換詳情，寬度小於 900 邏輯像素時預設收合；明確切換可覆寫
此預設。640×480 的寬內容可捲動操作。View → 主題切換深色／淺色，字級使用系統
字型；四種語言切換保留搜尋、目前識別及既有輸入，相依套件復原提示也會更新。
原生 Qt 圖示及焦點外框不需新圖片／主題套件。
``benchmarks/gui_workspace_capture.py`` 產生實際 Qt offscreen 截圖；平台找不到字型
時可用 ``--font`` 載入已安裝字型。Windows／Python／PySide／布局報告位於
``benchmarks/results/gui-workspace-f2``；原生多螢幕 DPI 留在 H3 驗收。

工作取消與自有資源
------------------

Actions → 取消目前工作會撤銷所選面板的工作；關閉時丟棄延遲的 owner／run／session
結果。TaskController 傳遞型別化結果、錯誤與進度，以及截止時間與取消 Event。
巢狀等待會喚醒，新動作在檢查點停止；較慢的裝置、網路、擷取、辨識及服務停止
操作在 Qt 外執行。進行中的原生呼叫須在後端時限內返回；取消不能復原已完成的
檔案、保管庫或全域服務變更，共用服務仍需明確執行 Stop。

GUI 錄製使用獨立錄製器或 X11 訂閱，保留借用的全域錄製。GUI 原始輸入持有可跨
成功工作保留，直到釋放、取消或面板銷毀；清理只釋放確認自有的輸入，失敗項目
保留供 Tools → 重試自有清理。保留原先已按住的輸入，未知初始鍵態會在配置前拒絕。
Session 的原生配置與關閉共用 Qt 外的鎖，失敗 peer／container 保留供重試。
此契約不提供跨 client 的原子保護，也不代表實體狀態已恢復；直接 headless 輸入
語意維持相容。完整目錄 I/O 稽核位於 ``docs/GUI_TASK_LIFECYCLE.md``；原生裝置、
GNOME／KDE 授權及混合 DPI 驗證仍留在 H3。

參考量測
--------

``benchmarks/results/gui-workspace-f4/README.md`` 保存相同環境的暖機前後樣本、
校準門檻與六張實際 Qt 截圖。Windows offscreen 中位數：啟動 6698→5894 ms，
Python 配置峰值 100.86→90.17 MB（tracemalloc，非 RSS），首次開啟 Mobile
19.37→22.81 ms，AC_sleep 事件迴圈 p95 263.16→16.33 ms；首次開啟成本仍可見。
用 ``python benchmarks/gui_startup.py --compare <before.json> <after.json> --budget <budgets.json>``
檢查校準中位數；不同環境或工作負載會拒絕比較。原生螢幕、授權與實體輸入仍在 H3。

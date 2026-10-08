選單驅動 GUI:Actions 選單取代分頁內按鈕
=========================================

主視窗改以選單列與低按鈕分頁版面重新設計。分頁只保留輸入欄位、表格與
結果/狀態檢視;每個分頁的指令移到一個可預期的位置——會隨當前分頁動態
重建的視窗層級 **Actions** 選單。

Actions 選單
------------

分頁有兩種方式呈現其指令:

* **註冊時宣告**——核心分頁(自動點擊、截圖、影像偵測、錄製、腳本執行器、
  報告)在 ``gui/main_widget.py`` 註冊時宣告 ``(label_key, handler)`` 配對。
* ``menu_actions()`` **掛鉤**——功能分頁提供 ``menu_actions()`` 方法,
  回傳相同的 ``[(label_key, handler), ...]`` 形狀;選單列查詢當前分頁並
  渲染其回傳內容。

48 個已註冊分頁中有 46 個以此方式呈現指令。**Script Builder** 與
**Remote Desktop** 刻意保留其互動式面板版面,Actions 選單在這兩頁顯示
佔位訊息。視窗層級選單無法取代的控制項則維持原位:堆疊觸發器表單內的
逐頁瀏覽按鈕、隨可見性切換的資料來源瀏覽按鈕,以及有狀態的自動更新
核取方塊。

導覽面板
--------

視窗左側依同樣五個分類列出每一個已註冊的分頁,不論是否已開啟;已開啟的以粗體
顯示。點一下就開啟該功能(已開啟則切到最前面)。搜尋框會隨輸入過濾清單——比對
標題、鍵名(``usb_devices``)或分類——按 **Return** 開啟第一個符合的項目。
``Ctrl+K``(**View → Search Features...**)從任何地方把游標移到搜尋框,
``Ctrl+B``(**View → Navigation Panel**)隱藏或顯示面板。

分頁在第一次顯示時才建立。視窗啟動時分頁列上有三個分頁——錄製、Script Builder
與遠端桌面——錄製在最前面;另外兩個在第一次點到時才建立,其他分頁則在開啟時建立。
在那之前,Script Builder 與遠端桌面(它會載入 WebRTC 相關套件)都不會被匯入。

小視窗,以及視窗會記住的事
--------------------------

分頁內容保有自己的最小尺寸:視窗小到放不下時,分頁會出現捲軸,而不是把表單擠扁。
遠端桌面本來就自己捲動內容,維持原樣。對於內嵌 ``AutoControlGUIWidget`` 的程式,
``widget.tabs`` 仍然以分頁內容為單位——``tabs.indexOf(page)``、
``tabs.widget(index)``、``tabs.currentWidget()`` 與 ``tabs.setCurrentWidget(page)``
收與回的都是分頁自己的 widget,不是包在外面的捲動區。

主題、字級、導覽面板是否顯示與寬度、視窗位置與大小,會存在
``~/.je_auto_control/gui_settings.ini``,下次啟動時還原。把
``JE_AUTOCONTROL_GUI_SETTINGS`` 設成另一個檔案可以換位置,設成 ``off`` 則什麼都
不記(測試套件就是這樣跑的)。

關閉分頁會保留它的 widget,再開啟時維持離開時的樣子。
``AutoControlGUIWidget.close_tab(key, release=True)`` 則是放掉它:先呼叫 widget
選擇性實作的 ``dispose()``——分頁在這裡停掉計時器與執行緒、移除它註冊的監聽——
再刪除 widget,下一次 ``open_tab(key)`` 會建立新的。主元件自己建立的表單(自動點擊、
截圖、影像偵測、錄製、腳本、報告)只會關閉,不會被放掉。

View 選單
---------

* **View → Tabs** 可依分類(核心 / 編輯 / 偵測與視覺 / 自動化引擎 / 系統)
  顯示或隱藏任一已註冊分頁。預設版面只開啟錄製、Script Builder 與遠端
  桌面;其餘分頁一個選單點擊即可叫出。分頁可關閉——關閉等同於在 View
  選單取消勾選。
* **View → Theme** 在深色與淺色主題之間切換。兩者都出自 ``gui/theme.py`` 的同一組
  設計 token;視窗不再使用 ``qt-material``。
* **View → Text Size** 提供自動(依螢幕高度)與預設字級,即時套用在目前的主題上。

契約測試
--------

``test/unit_test/headless/test_actions_menu_gui.py`` 守護此契約:每個已
註冊分頁都必須透過註冊宣告或 ``menu_actions()`` 掛鉤呈現指令(兩個豁免
分頁除外),且每個項目都必須是非空的 ``label_key`` 字串搭配可呼叫物件。
新分頁若忘了掛鉤會直接讓 CI 失敗,而不是默默出貨一個沒有任何可觸及指令
的分頁。探測程序在子行程中建構完整 widget,使 Qt 生命週期不會影響無頭
測試套件的其餘部分。

``test/unit_test/headless/test_gui_feature_parity.py`` 守其餘的部分:視窗以三個
工作流程分頁開啟、每個已註冊分頁都能從導覽面板開啟並填入 Actions 選單、640×420
的視窗會捲動而不是裁切、混合 DPI 的座標換算與 100% + 125% 桌面的實測一致。

量測 GUI
--------

兩支腳本輸出 JSON 報告,而且不會顯示視窗(使用 Qt 的 ``offscreen`` 平台,也不碰
GUI 設定檔):

.. code-block:: bash

   python benchmarks/gui_startup.py --runs 5 --output after.json
   python benchmarks/gui_workloads.py --output workloads.json
   python benchmarks/gui_startup.py --compare before.json after.json

``gui_startup.py`` 在全新的直譯器裡啟動視窗,回報 ``startup_ms``(從第一行到畫出
第一個畫面)、各階段時間與行程的記憶體。``gui_workloads.py`` 把每個分頁各開一次
(每個分頁的 ``first_open_ms``)、再切回去、在搜尋框輸入、切換主題,同時有一個 5 ms
的計時器在跳;``event_loop_p95_ms`` 就是那些 tick 晚到多久。``--compare`` 把兩份
報告並排,工作量或環境不同時拒絕比較。

====================================
新功能 (2026-06-19) — 原生 UI 控制
====================================

物件級桌面自動化:透過 OS 無障礙 API 讀取與操作原生控制項,而非點像素或
OCR 文字。對原生 app 而言,這比座標/影像自動化**可靠得多**——控制項以
name / role / app / **AutomationId** 定位,因此版面改變也不會壞。

無障礙層先前只能 *列出*、*尋找*、*點擊* 元素;現在還能透過控制模式
*操作* 它們。走完整五層(facade、``AC_*`` 執行器指令、MCP 工具、Script
Builder),並提供 Windows UIAutomation 後端;無法執行該動作的後端會拋出
清楚的 ``AccessibilityNotAvailableError``。

.. contents::
   :local:
   :depth: 2


讀取與設定值
============

::

    from je_auto_control import control_get_value, control_set_value

    # 直接讀 textbox / combo 的值(不用 OCR)。
    user = control_get_value(name="Username", app_name="myapp.exe")

    # 一次設定值(不必逐鍵輸入 / 處理焦點)。
    control_set_value("alice@example.com", automation_id="emailField")

``control_get_value`` 回傳控制項的值(無相符時回傳 ``None``);
``control_set_value`` 透過 Value pattern 寫入,成功回傳 ``True``。

執行器指令:``AC_control_get_value``、``AC_control_set_value``。


呼叫與切換
==========

::

    from je_auto_control import control_invoke, control_toggle

    control_invoke(name="Sign in")          # 按下按鈕
    control_toggle(name="Remember me")      # 切換核取方塊 / 開關

``control_invoke`` 觸發控制項的預設動作(Invoke pattern);
``control_toggle`` 切換核取方塊/開關(Toggle pattern)。兩者成功皆回傳
``True``。

執行器指令:``AC_control_invoke``、``AC_control_toggle``。


讀取表格 / 清單
================

::

    from je_auto_control import read_control_table

    rows = read_control_table(name="Results", app_name="myapp.exe")
    # -> [["Sam", "30"], ["Lee", "25"], ...]

``read_control_table`` 透過 Grid pattern 把 grid/table/list 控制項讀成
逐列的儲存格字串——不用 OCR 的可靠桌面資料抓取。

執行器指令:``AC_read_table``。


定位控制項
==========

每個呼叫都接受相同的比對條件——提供能唯一辨識控制項的任意組合:

* ``name`` — 控制項的無障礙名稱 / 標籤。
* ``role`` — 控制項型別。
* ``app_name`` — 所屬應用程式(例如 ``notepad.exe``)。
* ``automation_id`` — 最穩定的識別碼(Windows AutomationId),不受版面或
  在地化影響。


平台
====

Windows UIAutomation 後端(透過 ``comtypes``)實作全部四個動作。在尚無
控制驅動的平台/後端上,呼叫會拋出帶清楚訊息的
``AccessibilityNotAvailableError``,而非默默失敗。後端可抽換,因此邏輯以
注入的 fake 後端做單元測試——不需真實 GUI。

執行緒
------

Windows 後端可以從任何執行緒呼叫。COM 物件屬於建立它的執行緒,所以每個呼叫的執行緒
都有自己的 UIAutomation 物件:某個執行緒第一次呼叫無障礙 API 時,先在該執行緒初始化
COM(主執行緒是單執行緒 apartment,與 ``comtypes`` 匯入時的行為相同,也是 GUI 工具包
需要的;其他執行緒加入多執行緒 apartment;已經在某個 apartment 裡的執行緒維持原樣),
再建立物件。沒有任何元素會從一次呼叫留到下一次,所以不會有東西跨執行緒。從 GUI 啟動
的腳本跑在工作執行緒上,它的 ``AC_a11y_*`` 指令用的是那個執行緒自己的物件;
Accessibility 與 A11y Audit 分頁的指令也因此改在工作執行緒上執行。

撰寫時的環境沒有安裝 ``comtypes``:這條規則是由測試把關的——測試裡的假 COM 物件會拒絕
任何「不是建立它的執行緒」的使用——而不是對真實的 UIAutomation 實際跑過。

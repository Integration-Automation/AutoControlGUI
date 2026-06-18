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

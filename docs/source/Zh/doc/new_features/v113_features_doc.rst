ICU-lite MessageFormat(複數 / 選擇)
===================================

``i18n_test.check_catalog`` 只比較佔位符*集合*、``interpolate`` 只做扁平 ``${var}`` 取代——兩者都無法渲染
真正在地化所需的依數量變化訊息,例如 ``"{count, plural, one {# item} other {# items}}"``。本功能實作多數應用
會用到的 ICU MessageFormat 子集。

純標準函式庫;不匯入 ``PySide6``。複數/序數類別函式為純函式,且規則 callable 可注入,因此渲染在 CI 中
完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import format_message, plural_category, ordinal_category

    plural = "{count, plural, one {# item} other {# items}}"
    format_message(plural, {"count": 1})       # '1 item'
    format_message(plural, {"count": 5})       # '5 items'

    select = "{g, select, male {He} female {She} other {They}} won"
    format_message(select, {"g": "female"})    # 'She won'

    ordinal = "{place, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}"
    format_message(ordinal, {"place": 3})      # '3rd'

    plural_category(2)                         # 'other'
    ordinal_category(3)                        # 'few'

支援:簡單 ``{name}`` 參數、``select``(如性別)、``plural`` 與 ``selectordinal`` 搭配 CLDR 類別
(``zero``/``one``/``two``/``few``/``many``/``other``)、優先於類別的精確 ``=N`` 選擇器、``#`` 數量佔位符、
複數 ``offset:``(``#`` 變為 count − offset)、巢狀參數,以及 ICU 單引號跳脫(``''`` → ``'``;``'{'`` → 字面
大括號)。``plural_rules`` / ``ordinal_rules`` 可注入自訂類別函式;``locale`` 選擇內建規則(``en``、``fr``)。

執行器命令
----------

``AC_format_message`` 接受 ``pattern`` 與 JSON ``args`` 物件並回傳 ``{text}``,可帶 ``locale``。它以 MCP 工具
``ac_format_message`` 以及 Script Builder 中 **Data** 分類下的命令提供。

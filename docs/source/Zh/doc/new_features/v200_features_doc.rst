進階 TextPattern——搜尋 / 選取 / 讀取屬性
========================================

``ax_text`` 先前提供三種整段*讀取*(document / selection / visible 文字)。它無法**搜尋**子字串、
**選取**找到的範圍,或讀取文字的**格式屬性**——而這些正是斷言「錯誤字是紅色且粗體」或在輸入前
把游標 / 選取定位到匹配文字所需。本次把 TextPattern 從「傾印文字」擴充為「查詢與操作」文字。

* :func:`find_control_text` ——``text`` 是否出現在控制項中(TextPattern.FindText,搜尋真正的
  內容,而非 OCR),
* :func:`select_control_text` ——找到 ``text`` 並選取其範圍,讓接下來的按鍵取代它
  (FindText + Select),
* :func:`control_text_attributes` ——選取範圍的字型 / 顏色格式。

每個都是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派——可透過注入 fake
backend 進行無頭測試;真正的 UIA 呼叫位於 Windows 後端。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (find_control_text, select_control_text,
                                 control_text_attributes, type_text)

    if find_control_text("TODO", name="Editor"):
        select_control_text("TODO", name="Editor")    # 選取範圍現在涵蓋 "TODO"
        type_text("DONE")                              # 取代它

    control_text_attributes(name="Editor")
    # {"font_name": "Consolas", "font_size": 11.0, "bold": True,
    #  "italic": False, "foreground_color": 16711680}

``ignore_case``(預設 ``True``)控制搜尋。控制項以 ``name`` / ``role`` / ``app_name`` /
``automation_id`` 定位(與其他 TextPattern 讀取相同)。``find_control_text`` /
``select_control_text`` 回傳 ``bool``;``control_text_attributes`` 回傳格式字典(範圍跨越混合
格式時某些值可能為 ``None``),找不到則回傳 ``None``。

執行器指令
----------

``AC_find_control_text`` / ``AC_select_control_text``(``text`` / ``ignore_case``)與
``AC_control_text_attributes``(``{found, attributes}``)。皆以對應的 ``ac_*`` MCP 工具
(find / attributes 為唯讀、select 為破壞性)及 Script Builder 指令(位於 **Native UI** 分類下)
形式提供。

透過 UIA TextPattern 讀取原生文字(文件 / 選取 / 可見)
=======================================================

``control_get_value`` 透過 UIA ValuePattern 讀取控制項,但 ValuePattern 在多行編輯框、
RichEdit / 文件控制項與網頁文字區塊上會回傳**空字串**——而這些正是你最想讀取其文字的控制項。
UIA 透過另一個模式 ``TextPattern`` 提供這些文字,它把控制項內容建模為文字範圍(text range)。
``ax_text`` 在既有的無障礙後端 ABC 之上補上三種讀取:

* :func:`get_control_text` ——整份文件的文字(``DocumentRange``),
* :func:`get_selected_text` ——目前選取的文字(``GetSelection``),
* :func:`get_visible_text` ——僅螢幕上可見的文字(``GetVisibleRanges``)。

每個函式都是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派(與無障礙模組
其餘部分相同的接縫),因此無頭核心可在任何平台透過注入 fake backend 單元測試;真正的
UI Automation 呼叫位於 Windows 後端。未實作 TextPattern 的後端會拋出
``AccessibilityNotAvailableError``。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (get_control_text, get_selected_text,
                                 get_visible_text)

    # 一個 control_get_value 會回傳 "" 的多行編輯框:
    text = get_control_text(name="Editor", role="document")
    selection = get_selected_text(name="Editor")   # 沒有選取時回傳 ""
    on_screen = get_visible_text(name="Editor")    # 略過捲動到畫面外的列

全部以 ``name`` / ``role`` / ``app_name`` / ``automation_id`` 定位控制項(與
``control_get_value`` / ``control_invoke`` 相同)。各函式以 ``str`` 回傳文字,找不到控制項或
控制項未提供 TextPattern 時回傳 ``None``;``get_selected_text`` 在找到控制項但沒有選取時
回傳 ``""``。

執行器指令
----------

``AC_get_control_text`` / ``AC_get_selected_text`` / ``AC_get_visible_text`` 各自回傳
``{"text": ...}``。皆以對應的唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Native UI**
分類下)形式提供。

豐富的 UIA 元素屬性
===================

``list_accessibility_elements`` / ``AccessibilityElement``只帶有 name / role / bounds /
app / pid / automation_id。自動化在*動作之前*常需要更多資訊:**控制項是否啟用**(別點停用的
按鈕)、**是否在畫面外**(是否真的可見)、其 **item_status**(欄位的驗證 / 錯誤文字)、
**help_text**(工具提示),以及 **accelerator_key**(以快捷鍵而非點擊來驅動它)。``ax_props``
就提供這些高價值的 UIA 屬性。

* :func:`get_element_properties` ——完整的屬性字典,
* :func:`is_element_enabled` ——常見的動作前守衛。

每個函式都是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派——可在任何平台透過
注入 fake backend 進行無頭測試;真正的 UIA 屬性讀取位於 Windows 後端。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import get_element_properties, is_element_enabled

    get_element_properties(name="Save", role="button")
    # {"enabled": False, "offscreen": False, "help_text": "Save the file",
    #  "item_status": "", "accelerator_key": "Ctrl+S", "access_key": "S",
    #  "orientation": 0}

    if is_element_enabled(name="Submit"):
        click_text("Submit")          # 別點停用的按鈕

控制項以 ``name`` / ``role`` / ``app_name`` / ``automation_id`` 定位(與其他原生控制讀取相同)。
``get_element_properties`` 回傳屬性字典,找不到控制項時回傳 ``None``;``is_element_enabled``
回傳 ``enabled`` 旗標(找不到則為 ``None``)。

執行器指令
----------

``AC_get_element_properties`` 回傳 ``{found, properties}``。以唯讀
``ac_get_element_properties`` MCP 工具及 Script Builder 指令(位於 **Native UI** 分類下)
形式提供。

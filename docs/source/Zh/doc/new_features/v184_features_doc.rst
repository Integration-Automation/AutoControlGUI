鍵盤焦點順序(Tab 序列 / WCAG 稽核 / 設定焦點)
==============================================

工具組原本不對*鍵盤*導覽做任何推理——只有滑鼠座標與元素值。``focus_order`` 補上鍵盤這一層:

* :func:`is_interactive_role` ——某角色是否通常會接受鍵盤焦點,
* :func:`tab_order` ——可聚焦元素依 ``Tab`` 鍵造訪的順序(即其閱讀順序:由上到下、由左到右),
* :func:`audit_focus_order` ——針對扁平元素清單的 WCAG 2.4.x 焦點順序報告(序列加上被標記的
  問題,例如某可聚焦元素沒有可見面積——焦點會落在看不見的地方),
* :func:`focus_control` ——將鍵盤焦點設到某控制項上(UIA ``SetFocus``)。

前三者為針對 ``AccessibilityElement`` 清單的純函式:``tab_order`` 重用
``element_parse.reading_order`` 做列分群,``is_interactive_role`` 重用
``ax_tree_walk.humanize_role``,故無重複邏輯。``focus_control`` 是對可注入的
``accessibility.backends.get_backend()`` 接縫的薄分派;真正的 ``SetFocus`` 位於 Windows 後端。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (list_accessibility_elements, tab_order,
                                 audit_focus_order, focus_control)

    elements = list_accessibility_elements(app_name="myapp.exe")
    for el in tab_order(elements):           # Tab 造訪順序
        print(el.name, el.role)

    report = audit_focus_order(elements)
    # {"order": [...], "issues": [...], "focusable_count": N, "issue_count": M}

    focus_control(name="Username", role="edit")   # 把游標放進該欄位

可聚焦性以角色判定(互動角色:Button、Edit、CheckBox、ComboBox、RadioButton、Hyperlink、
ListItem、MenuItem、Slider、Tab/TabItem、TreeItem……)。``focus_control`` 與其他原生控制
動作一樣以 ``name`` / ``role`` / ``app_name`` / ``automation_id`` 定位,回傳 ``bool``。

執行器指令
----------

``AC_tab_order`` / ``AC_audit_focus_order``(``app_name`` / ``max_results``)列出並稽核存活的
應用程式;``AC_focus_control`` 設定焦點。三者皆以對應的 ``ac_*`` MCP 工具(兩個讀取為唯讀、
``ac_focus_control`` 為破壞性)及 Script Builder 指令(位於 **Native UI** 分類下)形式提供。

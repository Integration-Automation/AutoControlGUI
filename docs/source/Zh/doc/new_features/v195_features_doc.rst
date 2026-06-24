實體化虛擬化清單 / 格線中的離畫面項目
======================================

長清單、資料格線與樹(WPF / WinUI / 檔案總管 / 虛擬化 treeview)只會實體化已捲入視野的列——
離畫面的列**完全沒有**無障礙元素。因此 ``list_accessibility_elements`` /
``read_control_table`` / ``select_control_item`` 根本看不到它,而 ``scroll_control_into_view``
也幫不上忙,因為目標元素根本還不存在。這就是經典的「長清單裡找不到元素」的牆。

``realize_item`` 補上這個缺口:它以屬性在容器內定位該項目(UI Automation
``ItemContainerPattern.FindItemByProperty``)並將其實體化(``VirtualizedItemPattern.Realize``),
使其成為一個真正、可點擊或可讀取的元素。

它是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派(與無障礙模組其餘部分相同的
接縫)——可在任何平台透過注入 fake backend 進行無頭測試;真正的 UIA 呼叫位於 Windows 後端。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import realize_item, click_accessibility_element

    # 讓一個很下方的列「存在」,然後對它操作:
    row = realize_item("Order 5000", container_name="Orders")
    if row is not None:
        click_accessibility_element(name=row.name)   # 現在是真正的元素

    realize_item("row-42", by="automation_id", container_name="DataGrid")

``item_name`` 會比對項目的 Name(``by="name"``,預設)或其 AutomationId
(``by="automation_id"``)。容器以 ``container_name`` / ``container_role`` / ``app_name`` /
``automation_id`` 定位(與其他原生控制動作相同的比對方式)。回傳實體化後的
``AccessibilityElement``,若找不到容器或項目則回傳 ``None``。

執行器指令
----------

``AC_realize_item``(``item_name`` / ``by`` / ``container_name`` / ``container_role`` /
``app_name`` / ``automation_id``)回傳 ``{found, element}``。以唯讀 ``ac_realize_item`` MCP
工具及 Script Builder 指令(位於 **Native UI** 分類下)形式提供。

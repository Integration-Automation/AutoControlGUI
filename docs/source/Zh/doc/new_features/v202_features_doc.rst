反應式 UIA 事件等待——焦點變化
==============================

無障礙錄製器每約 250 毫秒*輪詢*一次焦點元素,因此可能錯過快速的焦點轉換,且慢上四分之一秒才反應。
UIA 提供真正的事件:``wait_for_focus_change`` 阻塞於原生的 ``AddFocusChangedEventHandler``,並在
焦點移動的當下回傳——這是零延遲、不漏失的「等到焦點落在對話框上」原語,是 ``wait_for_window`` /
``wait_for_image`` 在無障礙樹上的對應。

它是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派——可在任何平台透過注入 fake
backend 進行無頭測試;真正的事件訂閱(在呼叫執行緒上、以鎖註冊 / 取消註冊)位於 Windows 後端。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import wait_for_focus_change, click_text

    click_text("Settings")
    focused = wait_for_focus_change(timeout=3)
    # {"name": "Search", "role": "ControlType_50004", "app_name": "app.exe", ...}
    if focused is not None:
        ...   # 焦點已移動——對話框 / 下一個欄位已就緒

回傳新獲得焦點的元素 ``{name, role, app_name, bounds, …}``,若在 ``timeout`` 秒內(預設 ``5``)
沒有焦點變化則回傳 ``None``。

執行器指令
----------

``AC_wait_for_focus_change``(``timeout``)回傳 ``{changed, element}``。以唯讀
``ac_wait_for_focus_change`` MCP 工具及 Script Builder 指令(位於 **Native UI** 分類下)
形式提供。

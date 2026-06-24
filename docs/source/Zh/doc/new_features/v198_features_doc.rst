移動 / 縮放元素 + 視窗狀態(UIA Transform + Window)
==================================================

這是 **UIA 元素層級**,而非 ``window_layout`` / ``window_geometry`` 的 HWND / title 層級幾何。
``TransformPattern`` 移動與縮放某個沒有自己頂層視窗的特定控制項或浮動面板(可停靠工具列、MDI
子視窗、分隔器);``WindowPattern`` 最小化 / 最大化視窗,並——最有用地——回報其 **interaction
state(互動狀態)**,這是像素或標題輪詢給不出的可靠「這視窗是否就緒 / 被 modal 擋住?」訊號。

* :func:`move_element` / :func:`resize_element` ——TransformPattern,
* :func:`set_window_state` ——最小化 / 最大化 / 還原,
* :func:`window_interaction_state` ——就緒 / 被 modal 擋住的訊號。

每個都是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派——可透過注入 fake
backend 進行無頭測試;真正的 UIA 呼叫位於 Windows 後端。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (move_element, resize_element,
                                 set_window_state, window_interaction_state)

    move_element(100, 200, name="Tool Palette")     # 重新定位浮動面板
    resize_element(640, 480, name="Preview")        # 縮放控制項
    set_window_state("maximized", name="Editor")    # normal / maximized / minimized

    if window_interaction_state(name="Editor") == "ready":
        ...   # 不是 "blocked_by_modal" / "not_responding"——可安全驅動

元素 / 視窗以 ``name`` / ``role`` / ``app_name`` / ``automation_id`` 定位(與其他原生控制動作
相同)。動作回傳 ``bool``;``window_interaction_state`` 回傳 ``ready`` / ``blocked_by_modal`` /
``not_responding`` / ``running`` / ``closing``(找不到則為 ``None``)。

執行器指令
----------

``AC_move_element``(``x`` / ``y``)、``AC_resize_element``(``width`` / ``height``)、
``AC_set_window_state``(``state``)與 ``AC_window_interaction_state``(``{state}``)。皆以對應的
``ac_*`` MCP 工具(動作類為破壞性、讀取類為唯讀)及 Script Builder 指令(位於 **Native UI**
分類下)形式提供。

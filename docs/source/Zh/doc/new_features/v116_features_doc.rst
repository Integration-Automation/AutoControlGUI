多路徑點滑鼠手勢
================

``humanize.humanized_path`` 與 ``tween_drag`` 只在*單一*起點 → 終點之間插值。真實手勢——簽名、框選
(marquee / rubber-band)、拖曳經過多個放置目標、形狀手勢——需要任意的路徑點鏈,且可在整段路徑中持續按住按鍵。

:func:`plan_path` 為純點運算(重用 ``tween_drag`` 的具名緩動),本身即可單元測試;:func:`move_along_path` 與
:func:`drag_path` 透過可注入的 ``sink`` 派發,因此手勢可在無真實輸入下測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        plan_path, move_along_path, drag_path, path_easings,
    )

    # 經過每個路徑點的緩動點列(交接點不重複)
    plan_path([(100, 100), (400, 150), (400, 500)], per_segment_steps=20)

    move_along_path([(100, 100), (400, 150), (400, 500)])      # 沿折線移動
    drag_path([(50, 50), (300, 50), (300, 300)], button="mouse_left")  # L 形拖曳

``plan_path`` 以 ``per_segment_steps`` 個緩動步驟對每個相鄰點對插值(``easing`` 為 ``path_easings()`` 中任一
名稱——``linear`` / ``ease_in_out_quad`` / ``ease_out_cubic`` / ``ease_in_cubic``),且不重複共用的交接點。
``move_along_path`` 沿路徑發出移動事件;``drag_path`` 在第一個路徑點按下、移動經過整段路徑、在最後一點放開——
用於多停靠點拖曳。兩者皆可傳入 ``sink`` 以供無頭測試。

執行器命令
----------

``AC_move_along_path`` 與 ``AC_drag_path`` 接受 ``waypoints``(JSON ``[[x, y], ...]`` 列表)以及 ``easing`` /
``per_segment_steps``(拖曳另含 ``button``)。兩者皆以 MCP 工具(``ac_move_along_path`` / ``ac_drag_path``)
以及 Script Builder 中 **Mouse** 分類下的命令提供。

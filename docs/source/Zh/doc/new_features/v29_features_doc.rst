==========================================
新功能 (2026-06-19) — 緩動拖曳
==========================================

沿曲線路徑的決定性緩動拖曳(PyAutoGUI 風格的 ``tween``),補足既有的
人性化抖動。純標準庫;走完整五層。座標數學為純函式、可單元測試;派發
透過可注入的 sink。

.. contents::
   :local:
   :depth: 2


用法
====

::

    from je_auto_control import tween_points, tween_drag, easing_names

    tween_points((0, 0), (100, 50), steps=20, easing="ease_out_cubic")
    tween_drag((0, 0), (300, 200), steps=40, easing="ease_in_out_quad")

``tween_points`` 回傳兩點之間 ``steps + 1`` 個緩動點;``tween_drag`` 在
起點按下、沿各點移動、於終點放開。緩動函式:``linear`` /
``ease_in_out_quad`` / ``ease_out_cubic`` / ``ease_in_cubic``(見
:func:`easing_names`)。對應 ``AC_tween_drag`` / ``ac_tween_drag``
(``start`` / ``end`` 以 ``[x, y]`` 表示)。

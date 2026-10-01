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

節奏控制:有些應用程式(檔案總管、繪圖軟體、遊戲)靠游標的移動判定拖曳,而不是點擊::

    tween_drag((0, 0), (300, 200), steps=24, step_delay_s=0.012, settle_s=0.08)

``step_delay_s`` 是每次移動後停多久;``settle_s`` 是按下前先停在起點、按下後、放開前各停多久。
兩者預設 0(不停),必須是有限的非負數。任何一步丟出例外時,按鍵會在 ``finally`` 裡於游標
最後到達的位置放開,而不是終點,原本的例外照樣往外丟。

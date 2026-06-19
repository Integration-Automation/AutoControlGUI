==========================================
新功能 (2026-06-19) — 語意螢幕狀態
==========================================

既有像素(視覺回歸)差異的*語意*對應物:快照 accessibility 樹、把兩份
快照差異成**出現 / 消失 / 移動**,並取得螢幕的精簡結構化**描述**。這是
agent 驗證某步效果與自我定位所需的回饋訊號。純標準庫;走完整五層。

.. contents::
   :local:
   :depth: 2


快照與差異
==========

::

    from je_auto_control import snapshot, diff_snapshots, snapshot_screen, screen_changed

    before = snapshot_screen()      # 從即時 a11y 樹取基準
    ...                              # 執行某個步驟
    delta = screen_changed()         # 與基準比對
    delta["summary"]                 # ["appeared: window Save", "moved: button OK"]

``snapshot`` 把元素正規化為 ``[{role, name, bbox}]``(識別 =
``(role, name)``);``diff_snapshots(before, after)`` 回傳 ``added`` /
``removed`` / ``moved`` 清單,加上人類可讀的 ``summary`` 與
``changed_count``。``snapshot_screen`` / ``screen_changed`` 擷取並比對*即時*
樹(會快取基準)。對應 ``AC_screen_snapshot`` / ``AC_screen_diff`` /
``AC_screen_changed``。


描述螢幕
========

::

    from je_auto_control import describe_screen

    describe_screen()    # {app, element_count, by_role: {...}, controls: [...]}

給 agent 的廉價「我在哪」:各 role 計數與互動控制項的標籤。對應
``AC_describe_screen`` / ``ac_describe_screen``(差異家族則為 ``ac_screen_*``)。

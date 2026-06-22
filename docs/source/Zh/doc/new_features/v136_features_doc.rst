多螢幕 / 虛擬桌面幾何
======================

``snap_window``、``arrange_grid`` 與版面規劃器都只取單一主螢幕 ``(width, height)``——它們對多螢幕無感:
無法在第二台顯示器上鋪排、也無法處理負原點的虛擬桌面,而 ``coordinate_space`` 只縮放模型網格。本功能補上缺少
的實體層:列舉各螢幕、計算聯集虛擬邊界、查詢某點或某視窗位於哪台螢幕、在虛擬座標與各螢幕區域座標間轉換,
並把某點重映射到另一台螢幕上的等效位置。

幾何運算皆是對純 ``Monitor`` dataclass 的算術,因此完全可單元測試;只有 ``enumerate_monitors`` 的預設 provider
會碰到 OS(透過 ``mss``),且可注入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (enumerate_monitors, monitor_at_point,
                                 virtual_bounds, to_local, remap_point)

    monitors = enumerate_monitors()
    print(virtual_bounds(monitors))            # 涵蓋所有顯示器的 (x, y, w, h)

    here = monitor_at_point(monitors, x, y)    # 此點屬於哪台螢幕
    idx, lx, ly = to_local(monitors, x, y)     # 虛擬 -> (螢幕, 區域 x, 區域 y)

    # 把某點移到另一台螢幕上的等效相對位置。
    second = remap_point(monitors[0], monitors[1], 960, 540)

``Monitor`` 帶有 ``index, x, y, width, height, scale, primary`` 與 ``work`` 區域(``.bounds`` /
``.contains(x, y)`` / ``.to_dict()``)。``virtual_bounds`` 回傳聯集框(原點可能為負);``primary_monitor`` 取主螢幕;
``monitor_for_window(rect, monitors)`` 回傳視窗主要佔據的顯示器(最大重疊);``to_virtual`` 是 ``to_local`` 的反向;
``remap_point`` 保留分數位置,因此可跨不同解析度與 DPI 運作。

執行器命令
----------

``AC_enumerate_monitors`` → ``{count, monitors, virtual_bounds}`` 與 ``AC_monitor_at_point``(``x`` / ``y``)→
``{found, monitor}``。它們以 MCP 工具 ``ac_enumerate_monitors`` / ``ac_monitor_at_point`` 以及 Script Builder 中
**Window** 分類下的命令提供。

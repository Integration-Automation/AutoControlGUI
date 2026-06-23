視窗鋪排 / 版面幾何規劃器
==========================

``save_window_layout`` / ``restore_window_layout``擷取並重播使用者已經排好的*精確*位置,``snap_window`` 把*一個*
視窗移到一半或四分之一。沒有任何功能能*計算*出全新的多視窗版面。``tile_rect``、``grid_rects`` 與 ``cascade_rects``
是純幾何規劃器:給定螢幕工作區,回傳常見鋪排版面的目標矩形——左右半、四分之一、三分之一、R×C 網格、錯位層疊——
讓腳本能以決定性方式排列應用程式視窗。

此規劃器跨平台且無裝置相依,因此完全可單元測試;它回傳的矩形可與任何視窗移動後端組合。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import tile_rect, grid_rects, cascade_rects

    left = tile_rect((0, 0, 1920, 1080), "left_third", gap=8)
    print(left.as_tuple())                  # (8, 8, 624, 1064)

    for cell in grid_rects((0, 0, 1920, 1080), rows=2, cols=3):
        window_move("Editor", *cell.as_tuple())   # 6 格網格

    plan = cascade_rects((0, 0, 1920, 1080), count=4, offset=40)

``tile_rect`` 為具名 ``slot`` 回傳 ``WindowRect``(``x, y, width, height``,含 ``.as_tuple()`` 與 ``.to_dict()``)
——見 :func:`available_slots`(``left``、``top_right``、``center``、``left_third`` …);``gap`` 內縮各邊作為鋪排間距。
``grid_rects`` 為 ``rows`` × ``cols`` 網格的每格(列優先)回傳一個矩形。``cascade_rects`` 回傳 ``count`` 個錯位、
重疊且被夾在螢幕內的矩形(``size`` 預設為工作區的 60%)。未知 slot / 非正網格維度會丟出 ``ValueError``。

執行器命令
----------

``AC_tile_rect``(``slot`` / ``screen`` / ``gap`` → ``{rect}``)、``AC_grid_rects``(``rows`` / ``cols`` / ``screen``
/ ``gap`` → ``{count, rects}``)與 ``AC_cascade_rects``(``count`` / ``screen`` / ``offset`` / ``size`` →
``{count, rects}``)。``screen`` 預設為實際主螢幕工作區。它們以 MCP 工具 ``ac_tile_rect`` / ``ac_grid_rects`` /
``ac_cascade_rects`` 以及 Script Builder 中 **Window** 分類下的命令提供。

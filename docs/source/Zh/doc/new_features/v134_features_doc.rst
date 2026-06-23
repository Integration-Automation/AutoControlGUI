排列多個視窗(網格 / 層疊)
============================

``snap_window`` 移動*一個*視窗到一半或四分之一,而 :doc:`v133_features_doc` 規劃器只*計算*矩形、並不移動任何東西。
``arrange_grid`` 與 ``arrange_cascade`` 把這個迴圈補完:給定一組視窗標題,計算版面並實際移動每個符合的視窗——
把一組應用程式視窗鋪成網格,或以對角線層疊散開,一次呼叫完成。

它們以版面規劃器取得幾何,並沿用與 ``snap_window`` 相同的可注入 ``mover`` / ``screen_size`` 接縫,因此排列邏輯
完全可在無真實視窗下做單元測試。預設 mover 目前為 Win32(其他平台在其後端完成前為 no-op)。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import arrange_grid, arrange_cascade

    # 把三個編輯器鋪成自動形狀的網格(此處 2x2,使用前 3 格)。
    arrange_grid(["Editor", "Browser", "Terminal"])

    # 或明確的 1x3 列,含 8px 間距。
    arrange_grid(["Left", "Mid", "Right"], rows=1, cols=3, gap=8)

    # 將視窗以對角線散開。
    arrange_cascade(["Doc 1", "Doc 2", "Doc 3"], offset=40)

``arrange_grid`` 把 ``titles`` 鋪成 ``rows`` × ``cols`` 網格(預設為依視窗數量的近正方自動形狀),可加 ``gap``;
``arrange_cascade`` 讓每個視窗在前一個的右下方錯位 ``offset`` 像素,尺寸為工作區的 60%。兩者都回傳實際移動的
視窗數,並對超出網格容量的視窗保持不動。

執行器命令
----------

``AC_arrange_grid``(``titles`` JSON 陣列 + ``rows`` / ``cols`` / ``gap``)與 ``AC_arrange_cascade``
(``titles`` + ``offset``),各回傳 ``{moved, count}``。它們以 MCP 工具 ``ac_arrange_grid`` / ``ac_arrange_cascade``
(有副作用)以及 Script Builder 中 **Window** 分類下的命令提供。

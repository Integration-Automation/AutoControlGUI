粗粒度標籤螢幕網格(VLM Grounding)
==================================

視覺 / VLM grounding 在模型能引用*粗粒度儲存格*(「點擊 C3 格」)時,遠比引用容易
幻覺的原始像素座標更可靠——疊加標籤網格正是向此類模型描述截圖、並將其回答對應回
座標點的標準做法。框架先前沒有這個輔助工具。``screen_grid`` 在螢幕(或子 ``region``)
上鋪設 ``rows`` x ``cols`` 網格,以試算表風格標記每個儲存格(欄字母 + 列號,左上為
``A1``),並雙向轉換。

純標準函式庫幾何;唯一裝置相依的路徑是當未提供 ``region`` 或 ``screen_size`` 時抓取
即時螢幕尺寸的預設行為,因此每個函式都可透過傳入明確區域完整單元測試。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import grid_cells, cell_for_point, point_for_cell, click

    # 以 4x4 網格向模型描述螢幕
    for cell in grid_cells(4, 4):
        print(cell.label, cell.center)

    # 模型回答「C3」-> 轉成點擊
    click(*point_for_cell("C3", 4, 4))

    # 使用者點在哪個儲存格?
    cell = cell_for_point(820, 410, 4, 4)
    print(cell.label if cell else "outside")

``grid_cells(rows, cols, *, region=None, screen_size=None)`` 回傳列優先的
``GridCell`` 物件(``label`` / ``row`` / ``col`` / ``left`` / ``top`` / ``right`` /
``bottom`` + ``center``)。``cell_for_point`` 回傳包含該點的儲存格(點在區域外則回傳
``None``);``point_for_cell`` 回傳指定儲存格的中心 ``[x, y]``,可直接點擊。標籤超過
``Z`` 後以試算表風格延續(``AA``、``AB`` …)。

執行器指令
----------

``AC_grid_cells``(``rows`` / ``cols`` / ``region`` → ``{count, cells}``)、
``AC_cell_for_point``(``x`` / ``y`` / ``rows`` / ``cols`` / ``region`` →
``{found, cell}``)與 ``AC_point_for_cell``(``label`` / ``rows`` / ``cols`` /
``region`` → ``{point}``)。三者以 MCP 工具 ``ac_grid_cells`` / ``ac_cell_for_point`` /
``ac_point_for_cell``(唯讀)及 Script Builder 指令(位於 **Image** 分類下)形式提供。

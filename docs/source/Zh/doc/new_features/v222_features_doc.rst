試行與強制動作模式(Playwright 風格)
=====================================

``actionability.act_when_ready`` 只有一種行為:等待目標可操作,再動作(或逾時丟例外)。真實流程還需要
Playwright 定義的另外兩種模式:

* **trial(試行)**——執行每一項 actionability 檢查,但*不*真正動作;只回報它*是否會*動作。
  「這個控制項準備好了嗎?」的無副作用乾跑。
* **force(強制)**——跳過檢查,*立即*動作;當閘控判斷錯誤(把控制項誤判為被遮擋 / 停用)時的刻意逃生口。

:func:`act_with_mode` 在預設的閘控(``auto``)行為之外加上這兩種,使用與閘控相同的可注入接縫,
故每種模式都能在沒有螢幕的情況下測試。重用 :func:`actionability.wait_actionable`。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import act_with_mode

    bbox = lambda: (x, y, w, h)
    click = lambda point: do_click(point[0], point[1])

    act_with_mode(click, bbox, mode="auto")    # 閘控後若就緒則點擊
    report = act_with_mode(click, bbox, mode="trial")  # 乾跑,絕不點擊
    if report["actionable"]:
        ...
    act_with_mode(click, bbox, mode="force")   # 立即點擊,不檢查

每種模式皆回傳 ``{mode, acted, actionable, reason, point, result}``:``acted`` 表示動作是否執行,
``actionable`` / ``reason`` 來自閘控(``trial`` 不動作即回報這些),``result`` 為 action 的回傳值。
actionability 探針(``region_sampler`` / ``enabled_probe`` / ``hit_tester``)與 ``config`` 一如往常轉發給閘控。
未知的 ``mode`` 會丟出 ``ValueError``。

執行器指令
----------

``AC_act_with_mode``(``x`` / ``y`` 加上 ``mode`` / ``button`` → ``{mode, acted,
actionable, reason, point}``)以所選模式點擊一個點——``trial`` 是絕不點擊的乾跑探測,``force`` 無條件點擊。
以對應的 ``ac_act_with_mode`` MCP 工具及 Script Builder 指令(位於 **Flow** 分類下)形式提供。
:func:`act_with_mode`(接受任意 action)則是 Python API 介面。

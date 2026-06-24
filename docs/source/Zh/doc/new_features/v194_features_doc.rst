單次執行的步驟時間軸(瀑布圖 + 瓶頸步驟)
==========================================

動作 profiler 把計時按步驟*名稱*跨多次執行聚合——很適合「哪個動作平均較慢」,卻無助於「為什麼
*這一次*執行很慢」。單次執行是一條有序時間軸:步驟 A 跑完、接著 B、再 C,其中某一步主導了時間。
``step_timeline`` 把一次執行的步驟轉成瀑布圖(每步距起點的偏移、其時長、其占總時間的比例),並
排名瓶頸步驟,讓你能讀懂單一慢執行,而非平均值。

* :func:`build_timeline` ——瀑布圖加上 total / busy / bottleneck / parallelism,
* :func:`critical_steps` ——主導該次執行的步驟,最長者在前。

步驟可為任何帶名稱(預設 ``"name"``)與 ``duration`` 的字典;選填 ``start`` 會把它放到絕對
時間軸上(重疊 / 平行步驟),否則步驟會背靠背排列。純標準庫;不涉及裝置,不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import build_timeline, critical_steps

    steps = [{"name": "login", "duration": 1.0},
             {"name": "load_dashboard", "duration": 4.0},
             {"name": "submit", "duration": 1.0}]

    build_timeline(steps)
    # {"steps": [{"name": "login", "offset": 0.0, "duration": 1.0, "pct": 16.7},
    #            {"name": "load_dashboard", "offset": 1.0, ..., "pct": 66.7}, ...],
    #  "total": 6.0, "busy": 6.0,
    #  "bottleneck": {"name": "load_dashboard", "duration": 4.0},
    #  "parallelism": 1.0}

    critical_steps(steps, top=2)
    # [{"name": "load_dashboard", "duration": 4.0, "pct": 66.7},
    #  {"name": "login", "duration": 1.0, "pct": 16.7}]

``total`` 是牆鐘時間跨度,``busy`` 是各步驟時長總和;``parallelism`` = busy / total,純序列執行
為 ``1.0``,步驟重疊時 ``> 1``(需提供 ``start`` 時間)。``pct`` 是每步占總時間的比例。

執行器指令
----------

``AC_build_timeline``(``steps``)與 ``AC_critical_steps``(``steps`` / ``top``)。皆以唯讀
``ac_*`` MCP 工具及 Script Builder 指令(位於 **Testing** 分類下)形式提供。

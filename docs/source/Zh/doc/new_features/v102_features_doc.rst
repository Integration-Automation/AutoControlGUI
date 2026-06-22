移動平均平滑
==========

``stats.describe`` 彙總整個樣本,``timeseries`` 把計數器滾成速率,但沒有東西能平滑雜訊訊號或加權近期點。
本功能加入尾端的簡單 / 加權 / 指數加權移動平均,以及一個通用的滾動歸約器。

純標準函式庫;不匯入 ``PySide6``。每個函式皆為純函式(輸入值、輸出 list),因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import sma, wma, ewma, rolling

    sma([1, 2, 3, 4], 2)            # [1.0, 1.5, 2.5, 3.5]
    ewma([1, 2, 3], alpha=0.5)      # [1.0, 1.5, 2.25]
    wma(values, [1, 2, 3])          # 權重對齊到最新的點
    rolling(values, 5, max)         # 通用尾端視窗歸約

``sma`` 對每個 ``window`` 點的尾端視窗取平均;``wma`` 套用給定權重(對齊最新);``ewma`` 以 ``(0, 1]`` 的
``alpha`` 平滑;``rolling`` 對每個尾端視窗套用任意歸約器。全部回傳等長 list,因此結果與輸入時間線對齊
(``resource_profiler`` FPS/CPU 序列、延遲串流等)。

執行器命令
----------

``AC_sma`` 對 ``values`` 在 ``window`` 上回傳 ``{series}``;``AC_ewma`` 對 ``alpha`` 回傳 ``{series}``。
兩者皆以 MCP 工具(``ac_sma`` / ``ac_ewma``)以及 Script Builder 中 **Data** 分類下的命令提供。

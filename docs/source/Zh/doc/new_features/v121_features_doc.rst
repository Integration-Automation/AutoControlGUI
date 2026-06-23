等待區域顏色
============

``wait_for_pixel`` 精確比對單一點,``wait_until_pixel_changes`` 偵測單點的*任何*變化——兩者都無法回答
「等到狀態燈變綠」、「等到進度條大致填滿」或「等到紅色錯誤橫幅消失」。本功能為 ``smart_waits`` 家族加入
區域顏色等待。

像素計數為純函式輔助,:func:`wait_until_color` 接受可注入的 ``sampler``,因此迴圈可在無真實螢幕下測試。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import wait_until_color

    # 等到區域中 ≥ 60% 為(接近)綠色
    wait_until_color(region=[10, 10, 210, 40], target_rgb=[0, 200, 0],
                     tolerance=15, min_fraction=0.6, timeout_s=20)

    # 等到紅色橫幅消失
    wait_until_color(region=[0, 0, 800, 60], target_rgb=[200, 0, 0],
                     present=False, timeout_s=10)

在 ``tolerance``(各通道)內接近 ``target_rgb`` 的像素會被計數。``present=True`` 時,當該比例達到
``min_fraction`` 即成功;``present=False`` 時,當其低於該值即成功。結果為 ``WaitOutcome``
(``succeeded`` / ``reason`` / ``elapsed_s`` / ``samples_taken``)。

執行器命令
----------

``AC_wait_color`` 接受 ``target_rgb``(與選用的 ``region``)為 JSON 陣列,以及 ``tolerance`` / ``min_fraction`` /
``present`` / ``timeout_s`` / ``poll_interval_s``,並回傳 ``WaitOutcome`` dict。它以 MCP 工具 ``ac_wait_color``
以及 Script Builder 中 **Flow** 分類下的命令提供。

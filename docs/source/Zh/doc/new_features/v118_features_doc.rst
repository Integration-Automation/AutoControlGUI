等待消失(阻塞式 vanish 等待)
==============================

``wait_for_image`` / ``wait_for_text`` 會阻塞直到某物*出現*,``observer`` 則以非同步回呼在消失時觸發——但先前
沒有針對影像或文字的*阻塞式*「等到這個轉圈圈 / toast / 對話框**消失**再繼續」呼叫。``wait_until_window_closed``
只涵蓋視窗。本功能為 ``smart_waits`` 家族補上缺少的 vanish 等待。

通用的 :func:`wait_until_gone` 接受任意述詞,因此其迴圈可在無真實螢幕下做無頭測試;影像 / 文字輔助函式則
從定位函式建立該述詞。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        wait_until_gone, wait_until_image_gone, wait_until_text_gone,
    )

    # 通用:等到任意述詞變為 falsey
    wait_until_gone(lambda: spinner_is_visible(), timeout_s=15)

    wait_until_image_gone("spinner.png", timeout_s=15)     # 影像離開螢幕
    wait_until_text_gone("Loading...", timeout_s=15)        # OCR 文字消失

每個皆回傳 ``WaitOutcome``(``succeeded`` / ``reason`` / ``elapsed_s`` / ``samples_taken``)——與其他 smart
waits 相同的結果型別。``gone_for_s`` 要求目標需持續缺席該段時間才算成功(可消抖閃爍的元素);
``poll_interval_s`` / ``timeout_s`` 界定迴圈。

執行器命令
----------

``AC_wait_image_gone`` 與 ``AC_wait_text_gone`` 接受目標以及 ``timeout_s`` / ``poll_interval_s`` /
``gone_for_s``(影像另含 ``detect_threshold``),並回傳 ``WaitOutcome`` dict。兩者皆以 MCP 工具
(``ac_wait_image_gone`` / ``ac_wait_text_gone``)以及 Script Builder 中 **Flow** 分類下的命令提供。

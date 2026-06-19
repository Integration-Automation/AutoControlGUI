影片步驟疊加報告
================

一次執行已產生各步驟的螢幕截圖;:func:`write_step_video` 將它們轉成可分享的逐步走查影
片,每個步驟的畫面停留數秒,並燒入其字幕 —— 以及通過/失敗的色彩橫幅。它是 HTML/JSON
報告的視覺夥伴:審查者可逐步觀看自動化做了什麼。

其編排(哪些畫面、每步重複幾幀、哪段字幕)與 OpenCV 分離:``loader``、``drawer`` 與
``writer_factory`` 三個掛鉤皆可注入,因此組裝邏輯可用假物件進行單元測試,**無需**
``cv2`` / ``numpy`` 相依。真實路徑僅在未提供這些掛鉤時才延遲匯入 ``cv2``。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import VideoStep, write_step_video

    steps = [
        VideoStep("step1.png", caption="開啟應用", status="ok"),
        VideoStep("step2.png", caption="送出表單", status="error"),
    ]
    result = write_step_video(steps, "walkthrough.mp4",
                              fps=10, seconds_per_step=2.5)
    print(result)   # {output, steps, fps, frame_count}

步驟的 ``image`` 可為檔案路徑(以 ``cv2.imread`` 讀取)或記憶體中的畫面。``status`` 為
``ok`` / ``error`` 會將字幕橫幅著色為綠 / 紅。``build_overlay_plan(steps, fps,
seconds_per_step)`` 回傳各步驟的幀計畫而不進行任何 I/O,``render_overlay_frame(frame,
caption, status)`` 則燒入單一橫幅 —— 兩者皆可單獨使用。

執行器指令
----------

``AC_write_step_video`` 接受 ``steps``(``{image, caption, status}`` 的清單,或視覺化
建構器傳入的 JSON 字串)、``output`` 路徑,以及選用的 ``fps`` / ``seconds_per_step``;
回傳 ``{output, steps, fps, frame_count}``。相同操作亦提供為 MCP 工具
``ac_write_step_video``,以及 Script Builder 中 **Report** 分類下的指令。

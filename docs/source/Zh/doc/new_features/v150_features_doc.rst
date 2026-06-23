視窗客戶區幾何
==============

``window_capture.get_window_geometry`` 回傳視窗的*外框*邊界框(供截圖),但沒有*客戶區*矩形、沒有框邊內縮運算、
也沒有客戶區→螢幕的點對應。RPA 需要「不論標題列高度 / 邊框,在此視窗客戶區的 ``(x, y)`` 點擊」——這是視窗相對
點擊的基礎。本功能加入客戶區矩形、純框邊內縮與客戶區轉螢幕輔助函式,以及一次呼叫的 ``client_point``。

``frame_insets`` / ``client_to_screen`` 是純幾何(可無頭測試);只有 ``get_client_rect`` 的預設讀取器觸及 Win32
(``GetClientRect`` + ``ClientToScreen``),且可注入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (get_client_rect, client_point, frame_insets,
                                 client_to_screen)

    # 從視窗內容原點(非標題列)往內 20px、往下 30px 點擊。
    point = client_point("Calculator", 20, 30)
    if point:
        click(*point)

    rect = get_client_rect("Calculator")               # (x, y, width, height)
    insets = frame_insets(get_window_geometry("Calculator"), rect)  # 邊框大小

``get_client_rect`` 以螢幕座標原點回傳客戶區的 ``(x, y, width, height)``(或 ``None``);``client_point`` 把客戶區
區域內的點對應到螢幕,讓點擊不論視窗外框都落在內容上。``frame_insets`` 由外框與客戶區矩形回傳
``{left, top, right, bottom}`` 邊框 / 標題列厚度,``client_to_screen`` 則是底層的純位移。

執行器命令
----------

``AC_get_client_rect``(``title`` → ``{found, rect}``)與 ``AC_client_point``(``title`` / ``x`` / ``y`` →
``{found, point}``)。它們以 MCP 工具 ``ac_get_client_rect`` / ``ac_client_point`` 以及 Script Builder 中 **Window**
分類下的命令提供。

相對滑鼠移動
============

滑鼠 wrapper 只提供絕對的 ``set_mouse_position``——先前沒有「將指標位移 ``(dx, dy)``」(pynput / PyAutoGUI 的
``moveRel`` 慣用法),而相對指標 / 畫布 / FPS 類應用與漸進式拖曳都需要它。

:func:`relative_target` 為純算術(目前位置 + 位移),可單元測試;:func:`move_mouse_relative` 讀取即時位置並
設定新位置,getter 與 setter 皆可注入,因此可在無真實指標下測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import move_mouse_relative, relative_target

    move_mouse_relative(-40, 12)        # 從目前位置往左 40、往下 12
    # {'from': [200, 200], 'to': [160, 212], 'delta': [-40, 12]}

    relative_target((100, 100), 10, -5)   # (110, 95) — 純函式、無 I/O

``move_mouse_relative`` 讀取目前位置(若無法讀取則拋出 ``AutoControlMouseException``)、加上位移、再移動過去。
``get_position`` / ``set_position`` 預設為真實滑鼠 wrapper,但可注入以供無頭測試。

執行器命令
----------

``AC_move_mouse_relative`` 接受 ``dx`` / ``dy`` 並回傳 ``{from, to, delta}``。它以 MCP 工具
``ac_move_mouse_relative`` 以及 Script Builder 中 **Mouse** 分類下的命令提供。

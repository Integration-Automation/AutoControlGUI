============
錄製與回放
============

AutoControl 可以錄製滑鼠與鍵盤事件，並透過執行器回放。

使用範例
========

.. code-block:: python

   from time import sleep
   from je_auto_control import record, stop_record, execute_action

   # 開始錄製所有滑鼠與鍵盤事件
   record()

   sleep(5)  # 錄製 5 秒

   # 停止錄製並取得動作列表
   actions = stop_record()
   print(actions)

   # 回放錄製的動作
   execute_action(actions)

.. note::

   macOS **不支援** 動作錄製功能。請參考 :doc:`/getting_started/installation` 了解平台支援詳情。

運作方式
========

1. ``record()`` 啟動背景監聽器，擷取所有滑鼠與鍵盤事件。
2. ``stop_record()`` 停止監聯器並回傳與執行器相容的動作列表。
3. ``execute_action(actions)`` 透過內建執行器回放擷取的動作。

錄製的動作格式與 :doc:`/Zh/doc/keyword_and_executor/keyword_and_executor_doc` 使用的 JSON 格式相同，
可以儲存為檔案供日後回放。

編輯錄製內容
============

原始錄製每個游標取樣都會產生一筆事件，因此檔案龐大且雜亂。
:mod:`recording_edit.editor` 的輔助函式可加以整理。它們皆為**非破壞式** —
每個都回傳新的 list，不會更動輸入。

.. code-block:: python

   from je_auto_control import (
       dedupe_moves, merge_sleeps, trim_actions, adjust_delays,
       scale_coordinates,
   )

   actions = dedupe_moves(actions)          # 將滑鼠移動連續段壓縮成最後位置
   actions = merge_sleeps(actions)          # 把連續 AC_sleep 延遲加總成一個
   actions = trim_actions(actions, 2, -1)   # 去掉頭尾
   actions = adjust_delays(actions, 0.5)    # 以 2 倍速回放
   actions = scale_coordinates(actions, 1.5, 1.5)  # 在較大螢幕上回放

``dedupe_moves`` 只保留每個連續移動段的最後一筆(任何非移動動作都會結束該
段)，通常能把錄製縮小一個數量級且不改變回放行為;傳入 ``move_commands=[...]``
可將其他指令視為移動。``merge_sleeps`` 把每段連續 ``AC_sleep`` 合併為一個
加總秒數的 sleep。

其餘輔助函式 — ``insert_action``、``remove_action``、``filter_actions`` —
補齊整個工具組。``dedupe_moves``、``merge_sleeps``、``trim_actions``、
``adjust_delays`` 與 ``scale_coordinates`` 也透過 MCP 暴露為
``ac_dedupe_moves`` / ``ac_merge_sleeps`` / ``ac_trim_actions`` /
``ac_adjust_delays`` / ``ac_scale_coordinates``。

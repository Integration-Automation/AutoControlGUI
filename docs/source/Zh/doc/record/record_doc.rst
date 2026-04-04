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

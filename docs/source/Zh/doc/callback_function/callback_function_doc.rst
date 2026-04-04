================
回調函數執行器
================

回調函數執行器允許你執行一個自動化函式，並在完成後觸發回調函式。

基本用法
========

.. code-block:: python

   from je_auto_control import callback_executor

   result = callback_executor.callback_function(
       trigger_function_name="screen_size",
       callback_function=print,
       callback_param_method="args",
       callback_function_param={"": "回調已觸發！"}
   )
   print(f"回傳值: {result}")

運作方式
========

1. ``trigger_function_name`` 指定的函式首先執行。
2. 完成後，呼叫 ``callback_function``。
3. 觸發函式的回傳值在所有回調完成後回傳。

參數說明
========

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 參數
     - 說明
   * - ``trigger_function_name``
     - 要執行的函式名稱（必須存在於 ``event_dict`` 中）
   * - ``callback_function``
     - 觸發函式完成後要呼叫的函式
   * - ``callback_function_param``
     - 傳遞給回調函式的參數（dict）
   * - ``callback_param_method``
     - ``"args"`` 表示位置引數，``"kwargs"`` 表示關鍵字引數
   * - ``**kwargs``
     - 傳遞給觸發函式的額外關鍵字引數

擴充回調執行器
==============

載入外部套件函式到回調執行器：

.. code-block:: python

   from je_auto_control import package_manager

   # 載入 time 模組的所有函式
   package_manager.add_package_to_callback_executor("time")

查看目前的事件字典：

.. code-block:: python

   from je_auto_control import callback_executor

   print(callback_executor.event_dict)

.. note::

   回調執行器的 ``event_dict`` 應該包含與主執行器相同的函式對應。
   若不一致，則為 Bug。

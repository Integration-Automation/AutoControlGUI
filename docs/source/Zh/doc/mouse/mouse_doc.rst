Mouse documentation
----

* 主要用來模擬滑鼠的控制。
* 提供模擬點擊、設定位置等功能。

以下範例是取得鍵盤的資訊，
* mouse_table 是所有可以使用的按鍵

----

.. code-block:: python
    from je_auto_control import mouse_table

    print(mouse_table)

----

以下範例是按著滑鼠，一秒後釋放滑鼠

----

.. code-block:: python
    from time import sleep

    from je_auto_control import press_mouse, release_mouse

    press_mouse("mouse_right")
    release_mouse("mouse_right")

----

以下範例是點擊並放開滑鼠

----

.. code-block:: python
    from je_auto_control import click_mouse

    click_mouse("mouse_right")

----

以下範例是檢查滑鼠位置並改變滑鼠位置

----

.. code-block:: python
    from je_auto_control import position, set_position

    print(position)
    set_position(100, 100)

----

以下範例是3秒後滑鼠會往上 scroll

----

.. code-block:: python
    from time import sleep
    from je_auto_control import scroll

    sleep(3)

    scroll(100)
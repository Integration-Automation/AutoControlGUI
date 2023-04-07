圖片偵測
----

* Image 提供了關於圖像辨識的功能。
* 定位一張圖片在螢幕中的位置。
* 定位多張圖片在螢幕中的位置。
* 定位圖片在螢幕中的位置並點擊。

主要用來在螢幕上辨識圖片並進行點擊，或是判斷圖片是否存在螢幕上。

以下範例是定位所有圖片

.. code-block:: python

    import time

    from je_auto_control import locate_all_image
    from je_auto_control import screenshot

    time.sleep(2)

    # detect_threshold 0~1 , 1 is absolute equal
    # draw_image, mark the find target

    image_data = locate_all_image(screenshot(), detect_threshold=0.9, draw_image=False)
    print(image_data)

以下範例是定位並點擊圖片

.. code-block:: python

    import time

    from je_auto_control import locate_and_click
    from je_auto_control import screenshot

    time.sleep(2)

    # detect_threshold 0~1 , 1 is absolute equal
    # draw_image, mark the find target
    image_data = locate_and_click(screenshot(), "mouse_left", detect_threshold=0.9, draw_image=False)
    print(image_data)

以下範例是定位圖片

.. code-block:: python

    import time

    from je_auto_control import locate_image_center
    from je_auto_control import screenshot

    time.sleep(2)

    # detect_threshold 0~1 , 1 is absolute equal
    # draw_image, mark the find target

    image_data = locate_image_center(screenshot(), detect_threshold=0.9, draw_image=False)
    print(image_data)


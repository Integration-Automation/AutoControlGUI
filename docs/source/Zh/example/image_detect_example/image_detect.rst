========================
AutoControl ImageDetect
========================

| 這個範例會截圖並判斷截圖是否存在

.. code-block:: python

    import time
    from je_auto_control import screenshot
    from je_auto_control import locate_image_center

    time.sleep(2)
    """
    detect_threshold 0~1 , 1 is absolute equal
    draw_image, mark the find target
    """
    image_data = locate_image_center(screenshot(), detect_threshold=0.9, draw_image=False)
    print(image_data)


| 這個範例會截圖並判斷所有截圖是否存在

.. code-block:: python

    import time
    from je_auto_control import screenshot
    from je_auto_control import locate_all_image

    time.sleep(2)
    """
    detect_threshold 0~1 , 1 is absolute equal
    draw_image, mark the find target
    """
    image_data = locate_all_image(screenshot(), detect_threshold=0.9, draw_image=False)
    print(image_data)

| 這個範例會截圖並判斷截圖是否存在並點擊

.. code-block:: python

    import time
    from je_auto_control import screenshot
    from je_auto_control import locate_and_click

    time.sleep(2)
    """
    detect_threshold 0~1 , 1 is absolute equal
    draw_image, mark the find target
    """
    image_data = locate_and_click(screenshot(), detect_threshold=0.9, draw_image=False)
    print(image_data)
    )

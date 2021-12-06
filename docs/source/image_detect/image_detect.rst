========================
AutoControlGUI ImageDetect
========================

| locate image in center

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


| locate all image

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

| locate and click image in center

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

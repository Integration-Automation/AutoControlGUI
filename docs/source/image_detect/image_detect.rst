========================
AutoControlGUI ImageDetect
========================

| locate image in center

.. code-block:: python

    import time

    from je_auto_control import locate_image_center

    """
    detect_threshold 0~1 , 1 is absolute equal
    draw_image, mark the find target
    """
    image_data = locate_image_center("../../../test_template.png", detect_threshold=0.9, draw_image=False)
    print(image_data)

| locate all image

.. code-block:: python

    import time

    from je_auto_control import locate_all_image

    """
    detect_threshold 0~1 , 1 is absolute equal
    draw_image, mark the find target
    """
    image_data = locate_all_image("../../../test_template.png", detect_threshold=0.9, draw_image=False)
    print(image_data)

| locate and click image in center

.. code-block:: python

    import time

    from je_auto_control import locate_and_click

    """
    mouse_keycode, what mouse keycode you want to click
    detect_threshold, 0~1 , 1 is absolute equal
    draw_image, mark the find target
    """
    image_data = locate_and_click("../../../test_template.png", mouse_keycode="mouse_left", detect_threshold=0.9,
                                  draw_image=False)
    print(image_data)

| screenshot and locate

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
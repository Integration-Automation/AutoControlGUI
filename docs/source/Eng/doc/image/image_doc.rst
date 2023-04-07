Image detect
----

* Image detect provides functionalities related to image recognition.
* Locating the position of a single image on the screen.
* Locating the position of multiple images on the screen.
* Locating the position of an image on the screen and clicking on it.

This is mainly used to recognize images on the screen and perform clicks or determine if the image exists on the screen.

The following example is to locate all images.

.. code-block:: python

    import time

    from je_auto_control import locate_all_image
    from je_auto_control import screenshot

    time.sleep(2)

    # detect_threshold 0~1 , 1 is absolute equal
    # draw_image, mark the find target

    image_data = locate_all_image(screenshot(), detect_threshold=0.9, draw_image=False)
    print(image_data)

The following example is used to locate and click on an image.

.. code-block:: python

    import time

    from je_auto_control import locate_and_click
    from je_auto_control import screenshot

    time.sleep(2)

    # detect_threshold 0~1 , 1 is absolute equal
    # draw_image, mark the find target
    image_data = locate_and_click(screenshot(), "mouse_left", detect_threshold=0.9, draw_image=False)
    print(image_data)

The following example locates an image.

.. code-block:: python

    import time

    from je_auto_control import locate_image_center
    from je_auto_control import screenshot

    time.sleep(2)

    # detect_threshold 0~1 , 1 is absolute equal
    # draw_image, mark the find target

    image_data = locate_image_center(screenshot(), detect_threshold=0.9, draw_image=False)
    print(image_data)


========================
AutoControlGUI Screen
========================

| Check screen width and height

.. code-block:: python

    """
    check screen width and height
    """
    from je_auto_control import size

    print(size())

| Screenshot

.. code-block:: python

    from je_auto_control import screenshot

    """
    choose screenshot region
    """
    image = screenshot(region=[300, 400, 500, 600])

    print(image)

    """
    screenshot and save
    """
    image = screenshot("test.png")

    print(image)

    """
    only screenshot
    """
    image = screenshot()

    print(image)
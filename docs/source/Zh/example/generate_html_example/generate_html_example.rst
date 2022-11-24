========================
AutoControl 產生 HTML 報告
========================

.. code-block:: python

    import sys

    from je_auto_control import test_record
    from je_auto_control import press_key
    from je_auto_control import release_key
    from je_auto_control import write
    from je_auto_control import keys_table
    from je_auto_control import generate_html

    # init test_record to record test detail
    test_record.init_total_record = True

    print(keys_table.keys())
    # do something
    press_key("shift")
    write("123456789")
    press_key("return")
    release_key("return")
    assert (write("abcdefghijklmnopqrstuvwxyz") == "abcdefghijklmnopqrstuvwxyz")
    release_key("shift")
    press_key("return")
    release_key("return")
    assert (write("abcdefghijklmnopqrstuvwxyz") == "abcdefghijklmnopqrstuvwxyz")
    press_key("return")
    release_key("return")

    # this write will print one error -> keyboard write error can't find key : ? and write remain string
    try:
        assert (write("?123456789") == "123456789")
    except Exception as error:
        print(repr(error), file=sys.stderr)
        # this write will print one error -> keyboard write error can't find key : ! and write remain string
    try:
        write("!#@L@#{@#PL#{!@#L{!#{|##PO}!@#O@!O#P!)KI#O_!K")
    except Exception as error:
        print(repr(error), file=sys.stderr)

    print(test_record.total_record_list)
    # html name is test.html and this html will recode all test detail
    # if test_record.init_total_record = True
    generate_html("test")
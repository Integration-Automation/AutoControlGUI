from je_auto_control.utils.exception.exceptions import AutoControlCantFindKeyException
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.exceptions import AutoControlKeyboardException
from je_auto_control.utils.exception.exceptions import AutoControlMouseException
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.exception.exceptions import ImageNotFoundException

exception_list = [
    AutoControlException,
    AutoControlKeyboardException,
    AutoControlMouseException,
    AutoControlScreenException,
    AutoControlCantFindKeyException,
    ImageNotFoundException
]

for value in exception_list:
    try:
        print(value)
        if value is not ImageNotFoundException:
            raise value()
        raise value("test.png")
    except Exception as error:
        print(repr(error))

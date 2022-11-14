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
try:
    for index, value in enumerate(exception_list):
        try:
            # Branch Prediction
            print(value)
            if exception_list[index] != ImageNotFoundException:
                raise exception_list[index]()
            else:
                raise exception_list[index]("test.png")
        except Exception as error:
            print(error)
except AutoControlException:
    raise AutoControlException

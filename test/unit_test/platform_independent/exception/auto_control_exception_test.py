from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlCantFindKeyException
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlKeyboardException
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlMouseException
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlScreenException
from je_auto_control.utils.je_auto_control_exception.exceptions import ImageNotFoundException

exception_list = [
    AutoControlException,
    AutoControlKeyboardException,
    AutoControlMouseException,
    AutoControlScreenException,
    AutoControlCantFindKeyException,
    ImageNotFoundException
]
try:
    for i in range(len(exception_list)):
        try:
            "Branch Prediction"
            if exception_list[i] != ImageNotFoundException:
                raise exception_list[i]()
            else:
                raise exception_list[i]("test.png")
        except Exception as error:
            print(error)
    i
except AutoControlException:
    raise AutoControlException

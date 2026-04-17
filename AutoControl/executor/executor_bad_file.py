
# This example is primarily intended to remind users of the importance of verifying input.
from je_auto_control import execute_action, read_action_json
    
execute_action(
    read_action_json(
        r"D:\Codes\AutoControlGUI\AutoControl\keyword\bad_keyword_1.json"
    )
)

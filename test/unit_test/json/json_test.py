import os
import json
from queue import Queue

from je_auto_control import read_action_json
from je_auto_control import write_action_json

test_queue = Queue()
test_queue.put(("test_action", 100, 100))
test_queue.put(("test_action", 400, 400))
test_queue.put(("test_action", 200, 200))
test_list = list(test_queue.queue)
test_dumps_json = json.dumps(test_list)
print(test_dumps_json)
test_loads_json = json.loads(test_dumps_json)
print(test_loads_json)
list(test_loads_json)

write_action_json(os.getcwd() + "/test.json", test_dumps_json)
read_json = json.loads(read_action_json(os.getcwd() + "/test.json"))
print(read_json)

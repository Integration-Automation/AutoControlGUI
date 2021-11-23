from itertools import count

from je_auto_control import timeout
from time import sleep

counter = count(1)


def time_out_test_function():
    while True:
        sleep(1)
        print(next(counter))


if __name__ == "__main__":
    print(timeout(time_out_test_function, 5))

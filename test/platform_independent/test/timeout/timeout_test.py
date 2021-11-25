from itertools import count
from time import sleep

from je_auto_control import multiprocess_timeout

counter = count(1)


def time_not_out_function():
    print("Hello")


def time_out_test_function():
    while True:
        sleep(1)
        print(next(counter))


if __name__ == "__main__":
    print(multiprocess_timeout(time_not_out_function, 5))
    print(multiprocess_timeout(time_out_test_function, 5))

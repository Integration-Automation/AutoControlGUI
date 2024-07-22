import sys

from je_auto_control import start_autocontrol_socket_server

server = start_autocontrol_socket_server()
while True:
    if server.close_flag:
        sys.exit(0)

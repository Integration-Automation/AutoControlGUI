from je_auto_control import start_autocontrol_socket_server

try:
    server = start_autocontrol_socket_server()
    while not server.close_flag:
        pass
except Exception as error:
    print(repr(error))

from je_auto_control import start_autocontrol_socket_server

if "__main__" == __name__:
    server = start_autocontrol_socket_server()
    while not server.close_flag:
        pass

Socket Server API
----

.. code-block:: python

    import json
    import socketserver
    import sys
    import threading

    from je_auto_control.utils.executor.action_executor import execute_action


    class TCPServerHandler(socketserver.BaseRequestHandler):

        def handle(self):
            command_string = str(self.request.recv(8192).strip(), encoding="utf-8")
            socket = self.request
            print("command is: " + command_string, flush=True)
            if command_string == "quit_server":
                self.server.shutdown()
                self.server.close_flag = True
                print("Now quit server", flush=True)
            else:
                try:
                    execute_str = json.loads(command_string)
                    for execute_function, execute_return in execute_action(execute_str).items():
                        socket.sendto(str(execute_return).encode("utf-8"), self.client_address)
                        socket.sendto("\n".encode("utf-8"), self.client_address)
                    socket.sendto("Return_Data_Over_JE".encode("utf-8"), self.client_address)
                    socket.sendto("\n".encode("utf-8"), self.client_address)
                except Exception as error:
                    print(repr(error), file=sys.stderr)
                    try:
                        socket.sendto(str(error).encode("utf-8"), self.client_address)
                        socket.sendto("\n".encode("utf-8"), self.client_address)
                        socket.sendto("Return_Data_Over_JE".encode("utf-8"), self.client_address)
                        socket.sendto("\n".encode("utf-8"), self.client_address)
                    except Exception as error:
                        print(repr(error))


    class TCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):

        def __init__(self, server_address, RequestHandlerClass):
            super().__init__(server_address, RequestHandlerClass)
            self.close_flag: bool = False


    def start_autocontrol_socket_server(host: str = "localhost", port: int = 9938):
        if len(sys.argv) == 2:
            host = sys.argv[1]
        elif len(sys.argv) == 3:
            host = sys.argv[1]
            port = int(sys.argv[2])
        server = TCPServer((host, port), TCPServerHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        return server
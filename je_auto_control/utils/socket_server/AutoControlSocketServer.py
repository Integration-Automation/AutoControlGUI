import json
import socketserver
import threading

from je_auto_control import execute_action


class TCPServerHandler(socketserver.BaseRequestHandler):

    def handle(self):
        command_string = str(self.request.recv(8192).strip(), encoding="utf-8")
        print(command_string)
        if command_string == "quit_server":
            self.server.shutdown()
        else:
            try:
                execute_str = json.loads(command_string)
                execute_action(execute_str)
            except Exception as error:
                print(repr(error))


class TCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


def start_autocontrol_socket_server(host: str = "localhost", port: int = 9938):
    server = TCPServer((host, port), TCPServerHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return server


if "__main__" == __name__:
    start_autocontrol_socket_server()
    while True:
        pass

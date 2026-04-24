import json
import socketserver
import threading

from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


class TCPServerHandler(socketserver.BaseRequestHandler):

    def handle(self) -> None:
        command_string = str(self.request.recv(8192).strip(), encoding="utf-8")
        socket = self.request
        autocontrol_logger.info("command is: %s", command_string)
        if command_string == "quit_server":
            self.server.shutdown()
            self.server.close_flag = True
            autocontrol_logger.info("Now quit server")
        else:
            try:
                execute_str = json.loads(command_string)
                for execute_return in execute_action(execute_str).values():
                    socket.sendall(str(execute_return).encode("utf-8"))
                    socket.sendall("\n".encode("utf-8"))
                socket.sendall("Return_Data_Over_JE".encode("utf-8"))
                socket.sendall("\n".encode("utf-8"))
            except (ValueError, RuntimeError) as error:
                autocontrol_logger.error("socket command failed: %r", error)
                try:
                    socket.sendall(str(error).encode("utf-8"))
                    socket.sendall("\n".encode("utf-8"))
                    socket.sendall("Return_Data_Over_JE".encode("utf-8"))
                    socket.sendall("\n".encode("utf-8"))
                except OSError as send_error:
                    autocontrol_logger.error("send error reply failed: %r", send_error)


class TCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):

    def __init__(self, server_address, request_handler_class):
        super().__init__(server_address, request_handler_class)
        self.close_flag: bool = False


def start_autocontrol_socket_server(host: str = "127.0.0.1", port: int = 9938) -> TCPServer:
    """
    Start the AutoControl TCP command server.
    啟動 AutoControl TCP 指令伺服器。

    :param host: bind address; defaults to localhost for least privilege.
    :param port: TCP port to listen on.
    """
    server = TCPServer((host, port), TCPServerHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return server

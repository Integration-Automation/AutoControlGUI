import json
import socketserver
import threading

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_RECV_CHUNK_BYTES = 8192
# Safety cap so a client that never sends the newline terminator can't make us
# buffer without bound. Generous enough for very large action scripts.
_MAX_COMMAND_BYTES = 8 * 1024 * 1024
_COMMAND_TERMINATOR = b"\n"


def _read_command(request) -> str:
    """Read one newline-terminated command, spanning as many TCP reads as needed.

    A single ``recv`` returns whatever one TCP segment carried, not the whole
    message, so a >8 KiB script was silently truncated and then failed to parse.
    Accumulate chunks until the client's ``\\n`` terminator arrives (matching the
    request framing every client already uses), the peer half-closes (EOF), or
    the safety cap is hit.
    """
    chunks = []
    total = 0
    while True:
        chunk = request.recv(_RECV_CHUNK_BYTES)
        if not chunk:
            break  # EOF: peer finished sending
        chunks.append(chunk)
        total += len(chunk)
        if _COMMAND_TERMINATOR in chunk or total >= _MAX_COMMAND_BYTES:
            break
    return str(b"".join(chunks).strip(), encoding="utf-8")


def _close_server_async(server: socketserver.TCPServer) -> None:
    """Shut the server down and release its port, off the handler thread.

    必須另開執行緒:ThreadingMixIn.server_close() 會 join 所有 handler
    執行緒,若由 handler 自己呼叫就會 "cannot join current thread"。
    Must run on its own thread. shutdown() waits for the serve_forever loop,
    and ThreadingMixIn.server_close() joins every handler thread — including
    the one that asked to quit, which raises "cannot join current thread".

    server_close() is the part that actually frees the port: shutdown() only
    stops the accept loop, leaving the listening socket open, so a restart on
    the same port failed with EADDRINUSE / WinError 10048.
    """
    def _close() -> None:
        server.shutdown()
        server.server_close()

    threading.Thread(target=_close, name="ac-socket-close",
                     daemon=True).start()


class TCPServerHandler(socketserver.BaseRequestHandler):

    def handle(self) -> None:
        command_string = _read_command(self.request)
        socket = self.request
        autocontrol_logger.info("command is: %s", command_string)
        if command_string == "quit_server":
            autocontrol_logger.info("Now quit server")
            _close_server_async(self.server)
        else:
            try:
                execute_str = json.loads(command_string)
                for execute_return in execute_action(execute_str).values():
                    socket.sendall(str(execute_return).encode("utf-8"))
                    socket.sendall("\n".encode("utf-8"))
                socket.sendall("Return_Data_Over_JE".encode("utf-8"))
                socket.sendall("\n".encode("utf-8"))
            # AutoControlException is the base of every framework error: an
            # empty payload raises AutoControlActionNullException and an unknown
            # command AutoControlActionException. Missing it here killed the
            # handler thread, so the client saw a bare EOF with no error line or
            # terminator. Catch the family and always answer with the error +
            # the Return_Data_Over_JE sentinel below.
            except (ValueError, RuntimeError, AutoControlException) as error:
                autocontrol_logger.error("socket command failed: %r", error)
                try:
                    socket.sendall(str(error).encode("utf-8"))
                    socket.sendall("\n".encode("utf-8"))
                    socket.sendall("Return_Data_Over_JE".encode("utf-8"))
                    socket.sendall("\n".encode("utf-8"))
                except OSError as send_error:
                    autocontrol_logger.error("send error reply failed: %r", send_error)


class TCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Threaded TCP command server for AutoControl.

    ``close_flag`` used to live here. It was written on quit_server and read
    by nobody in the tree — a dead flag standing in for the ``server_close()``
    that was actually missing. Ask the socket instead: ``server.socket``
    is closed once quit_server has run.
    """


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

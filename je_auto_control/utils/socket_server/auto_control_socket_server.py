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
    Accumulate chunks until the command is complete (see :func:`_is_complete`),
    the peer half-closes (EOF), or the safety cap is hit.
    """
    chunks = []
    total = 0
    while True:
        chunk = request.recv(_RECV_CHUNK_BYTES)
        if not chunk:
            break  # EOF: peer finished sending
        chunks.append(chunk)
        total += len(chunk)
        if total >= _MAX_COMMAND_BYTES:
            break
        if chunk.endswith(_COMMAND_TERMINATOR) and _is_complete(b"".join(chunks)):
            break
    # errors="replace": invalid UTF-8 then fails as bad JSON and is answered
    # with the error and the sentinel, instead of a UnicodeDecodeError that
    # escaped every handler here and dropped the client without a reply.
    return b"".join(chunks).strip().decode("utf-8", errors="replace")


def _is_complete(buffer: bytes) -> bool:
    """Whether a buffer ending in the terminator holds the whole command.

    A newline is also ordinary whitespace inside JSON, so stopping at the
    first one cut pretty-printed commands short ("Expecting value"). The
    command is complete when it parses, or when it fails before its end --
    malformed, answered with the error as before. It is still arriving when
    parsing fails exactly at the end of what has come so far.
    """
    text = buffer.strip().decode("utf-8", errors="replace")
    try:
        json.loads(text)
    except ValueError as error:
        position = getattr(error, "pos", None)
        return position is None or position < len(text)
    except RecursionError:
        # Too deep to parse: complete, and answered with the error. It used
        # to escape the read and drop the client without a reply.
        return True
    return True


def _close_server_async(server: socketserver.BaseServer) -> None:
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


_HANDLER_TIMEOUT_S = 30.0


class TCPServerHandler(socketserver.BaseRequestHandler):

    def handle(self) -> None:
        try:
            self.request.settimeout(_HANDLER_TIMEOUT_S)
            command_string = _read_command(self.request)
        except OSError as error:
            # The timeout bounds each read, not the command: a client that
            # stops sending is dropped after it, one that trickles bytes is
            # held until the size cap.
            autocontrol_logger.info("socket command read dropped: %r", error)
            return
        socket = self.request
        # Not the text itself: it may carry a vault passphrase or secret, and
        # execute_action logs the parsed list with those masked.
        autocontrol_logger.info("command received: %d characters", len(command_string))
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

    ``daemon_threads`` so a stalled handler thread never blocks interpreter
    exit (and, with the per-handler read timeout, stalled clients are dropped
    rather than accumulating non-daemon threads).

    ``close_flag`` used to live here. It was written on quit_server and read
    by nobody in the tree — a dead flag standing in for the ``server_close()``
    that was actually missing. Ask the socket instead: ``server.socket``
    is closed once quit_server has run.
    """

    daemon_threads = True


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

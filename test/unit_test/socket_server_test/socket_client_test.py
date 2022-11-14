import socket

HOST, PORT = "localhost", 9938
data = """quit_server"""

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
    client_socket.connect((HOST, PORT))
    client_socket.sendall(bytes(data + "\n", "utf-8"))
    received = str(client_socket.recv(8192), "utf-8")

import socket
import json


def receive_complete_data(sock, buffer_size=1024):
    data = b""
    while True:
        part = sock.recv(buffer_size)
        if not part:
            break
        data += part
        try:
            return json.loads(data.decode())
        except json.JSONDecodeError:
            continue  # 继续接收数据


def create_connection(target_ip, target_port):
    try:
        # 创建socket对象
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 连接到目标IP和端口
        client_socket.connect((target_ip, target_port))
        print(f"Connected to {target_ip} on port {target_port}")
        return client_socket
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def send_data(client_socket, data, buffer_size=1024):
    try:
        client_socket.sendall(data.encode())
        response_data = receive_complete_data(client_socket, buffer_size)
        return response_data
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# 去除了连接建立和关闭的部分，由调用者负责

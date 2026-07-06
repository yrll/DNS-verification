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


def send_data(target_ip, target_port, data, buffer_size=1024):
    # 创建socket对象
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # 连接到目标IP和端口
        s.connect((target_ip, target_port))
        print(f"Connected to {target_ip} on port {target_port}")

        # 发送数据
        print(f"Sending data to {target_ip}: {data}")
        s.sendall(data.encode())
        print(f"Data sent to {target_ip}")

        # 接收响应
        response_data = receive_complete_data(s, buffer_size)
        print(f"Received response from {target_ip}: {response_data}")

        return response_data
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # 关闭socket连接
        s.close()

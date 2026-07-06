import socket
import threading
import json
import networkx as nx
from config.log_config import logger
from core.check_properties import *
from config.output_config import Output

cross_function_mapping = {
    'check_delegation_inconsistency': check_delegation_inconsistency,
    'check_cyclic_zone_dependency': check_cyclic_zone_dependency
}
client_results = {}


def handle_client(client_socket, client_address, local_data, buffer_size=1024):
    try:
        with client_socket:
            data_buffer = b""
            while True:
                # 接收数据
                receive_data = client_socket.recv(buffer_size)
                if not receive_data:
                    logger.info(f"Connection closed by {client_address}")
                    break
                data_buffer += receive_data

                try:
                    # 尝试反序列化JSON数据
                    receive_data_json = json.loads(data_buffer.decode())
                    data_buffer = b""  # 成功解析，清空缓冲区
                except json.JSONDecodeError:
                    # JSON不完整，继续接收数据
                    continue

                print(f"Received data from {client_address}: {receive_data_json}: len={len(receive_data_json)}")

                # 处理数据,这里列表中只有一个数据，所以按照索引index为0，[0]应该快一点
                for receive_data in receive_data_json:
                    check_domain = receive_data['check_domain']
                    check_property = receive_data['check_property']
                    check_data = nx.node_link_graph(receive_data['check_data'])
                    if check_property == 'check_delegation_inconsistency':
                        check_flag, output_list = check_delegation_inconsistency(check_domain, check_data, local_data)
                        result_json = {
                            'check_flag': check_flag,
                            'output_list': output_list
                        }
                        client_results[client_address] = result_json
                        client_socket.sendall(json.dumps(result_json).encode())

    except json.JSONDecodeError as e:
        print(f"JSON decode error with {client_address}: {e}")
        logger.error(f"JSON decode error with {client_address}: {e}")
    except Exception as e:
        logger.error(f"An error occurred with {client_address}: {e}")
    finally:
        if client_address in client_results:
            Output.save_data(data=client_results[client_address])
            del client_results[client_address]
            # 确保关闭socket
        client_socket.close()


def start_server(ip, port, local_data, buffer_size=1024):
    # 创建socket对象
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # 绑定到IP地址和端口
        server.bind((ip, port))
        # 开始监听传入连接
        server.listen(1)
        print(f"Server listening on {ip}:{port}")
        logger.info(f"Server listening on {ip}:{port}")
        while True:
            # 接受一个连接，返回一个新的socket用于通信
            client_socket, client_address = server.accept()
            print(f"Connected by {client_address}")

            # 为每个连接创建一个新的线程
            thread = threading.Thread(target=handle_client,
                                      args=(client_socket, client_address, local_data, buffer_size))
            thread.start()
    except KeyboardInterrupt:
        logger.info("Server is shutting down.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # 确保关闭服务器socket
        server.close()

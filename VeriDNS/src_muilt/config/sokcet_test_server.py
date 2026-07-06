import socket
import threading
import json
import networkx as nx
from config.log_config import setup_logging
from core.check_properties import *
from config.output_config import Output
import psutil
from time import perf_counter_ns, sleep
import pandas as pd
import os

cross_function_mapping = {
    'check_delegation_inconsistency': check_delegation_inconsistency,
    'check_cyclic_zone_dependency': check_cyclic_zone_dependency
}
client_results = {}
logger = setup_logging(log_file="run_distributed_server.log")
# 获取当前进程的对象
process = psutil.Process()

def find_zone_by_check_domain(local_data, check_domain):
    check_domain_zone = '.'.join(check_domain.split('.')[-3:])
    for zone_info in local_data:
        if zone_info['origin'].endswith(check_domain_zone):
            # logger.info(f"Found zone for {check_domain_zone}: {zone_info['origin']}")
            return zone_info['zone_glue_graph']
    return None


def handle_client(client_socket, client_address, local_data, buffer_size=1024):
    check_time_all = []
    cpu_usage_all = []
    memory_usage_all = []
    check_domain = ""
    try:
        with client_socket:
            data_buffer = b""
            while True:
                # 接收数据
                receive_data = client_socket.recv(buffer_size)
                if not receive_data:
                    break
                data_buffer += receive_data

                try:
                    # 尝试反序列化JSON数据
                    receive_data_json = json.loads(data_buffer.decode())
                    data_buffer = b""  # 成功解析，清空缓冲区
                except json.JSONDecodeError:
                    # JSON不完整，继续接收数据
                    continue

                # 处理数据,这里列表中只有一个数据，所以按照索引index为0，[0]应该快一点
                
                # for receive_data in receive_data_json:
                check_domain = receive_data_json['check_domain']
                check_property = receive_data_json['check_property']
                check_data = nx.node_link_graph(receive_data_json['check_data'])
               
                # 调用相应的检查函数，并返回检查结果和输出列表
                if check_property == 'check_delegation_inconsistency':
                    local_data_zone = find_zone_by_check_domain(local_data, check_domain)
                    if local_data_zone:
                        start_time = perf_counter_ns()
                        check_flag, output_list = check_delegation_inconsistency(check_domain, check_data, local_data_zone)
                        end_time = perf_counter_ns()

                        check_time = (end_time - start_time) / 1e9
                        check_time_all.append(check_time)
                        cpu_usage = process.cpu_percent(interval=None)
                        memory_info = process.memory_info()
                        memory_usage = memory_info.rss  # 以字节为单位

                        cpu_usage_all.append(cpu_usage)
                        memory_usage_all.append(memory_usage / 1024 / 1024)

                        result_json = {
                            'check_flag': check_flag,
                            'output_list': output_list
                        }
                        client_results[client_address] = result_json
                        # print(f"result_json: {result_json}")
                        client_socket.sendall(json.dumps(result_json).encode())
                    else:
                       
                        client_socket.sendall(json.dumps({'error': f"Failed to find any zone for {check_domain}"}).encode())
                        logger.error(f"Failed to find any zone for {check_domain}, client_address: {client_address}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error with {client_address}: {e}")
    except Exception as e:
        logger.error(f"An error occurred with {client_address}: {e}")
    finally:

        if client_address in client_results:
            save_to_csv(f"server_{client_address[0]}_{check_domain}_metrics.csv", check_time_all, cpu_usage_all,
                        memory_usage_all)  # 保存数据到CSV文件
            del client_results[client_address]
            # 确保关闭socket
        client_socket.close()


def save_to_csv(file_name, check_time_all, cpu_usage_all, memory_usage_all):
    try:
        df = pd.DataFrame({
            'Check Time (s)': check_time_all,
            'CPU Usage (%)': cpu_usage_all,
            'Memory Usage (MB)': memory_usage_all
        })
        # 检查文件是否存在
        file_exists = os.path.isfile(file_name)
        # 如果文件存在，使用 mode='a' 追加数据，否则创建新文件
        df.to_csv(f'{file_name}', mode='a', index=False, header=not file_exists)
        logger.info(f"Server metrics saved to {file_name}")
    except Exception as e:
        logger.error(f"Failed to save server metrics to CSV: {e}")


def start_server(ip, port, local_data, buffer_size=1024):
    # 创建socket对象
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # 绑定到IP地址和端口
        server.bind((ip, port))
        # 开始监听传入连接
        server.listen(1000)
        
        logger.info(f"Server listening on {ip}:{port}")
        while True:
            # 接受一个连接，返回一个新的socket用于通信
            client_socket, client_address = server.accept()
            # print(f"Connected by {client_address}")

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

import os
import json
from time import perf_counter_ns, sleep
from core.zone_graph import ZoneGraph
from tools.zone_file_parser import ZoneFileParser
from config.check_config import *
import csv
from pathlib import Path
import psutil
import pandas as pd
import logging
import datetime
import config.sokcet_test_client as client_config
from threading import Thread
from queue import Queue

logging.basicConfig(filename='run_client.log', level=logging.INFO)
logger = logging.getLogger()


def run_single_file(dataset_path):
    print(f"folder_path: {dataset_path}")
    # 记录开始时间
    start_time = perf_counter_ns()  # 纳秒级别
    metadata_path = os.path.join(dataset_path, 'metadata.json')
    # 读取并解析metadata.json文件
    with open(metadata_path, 'r') as file:
        metadata = json.load(file)
    # metadata.json中只有一个ZoneFiles条目，获取其FileName
    if metadata.get('ZoneFiles') and len(metadata['ZoneFiles']) > 0:
        file_name = metadata['ZoneFiles'][0].get('FileName')
    else:
        return

    zone_file_path = os.path.join(dataset_path, file_name)
    zone_file_parser = ZoneFileParser(zone_name=file_name, zone_file_path=zone_file_path)
    io_time = perf_counter_ns()  # 纳秒级别
    # 读取并解析zone文件
    origin = zone_file_parser.get_origin()
    rr_list = zone_file_parser.get_records()
    zone_graph = ZoneGraph(origin=origin, rr_list=rr_list)
    build_graph_time = perf_counter_ns()  # 纳秒级别

    # 生成zone_graph, [文件名, 记录数, 读文件时间, 构建图时间, 总时间]
    return zone_graph, [file_name, len(rr_list), (io_time - start_time) / 1e9, (build_graph_time - io_time) / 1e9,
                        (build_graph_time - start_time) / 1e9]


def save_to_csv(check_time_all, cpu_usage_all, memory_usage_all, filename):
    try:
        df = pd.DataFrame({
            'Check Time (s)': check_time_all,
            'CPU Usage (%)': cpu_usage_all,
            'Memory Usage (MB)': memory_usage_all
        })
        df.to_csv(filename, index=False)
        logger.info(f"Client metrics saved to {filename}")
    except Exception as e:
        logger.error(f"Failed to save Client metrics to CSV: {e}")


def handle_client(client_info, client_socket_port):
    # 获取当前线程的对象
    process = psutil.Process()
    # 使用队列来存储性能数据
    check_time_queue = Queue()
    cpu_usage_queue = Queue()
    memory_usage_queue = Queue()

    check_domain = client_info.get('check_domain')
    address = client_info.get('address')
    # 建立连接
    client_socket = client_config.create_connection(address, client_socket_port)
    if client_socket is None:
        logger.error(f"Failed to establish connection to {address}")
        return

    try:
        for i in range(1, run_time + 1):
            start_time = perf_counter_ns()  # 纳秒级别
            response_data = client_config.send_data(client_socket, json.dumps(client_info))
            # print(response_data)
            end_time = perf_counter_ns()  # 纳秒级别
            check_time = (end_time - start_time) / 1e9
            check_time_queue.put(check_time)

            # 获取并记录CPU和内存使用情况
            cpu_usage = process.cpu_percent(interval=None)
            memory_info = process.memory_info()
            memory_usage = memory_info.rss  # 以字节为单位

            cpu_usage_queue.put(cpu_usage)
            memory_usage_queue.put(memory_usage / 1024 / 1024)  # 转换为MB
            if i % batch_size == 0:
                logger.info(f"client to {address}have handled {i} times")
    finally:
        # 关闭连接
        client_socket.close()

    check_time_all = list(check_time_queue.queue)
    cpu_usage_all = list(cpu_usage_queue.queue)
    memory_usage_all = list(memory_usage_queue.queue)
    save_to_csv(check_time_all, cpu_usage_all, memory_usage_all, filename=f"client_to_{address}_{check_domain}.csv")


if __name__ == '__main__':
    run_time = 1000000
    batch_size = 50000

    root_path = Path.cwd()
    config_path = root_path / 'config' / 'check_cross.yml'
    # 读取配置文件
    with open(config_path, 'r', encoding='utf-8') as file:
        check_cross_config = yaml.safe_load(file)
    local_ip = check_cross_config['local_info'].get('local_ip')
    zonefile_path = check_cross_config['local_info'].get('zonefile_path')
    # zonefile_path = r'D:\codewriting_graduate\me_python\my_paper_sigcomm\dataset\com'
    socket_port = check_cross_config['socket_settings'].get('port')
    print(f"local_ip:{local_ip}")
    # print(f"local_ip: {local_ip}, zonefile_path: {zonefile_path}. socket_port:{socket_port}")
    zone_graph, result = run_single_file(zonefile_path)
    clients_info = get_check_delegation_inconsistency_client_info(glue_graph=zone_graph.get_glue_graph())
    print(f"clients_info{clients_info}")
    # 剔除 address == local_ip 的数据
    filtered_clients_info = [client_info for client_info in clients_info if client_info.get('address') != local_ip]
    logger.info(f"length of filtered_clients_info: {len(filtered_clients_info)}")

    # 为每一个 client_info 添加一个线程
    threads = []
    for client_info in filtered_clients_info:
        thread = Thread(target=handle_client, args=(client_info, socket_port))
        threads.append(thread)
        thread.start()

    # 等待所有线程完成
    for thread in threads:
        thread.join()

    logger.info(f"run_clients finished")


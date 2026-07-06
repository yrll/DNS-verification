import yaml
import os
import json
from time import perf_counter_ns, sleep
from core.zone_graph import ZoneGraph
from tools.zone_file_parser import ZoneFileParser
from core.check_properties import *
from pathlib import Path
import config.sokcet_test_server as server_config
from threading import Thread
import concurrent.futures
# import logging
import datetime
from queue import Queue
import psutil
import pandas as pd
import config.sokcet_test_client as client_config
import config.sokcet_test_server as server_config
from config.log_config import setup_logging

# 自定义log文件名

# logging.basicConfig(filename='run_client.log', level=logging.INFO)
# logger = logging.getLogger()
# # 添加文件处理程序
# file_handler = logging.FileHandler('run_client.log')
# logger.addHandler(file_handler)
# 自定义log文件名
logger = setup_logging(log_file="run_distributed_main.log")

def process_zone_file(file_name, dataset_path, origin, zone_graph_list,zone_glue_graph_list, start_time,time_log):
    zone_file_path = os.path.join(dataset_path, file_name)
    zone_file_parser = ZoneFileParser(zone_name=file_name, zone_file_path=zone_file_path, origin=origin)
    io_time = perf_counter_ns()  # 纳秒级别
    # 读取并解析zone文件 
    origin = zone_file_parser.get_origin()
    rr_list = zone_file_parser.get_records()
    zone_graph = ZoneGraph(origin=origin, rr_list=rr_list)
    build_graph_time = perf_counter_ns()  # 纳秒级别
    # [文件名, 记录数, 读文件时间, 构建图时间, 总时间]
    file_time_log=[file_name, len(rr_list), (io_time - start_time) / 1e9, (build_graph_time - io_time) / 1e9,
                        (build_graph_time - start_time) / 1e9]
    
    zone_graph_list.append({'origin': zone_graph.get_origin(), 'zone_graph': zone_graph})
    zone_glue_graph_list.append({'origin': zone_graph.get_origin(), 'zone_glue_graph': zone_graph.get_glue_graph()})
    time_log.append(file_time_log)
    # logger.info(f"file_time_log:{file_time_log}")
    # logger.info(f"rr_list: {(rr.get_record_tuple()) for rr in rr_list}")
    
def build_zone_graph(dataset_path):
    # print(f"folder_path: {dataset_path}")
    # 记录开始时间
    start_time = perf_counter_ns()  # 纳秒级别
    metadata_path = os.path.join(dataset_path, 'metadata.json')
    # 读取并解析metadata.json文件
    with open(metadata_path, 'r') as file:
        metadata = json.load(file)
    # metadata.json中只有一个ZoneFiles条目，获取其FileName
    file_name_list = []
    origin_list = []
    if metadata.get('ZoneFiles') and len(metadata['ZoneFiles']) > 0:
        for entry in metadata['ZoneFiles']:
            file_name_list.append(entry['FileName'])
            origin_list.append(entry['Origin'])
    else:
        return
    # print(f"file_name_list：{file_name_list}")
    
    zone_graph_list = []
    zone_glue_graph_list = []
    time_log=[]
    threads = []
    for file_name,origin in zip(file_name_list,origin_list):
        
        thread = Thread(target=process_zone_file, args=(file_name, dataset_path, origin, zone_graph_list,zone_glue_graph_list,start_time,time_log))
        thread.start()
        threads.append(thread)
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    end_time = perf_counter_ns()  # 纳秒级别
    # print(f"build_zone_graph finished, time: {(end_time - start_time) / 1e9}s")
    # 生成zone_graph, 
    return zone_graph_list, zone_glue_graph_list,time_log,(end_time - start_time) / 1e9


def get_clients_info(entry, check_property,local_ip):
    clients_info = []
    if check_property == 'check_delegation_inconsistency':
        clients_info = get_check_delegation_inconsistency_client_info(glue_graph=entry['zone_glue_graph'])
    elif check_property == 'check_cyclic_zone_dependency':
        clients_info = get_check_cyclic_zone_dependency_client_info(glue_graph=entry['zone_glue_graph'])
     # 剔除 address == local_ip 的数据
    filtered_clients_info = [client_info for client_info in clients_info if client_info.get('address') != local_ip]
    return filtered_clients_info
    
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


def handle_client(client_info, socket_port):
    # 获取当前线程的对象
    process = psutil.Process()
    # 使用队列来存储性能数据
    check_time_queue = Queue()
    cpu_usage_queue = Queue()
    memory_usage_queue = Queue()
    check_domain = client_info.get('check_domain')
    # print(f"check_domain: {check_domain}")
    address = client_info.get('address')
    # 建立连接
    client_socket = client_config.create_connection(address, socket_port)
    if client_socket is None:
        logger.error(f"Failed to establish connection to {address}")
        return
    try:
        # start_time = perf_counter_ns()  # 纳秒级别
        # response_data = client_config.send_data(client_socket, json.dumps(client_info))
        # end_time = perf_counter_ns()  # 纳秒级别
        # check_time = (end_time - start_time) / 1e9
        # check_time_queue.put(check_time)

        # # 获取并记录CPU和内存使用情况
        # cpu_usage = process.cpu_percent(interval=None)
        # memory_info = process.memory_info()
        # memory_usage = memory_info.rss  # 以字节为单位
        # cpu_usage_queue.put(cpu_usage)
        # memory_usage_queue.put(memory_usage / 1024 / 1024)  # 转换为MB
        # if not response_data['check_flag']:
        #     logger.info(f"response_data : {response_data}")
            
        # ===================================
            
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
                current_time = datetime.datetime.now()
                logger.info(f"{current_time} client to {address}have handled {i} times")
            if not response_data['check_flag']:
                logger.info(f"response_data : {response_data}")
    finally:
        # 关闭连接
        client_socket.close()

    check_time_all = list(check_time_queue.queue)
    cpu_usage_all = list(cpu_usage_queue.queue)
    memory_usage_all = list(memory_usage_queue.queue)
    save_to_csv(check_time_all, cpu_usage_all, memory_usage_all, filename=f"client_to_{address}_{check_domain}.csv")

def start_server_in_thread():
    server_config.start_server(socket_ip, socket_port, zone_glue_graph_list, buffer_size=4096)

if __name__ == '__main__':
    run_time = 10000
    batch_size = 500
    
    root_path = Path.cwd()
    config_path = root_path / 'config' / 'check_cross.yml'
    # 读取配置文件
    with open(config_path, 'r', encoding='utf-8') as file:
        check_cross_config = yaml.safe_load(file)
    socket_ip = check_cross_config['socket_settings'].get('ip')
    socket_port = check_cross_config['socket_settings'].get('port')
    zonefile_path = check_cross_config['local_info'].get('zonefile_path')
    local_ip = check_cross_config['local_info'].get('local_ip')
    check_property_list = check_cross_config['check_property']
    
    # print(f"check_property_list: {check_property_list}")
    
    start_time = perf_counter_ns()  # 纳秒级别
    zone_graph_list, zone_glue_graph_list, each_time_log, total_time = build_zone_graph(zonefile_path)
    # build_zone_graph_time = perf_counter_ns()  # 纳秒级别
    # logger.info(f"build_zone_graph_time: {(build_zone_graph_time - start_time)/1e9} s")
    # print(f"each_time_log: {each_time_log}")
    # print(f"total_time: {total_time} s")
    # 启动服务器的单独线程
    
    # # ======================= start server =======================
    # 启动服务器的单独线程
    server_thread = Thread(target=start_server_in_thread)
    server_thread.start()
    
    sleep(5)

    # ======================= start client =======================
    filtered_clients_info_all = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # 提交任务
        futures = []
        for entry in zone_glue_graph_list:
            for check_property in check_property_list:
                futures.append(executor.submit(get_clients_info, entry, check_property['name'],local_ip))
        # 获取结果
        for future in concurrent.futures.as_completed(futures):
            filtered_clients_info = future.result()
            if filtered_clients_info:  # 如果filtered_clients_info不为空
                filtered_clients_info_all.extend(filtered_clients_info)
                # for entry in filtered_clients_info:
                #     logger.info(f"entry: {entry }")
      
    # 为每一个 client_info 添加一个线程
    threads = []
    for client_info in filtered_clients_info_all:
        thread = Thread(target=handle_client, args=(client_info, socket_port))
        threads.append(thread)
        thread.start()

    # 等待所有线程完成
    for thread in threads:
        thread.join()

    
    
    # logger.info(f'have finished all the checks')
    # import os
    # current_directory = os.getcwd()
    # print("当前工作目录:", current_directory)
    
    # print(f"zone_graph_list: {zone_glue_graph_list}")
    # print(f"time_log: {time_log}")
    # server_config.start_server(socket_ip, socket_port, zone_glue_graph_list, buffer_size=4096)
    # filtered_clients_info_all = []
    # for entry in zone_glue_graph_list:
    #     for check_property in check_property_list:
    #         if check_property == 'delegation_inconsistency':
    #             clients_info = get_check_delegation_inconsistency_client_info(glue_graph=entry['zone_glue_graph'])
    #         elif check_property == 'check_cyclic_zone_dependency':
    #             clients_info = get_check_cyclic_zone_dependency_client_info(glue_graph=entry['zone_glue_graph'])
    #         # 剔除 address == local_ip 的数据
    #         filtered_clients_info = [client_info for client_info in clients_info if client_info.get('address') != local_ip]
    #         filtered_clients_info_all.append(filtered_clients_info)
    # print(f"filtered_clients_info: {filtered_clients_info} \n \n")
    #  使用ThreadPoolExecutor并发处理
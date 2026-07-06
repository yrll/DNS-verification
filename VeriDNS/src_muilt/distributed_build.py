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
import logging
import datetime
from queue import Queue
import psutil
import pandas as pd
import config.sokcet_test_client as client_config
import config.sokcet_test_server as server_config
from config.log_config import setup_logging


logger = setup_logging(log_file="run_distributed_build.log")
# logging.basicConfig(filename='run_distributed_build.log', level=logging.INFO)
# logger = logging.getLogger()
# # 添加文件处理程序
# file_handler = logging.FileHandler('run_distributed_build.log')
# logger.addHandler(file_handler)

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




if __name__ == '__main__':
    root_path = Path.cwd()
    config_path = root_path / 'config' / 'check_cross.yml'
    # 读取配置文件
    with open(config_path, 'r', encoding='utf-8') as file:
        check_cross_config = yaml.safe_load(file)
    zonefile_path = check_cross_config['local_info'].get('zonefile_path')
    
    
    
    epoch = 10000
    batch_size = 500
    write_data = []
    logger.info(f"start build_zone_graph, epoch: {epoch}")
    for i in range(epoch):
        start_time = perf_counter_ns()  # 纳秒级别
        zone_graph_list, zone_glue_graph_list, each_time_log, total_time = build_zone_graph(zonefile_path)
        # build_zone_graph_time = perf_counter_ns()  # 纳秒级别
        # logger.info(f"build_zone_graph_time: {(build_zone_graph_time - start_time)/1e9} s")
        df = pd.DataFrame(each_time_log, columns=['filename', 'record_count', 'read_time', 'build_time', 'total_time'])
        # 找出total_time最大的那一组数据
        max_total_time_row = df.sort_values(by='total_time', ascending=False).iloc[0]
        write_data.append(max_total_time_row)
        if i % batch_size == 0:
            logger.info(f"epoch: {i} finished")
        
    df_to_save = pd.DataFrame(write_data, columns=['filename', 'record_count', 'read_time', 'build_time', 'total_time'])
    df_to_save.to_csv('zone_build_time.csv', index=False)
    logger.info(f"end build_zone_graph, epoch: {epoch}")
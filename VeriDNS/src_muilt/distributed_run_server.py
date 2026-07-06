
import yaml
import os
import json
from time import perf_counter_ns, sleep
from core.zone_graph import ZoneGraph
from tools.zone_file_parser import ZoneFileParser
from pathlib import Path
import config.sokcet_test_server as server_config


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


if __name__ == '__main__':
    root_path = Path.cwd()
    config_path = root_path / 'config' / 'check_cross.yml'
    # 读取配置文件
    with open(config_path, 'r', encoding='utf-8') as file:
        check_cross_config = yaml.safe_load(file)
    socket_ip = check_cross_config['socket_settings'].get('ip')
    socket_port = check_cross_config['socket_settings'].get('port')
    zonefile_path = check_cross_config['local_info'].get('zonefile_path')

    zone_graph, result = run_single_file(zonefile_path)

    server_config.start_server(socket_ip, socket_port, zone_graph.get_glue_graph(), buffer_size=4096)

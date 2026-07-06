import os
import json
from time import perf_counter_ns
from core.zone_graph import ZoneGraph
from tools.zone_file_parser import ZoneFileParser
from config.check_config import check_self
import csv
from pathlib import Path
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import datetime

Result = namedtuple('Result', ['file_name', 'rr_count', 'io_time', 'build_graph_time', 'total_build_time', 'check_time',
                               'check_result'])


def run_single_file(folder_path):
    try:
        # 记录开始时间
        start_time = perf_counter_ns()  # 纳秒级别
        metadata_path = os.path.join(folder_path, 'metadata.json')
        # 读取并解析metadata.json文件
        with open(metadata_path, 'r') as file:
            metadata = json.load(file)
        # metadata.json中只有一个ZoneFiles条目，获取其FileName
        if metadata.get('ZoneFiles') and len(metadata['ZoneFiles']) > 0:
            file_name = metadata['ZoneFiles'][0].get('FileName')
        else:
            return None

        zone_file_path = os.path.join(folder_path, file_name)
        zone_file_parser = ZoneFileParser(
            zone_name=file_name, zone_file_path=zone_file_path)
        io_time = perf_counter_ns()  # 纳秒级别
        # 读取并解析zone文件
        origin = zone_file_parser.get_origin()
        rr_list = zone_file_parser.get_records()
        zone_graph = ZoneGraph(origin=origin, rr_list=rr_list)
        build_graph_time = perf_counter_ns()  # 纳秒级别
        check_all = check_self(zone_graph)
        check_time = perf_counter_ns()

        # 返回结果
        result_data = Result(
            file_name[:-4],
            len(rr_list),
            (io_time - start_time) / 1e9,
            (build_graph_time - io_time) / 1e9,
            (build_graph_time - start_time) / 1e9,
            (check_time - build_graph_time) / 1e9,
            {'file_name': file_name[:-4], 'check_result': check_all}
        )
        return result_data
    except Exception as e:
        logging.exception(f"Error processing {folder_path}: {e}")
        return None


def run_multiple_folders(base_path, csv_file_path, bug_result_path, batch_size=5000):
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(
            ['file_name', 'rr_count', 'io_time(s)', 'build_graph_time(s)', 'build_have_io_time(s)', 'check_time(s)'])
    results = []
    completed_sub_folders = 0
    with ThreadPoolExecutor(max_workers=os.cpu_count() * 2) as executor:
        futures = {executor.submit(run_single_file, os.path.join(base_path, name)): name for name in
                   os.listdir(base_path) if os.path.isdir(os.path.join(base_path, name))}
        for future in as_completed(futures):
            result_single_domain = future.result()
            if result_single_domain is not None:
                results.append(result_single_domain)
            completed_sub_folders += 1
            if completed_sub_folders % batch_size == 0:
                save_results(results, csv_file_path, bug_result_path)
                results = []
                current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logger.info(
                    f'{current_time} have completed {completed_sub_folders} sub folders')

    save_results(results, csv_file_path, bug_result_path)
    end_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"{end_time}:End running {check_property} check.")


def save_results(results, csv_file_path, bug_result_path):
    run_all_time = []
    check_all_result = []
    for result in results:
        file_name, rr_count, io_time, build_graph_time, total_build_time, check_time, check_result = result
        # 添加到对应的列表中
        run_all_time.append([file_name, rr_count, io_time,
                             build_graph_time, total_build_time, check_time])
        check_all_result.append(check_result)

    run_time_save(csv_file_path, run_all_time)
    bug_result_save(bug_result_path, check_all_result)


def bug_result_save(results_path, check_all_result):
    # 确保结果保存路径存在
    os.makedirs(results_path, exist_ok=True)
    # 遍历check_all_result列表
    for result in check_all_result:
        file_name = result['file_name']
        check_result = result['check_result']
        # 检查check_result是否不为空
        if check_result:
            # 去除.txt后缀
            json_file_name = file_name + '.json'
            full_path = os.path.join(results_path, json_file_name)
            with open(full_path, 'w', encoding='utf-8') as json_file:
                json.dump(check_result, json_file,
                          ensure_ascii=False, indent=4)


def run_time_save(csv_file_path, run_all_time):
    # 打开文件用于写入
    with open(csv_file_path, 'a', newline='', encoding='utf-8') as file:
        # 创建一个csv写入器
        writer = csv.writer(file)
        # 写入数据到CSV文件
        for row in run_all_time:
            writer.writerow(row)


if __name__ == '__main__':
    # 注意三个参数：check_property、dataset_path、batch_size、check_self.yml 参数
    check_property = "all"
    batch_size = 1000
    dataset_name = "census_100000_single"
    # batch_size = 1
    # dataset_name = "problems"

    start_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    start_time_str = str(start_time).replace(":", ".")
    # 设置日志记录器
    logging.basicConfig(
        filename=f'{dataset_name}_{check_property}_{start_time_str}.log', level=logging.INFO)
    logger = logging.getLogger()
    logger.info(f"{start_time}:Start running {check_property} check.")
    project_root = Path.cwd().parent
    dataset_path = project_root / f'{dataset_name}'
    # 定义CSV文件的名称
    csv_file_path = project_root / f'csv_us_{dataset_name}_{check_property}_{start_time_str}.csv'
    bug_result_path = project_root / f'us_bugs_file_{dataset_name}_{check_property}'

    run_multiple_folders(dataset_path, csv_file_path,
                         bug_result_path, batch_size=batch_size)

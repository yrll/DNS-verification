import yaml
import os

from core.zone_graph import ZoneGraph
from core.check_properties import *
import json


def check_self(zone_graph: ZoneGraph):
    file_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 读取配置文件
    with open(os.path.join(file_path, r'config/check_self.yml'), 'r', encoding='utf-8') as file:
        check_self_config = yaml.safe_load(file)

    glue_graph = zone_graph.get_glue_graph()
    all_graph = zone_graph.get_all_graph()
    cname_graph = zone_graph.get_cname_graph()
    dname_graph = zone_graph.get_dname_graph()
    # 根据配置文件中的值调用函数
    all_check_output_list = []
    if check_self_config.get('check_domain_overflow', False):
        check_flag, output_list = check_domain_overflow(all_graph)
        if not check_flag:
            all_check_output_list.extend(output_list)
    if check_self_config.get('check_miss_glue_record', False):
        check_flag, output_list, graph = check_miss_glue_record(glue_graph)
        if not check_flag:
            all_check_output_list.extend(output_list)
    if check_self_config.get('check_lame_delegation', False):
        check_flag, output_list, graph = check_lame_delegation(glue_graph)
        if not check_flag:
            all_check_output_list.extend(output_list)
    if check_self_config.get('check_non_existent_domain', False):
        check_flag, output_list = check_non_existent_domain(all_graph)
        if not check_flag:
            all_check_output_list.extend(output_list)
    if check_self_config.get('check_rewrite_blackholing', False):
        check_flag, output_list = check_rewrite_blackholing(cname_graph, dname_graph)
        if not check_flag:
            all_check_output_list.extend(output_list)
    if check_self_config.get('check_rewrite_loop', False):
        check_flag, output_list = check_rewrite_loop(cname_graph, dname_graph)
        if not check_flag:
            all_check_output_list.extend(output_list)
    return all_check_output_list


function_mapping = {
    'check_delegation_inconsistency': check_delegation_inconsistency,
    'check_cyclic_zone_dependency': check_cyclic_zone_dependency
}


def check_cross(zone_graph: ZoneGraph):
    from config.sokcet_SLD import start_server
    from config.sokcet_TLD import send_data

    file_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 读取配置文件
    with open(os.path.join(file_path, r'config/check_cross.yml'), 'r', encoding='utf-8') as file:
        check_cross_config = yaml.safe_load(file)
    # 解析YAML配置
    glue_graph = zone_graph.get_glue_graph()
    all_graph = zone_graph.get_all_graph()
    all_check_output_list = []
    # 检查是否有check_property项，并遍历它

    socket_ip = check_cross_config['socket_settings'].get('ip')
    socket_port = check_cross_config['socket_settings'].get('port')

    if 'check_property' in check_cross_config:
        for item in check_cross_config['check_property']:
            name = item.get('name')
            service = item.get('service')
            if name == 'check_delegation_inconsistency':
                if service == 'client':
                    clients_info = get_check_delegation_inconsistency_client_info(glue_graph)
                    for client_info in clients_info:
                        address = client_info.get('address')
                        if address == socket_ip:
                            continue
                        response_data = send_data(address, socket_port, data=json.dumps(clients_info))
                        print(f"response_data: {response_data}")
                        if response_data:
                            check_flag, output_list = response_data.get('check_flag'), response_data.get('output_list')
                            if not check_flag:
                                all_check_output_list.extend(output_list)
                elif service == 'server':
                    start_server(socket_ip, socket_port, glue_graph)
                    # print("server start")

    else:
        print("No 'check_property' found in the configuration.")
    return all_check_output_list

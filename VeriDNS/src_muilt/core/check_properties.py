import re

import networkx as nx
import dns.resolver
import dns.exception


def format_error_message(property_str, domain_name, error_info):
    return {
        "Property": property_str,
        "domain_name": domain_name,
        "error_message": {
            "info": error_info
        }
    }


def check_zero_time_to_live():
    pass


def check_domain_overflow(all_graph: nx.DiGraph):
    """
    REF:
        RFC 1035  https://www.rfc-editor.org/rfc/rfc1035.html
        Domain names in the IN-ADDR.ARPA domain are defined to have up to four
        labels in addition to the IN-ADDR.ARPA suffix.  Each label represents
        one octet of an Internet address, and is expressed as a character string
        for a decimal value in the range 0-255 (with leading zeros omitted
        except in the case of a zero octet which is represented by a single
        zero).
   function:
        <d,t,c,τ,v> = <domain-name, time-to-live, class, type, value>
        <d,t,c,τ,v>, the length of d and v is limited to 253 characters, and the length of t and c is limited to 63 labels.
        labels: www.google.com -> 3 labels
        character string:  www.google.com -> 15 characters
    """
    all_nodes = list(all_graph.nodes())
    check_flag = True
    output_list = []

    def is_domain_name(element):
        """
        判断是否为域名
        支持 FQDN（以 . 结尾）和普通域名格式
        """
        # 匹配域名格式：至少包含一个点，由字母数字和连字符组成
        # 支持 example.com 和 example.com. 两种格式
        # 更宽松的匹配：允许单字符标签
        pattern = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*\.)+[a-zA-Z0-9]+\.?$')
        return bool(pattern.match(element))

    domain_elements = [element for element in all_nodes if is_domain_name(element)]

    # Check if the length of domain name is less than or equal to 253 characters
    check_property = "check_domain_overflow"
    for domain_name in domain_elements:
        if len(domain_name) > 253:
            check_flag = False
            output_list.append(
                format_error_message(check_property, domain_name, "exceeds the maximum length of 253 characters"))
        labels = domain_name.split('.')
        # 过滤掉空标签（由末尾的 . 产生）
        labels = [label for label in labels if label]
        if len(labels) > 127:
            check_flag = False
            output_list.append(
                format_error_message(check_property, domain_name, "exceeds the maximum number of labels of 127"))
        for label in labels:
            if len(label) > 63:
                check_flag = False
                output_list.append(
                    format_error_message(check_property, domain_name, f"label '{label}' exceeds the maximum length of 63 characters"))
    return check_flag, output_list


def check_miss_glue_record(glue_graph: nx.DiGraph):
    """
    检查缺失的 Glue 记录
    
    根据 RFC 1912 和模型定义：
    (s_i, NS, s_j) ∈ E ∧ glue(s_i, s_j) ∧ ¬∃(s_j, t, s_k), t ∈ {A, AAAA}
    
    对于 NS 委派，如果目标 nameserver 的域名在当前 origin 下（或在被委派域的子域下），
    且没有对应的 A 或 AAAA 记录，则缺失 glue 记录。
    """
    graph = glue_graph.copy()
    origin = graph.graph.get('origin')
    in_degree = graph.in_degree()
    start_nodes = [node for node, degree in in_degree if degree == 0]
    output_list = []
    check_flag = True
    check_property = "check_miss_glue_record"
    
    for node in start_nodes:
        # 获取该节点的所有 NS 记录
        ns_edges = [(source, target, data) for source, target, data in graph.out_edges(node, data=True) 
                    if data.get('query_type') == 'NS']
        
        for source, ns_server, edge_data in ns_edges:
            # 检查 NS 服务器是否需要 glue 记录
            # 条件1: NS 服务器是当前 origin 的子域
            # 条件2: NS 服务器是被委派域的子域（in-bailiwick）
            needs_glue = False
            
            if ns_server.endswith('.' + origin) or ns_server == origin:
                # NS 服务器在当前 zone 下
                needs_glue = True
            elif ns_server.endswith('.' + source) or ns_server == source:
                # NS 服务器在被委派域的子域下（in-bailiwick nameserver）
                needs_glue = True
            
            if needs_glue:
                # 检查是否存在 A 或 AAAA 记录
                glue_records = [edge for edge in graph.out_edges(ns_server, data=True) 
                               if edge[2].get('query_type') in {'A', 'AAAA'}]
                
                if len(glue_records) == 0:
                    check_flag = False
                    output_list.append(
                        format_error_message(
                            check_property, 
                            ns_server, 
                            f"NS server '{ns_server}' for domain '{source}' is in-bailiwick but missing A/AAAA glue record"
                        )
                    )
    
    return check_flag, output_list, graph


def check_lame_delegation(glue_graph: nx.DiGraph):
    graph = glue_graph.copy()
    in_degree = graph.in_degree()
    start_nodes = [node for node, degree in in_degree if degree == 0]
    output_list = []
    check_flag = True
    check_property = "check_lame_delegation"
    for node in start_nodes:
        domain_name = str(node)
        child_nodes_edges = graph.out_edges(node, data=True)
        child_nodes = [edge[1] for edge in child_nodes_edges if edge[2]['query_type'] == 'NS']
        for ns_server in child_nodes:
            out_edges = graph.out_edges(ns_server, data=True)
            # Check if the NS server has an A record
            # if not, resolve the NS server's IP address
            ns_ip = [edge[1] for edge in out_edges if edge[2]['query_type'] == 'A']

            if len(ns_ip) == 0:
                try:
                    ns_ip = dns.resolver.resolve(ns_server, 'A')[0].to_text()
                except Exception as e:
                    output_list.append(format_error_message(check_property, domain_name=domain_name,
                                                            error_info=f"{domain_name}:{ns_server} have {str(e)}"))
                    check_flag = False
                    continue
            else:
                ns_ip = ns_ip[0]
            question = dns.message.make_query(domain_name, 'A')
            # 发送DNS查询请求到指定的名称服务器
            try:
                response = dns.query.tcp(question, ns_ip)
                # 检查响应中的AA位（Authoritative Answer）
                if not (response.flags & dns.flags.AA):
                    output_list.append(format_error_message(check_property, domain_name,
                                                            f"{ns_server} does not have an authoritative answer for {domain_name}"))
                    check_flag = False
                    continue

            except dns.query.BadResponse:
                output_list.append(format_error_message(check_property, domain_name=domain_name,
                                                        error_info=f"Bad response received from {ns_server}."))
                check_flag = False
                continue

            except Exception as e:
                output_list.append(format_error_message(check_property, domain_name=domain_name,
                                                        error_info=f"{domain_name}:{ns_server} have {str(e)}"))
                check_flag = False
                continue

    return check_flag, output_list, graph


def check_non_existent_domain(all_graph: nx.DiGraph):
    all_nodes = list(all_graph.nodes())
    output_list = []
    check_flag = True

    def is_domain_name(pattern, element):
        return bool(pattern.match(element))

    pattern = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*\.)+[a-zA-Z]{2,}$')

    domain_elements = [element for element in all_nodes if is_domain_name(pattern, element)]

    msg = ""
    for element in domain_elements:
        try:
            answers = dns.resolver.resolve(element, 'A')
        except dns.resolver.Timeout:
            msg = f"{element} Server not found or refused to answer (TIMEOUT)"
        except dns.resolver.NXDOMAIN:
            msg = f"{element} Domain does not exist (NXDOMAIN)"
        except dns.resolver.NoAnswer:
            msg = f"{element} No answer records (NoAnswer)"
        except dns.resolver.NoNameservers:
            msg = f"{element} No nameservers found (NoNameservers)"
        except dns.exception.DNSException as e:
            msg = f"{element} DNS Exception: {e}"
        except Exception as e:
            msg = f"{element} Exception: {e}"
        if msg != "":
            check_flag = False
            output_list.append(format_error_message("check_non_existent_domain", element, msg))
            msg = ""
    return check_flag, output_list


def check_rewrite_loop(cname_graph: nx.DiGraph,dname_graph: nx.DiGraph):
    origin = cname_graph.graph.get('origin')
    try:
        topological_sort = list(nx.topological_sort(cname_graph))
        has_cycle = False
    except nx.NetworkXUnfeasible:
        has_cycle = True
    if has_cycle:
        return False, [format_error_message("check_rewrite_loop", origin, f"{origin} has cname record loop ")]

    try:
        topological_sort = list(nx.topological_sort(dname_graph))
        has_cycle = False
    except nx.NetworkXUnfeasible:
        has_cycle = True
    if has_cycle:
        return False, [format_error_message("check_rewrite_loop", origin, f"{origin} has dname record loop ")]
    G_combined = nx.compose(cname_graph, dname_graph)
    try:
        topological_sort = list(nx.topological_sort(G_combined))
        has_cycle = False
    except nx.NetworkXUnfeasible:
        has_cycle = True
    if has_cycle:
        return False, [format_error_message("check_rewrite_loop", origin, f"{origin} has cname and dname record loop ")]
    return True, []


def check_rewrite_blackholing(cname_graph: nx.DiGraph, dname_graph: nx.DiGraph):
    check_flag = False
    check_loop_flag,check_loop_result=check_rewrite_loop(cname_graph,dname_graph)
    if not check_loop_flag:
        return check_loop_flag,check_loop_result
    
    G_combined = nx.compose(cname_graph, dname_graph)
    leaf_nodes = [node for node in G_combined.nodes() if G_combined.out_degree(node) == 0]
    output_list = []
    for element in leaf_nodes:
        msg = ""
        try:
            answers = dns.resolver.resolve(element, 'A')
        except dns.resolver.Timeout:
            msg = f"{element} Server not found or refused to answer (TIMEOUT)"
        except dns.resolver.NXDOMAIN:
            msg = f"{element} Domain does not exist (NXDOMAIN)"
        except dns.resolver.NoAnswer:
            msg = f"{element} No answer records (NoAnswer)"
        except dns.resolver.NoNameservers:
            msg = f"{element} No nameservers found (NoNameservers)"
        except dns.exception.DNSException as e:
            msg = f"{element} DNS Exception: {e}"
        except Exception as e:
            msg = f"{element} Exception: {e}"
        if msg != "":
            check_flag = False
            output_list.append(format_error_message("check_rewrite_blackholing", element, msg))
            msg = ""
    return check_flag, output_list


def check_answer_inconsistency():
    pass


# ================= cross-checking ==================
# 对应相同的domain的NS记录，父域的NS记录要和子域的NS记录要完全一样

# def get_check_delegation_inconsistency_client_info(glue_graph: nx.DiGraph):
#     # TLD： glue_graph:
#     # school.com NS ns1.school.com
#     # school.com NS ns2.school.com
#     # python.org NS ns1.python.org
#     # return: [school_graph, python_graph]
#
#     s_i_nodes = [node for node, degree in glue_graph.in_degree if degree == 0]
#     origin = glue_graph.graph.get('origin')
#     sub_graphs = []
#     for node in s_i_nodes:
#         sub_graph = nx.DiGraph(origin=origin)
#         sub_graph.add_node(node)
#         first_layer_edges = [(s_i, s_m, t_m) for s_i, s_m, t_m in glue_graph.out_edges(node, data=True) if
#                              t_m['query_type'] == 'NS']
#         for s_i, s_m_node, t_m in first_layer_edges:
#             sub_graph.add_edge(s_i, s_m_node, **t_m)
#             second_layer_edges = [(s_m, s_f, t_f) for s_m, s_f, t_f in glue_graph.out_edges(s_m_node, data=True) if
#                                   t_f['query_type'] in {'A', 'AAAA'}]
#             for s_m, s_f_node, t_f in second_layer_edges:
#                 sub_graph.add_edge(s_m, s_f_node, **t_f)
#
#             for s_m, s_f_node, t_f in second_layer_edges:
#                 packet_data = {
#                     'check_domain': s_i,
#                     'check_ns_server': s_m,
#                     'check_property': 'check_delegation_inconsistency',
#                     'query_type': t_f['query_type'],
#                     'address': s_f_node,
#                     'check_data': nx.node_link_data(sub_graph)
#                 }
#                 sub_graphs.append(packet_data)
#     return sub_graphs

def get_check_delegation_inconsistency_client_info(glue_graph: nx.DiGraph):
    # TLD: glue_graph:
    # school.com NS ns1.school.com
    # school.com NS ns2.school.com
    # python.org NS ns1.python.org
    # return: [school_graph, python_graph]

    s_i_nodes = [node for node, degree in glue_graph.in_degree if degree == 0]
    origin = glue_graph.graph.get('origin')
    sub_graphs = []

    for node in s_i_nodes:
        sub_graph = nx.DiGraph(origin=origin)
        sub_graph.add_node(node)

        # First layer edges
        first_layer_edges = [
            (s_i, s_m, t_m) for s_i, s_m, t_m in glue_graph.out_edges(node, data=True) if t_m['query_type'] == 'NS'
        ]
        sub_graph.add_edges_from(first_layer_edges)

        # Second layer edges
        second_layer_edges = [
            (s_m, s_f, t_f) for s_i, s_m, t_m in first_layer_edges
            for s_m, s_f, t_f in glue_graph.out_edges(s_m, data=True) if t_f['query_type'] in {'A', 'AAAA'}
        ]
        sub_graph.add_edges_from(second_layer_edges)

        for s_i, s_m_node, t_m in first_layer_edges:
            for s_m, s_f_node, t_f in [
                (s_m, s_f, t_f) for s_m, s_f, t_f in glue_graph.out_edges(s_m_node, data=True)
                if t_f['query_type'] in {'A', 'AAAA'}
            ]:
                packet_data = {
                    'check_domain': node,
                    'check_ns_server': s_m_node,
                    'check_property': 'check_delegation_inconsistency',
                    'query_type': t_f['query_type'],
                    'address': s_f_node,
                    'check_data': nx.node_link_data(sub_graph)
                }
                sub_graphs.append(packet_data)

    return sub_graphs
# def check_delegation_inconsistency(check_domain, receive_graph: nx.DiGraph, local_graph: nx.DiGraph):
#     receive_origin = receive_graph.graph.get('origin')
#     local_origin = local_graph.graph.get('origin')
#     s_i_nodes = [node for node, degree in receive_graph.in_degree if degree == 0]
#     check_flag = True
#     output_list = []
#     check_property = "check_delegation_inconsistency"
#     if check_domain not in s_i_nodes:
#         return False, [
#             format_error_message(check_property, local_origin,
#                                  f"from {receive_origin} to {local_origin}, check {check_property}, {local_origin} don't have {check_domain} records")]
#     else:
#         receive_s_m_nodes = [s_m for s_i, s_m, t_m in
#                              receive_graph.out_edges(check_domain, data=True) if t_m['query_type'] == 'NS']
#         local_s_m_nodes = [s_m for s_i, s_m, t_m in local_graph.out_edges(check_domain, data=True)
#                            if t_m['query_type'] == 'NS']
#         receive_s_m_set = set(receive_s_m_nodes)
#         local_s_m_set = set(local_s_m_nodes)
#         are_equal = set(receive_s_m_nodes) == set(local_s_m_nodes)
#         if are_equal:
#             for s_m_node in receive_s_m_nodes:
#                 receive_s_f_nodes = [s_f for s_m, s_f, t_f in
#                                      receive_graph.out_edges(s_m_node, data=True) if t_f['query_type'] in {'A', 'AAAA'}]
#                 local_s_f_nodes = [s_f for s_m, s_f, t_f in local_graph.out_edges(check_domain, data=True)
#                                    if t_f['query_type'] in {'A', 'AAAA'}]
#                 receive_s_f_set = set(receive_s_f_nodes)
#                 local_s_f_set = set(local_s_f_nodes)
#                 are_equal = set(receive_s_f_set) == set(local_s_f_set)
#                 if not are_equal:
#                     check_flag = False
#                     miss = receive_s_f_set - local_s_f_set
#                     if miss:
#                         output_list.append(
#                             format_error_message(check_property, local_origin,
#                                                  f"from {receive_origin} to {local_origin}, check {check_property}, {local_origin} {s_m_node} miss {miss} records"))
#                     else:
#                         miss = local_s_f_set - receive_s_f_set
#                         output_list.append(
#                             format_error_message(check_property, receive_origin,
#                                                  f"from {local_origin} to {receive_origin}, check {check_property}, {receive_origin} {s_m_node} miss {miss} records"))
#         else:
#             miss = receive_s_m_set - local_s_m_set
#             if miss:
#                 return False, [format_error_message(check_property, local_origin,
#                                                     f"from {receive_origin} to {local_origin}, check {check_property}, {local_origin} miss {miss} records")]
#             else:
#                 miss = local_s_m_set - receive_s_m_set
#                 return False, [format_error_message(check_property, receive_origin,
#                                                     f"from {local_origin} to {receive_origin}, check {check_property}, {receive_origin} miss {miss} records")]
#     return check_flag, output_list

def check_delegation_inconsistency(check_domain, receive_graph: nx.DiGraph, local_graph: nx.DiGraph):
    receive_origin = receive_graph.graph.get('origin')
    local_origin = local_graph.graph.get('origin')

    s_i_nodes = {node for node, degree in receive_graph.in_degree if degree == 0}
    check_property = "check_delegation_inconsistency"

    if check_domain not in s_i_nodes:
        return False, [
            format_error_message(
                check_property, local_origin,
                f"from {receive_origin} to {local_origin},  {local_origin} doesn't have {check_domain} records"
            )
        ]

    receive_s_m_nodes = {
        s_m for s_i, s_m, t_m in receive_graph.out_edges(check_domain, data=True) if t_m['query_type'] == 'NS'
    }
    local_s_m_nodes = {
        s_m for s_i, s_m, t_m in local_graph.out_edges(check_domain, data=True) if t_m['query_type'] == 'NS'
    }

    if receive_s_m_nodes != local_s_m_nodes:
        return False, [format_error_message(
            check_property, local_origin,
            f"miss NS records"
        )]
        # miss = receive_s_m_nodes - local_s_m_nodes
        # if miss:
        #     return False, [
        #         format_error_message(
        #             check_property, local_origin,
        #             f"from {receive_origin} to {local_origin},  {local_origin} misses {miss} records"
        #         )
        #     ]
        # miss = local_s_m_nodes - receive_s_m_nodes
        # return False, [
        #     format_error_message(
        #         check_property, receive_origin,
        #         f"from {local_origin} to {receive_origin},  {receive_origin} misses {miss} records"
        #     )
        # ]

    output_list = []
    check_flag = True

    for s_m_node in receive_s_m_nodes:
        receive_s_f_nodes = {
            s_f for s_m, s_f, t_f in receive_graph.out_edges(s_m_node, data=True) if t_f['query_type'] in {'A', 'AAAA'}
        }
        local_s_f_nodes = {
            s_f for s_m, s_f, t_f in local_graph.out_edges(s_m_node, data=True) if t_f['query_type'] in {'A', 'AAAA'}
        }

        if receive_s_f_nodes != local_s_f_nodes:
            check_flag = False
            output_list.append(
                format_error_message(
                    check_property, local_origin,
                    f"{s_m_node} miss records"
                )
            )
            # miss = receive_s_f_nodes - local_s_f_nodes
            # if miss:
            #     output_list.append(
            #         format_error_message(
            #             check_property, local_origin,
            #             f"from {receive_origin} to {local_origin},  {local_origin} {s_m_node} misses {miss} records"
            #         )
            #     )
            # else:
            #     miss = local_s_f_nodes - receive_s_f_nodes
            #     output_list.append(
            #         format_error_message(
            #             check_property, receive_origin,
            #             f"from {local_origin} to {receive_origin}, {receive_origin} {s_m_node} misses {miss} records"
            #         )
            #     )

    return check_flag, output_list


# ================= Cyclic Zone Dependency ==================

def get_check_cyclic_zone_dependency_client_info(glue_graph: nx.DiGraph):
    """
    为 Cyclic Zone Dependency 检测生成客户端信息
    
    遍历所有 NS 委派，为每个需要跨域验证的委派生成检测数据包。
    这些数据包将被发送到对应的 NS 服务器进行循环依赖检测。
    
    返回格式:
    [
        {
            'check_domain': 被委派的域名,
            'check_ns_server': NS 服务器名称,
            'check_property': 'check_cyclic_zone_dependency',
            'query_type': 'A' 或 'AAAA',
            'address': NS 服务器的 IP 地址,
            'check_data': 当前的委派路径信息
        },
        ...
    ]
    """
    s_i_nodes = [node for node, degree in glue_graph.in_degree if degree == 0]
    origin = glue_graph.graph.get('origin')
    client_info_list = []
    
    for node in s_i_nodes:
        # 获取所有 NS 委派边
        ns_edges = [
            (s_i, s_m, t_m) for s_i, s_m, t_m in glue_graph.out_edges(node, data=True) 
            if t_m['query_type'] == 'NS'
        ]
        
        for s_i, s_m_node, t_m in ns_edges:
            # 获取 NS 服务器的 A/AAAA 记录
            address_edges = [
                (s_m, s_f, t_f) for s_m, s_f, t_f in glue_graph.out_edges(s_m_node, data=True)
                if t_f['query_type'] in {'A', 'AAAA'}
            ]
            
            for s_m, s_f_node, t_f in address_edges:
                # 构建委派路径信息
                delegation_path = {
                    'origin': origin,
                    'delegated_domain': node,
                    'ns_server': s_m_node,
                    'delegation_edge': (node, s_m_node)
                }
                
                packet_data = {
                    'check_domain': node,
                    'check_ns_server': s_m_node,
                    'check_property': 'check_cyclic_zone_dependency',
                    'query_type': t_f['query_type'],
                    'address': s_f_node,
                    'check_data': delegation_path,
                    'delegation_path': []  # 将在检测过程中累积
                }
                client_info_list.append(packet_data)
    
    return client_info_list


def check_cyclic_zone_dependency(check_domain: str, delegation_path: list, local_graph: nx.DiGraph):
    """
    检测循环域依赖
    
    根据模型定义：
    π = {(s¹_i, NS, s¹_j), (s²_i, NS, s²_j), ..., (s^m_i, NS, s^m_i)}
    
    在解析路径中，每条委派边 (s^k_i, NS, s^k_j) 只能出现一次。
    如果同一条委派边出现多次，则存在循环依赖，会导致解析失败。
    
    参数:
        check_domain: 当前要检查的域名
        delegation_path: 已经经过的委派路径列表，格式为 [(zone1, ns1), (zone2, ns2), ...]
        local_graph: 当前域的 RSG 图
    
    返回:
        (check_flag, output_list)
        check_flag: True 表示没有循环，False 表示检测到循环
        output_list: 错误信息列表
    """
    local_origin = local_graph.graph.get('origin')
    check_property = "check_cyclic_zone_dependency"
    output_list = []
    
    # 获取当前域中的所有 NS 委派
    s_i_nodes = [node for node, degree in local_graph.in_degree if degree == 0]
    
    # 检查当前域是否包含要查询的域名
    if check_domain not in s_i_nodes:
        # 当前域不包含该域名，无法继续检测
        return True, []
    
    # 获取该域名的所有 NS 委派
    ns_edges = [
        (s_i, s_m, t_m) for s_i, s_m, t_m in local_graph.out_edges(check_domain, data=True)
        if t_m['query_type'] == 'NS'
    ]
    
    # 检查每条 NS 委派是否在路径中已经出现过
    for s_i, s_m_node, t_m in ns_edges:
        current_delegation = (s_i, s_m_node)
        
        # 检查这条委派边是否已经在路径中
        if current_delegation in delegation_path:
            # 检测到循环依赖
            cycle_path = delegation_path + [current_delegation]
            cycle_info = " -> ".join([f"({d[0]} NS {d[1]})" for d in cycle_path])
            
            output_list.append(
                format_error_message(
                    check_property,
                    local_origin,
                    f"Cyclic zone dependency detected: {cycle_info}"
                )
            )
            return False, output_list
    
    # 没有检测到循环
    return True, output_list


def check_cyclic_zone_dependency_with_path_tracking(
    check_domain: str, 
    delegation_path: list, 
    local_graph: nx.DiGraph,
    visited_zones: set = None
):
    """
    带路径追踪的循环域依赖检测（增强版）
    
    除了检测委派边的重复，还追踪访问过的域，防止更复杂的循环模式。
    
    参数:
        check_domain: 当前要检查的域名
        delegation_path: 已经经过的委派路径列表
        local_graph: 当前域的 RSG 图
        visited_zones: 已访问的域集合
    
    返回:
        (check_flag, output_list, new_delegation_path)
    """
    if visited_zones is None:
        visited_zones = set()
    
    local_origin = local_graph.graph.get('origin')
    check_property = "check_cyclic_zone_dependency"
    output_list = []
    
    # 检查当前域是否已经访问过
    if local_origin in visited_zones:
        output_list.append(
            format_error_message(
                check_property,
                local_origin,
                f"Zone '{local_origin}' has been visited before, cyclic dependency detected"
            )
        )
        return False, output_list, delegation_path
    
    # 标记当前域为已访问
    visited_zones.add(local_origin)
    
    # 获取当前域中的所有起始节点
    s_i_nodes = [node for node, degree in local_graph.in_degree if degree == 0]
    
    if check_domain not in s_i_nodes:
        # 当前域不包含该域名
        return True, [], delegation_path
    
    # 获取该域名的所有 NS 委派
    ns_edges = [
        (s_i, s_m, t_m) for s_i, s_m, t_m in local_graph.out_edges(check_domain, data=True)
        if t_m['query_type'] == 'NS'
    ]
    
    # 检查每条 NS 委派
    for s_i, s_m_node, t_m in ns_edges:
        current_delegation = (s_i, s_m_node)
        
        # 检查这条委派边是否已经在路径中
        if current_delegation in delegation_path:
            cycle_path = delegation_path + [current_delegation]
            cycle_info = " -> ".join([f"({d[0]} NS {d[1]})" for d in cycle_path])
            
            output_list.append(
                format_error_message(
                    check_property,
                    local_origin,
                    f"Cyclic delegation edge detected: {cycle_info}"
                )
            )
            return False, output_list, delegation_path
    
    # 更新委派路径
    new_delegation_path = delegation_path.copy()
    for s_i, s_m_node, t_m in ns_edges:
        new_delegation_path.append((s_i, s_m_node))
    
    return True, output_list, new_delegation_path


# ================= Cross-Checking for Rewrite Loop and Blackholing ==================

def get_check_rewrite_loop_client_info(cname_graph: nx.DiGraph, dname_graph: nx.DiGraph):
    """
    为跨域 Rewrite Loop 检测生成客户端信息
    
    当 CNAME/DNAME 链指向外部域时，需要跨域检测是否存在循环。
    
    返回格式:
    [
        {
            'check_domain': 重写链的终点域名,
            'check_property': 'check_rewrite_loop_cross',
            'rewrite_path': 已经经过的重写路径,
            'check_data': 重写链信息
        },
        ...
    ]
    """
    origin = cname_graph.graph.get('origin')
    client_info_list = []
    
    # 合并 CNAME 和 DNAME 图
    G_combined = nx.compose(cname_graph, dname_graph)
    
    # 获取所有叶子节点（重写链的终点）
    leaf_nodes = [node for node in G_combined.nodes() if G_combined.out_degree(node) == 0]
    
    for leaf_node in leaf_nodes:
        # 检查叶子节点是否在当前 origin 之外
        if not (leaf_node.endswith('.' + origin) or leaf_node == origin):
            # 这是一个外部域名，需要跨域检测
            
            # 构建到达这个叶子节点的路径
            rewrite_path = []
            # 使用 BFS 找到所有到达叶子节点的路径
            for source in G_combined.nodes():
                if G_combined.in_degree(source) == 0:  # 起始节点
                    try:
                        paths = list(nx.all_simple_paths(G_combined, source, leaf_node))
                        for path in paths:
                            # 构建路径信息
                            path_edges = []
                            for i in range(len(path) - 1):
                                edge_data = G_combined.get_edge_data(path[i], path[i+1])
                                path_edges.append((path[i], path[i+1], edge_data['query_type']))
                            rewrite_path.append(path_edges)
                    except nx.NetworkXNoPath:
                        continue
            
            if rewrite_path:
                packet_data = {
                    'check_domain': leaf_node,
                    'check_property': 'check_rewrite_loop_cross',
                    'origin': origin,
                    'rewrite_path': rewrite_path,
                    'check_data': {
                        'leaf_node': leaf_node,
                        'paths': rewrite_path
                    }
                }
                client_info_list.append(packet_data)
    
    return client_info_list


def check_rewrite_loop_cross(check_domain: str, rewrite_path: list, local_cname_graph: nx.DiGraph, 
                             local_dname_graph: nx.DiGraph):
    """
    跨域 Rewrite Loop 检测
    
    检查从外部域传入的重写路径，加上本地的重写链，是否形成循环。
    
    参数:
        check_domain: 要检查的域名（重写链的起点，也是跨域连接点）
        rewrite_path: 已经经过的重写路径（来自其他域）
                     格式: [[('source1', 'target1', 'CNAME'), ...], ...]
        local_cname_graph: 本地的 CNAME 图
        local_dname_graph: 本地的 DNAME 图
    
    返回:
        (check_flag, output_list)
    """
    local_origin = local_cname_graph.graph.get('origin')
    check_property = "check_rewrite_loop_cross"
    output_list = []
    
    # 合并本地的 CNAME 和 DNAME 图
    G_local = nx.compose(local_cname_graph, local_dname_graph)
    
    # 检查 check_domain 是否在本地图中
    if check_domain not in G_local.nodes():
        # 域名不在本地，无法继续检测
        return True, []
    
    # 构建已访问的域名集合（从 rewrite_path 中提取）
    # 注意：check_domain 本身是连接点，不应该被视为"已访问"
    visited_domains = set()
    for path_list in rewrite_path:
        # path_list 是一个路径，包含多个边
        for edge in path_list:
            # edge 是一个元组: (source, target, query_type)
            if isinstance(edge, tuple) and len(edge) >= 2:
                source, target = edge[0], edge[1]
                visited_domains.add(source)
                # 不要将 check_domain 添加到 visited_domains
                # 因为它是当前检查的起点
                if target != check_domain:
                    visited_domains.add(target)
    
    # 检查本地的重写链
    # 从 check_domain 开始进行 DFS
    def dfs_check_cycle(current_node, visited_in_local, is_first_node=False):
        """
        DFS 检查循环
        
        参数:
            current_node: 当前节点
            visited_in_local: 本地已访问的节点集合
            is_first_node: 是否是起始节点（check_domain）
        """
        # 如果不是起始节点，检查是否在外部路径中出现过
        if not is_first_node and current_node in visited_domains:
            # 检测到循环：当前节点在之前的跨域路径中已经出现过
            return True, current_node
        
        if current_node in visited_in_local:
            # 在本地路径中检测到循环
            return True, current_node
        
        visited_in_local.add(current_node)
        
        # 检查当前节点的所有出边
        for _, target, edge_data in G_local.out_edges(current_node, data=True):
            if edge_data.get('query_type') in {'CNAME', 'DNAME'}:
                has_cycle, cycle_node = dfs_check_cycle(target, visited_in_local.copy(), False)
                if has_cycle:
                    return True, cycle_node
        
        return False, None
    
    # 从 check_domain 开始检查，标记为起始节点
    has_cycle, cycle_node = dfs_check_cycle(check_domain, set(), is_first_node=True)
    
    if has_cycle:
        output_list.append(
            format_error_message(
                check_property,
                local_origin,
                f"Cross-zone rewrite loop detected: domain '{cycle_node}' appears in both external and local rewrite paths"
            )
        )
        return False, output_list
    
    return True, output_list


def get_check_rewrite_blackholing_client_info(cname_graph: nx.DiGraph, dname_graph: nx.DiGraph):
    """
    为跨域 Rewrite Blackholing 检测生成客户端信息
    
    当 CNAME/DNAME 链指向外部域时，需要跨域检测终点域名是否存在。
    
    返回格式:
    [
        {
            'check_domain': 重写链的终点域名,
            'check_property': 'check_rewrite_blackholing_cross',
            'rewrite_chain': 重写链信息,
            'check_data': 检测数据
        },
        ...
    ]
    """
    origin = cname_graph.graph.get('origin')
    client_info_list = []
    
    # 合并 CNAME 和 DNAME 图
    G_combined = nx.compose(cname_graph, dname_graph)
    
    # 获取所有叶子节点（重写链的终点）
    leaf_nodes = [node for node in G_combined.nodes() if G_combined.out_degree(node) == 0]
    
    for leaf_node in leaf_nodes:
        # 检查叶子节点是否在当前 origin 之外
        if not (leaf_node.endswith('.' + origin) or leaf_node == origin):
            # 这是一个外部域名，需要跨域检测其是否存在
            
            # 构建重写链信息
            rewrite_chain = []
            for source in G_combined.nodes():
                if G_combined.in_degree(source) == 0:  # 起始节点
                    try:
                        paths = list(nx.all_simple_paths(G_combined, source, leaf_node))
                        for path in paths:
                            chain_info = {
                                'source': source,
                                'target': leaf_node,
                                'path': path
                            }
                            rewrite_chain.append(chain_info)
                    except nx.NetworkXNoPath:
                        continue
            
            if rewrite_chain:
                packet_data = {
                    'check_domain': leaf_node,
                    'check_property': 'check_rewrite_blackholing_cross',
                    'origin': origin,
                    'rewrite_chain': rewrite_chain,
                    'check_data': {
                        'leaf_node': leaf_node,
                        'chains': rewrite_chain
                    }
                }
                client_info_list.append(packet_data)
    
    return client_info_list


def check_rewrite_blackholing_cross(check_domain: str, local_cname_graph: nx.DiGraph, 
                                    local_dname_graph: nx.DiGraph):
    """
    跨域 Rewrite Blackholing 检测
    
    检查从外部域传入的域名，在本地是否可以解析（是否存在）。
    
    参数:
        check_domain: 要检查的域名
        local_cname_graph: 本地的 CNAME 图
        local_dname_graph: 本地的 DNAME 图
    
    返回:
        (check_flag, output_list)
    """
    local_origin = local_cname_graph.graph.get('origin')
    check_property = "check_rewrite_blackholing_cross"
    output_list = []
    
    # 合并本地的 CNAME 和 DNAME 图
    G_local = nx.compose(local_cname_graph, local_dname_graph)
    
    # 检查 check_domain 是否在本地图中
    if check_domain not in G_local.nodes():
        # 域名不在本地图中，尝试 DNS 查询
        try:
            answers = dns.resolver.resolve(check_domain, 'A')
            # 域名存在，没有黑洞
            return True, []
        except dns.resolver.NXDOMAIN:
            output_list.append(
                format_error_message(
                    check_property,
                    local_origin,
                    f"Cross-zone rewrite blackholing: domain '{check_domain}' does not exist (NXDOMAIN)"
                )
            )
            return False, output_list
        except dns.resolver.NoAnswer:
            output_list.append(
                format_error_message(
                    check_property,
                    local_origin,
                    f"Cross-zone rewrite blackholing: domain '{check_domain}' has no answer records"
                )
            )
            return False, output_list
        except Exception as e:
            output_list.append(
                format_error_message(
                    check_property,
                    local_origin,
                    f"Cross-zone rewrite blackholing: failed to resolve '{check_domain}': {str(e)}"
                )
            )
            return False, output_list
    
    # 域名在本地图中，检查是否有进一步的重写或最终解析
    # 如果域名是叶子节点且没有 A/AAAA 记录，则可能是黑洞
    if G_local.out_degree(check_domain) == 0:
        # 这是一个叶子节点，需要检查是否有实际的解析记录
        # 这里应该检查 all_graph 中是否有 A/AAAA 记录
        # 但由于我们只有 CNAME/DNAME 图，我们进行 DNS 查询
        try:
            answers = dns.resolver.resolve(check_domain, 'A')
            return True, []
        except Exception as e:
            output_list.append(
                format_error_message(
                    check_property,
                    local_origin,
                    f"Cross-zone rewrite blackholing: domain '{check_domain}' cannot be resolved: {str(e)}"
                )
            )
            return False, output_list
    
    # 域名有进一步的重写，继续检查
    return True, []

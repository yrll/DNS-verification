"""
增量验证模块

实现 DNS Zone 文件的增量验证功能，当 zone 文件发生变化时，
只验证受影响的部分，而不是重新验证整个配置。

根据模型定义，增量验证包括三个阶段：
1. Delta 计算：将 zone 文件的变化转换为图操作
2. 影响分析：通过双向图遍历识别受影响的子图
3. 增量检测：只对受影响的子图进行属性验证
"""

import networkx as nx
from typing import Set, List, Tuple, Dict
import sys
import os

# 添加 src_muilt 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from entity.resource_record import ResourceRecord
from enums.rr_enum import QueryType


class DeltaOperation:
    """表示一个图操作（增加、删除、修改）"""
    
    def __init__(self, op_type: str, record: ResourceRecord, old_record: ResourceRecord = None):
        """
        参数:
            op_type: 操作类型 ('ADD', 'DELETE', 'UPDATE')
            record: 新的或被删除的记录
            old_record: 对于 UPDATE 操作，这是旧记录
        """
        self.op_type = op_type
        self.record = record
        self.old_record = old_record
    
    def __repr__(self):
        if self.op_type == 'UPDATE':
            return f"UPDATE: {self.old_record} -> {self.record}"
        else:
            return f"{self.op_type}: {self.record}"


class IncrementalVerifier:
    """增量验证器"""
    
    def __init__(self, original_graph: nx.DiGraph):
        """
        参数:
            original_graph: 原始的 RSG 图
        """
        self.original_graph = original_graph.copy()
        self.delta_operations = []
        self.affected_nodes = set()
        self.affected_subgraph = None
    
    def compute_delta(self, old_records: List[ResourceRecord], 
                     new_records: List[ResourceRecord]) -> List[DeltaOperation]:
        """
        计算两个记录集合之间的差异
        
        参数:
            old_records: 旧的记录列表
            new_records: 新的记录列表
        
        返回:
            Delta 操作列表
        """
        delta_ops = []
        
        # 将记录转换为可比较的格式
        def record_to_tuple(record):
            domain_name, query_type, value = record.get_record_tuple()
            return (domain_name, query_type, value)
        
        old_set = {record_to_tuple(r): r for r in old_records}
        new_set = {record_to_tuple(r): r for r in new_records}
        
        old_keys = set(old_set.keys())
        new_keys = set(new_set.keys())
        
        # 删除的记录
        deleted_keys = old_keys - new_keys
        for key in deleted_keys:
            delta_ops.append(DeltaOperation('DELETE', old_set[key]))
        
        # 新增的记录
        added_keys = new_keys - old_keys
        for key in added_keys:
            delta_ops.append(DeltaOperation('ADD', new_set[key]))
        
        # 注意：在我们的简化模型中，记录的修改会被表示为删除+添加
        # 因为记录的唯一性由 (domain_name, query_type, value) 决定
        
        self.delta_operations = delta_ops
        return delta_ops
    
    def apply_delta_to_graph(self, graph: nx.DiGraph, 
                            delta_ops: List[DeltaOperation]) -> nx.DiGraph:
        """
        将 delta 操作应用到图上
        
        参数:
            graph: 要修改的图
            delta_ops: Delta 操作列表
        
        返回:
            修改后的图
        """
        modified_graph = graph.copy()
        
        for op in delta_ops:
            domain_name, query_type, value = op.record.get_record_tuple()
            
            if op.op_type == 'ADD':
                # 添加节点和边
                if domain_name not in modified_graph.nodes():
                    modified_graph.add_node(domain_name)
                if value not in modified_graph.nodes():
                    modified_graph.add_node(value)
                modified_graph.add_edge(domain_name, value, query_type=query_type)
            
            elif op.op_type == 'DELETE':
                # 删除边
                if modified_graph.has_edge(domain_name, value):
                    modified_graph.remove_edge(domain_name, value)
                # 如果节点没有其他边，可以选择删除节点
                # 但为了安全起见，我们保留孤立节点
        
        return modified_graph
    
    def analyze_impact(self, delta_ops: List[DeltaOperation]) -> Set[str]:
        """
        分析 delta 操作的影响范围
        
        通过双向图遍历识别受影响的节点：
        - 后向遍历：识别所有受影响的前驱路径
        - 前向遍历：识别所有受影响的后继路径
        
        参数:
            delta_ops: Delta 操作列表
        
        返回:
            受影响的节点集合
        """
        affected = set()
        
        # 收集所有直接受影响的节点
        focal_nodes = set()
        for op in delta_ops:
            domain_name, query_type, value = op.record.get_record_tuple()
            focal_nodes.add(domain_name)
            focal_nodes.add(value)
        
        # 对每个焦点节点进行双向遍历
        for node in focal_nodes:
            if node not in self.original_graph.nodes():
                continue
            
            # 后向遍历：找到所有前驱节点
            predecessors = self._backward_traversal(node)
            affected.update(predecessors)
            
            # 前向遍历：找到所有后继节点
            successors = self._forward_traversal(node)
            affected.update(successors)
            
            # 包含焦点节点本身
            affected.add(node)
        
        self.affected_nodes = affected
        return affected
    
    def _backward_traversal(self, start_node: str) -> Set[str]:
        """
        后向遍历：从起始节点向前遍历，找到所有前驱节点
        
        参数:
            start_node: 起始节点
        
        返回:
            前驱节点集合
        """
        predecessors = set()
        visited = set()
        stack = [start_node]
        
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            predecessors.add(node)
            
            # 获取所有前驱节点
            for pred in self.original_graph.predecessors(node):
                if pred not in visited:
                    stack.append(pred)
        
        return predecessors
    
    def _forward_traversal(self, start_node: str) -> Set[str]:
        """
        前向遍历：从起始节点向后遍历，找到所有后继节点
        
        参数:
            start_node: 起始节点
        
        返回:
            后继节点集合
        """
        successors = set()
        visited = set()
        stack = [start_node]
        
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            successors.add(node)
            
            # 获取所有后继节点
            for succ in self.original_graph.successors(node):
                if succ not in visited:
                    stack.append(succ)
        
        return successors
    
    def extract_affected_subgraph(self, modified_graph: nx.DiGraph, 
                                  affected_nodes: Set[str]) -> nx.DiGraph:
        """
        从修改后的图中提取受影响的子图
        
        参数:
            modified_graph: 修改后的完整图
            affected_nodes: 受影响的节点集合
        
        返回:
            受影响的子图
        """
        # 创建子图，只包含受影响的节点和它们之间的边
        subgraph = modified_graph.subgraph(affected_nodes).copy()
        
        # 保留原图的属性
        if 'origin' in modified_graph.graph:
            subgraph.graph['origin'] = modified_graph.graph['origin']
        
        self.affected_subgraph = subgraph
        return subgraph
    
    def incremental_verify(self, old_records: List[ResourceRecord], 
                          new_records: List[ResourceRecord],
                          check_functions: List) -> Tuple[nx.DiGraph, Set[str], Dict]:
        """
        执行完整的增量验证流程
        
        参数:
            old_records: 旧的记录列表
            new_records: 新的记录列表
            check_functions: 要执行的检测函数列表
        
        返回:
            (修改后的图, 受影响的节点集合, 检测结果)
        """
        # 阶段 1: 计算 Delta
        delta_ops = self.compute_delta(old_records, new_records)
        
        if not delta_ops:
            # 没有变化，无需验证
            return self.original_graph, set(), {'status': 'no_change'}
        
        # 阶段 2: 影响分析
        affected_nodes = self.analyze_impact(delta_ops)
        
        # 应用 delta 到图
        modified_graph = self.apply_delta_to_graph(self.original_graph, delta_ops)
        
        # 提取受影响的子图
        affected_subgraph = self.extract_affected_subgraph(modified_graph, affected_nodes)
        
        # 阶段 3: 增量检测
        # 只对受影响的子图执行属性检测
        check_results = {
            'delta_operations': len(delta_ops),
            'affected_nodes': len(affected_nodes),
            'affected_edges': affected_subgraph.number_of_edges(),
            'checks': {}
        }
        
        for check_func in check_functions:
            func_name = check_func.__name__
            try:
                # 根据函数签名调用不同的检测函数
                if 'glue_graph' in check_func.__code__.co_varnames:
                    # 需要 glue_graph 参数
                    result = check_func(affected_subgraph)
                elif 'cname_graph' in check_func.__code__.co_varnames:
                    # 需要 cname_graph 和 dname_graph 参数
                    # 这里简化处理，实际应该分离不同类型的图
                    result = check_func(affected_subgraph, nx.DiGraph())
                else:
                    result = check_func(affected_subgraph)
                
                check_results['checks'][func_name] = {
                    'passed': result[0] if isinstance(result, tuple) else result,
                    'errors': result[1] if isinstance(result, tuple) and len(result) > 1 else []
                }
            except Exception as e:
                check_results['checks'][func_name] = {
                    'passed': False,
                    'error': str(e)
                }
        
        return modified_graph, affected_nodes, check_results
    
    def get_statistics(self) -> Dict:
        """
        获取增量验证的统计信息
        
        返回:
            统计信息字典
        """
        total_nodes = self.original_graph.number_of_nodes()
        total_edges = self.original_graph.number_of_edges()
        affected_nodes_count = len(self.affected_nodes)
        affected_edges_count = self.affected_subgraph.number_of_edges() if self.affected_subgraph else 0
        
        return {
            'total_nodes': total_nodes,
            'total_edges': total_edges,
            'affected_nodes': affected_nodes_count,
            'affected_edges': affected_edges_count,
            'node_reduction': f"{(1 - affected_nodes_count/total_nodes)*100:.2f}%" if total_nodes > 0 else "N/A",
            'edge_reduction': f"{(1 - affected_edges_count/total_edges)*100:.2f}%" if total_edges > 0 else "N/A",
            'delta_operations': len(self.delta_operations)
        }


def demonstrate_incremental_verification():
    """
    演示增量验证的工作流程
    
    修改 ns2.campus.com 的 IP 地址从 17.17.17.32 到 17.17.17.33
    """
    print("=" * 60)
    print("增量验证演示")
    print("=" * 60)
    
    # 创建原始图（模拟 campus.com 的配置）
    original_graph = nx.DiGraph(origin='campus.com.')
    
    # 添加原始记录
    # campus.com NS ns1.campus.com
    original_graph.add_edge('campus.com.', 'ns1.campus.com.', query_type='NS')
    # campus.com NS ns2.campus.com
    original_graph.add_edge('campus.com.', 'ns2.campus.com.', query_type='NS')
    # ns1.campus.com A 17.17.17.31
    original_graph.add_edge('ns1.campus.com.', '17.17.17.31', query_type='A')
    # ns2.campus.com A 17.17.17.32 (旧 IP)
    original_graph.add_edge('ns2.campus.com.', '17.17.17.32', query_type='A')
    
    print(f"\n原始图统计:")
    print(f"  节点数: {original_graph.number_of_nodes()}")
    print(f"  边数: {original_graph.number_of_edges()}")
    
    # 创建增量验证器
    verifier = IncrementalVerifier(original_graph)
    
    # 模拟记录变化：修改 ns2.campus.com 的 IP
    old_records = [
        ResourceRecord('ns2.campus.com.', 'A', '17.17.17.32')
    ]
    
    new_records = [
        ResourceRecord('ns2.campus.com.', 'A', '17.17.17.33')
    ]
    
    # 计算 Delta
    delta_ops = verifier.compute_delta(old_records, new_records)
    print(f"\nDelta 操作:")
    for op in delta_ops:
        print(f"  {op}")
    
    # 影响分析
    affected_nodes = verifier.analyze_impact(delta_ops)
    print(f"\n受影响的节点:")
    for node in sorted(affected_nodes):
        print(f"  - {node}")
    
    # 应用 Delta
    modified_graph = verifier.apply_delta_to_graph(original_graph, delta_ops)
    
    # 提取受影响的子图
    affected_subgraph = verifier.extract_affected_subgraph(modified_graph, affected_nodes)
    
    print(f"\n受影响的子图统计:")
    print(f"  节点数: {affected_subgraph.number_of_nodes()}")
    print(f"  边数: {affected_subgraph.number_of_edges()}")
    
    # 统计信息
    stats = verifier.get_statistics()
    print(f"\n增量验证效率:")
    print(f"  节点减少: {stats['node_reduction']}")
    print(f"  边减少: {stats['edge_reduction']}")
    print(f"  只需验证 {stats['affected_nodes']}/{stats['total_nodes']} 个节点")
    
    print("\n" + "=" * 60)
    print("增量验证演示完成")
    print("=" * 60)


if __name__ == '__main__':
    demonstrate_incremental_verification()

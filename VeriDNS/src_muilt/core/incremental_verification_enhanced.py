"""
增强版增量验证模块

实现与检测系统的深度集成，包括：
1. 图类型分离（NS/Glue图、CNAME图、DNAME图）
2. 属性特定的影响分析
3. 与现有检测函数的无缝集成
4. 支持批量修改优化
"""

import networkx as nx
from typing import Set, List, Tuple, Dict, Optional, Callable
from enum import Enum
import sys
import os

# 添加 src_muilt 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from entity.resource_record import ResourceRecord
from enums.rr_enum import QueryType


class GraphType(Enum):
    """图类型枚举"""
    ALL = "all"           # 所有记录
    GLUE = "glue"         # NS 和 A/AAAA 记录（用于 glue 检测）
    CNAME = "cname"       # CNAME 记录
    DNAME = "dname"       # DNAME 记录
    DELEGATION = "delegation"  # 跨域委派关系


class PropertyType(Enum):
    """属性类型枚举"""
    DOMAIN_OVERFLOW = "domain_overflow"
    MISSING_GLUE = "missing_glue"
    LAME_DELEGATION = "lame_delegation"
    REWRITE_LOOP = "rewrite_loop"
    REWRITE_BLACKHOLING = "rewrite_blackholing"
    CYCLIC_ZONE_DEPENDENCY = "cyclic_zone_dependency"


class ImpactScope(Enum):
    """影响范围类型"""
    LOCAL = "local"           # 只影响修改的节点本身
    FORWARD = "forward"       # 影响后继节点
    BACKWARD = "backward"     # 影响前驱节点
    BIDIRECTIONAL = "bidirectional"  # 双向影响


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
        
        # 提取记录信息
        self.domain_name, self.query_type, self.value = record.get_record_tuple()
        
        # 确定影响的图类型
        self.affected_graph_types = self._determine_affected_graphs()
    
    def _determine_affected_graphs(self) -> Set[GraphType]:
        """确定此操作影响哪些图类型"""
        affected = {GraphType.ALL}
        
        if self.query_type in {'NS', 'A', 'AAAA'}:
            affected.add(GraphType.GLUE)
        if self.query_type == 'CNAME':
            affected.add(GraphType.CNAME)
        if self.query_type == 'DNAME':
            affected.add(GraphType.DNAME)
        
        return affected
    
    def __repr__(self):
        if self.op_type == 'UPDATE':
            return f"UPDATE: {self.old_record} -> {self.record}"
        else:
            return f"{self.op_type}: {self.record}"


class PropertyImpactStrategy:
    """属性影响分析策略"""
    
    @staticmethod
    def get_strategy(property_type: PropertyType) -> Dict:
        """
        获取特定属性的影响分析策略
        
        返回:
            {
                'scope': ImpactScope,
                'graph_types': Set[GraphType],
                'max_depth': Optional[int]
            }
        """
        strategies = {
            PropertyType.DOMAIN_OVERFLOW: {
                'scope': ImpactScope.LOCAL,
                'graph_types': {GraphType.ALL},
                'max_depth': 0,  # 只检查节点本身
                'description': 'Domain Overflow 只需检查域名本身'
            },
            PropertyType.MISSING_GLUE: {
                'scope': ImpactScope.BIDIRECTIONAL,
                'graph_types': {GraphType.GLUE},
                'max_depth': 2,  # 向后到父域，向前到 IP
                'description': 'Missing Glue 需要检查父域、NS 记录及其 glue'
            },
            PropertyType.LAME_DELEGATION: {
                'scope': ImpactScope.BIDIRECTIONAL,
                'graph_types': {GraphType.GLUE},
                'max_depth': 2,
                'description': 'Lame Delegation 需要检查父域、NS 记录及其可达性'
            },
            PropertyType.REWRITE_LOOP: {
                'scope': ImpactScope.BIDIRECTIONAL,
                'graph_types': {GraphType.CNAME, GraphType.DNAME},
                'max_depth': None,  # 需要完整链
                'description': 'Rewrite Loop 需要完整的 CNAME/DNAME 链'
            },
            PropertyType.REWRITE_BLACKHOLING: {
                'scope': ImpactScope.FORWARD,
                'graph_types': {GraphType.CNAME, GraphType.DNAME},
                'max_depth': None,
                'description': 'Rewrite Blackholing 需要完整的重写链'
            },
            PropertyType.CYCLIC_ZONE_DEPENDENCY: {
                'scope': ImpactScope.BIDIRECTIONAL,
                'graph_types': {GraphType.GLUE, GraphType.DELEGATION},
                'max_depth': None,
                'description': 'Cyclic Zone Dependency 需要完整的委派链'
            }
        }
        
        return strategies.get(property_type, {
            'scope': ImpactScope.BIDIRECTIONAL,
            'graph_types': {GraphType.ALL},
            'max_depth': None,
            'description': '默认策略：双向完整遍历'
        })


class MultiGraphManager:
    """多图管理器 - 管理不同类型的图"""
    
    def __init__(self, origin: str = None):
        """
        参数:
            origin: zone 的原点域名
        """
        self.origin = origin
        self.graphs = {
            GraphType.ALL: nx.DiGraph(origin=origin),
            GraphType.GLUE: nx.DiGraph(origin=origin),
            GraphType.CNAME: nx.DiGraph(origin=origin),
            GraphType.DNAME: nx.DiGraph(origin=origin),
            GraphType.DELEGATION: nx.DiGraph(origin=origin)
        }
    
    def add_record(self, record: ResourceRecord):
        """添加记录到相应的图中"""
        domain_name, query_type, value = record.get_record_tuple()
        
        # 添加到 ALL 图
        self._add_edge(GraphType.ALL, domain_name, value, query_type)
        
        # 根据类型添加到特定图
        if query_type in {'NS', 'A', 'AAAA'}:
            self._add_edge(GraphType.GLUE, domain_name, value, query_type)
        elif query_type == 'CNAME':
            self._add_edge(GraphType.CNAME, domain_name, value, query_type)
        elif query_type == 'DNAME':
            self._add_edge(GraphType.DNAME, domain_name, value, query_type)
    
    def remove_record(self, record: ResourceRecord):
        """从相应的图中删除记录"""
        domain_name, query_type, value = record.get_record_tuple()
        
        # 从 ALL 图删除
        self._remove_edge(GraphType.ALL, domain_name, value)
        
        # 从特定图删除
        if query_type in {'NS', 'A', 'AAAA'}:
            self._remove_edge(GraphType.GLUE, domain_name, value)
        elif query_type == 'CNAME':
            self._remove_edge(GraphType.CNAME, domain_name, value)
        elif query_type == 'DNAME':
            self._remove_edge(GraphType.DNAME, domain_name, value)
    
    def _add_edge(self, graph_type: GraphType, source: str, target: str, edge_type: str):
        """添加边到指定图"""
        graph = self.graphs[graph_type]
        if source not in graph.nodes():
            graph.add_node(source)
        if target not in graph.nodes():
            graph.add_node(target)
        graph.add_edge(source, target, query_type=edge_type)
    
    def _remove_edge(self, graph_type: GraphType, source: str, target: str):
        """从指定图删除边"""
        graph = self.graphs[graph_type]
        if graph.has_edge(source, target):
            graph.remove_edge(source, target)
    
    def get_graph(self, graph_type: GraphType) -> nx.DiGraph:
        """获取指定类型的图"""
        return self.graphs[graph_type]
    
    def copy(self) -> 'MultiGraphManager':
        """创建深拷贝"""
        new_manager = MultiGraphManager(self.origin)
        for graph_type, graph in self.graphs.items():
            new_manager.graphs[graph_type] = graph.copy()
        return new_manager


class EnhancedIncrementalVerifier:
    """增强版增量验证器"""
    
    def __init__(self, original_graphs: MultiGraphManager):
        """
        参数:
            original_graphs: 原始的多图管理器
        """
        self.original_graphs = original_graphs.copy()
        self.modified_graphs = None
        self.delta_operations = []
        self.affected_nodes_by_property = {}  # 每个属性的受影响节点
        self.statistics = {}
    
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
        
        self.delta_operations = delta_ops
        return delta_ops
    
    def apply_delta(self, delta_ops: List[DeltaOperation]) -> MultiGraphManager:
        """
        将 delta 操作应用到图上
        
        参数:
            delta_ops: Delta 操作列表
        
        返回:
            修改后的多图管理器
        """
        modified_graphs = self.original_graphs.copy()
        
        for op in delta_ops:
            if op.op_type == 'ADD':
                modified_graphs.add_record(op.record)
            elif op.op_type == 'DELETE':
                modified_graphs.remove_record(op.record)
        
        self.modified_graphs = modified_graphs
        return modified_graphs
    
    def analyze_impact_for_property(self, 
                                    property_type: PropertyType,
                                    delta_ops: List[DeltaOperation]) -> Set[str]:
        """
        为特定属性分析影响范围
        
        参数:
            property_type: 属性类型
            delta_ops: Delta 操作列表
        
        返回:
            受影响的节点集合
        """
        strategy = PropertyImpactStrategy.get_strategy(property_type)
        scope = strategy['scope']
        graph_types = strategy['graph_types']
        max_depth = strategy['max_depth']
        
        affected = set()
        
        # 收集焦点节点（只考虑影响相关图类型的操作）
        focal_nodes = set()
        for op in delta_ops:
            # 检查此操作是否影响当前属性关心的图类型
            if graph_types & op.affected_graph_types:
                focal_nodes.add(op.domain_name)
                focal_nodes.add(op.value)
        
        # 根据策略选择遍历方式
        for node in focal_nodes:
            if scope == ImpactScope.LOCAL:
                # 只包含节点本身
                affected.add(node)
            
            elif scope == ImpactScope.FORWARD:
                # 前向遍历
                for graph_type in graph_types:
                    if graph_type in self.original_graphs.graphs:
                        graph = self.original_graphs.get_graph(graph_type)
                        successors = self._forward_traversal(graph, node, max_depth)
                        affected.update(successors)
            
            elif scope == ImpactScope.BACKWARD:
                # 后向遍历
                for graph_type in graph_types:
                    if graph_type in self.original_graphs.graphs:
                        graph = self.original_graphs.get_graph(graph_type)
                        predecessors = self._backward_traversal(graph, node, max_depth)
                        affected.update(predecessors)
            
            elif scope == ImpactScope.BIDIRECTIONAL:
                # 双向遍历
                for graph_type in graph_types:
                    if graph_type in self.original_graphs.graphs:
                        graph = self.original_graphs.get_graph(graph_type)
                        predecessors = self._backward_traversal(graph, node, max_depth)
                        successors = self._forward_traversal(graph, node, max_depth)
                        affected.update(predecessors)
                        affected.update(successors)
        
        self.affected_nodes_by_property[property_type] = affected
        return affected
    
    def _forward_traversal(self, graph: nx.DiGraph, start_node: str, 
                          max_depth: Optional[int] = None) -> Set[str]:
        """
        前向遍历
        
        参数:
            graph: 要遍历的图
            start_node: 起始节点
            max_depth: 最大深度（None 表示无限制）
        
        返回:
            后继节点集合
        """
        if start_node not in graph.nodes():
            return set()
        
        successors = set()
        visited = set()
        queue = [(start_node, 0)]  # (节点, 深度)
        
        while queue:
            node, depth = queue.pop(0)
            
            if node in visited:
                continue
            
            if max_depth is not None and depth > max_depth:
                continue
            
            visited.add(node)
            successors.add(node)
            
            # 获取所有后继节点
            for succ in graph.successors(node):
                if succ not in visited:
                    queue.append((succ, depth + 1))
        
        return successors
    
    def _backward_traversal(self, graph: nx.DiGraph, start_node: str,
                           max_depth: Optional[int] = None) -> Set[str]:
        """
        后向遍历
        
        参数:
            graph: 要遍历的图
            start_node: 起始节点
            max_depth: 最大深度（None 表示无限制）
        
        返回:
            前驱节点集合
        """
        if start_node not in graph.nodes():
            return set()
        
        predecessors = set()
        visited = set()
        queue = [(start_node, 0)]  # (节点, 深度)
        
        while queue:
            node, depth = queue.pop(0)
            
            if node in visited:
                continue
            
            if max_depth is not None and depth > max_depth:
                continue
            
            visited.add(node)
            predecessors.add(node)
            
            # 获取所有前驱节点
            for pred in graph.predecessors(node):
                if pred not in visited:
                    queue.append((pred, depth + 1))
        
        return predecessors
    
    def extract_affected_subgraph(self, graph_type: GraphType, 
                                  affected_nodes: Set[str]) -> nx.DiGraph:
        """
        从修改后的图中提取受影响的子图
        
        参数:
            graph_type: 图类型
            affected_nodes: 受影响的节点集合
        
        返回:
            受影响的子图
        """
        if self.modified_graphs is None:
            raise ValueError("必须先调用 apply_delta()")
        
        full_graph = self.modified_graphs.get_graph(graph_type)
        
        # 只包含存在于图中的节点
        valid_nodes = [n for n in affected_nodes if n in full_graph.nodes()]
        
        if not valid_nodes:
            # 返回空图
            return nx.DiGraph(origin=full_graph.graph.get('origin'))
        
        subgraph = full_graph.subgraph(valid_nodes).copy()
        
        # 保留原图的属性
        if 'origin' in full_graph.graph:
            subgraph.graph['origin'] = full_graph.graph['origin']
        
        return subgraph
    
    def incremental_verify(self, 
                          old_records: List[ResourceRecord],
                          new_records: List[ResourceRecord],
                          check_config: Dict[PropertyType, Callable]) -> Dict:
        """
        执行完整的增量验证流程
        
        参数:
            old_records: 旧的记录列表
            new_records: 新的记录列表
            check_config: 检测配置 {PropertyType: check_function}
        
        返回:
            检测结果字典
        """
        # 阶段 1: 计算 Delta
        delta_ops = self.compute_delta(old_records, new_records)
        
        if not delta_ops:
            return {
                'status': 'no_change',
                'message': '没有检测到配置变化'
            }
        
        # 阶段 2: 应用 Delta
        self.apply_delta(delta_ops)
        
        # 阶段 3: 为每个属性分析影响并执行检测
        results = {
            'delta_operations': len(delta_ops),
            'delta_details': [str(op) for op in delta_ops],
            'checks': {},
            'statistics': {}
        }
        
        for property_type, check_func in check_config.items():
            # 分析此属性的影响范围
            affected_nodes = self.analyze_impact_for_property(property_type, delta_ops)
            
            if not affected_nodes:
                results['checks'][property_type.value] = {
                    'status': 'skipped',
                    'reason': '没有受影响的节点'
                }
                continue
            
            # 获取策略信息
            strategy = PropertyImpactStrategy.get_strategy(property_type)
            graph_types = strategy['graph_types']
            
            # 提取受影响的子图并执行检测
            try:
                check_result = self._execute_check(
                    property_type, 
                    check_func, 
                    graph_types, 
                    affected_nodes
                )
                
                results['checks'][property_type.value] = check_result
                
                # 记录统计信息
                results['statistics'][property_type.value] = {
                    'affected_nodes': len(affected_nodes),
                    'strategy': strategy['description']
                }
                
            except Exception as e:
                results['checks'][property_type.value] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        self.statistics = results['statistics']
        return results
    
    def _execute_check(self, 
                      property_type: PropertyType,
                      check_func: Callable,
                      graph_types: Set[GraphType],
                      affected_nodes: Set[str]) -> Dict:
        """
        执行特定属性的检测
        
        参数:
            property_type: 属性类型
            check_func: 检测函数
            graph_types: 需要的图类型
            affected_nodes: 受影响的节点
        
        返回:
            检测结果
        """
        # 根据属性类型准备参数
        if property_type == PropertyType.DOMAIN_OVERFLOW:
            # check_domain_overflow(all_graph)
            subgraph = self.extract_affected_subgraph(GraphType.ALL, affected_nodes)
            check_flag, errors = check_func(subgraph)
        
        elif property_type in [PropertyType.MISSING_GLUE, PropertyType.LAME_DELEGATION]:
            # check_miss_glue_record(glue_graph) 或 check_lame_delegation(glue_graph)
            subgraph = self.extract_affected_subgraph(GraphType.GLUE, affected_nodes)
            check_flag, errors = check_func(subgraph)
        
        elif property_type in [PropertyType.REWRITE_LOOP, PropertyType.REWRITE_BLACKHOLING]:
            # check_rewrite_loop(cname_graph, dname_graph)
            cname_subgraph = self.extract_affected_subgraph(GraphType.CNAME, affected_nodes)
            dname_subgraph = self.extract_affected_subgraph(GraphType.DNAME, affected_nodes)
            check_flag, errors = check_func(cname_subgraph, dname_subgraph)
        
        else:
            # 默认：使用 ALL 图
            subgraph = self.extract_affected_subgraph(GraphType.ALL, affected_nodes)
            check_flag, errors = check_func(subgraph)
        
        return {
            'status': 'passed' if check_flag else 'failed',
            'passed': check_flag,
            'errors': errors if errors else [],
            'error_count': len(errors) if errors else 0
        }
    
    def get_efficiency_report(self) -> Dict:
        """
        获取效率报告
        
        返回:
            效率统计信息
        """
        report = {
            'delta_operations': len(self.delta_operations),
            'properties_checked': len(self.affected_nodes_by_property),
            'by_property': {}
        }
        
        for property_type, affected_nodes in self.affected_nodes_by_property.items():
            # 获取对应图类型的总节点数
            strategy = PropertyImpactStrategy.get_strategy(property_type)
            graph_types = strategy['graph_types']
            
            total_nodes = 0
            for graph_type in graph_types:
                if graph_type in self.original_graphs.graphs:
                    total_nodes = max(total_nodes, 
                                    self.original_graphs.get_graph(graph_type).number_of_nodes())
            
            affected_count = len(affected_nodes)
            reduction = (1 - affected_count / total_nodes) * 100 if total_nodes > 0 else 0
            
            report['by_property'][property_type.value] = {
                'total_nodes': total_nodes,
                'affected_nodes': affected_count,
                'reduction_percentage': f"{reduction:.2f}%",
                'strategy': strategy['description']
            }
        
        return report


def build_multi_graph_from_records(records: List[ResourceRecord], 
                                   origin: str = None) -> MultiGraphManager:
    """
    从记录列表构建多图管理器
    
    参数:
        records: 记录列表
        origin: zone 的原点域名
    
    返回:
        多图管理器
    """
    manager = MultiGraphManager(origin)
    
    for record in records:
        manager.add_record(record)
    
    return manager


# 示例：演示增强版增量验证
def demonstrate_enhanced_incremental_verification():
    """演示增强版增量验证的工作流程"""
    print("=" * 70)
    print("增强版增量验证演示")
    print("=" * 70)
    
    # 创建原始记录
    original_records = [
        ResourceRecord('example.com.', 'NS', 'ns1.example.com.'),
        ResourceRecord('example.com.', 'NS', 'ns2.example.com.'),
        ResourceRecord('ns1.example.com.', 'A', '192.0.2.1'),
        ResourceRecord('ns2.example.com.', 'A', '192.0.2.2'),
        ResourceRecord('www.example.com.', 'CNAME', 'web.example.com.'),
        ResourceRecord('web.example.com.', 'A', '192.0.2.10'),
    ]
    
    # 构建多图
    original_graphs = build_multi_graph_from_records(original_records, 'example.com.')
    
    print(f"\n原始图统计:")
    print(f"  ALL 图: {original_graphs.get_graph(GraphType.ALL).number_of_nodes()} 节点, "
          f"{original_graphs.get_graph(GraphType.ALL).number_of_edges()} 边")
    print(f"  GLUE 图: {original_graphs.get_graph(GraphType.GLUE).number_of_nodes()} 节点, "
          f"{original_graphs.get_graph(GraphType.GLUE).number_of_edges()} 边")
    print(f"  CNAME 图: {original_graphs.get_graph(GraphType.CNAME).number_of_nodes()} 节点, "
          f"{original_graphs.get_graph(GraphType.CNAME).number_of_edges()} 边")
    
    # 创建增量验证器
    verifier = EnhancedIncrementalVerifier(original_graphs)
    
    # 模拟修改：更改 ns2 的 IP
    old_records = [ResourceRecord('ns2.example.com.', 'A', '192.0.2.2')]
    new_records = [ResourceRecord('ns2.example.com.', 'A', '192.0.2.3')]
    
    # 计算 Delta
    delta_ops = verifier.compute_delta(old_records, new_records)
    print(f"\nDelta 操作:")
    for op in delta_ops:
        print(f"  {op}")
        print(f"    影响的图类型: {[gt.value for gt in op.affected_graph_types]}")
    
    # 应用 Delta
    verifier.apply_delta(delta_ops)
    
    # 为不同属性分析影响
    print(f"\n属性特定的影响分析:")
    
    properties_to_check = [
        PropertyType.DOMAIN_OVERFLOW,
        PropertyType.MISSING_GLUE,
        PropertyType.REWRITE_LOOP
    ]
    
    for prop_type in properties_to_check:
        affected = verifier.analyze_impact_for_property(prop_type, delta_ops)
        strategy = PropertyImpactStrategy.get_strategy(prop_type)
        
        print(f"\n  {prop_type.value}:")
        print(f"    策略: {strategy['description']}")
        print(f"    影响范围: {strategy['scope'].value}")
        print(f"    最大深度: {strategy['max_depth']}")
        print(f"    受影响节点数: {len(affected)}")
        print(f"    受影响节点: {sorted(affected)}")
    
    # 效率报告
    print(f"\n效率报告:")
    report = verifier.get_efficiency_report()
    for prop_name, stats in report['by_property'].items():
        print(f"\n  {prop_name}:")
        print(f"    总节点数: {stats['total_nodes']}")
        print(f"    受影响节点: {stats['affected_nodes']}")
        print(f"    节点减少: {stats['reduction_percentage']}")
    
    print("\n" + "=" * 70)
    print("演示完成")
    print("=" * 70)


if __name__ == '__main__':
    demonstrate_enhanced_incremental_verification()

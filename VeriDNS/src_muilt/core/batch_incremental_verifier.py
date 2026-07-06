"""
批量增量验证模块

支持批量修改的优化，包括：
1. 事务性批量修改
2. Delta 操作合并
3. 影响范围优化
4. 原子性保证
"""

import networkx as nx
from typing import Set, List, Tuple, Dict, Optional, Callable
from enum import Enum
import sys
import os

# 添加 src_muilt 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from entity.resource_record import ResourceRecord
from core.incremental_verification_enhanced import (
    EnhancedIncrementalVerifier,
    MultiGraphManager,
    DeltaOperation,
    PropertyType,
    GraphType,
    build_multi_graph_from_records
)


class BatchModification:
    """批量修改操作"""
    
    def __init__(self, modification_id: str = None):
        """
        参数:
            modification_id: 修改批次的唯一标识
        """
        self.modification_id = modification_id or self._generate_id()
        self.old_records = []
        self.new_records = []
        self.description = ""
        self.timestamp = None
    
    def _generate_id(self) -> str:
        """生成唯一 ID"""
        import time
        return f"batch_{int(time.time() * 1000)}"
    
    def add_modification(self, old_record: ResourceRecord, new_record: ResourceRecord):
        """
        添加一个修改操作
        
        参数:
            old_record: 旧记录
            new_record: 新记录
        """
        self.old_records.append(old_record)
        self.new_records.append(new_record)
    
    def add_deletion(self, record: ResourceRecord):
        """
        添加一个删除操作
        
        参数:
            record: 要删除的记录
        """
        self.old_records.append(record)
    
    def add_addition(self, record: ResourceRecord):
        """
        添加一个新增操作
        
        参数:
            record: 要新增的记录
        """
        self.new_records.append(record)
    
    def set_description(self, description: str):
        """设置修改描述"""
        self.description = description
    
    def get_summary(self) -> Dict:
        """获取修改摘要"""
        return {
            'id': self.modification_id,
            'description': self.description,
            'old_records_count': len(self.old_records),
            'new_records_count': len(self.new_records),
            'timestamp': self.timestamp
        }
    
    def __repr__(self):
        return f"BatchModification(id={self.modification_id}, old={len(self.old_records)}, new={len(self.new_records)})"


class BatchIncrementalVerifier(EnhancedIncrementalVerifier):
    """批量增量验证器"""
    
    def __init__(self, original_graphs: MultiGraphManager):
        """
        参数:
            original_graphs: 原始的多图管理器
        """
        super().__init__(original_graphs)
        self.batch_history = []  # 批量修改历史
        self.pending_batch = None  # 待处理的批量修改
    
    def start_batch(self, description: str = "") -> BatchModification:
        """
        开始一个批量修改事务
        
        参数:
            description: 批量修改的描述
        
        返回:
            BatchModification 对象
        """
        if self.pending_batch is not None:
            raise ValueError("已有待处理的批量修改，请先提交或回滚")
        
        self.pending_batch = BatchModification()
        self.pending_batch.set_description(description)
        
        return self.pending_batch
    
    def add_to_batch(self, old_record: Optional[ResourceRecord] = None, 
                     new_record: Optional[ResourceRecord] = None):
        """
        向当前批量修改添加操作
        
        参数:
            old_record: 旧记录（None 表示新增）
            new_record: 新记录（None 表示删除）
        """
        if self.pending_batch is None:
            raise ValueError("没有活动的批量修改，请先调用 start_batch()")
        
        if old_record is None and new_record is None:
            raise ValueError("old_record 和 new_record 不能同时为 None")
        
        if old_record is None:
            # 新增操作
            self.pending_batch.add_addition(new_record)
        elif new_record is None:
            # 删除操作
            self.pending_batch.add_deletion(old_record)
        else:
            # 修改操作
            self.pending_batch.add_modification(old_record, new_record)
    
    def commit_batch(self, check_config: Dict[PropertyType, Callable]) -> Dict:
        """
        提交批量修改并执行验证
        
        参数:
            check_config: 检测配置
        
        返回:
            验证结果
        """
        if self.pending_batch is None:
            raise ValueError("没有待提交的批量修改")
        
        import time
        self.pending_batch.timestamp = time.time()
        
        # 执行增量验证
        results = self.incremental_verify(
            self.pending_batch.old_records,
            self.pending_batch.new_records,
            check_config
        )
        
        # 添加批量修改信息
        results['batch_info'] = self.pending_batch.get_summary()
        
        # 保存到历史
        self.batch_history.append({
            'batch': self.pending_batch,
            'results': results
        })
        
        # 清除待处理批量修改
        self.pending_batch = None
        
        return results
    
    def rollback_batch(self):
        """回滚当前批量修改"""
        if self.pending_batch is None:
            raise ValueError("没有待回滚的批量修改")
        
        self.pending_batch = None
    
    def optimize_batch_delta(self, delta_ops: List[DeltaOperation]) -> List[DeltaOperation]:
        """
        优化批量 Delta 操作
        
        合并相关的操作，减少冗余
        
        参数:
            delta_ops: 原始 Delta 操作列表
        
        返回:
            优化后的 Delta 操作列表
        """
        # 按节点分组
        ops_by_node = {}
        for op in delta_ops:
            key = (op.domain_name, op.query_type)
            if key not in ops_by_node:
                ops_by_node[key] = []
            ops_by_node[key].append(op)
        
        optimized_ops = []
        
        for key, ops in ops_by_node.items():
            if len(ops) == 1:
                # 单个操作，直接保留
                optimized_ops.append(ops[0])
            else:
                # 多个操作，尝试合并
                # 例如：DELETE A -> ADD B 可以合并为 UPDATE A->B
                deletes = [op for op in ops if op.op_type == 'DELETE']
                adds = [op for op in ops if op.op_type == 'ADD']
                
                if len(deletes) == 1 and len(adds) == 1:
                    # 可以合并为 UPDATE
                    optimized_ops.append(
                        DeltaOperation('UPDATE', adds[0].record, deletes[0].record)
                    )
                else:
                    # 无法合并，保留所有操作
                    optimized_ops.extend(ops)
        
        return optimized_ops
    
    def analyze_batch_impact(self, 
                            property_type: PropertyType,
                            delta_ops: List[DeltaOperation]) -> Dict:
        """
        分析批量修改的影响
        
        参数:
            property_type: 属性类型
            delta_ops: Delta 操作列表
        
        返回:
            影响分析结果
        """
        # 优化 Delta 操作
        optimized_ops = self.optimize_batch_delta(delta_ops)
        
        # 分析影响
        affected_nodes = self.analyze_impact_for_property(property_type, optimized_ops)
        
        # 计算优化效果
        original_focal_nodes = set()
        for op in delta_ops:
            original_focal_nodes.add(op.domain_name)
            original_focal_nodes.add(op.value)
        
        optimized_focal_nodes = set()
        for op in optimized_ops:
            optimized_focal_nodes.add(op.domain_name)
            optimized_focal_nodes.add(op.value)
        
        return {
            'original_delta_count': len(delta_ops),
            'optimized_delta_count': len(optimized_ops),
            'delta_reduction': len(delta_ops) - len(optimized_ops),
            'original_focal_nodes': len(original_focal_nodes),
            'optimized_focal_nodes': len(optimized_focal_nodes),
            'affected_nodes': len(affected_nodes),
            'affected_nodes_list': sorted(affected_nodes)
        }
    
    def get_batch_history(self) -> List[Dict]:
        """获取批量修改历史"""
        return [
            {
                'batch_id': item['batch'].modification_id,
                'description': item['batch'].description,
                'timestamp': item['batch'].timestamp,
                'old_records': len(item['batch'].old_records),
                'new_records': len(item['batch'].new_records),
                'status': item['results'].get('status', 'unknown')
            }
            for item in self.batch_history
        ]
    
    def batch_verify_with_optimization(self,
                                      batch: BatchModification,
                                      check_config: Dict[PropertyType, Callable]) -> Dict:
        """
        使用优化策略执行批量验证
        
        参数:
            batch: 批量修改对象
            check_config: 检测配置
        
        返回:
            验证结果（包含优化统计）
        """
        # 计算 Delta
        delta_ops = self.compute_delta(batch.old_records, batch.new_records)
        
        # 优化 Delta
        optimized_ops = self.optimize_batch_delta(delta_ops)
        
        # 应用优化后的 Delta
        self.delta_operations = optimized_ops
        self.apply_delta(optimized_ops)
        
        # 为每个属性分析影响并执行检测
        results = {
            'batch_info': batch.get_summary(),
            'delta_optimization': {
                'original_count': len(delta_ops),
                'optimized_count': len(optimized_ops),
                'reduction': len(delta_ops) - len(optimized_ops)
            },
            'checks': {},
            'statistics': {}
        }
        
        for property_type, check_func in check_config.items():
            # 分析影响
            impact_analysis = self.analyze_batch_impact(property_type, delta_ops)
            
            affected_nodes = self.affected_nodes_by_property.get(property_type, set())
            
            if not affected_nodes:
                results['checks'][property_type.value] = {
                    'status': 'skipped',
                    'reason': '没有受影响的节点'
                }
                continue
            
            # 执行检测
            try:
                from core.incremental_verification_enhanced import PropertyImpactStrategy
                strategy = PropertyImpactStrategy.get_strategy(property_type)
                graph_types = strategy['graph_types']
                
                check_result = self._execute_check(
                    property_type,
                    check_func,
                    graph_types,
                    affected_nodes
                )
                
                results['checks'][property_type.value] = check_result
                results['statistics'][property_type.value] = impact_analysis
                
            except Exception as e:
                results['checks'][property_type.value] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        return results


def demonstrate_batch_verification():
    """演示批量增量验证"""
    print("=" * 70)
    print("批量增量验证演示")
    print("=" * 70)
    
    # 创建原始配置
    records = [
        ResourceRecord('example.com.', 'NS', 'ns1.example.com.'),
        ResourceRecord('example.com.', 'NS', 'ns2.example.com.'),
        ResourceRecord('example.com.', 'NS', 'ns3.example.com.'),
        ResourceRecord('ns1.example.com.', 'A', '192.0.2.1'),
        ResourceRecord('ns2.example.com.', 'A', '192.0.2.2'),
        ResourceRecord('ns3.example.com.', 'A', '192.0.2.3'),
        ResourceRecord('www.example.com.', 'A', '192.0.2.10'),
        ResourceRecord('mail.example.com.', 'A', '192.0.2.20'),
    ]
    
    original_graphs = build_multi_graph_from_records(records, 'example.com.')
    verifier = BatchIncrementalVerifier(original_graphs)
    
    print(f"\n原始配置:")
    print(f"  总记录数: {len(records)}")
    print(f"  节点数: {original_graphs.get_graph(GraphType.ALL).number_of_nodes()}")
    
    # 场景 1: 使用事务性批量修改
    print(f"\n" + "=" * 70)
    print("场景 1: 事务性批量修改")
    print("=" * 70)
    
    batch = verifier.start_batch("更新所有 NS 服务器的 IP 地址")
    
    # 添加多个修改
    verifier.add_to_batch(
        ResourceRecord('ns1.example.com.', 'A', '192.0.2.1'),
        ResourceRecord('ns1.example.com.', 'A', '192.0.2.11')
    )
    verifier.add_to_batch(
        ResourceRecord('ns2.example.com.', 'A', '192.0.2.2'),
        ResourceRecord('ns2.example.com.', 'A', '192.0.2.22')
    )
    verifier.add_to_batch(
        ResourceRecord('ns3.example.com.', 'A', '192.0.2.3'),
        ResourceRecord('ns3.example.com.', 'A', '192.0.2.33')
    )
    
    print(f"\n批量修改摘要:")
    summary = batch.get_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")
    
    # 提交批量修改
    from core.check_properties import check_domain_overflow, check_miss_glue_record
    
    check_config = {
        PropertyType.DOMAIN_OVERFLOW: check_domain_overflow,
        PropertyType.MISSING_GLUE: check_miss_glue_record,
    }
    
    results = verifier.commit_batch(check_config)
    
    print(f"\n验证结果:")
    print(f"  Delta 操作数: {results.get('delta_operations', 0)}")
    print(f"  检测项数: {len(results.get('checks', {}))}")
    
    for prop_name, result in results.get('checks', {}).items():
        print(f"\n  {prop_name}:")
        print(f"    状态: {result.get('status', 'unknown')}")
        if 'error_count' in result:
            print(f"    错误数: {result['error_count']}")
    
    # 场景 2: Delta 优化
    print(f"\n" + "=" * 70)
    print("场景 2: Delta 优化演示")
    print("=" * 70)
    
    # 创建新的批量修改
    batch2 = BatchModification()
    batch2.set_description("测试 Delta 优化")
    
    # 添加会被优化的操作
    batch2.add_deletion(ResourceRecord('test.example.com.', 'A', '192.0.2.100'))
    batch2.add_addition(ResourceRecord('test.example.com.', 'A', '192.0.2.101'))
    
    # 计算 Delta
    delta_ops = verifier.compute_delta(batch2.old_records, batch2.new_records)
    
    print(f"\n原始 Delta 操作:")
    for op in delta_ops:
        print(f"  {op}")
    
    # 优化 Delta
    optimized_ops = verifier.optimize_batch_delta(delta_ops)
    
    print(f"\n优化后的 Delta 操作:")
    for op in optimized_ops:
        print(f"  {op}")
    
    print(f"\n优化效果:")
    print(f"  原始操作数: {len(delta_ops)}")
    print(f"  优化后操作数: {len(optimized_ops)}")
    print(f"  减少: {len(delta_ops) - len(optimized_ops)} 个操作")
    
    # 场景 3: 批量修改历史
    print(f"\n" + "=" * 70)
    print("场景 3: 批量修改历史")
    print("=" * 70)
    
    history = verifier.get_batch_history()
    print(f"\n历史记录数: {len(history)}")
    for i, item in enumerate(history, 1):
        print(f"\n  批次 {i}:")
        print(f"    ID: {item['batch_id']}")
        print(f"    描述: {item['description']}")
        print(f"    旧记录数: {item['old_records']}")
        print(f"    新记录数: {item['new_records']}")
        print(f"    状态: {item['status']}")
    
    print("\n" + "=" * 70)
    print("演示完成")
    print("=" * 70)


if __name__ == '__main__':
    demonstrate_batch_verification()

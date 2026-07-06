"""
跨域增量验证模块

实现跨域增量验证功能，包括：
1. Delta 传播机制
2. 增量跨域检测协议
3. 级联更新通知
4. 分布式增量验证
"""

import socket
import threading
import json
import networkx as nx
from typing import Set, List, Tuple, Dict, Optional, Callable
from enum import Enum
import sys
import os
import time

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

# 创建 logger
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class CrossZoneMessageType(Enum):
    """跨域消息类型"""
    DELTA_NOTIFICATION = "delta_notification"      # Delta 通知
    INCREMENTAL_CHECK_REQUEST = "incremental_check_request"  # 增量检测请求
    INCREMENTAL_CHECK_RESPONSE = "incremental_check_response"  # 增量检测响应
    CASCADE_UPDATE = "cascade_update"              # 级联更新
    SYNC_REQUEST = "sync_request"                  # 同步请求
    SYNC_RESPONSE = "sync_response"                # 同步响应


class CrossZoneMessage:
    """跨域消息"""
    
    def __init__(self, 
                 message_type: CrossZoneMessageType,
                 source_zone: str,
                 target_zone: str,
                 payload: Dict):
        """
        参数:
            message_type: 消息类型
            source_zone: 源域
            target_zone: 目标域
            payload: 消息负载
        """
        self.message_type = message_type
        self.source_zone = source_zone
        self.target_zone = target_zone
        self.payload = payload
        self.timestamp = time.time()
        self.message_id = self._generate_id()
    
    def _generate_id(self) -> str:
        """生成消息 ID"""
        return f"{self.source_zone}_{self.target_zone}_{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'message_type': self.message_type.value,
            'source_zone': self.source_zone,
            'target_zone': self.target_zone,
            'payload': self.payload,
            'timestamp': self.timestamp,
            'message_id': self.message_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CrossZoneMessage':
        """从字典创建"""
        msg = cls(
            CrossZoneMessageType(data['message_type']),
            data['source_zone'],
            data['target_zone'],
            data['payload']
        )
        msg.timestamp = data['timestamp']
        msg.message_id = data['message_id']
        return msg
    
    def __repr__(self):
        return f"CrossZoneMessage({self.message_type.value}, {self.source_zone} -> {self.target_zone})"


class DeltaNotification:
    """Delta 通知"""
    
    def __init__(self, 
                 zone: str,
                 delta_ops: List[DeltaOperation],
                 affected_external_zones: Set[str]):
        """
        参数:
            zone: 发生变化的域
            delta_ops: Delta 操作列表
            affected_external_zones: 受影响的外部域集合
        """
        self.zone = zone
        self.delta_ops = delta_ops
        self.affected_external_zones = affected_external_zones
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'zone': self.zone,
            'delta_ops': [
                {
                    'op_type': op.op_type,
                    'domain_name': op.domain_name,
                    'query_type': op.query_type,
                    'value': op.value
                }
                for op in self.delta_ops
            ],
            'affected_external_zones': list(self.affected_external_zones)
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DeltaNotification':
        """从字典创建"""
        delta_ops = [
            DeltaOperation(
                op_data['op_type'],
                ResourceRecord(
                    op_data['domain_name'],
                    op_data['query_type'],
                    op_data['value']
                )
            )
            for op_data in data['delta_ops']
        ]
        
        return cls(
            data['zone'],
            delta_ops,
            set(data['affected_external_zones'])
        )


class CrossZoneIncrementalVerifier(EnhancedIncrementalVerifier):
    """跨域增量验证器"""
    
    def __init__(self, 
                 original_graphs: MultiGraphManager,
                 zone_name: str,
                 listen_ip: str = "0.0.0.0",
                 listen_port: int = 9000):
        """
        参数:
            original_graphs: 原始的多图管理器
            zone_name: 当前域名
            listen_ip: 监听 IP
            listen_port: 监听端口
        """
        super().__init__(original_graphs)
        self.zone_name = zone_name
        self.listen_ip = listen_ip
        self.listen_port = listen_port
        
        # 跨域相关
        self.external_zone_registry = {}  # 外部域注册表 {zone_name: (ip, port)}
        self.pending_notifications = []   # 待发送的通知
        self.received_notifications = []  # 接收到的通知
        
        # 服务器相关
        self.server_socket = None
        self.server_thread = None
        self.is_running = False
    
    def register_external_zone(self, zone_name: str, ip: str, port: int):
        """
        注册外部域
        
        参数:
            zone_name: 域名
            ip: IP 地址
            port: 端口
        """
        self.external_zone_registry[zone_name] = (ip, port)
        logger.info(f"Registered external zone: {zone_name} at {ip}:{port}")
    
    def identify_affected_external_zones(self, delta_ops: List[DeltaOperation]) -> Set[str]:
        """
        识别受影响的外部域
        
        参数:
            delta_ops: Delta 操作列表
        
        返回:
            受影响的外部域集合
        """
        affected_zones = set()
        
        for op in delta_ops:
            # 检查是否是 NS 记录的修改
            if op.query_type == 'NS':
                # NS 记录的修改可能影响子域
                # 提取子域名
                if op.value.endswith('.'):
                    # 检查是否是外部域
                    if not op.value.endswith(self.zone_name):
                        # 提取域名
                        parts = op.value.rstrip('.').split('.')
                        if len(parts) >= 2:
                            external_zone = '.'.join(parts[-2:]) + '.'
                            if external_zone in self.external_zone_registry:
                                affected_zones.add(external_zone)
            
            # 检查是否是 A/AAAA 记录的修改（可能影响 glue）
            elif op.query_type in {'A', 'AAAA'}:
                # 检查此域名是否被其他域作为 NS 使用
                glue_graph = self.original_graphs.get_graph(GraphType.GLUE)
                for edge in glue_graph.edges(data=True):
                    if edge[2].get('query_type') == 'NS' and edge[1] == op.domain_name:
                        # 此域名被用作 NS，检查父域
                        parent_domain = edge[0]
                        if not parent_domain.endswith(self.zone_name):
                            # 外部域
                            parts = parent_domain.rstrip('.').split('.')
                            if len(parts) >= 2:
                                external_zone = '.'.join(parts[-2:]) + '.'
                                if external_zone in self.external_zone_registry:
                                    affected_zones.add(external_zone)
        
        return affected_zones
    
    def send_delta_notification(self, 
                                delta_ops: List[DeltaOperation],
                                affected_zones: Set[str]) -> Dict[str, bool]:
        """
        发送 Delta 通知到受影响的外部域
        
        参数:
            delta_ops: Delta 操作列表
            affected_zones: 受影响的外部域集合
        
        返回:
            发送结果 {zone_name: success}
        """
        results = {}
        
        notification = DeltaNotification(
            self.zone_name,
            delta_ops,
            affected_zones
        )
        
        for zone in affected_zones:
            if zone not in self.external_zone_registry:
                logger.warning(f"External zone {zone} not registered")
                results[zone] = False
                continue
            
            ip, port = self.external_zone_registry[zone]
            
            message = CrossZoneMessage(
                CrossZoneMessageType.DELTA_NOTIFICATION,
                self.zone_name,
                zone,
                notification.to_dict()
            )
            
            try:
                success = self._send_message(ip, port, message)
                results[zone] = success
                
                if success:
                    logger.info(f"Delta notification sent to {zone} at {ip}:{port}")
                else:
                    logger.error(f"Failed to send delta notification to {zone}")
            
            except Exception as e:
                logger.error(f"Error sending delta notification to {zone}: {e}")
                results[zone] = False
        
        return results
    
    def send_incremental_check_request(self,
                                      target_zone: str,
                                      check_domain: str,
                                      property_type: PropertyType,
                                      affected_subgraph: nx.DiGraph) -> Optional[Dict]:
        """
        发送增量检测请求
        
        参数:
            target_zone: 目标域
            check_domain: 检测域名
            property_type: 属性类型
            affected_subgraph: 受影响的子图
        
        返回:
            检测结果
        """
        if target_zone not in self.external_zone_registry:
            logger.error(f"Target zone {target_zone} not registered")
            return None
        
        ip, port = self.external_zone_registry[target_zone]
        
        # 准备请求数据
        payload = {
            'check_domain': check_domain,
            'property_type': property_type.value,
            'affected_subgraph': nx.node_link_data(affected_subgraph),
            'source_zone': self.zone_name
        }
        
        message = CrossZoneMessage(
            CrossZoneMessageType.INCREMENTAL_CHECK_REQUEST,
            self.zone_name,
            target_zone,
            payload
        )
        
        try:
            response = self._send_message_with_response(ip, port, message)
            
            if response:
                logger.info(f"Received incremental check response from {target_zone}")
                return response
            else:
                logger.error(f"No response from {target_zone}")
                return None
        
        except Exception as e:
            logger.error(f"Error sending incremental check request to {target_zone}: {e}")
            return None
    
    def _send_message(self, ip: str, port: int, message: CrossZoneMessage) -> bool:
        """
        发送消息（无需响应）
        
        参数:
            ip: 目标 IP
            port: 目标端口
            message: 消息
        
        返回:
            是否成功
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)  # 5 秒超时
            s.connect((ip, port))
            
            data = json.dumps(message.to_dict())
            s.sendall(data.encode())
            
            s.close()
            return True
        
        except Exception as e:
            logger.error(f"Error sending message to {ip}:{port}: {e}")
            return False
    
    def _send_message_with_response(self, 
                                    ip: str, 
                                    port: int, 
                                    message: CrossZoneMessage,
                                    timeout: int = 10) -> Optional[Dict]:
        """
        发送消息并等待响应
        
        参数:
            ip: 目标 IP
            port: 目标端口
            message: 消息
            timeout: 超时时间（秒）
        
        返回:
            响应数据
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            
            # 发送消息
            data = json.dumps(message.to_dict())
            s.sendall(data.encode())
            
            # 接收响应
            response_data = self._receive_complete_data(s)
            
            s.close()
            return response_data
        
        except socket.timeout:
            logger.error(f"Timeout waiting for response from {ip}:{port}")
            return None
        except Exception as e:
            logger.error(f"Error sending message with response to {ip}:{port}: {e}")
            return None
    
    def _receive_complete_data(self, sock: socket.socket, buffer_size: int = 4096) -> Optional[Dict]:
        """
        接收完整的 JSON 数据
        
        参数:
            sock: socket 对象
            buffer_size: 缓冲区大小
        
        返回:
            解析后的数据
        """
        data = b""
        while True:
            try:
                part = sock.recv(buffer_size)
                if not part:
                    break
                data += part
                
                # 尝试解析 JSON
                try:
                    return json.loads(data.decode())
                except json.JSONDecodeError:
                    continue  # 继续接收数据
            except socket.timeout:
                break
        
        return None
    
    def start_server(self):
        """启动服务器监听"""
        if self.is_running:
            logger.warning("Server is already running")
            return
        
        self.is_running = True
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        logger.info(f"Cross-zone incremental verification server started on {self.listen_ip}:{self.listen_port}")
    
    def stop_server(self):
        """停止服务器"""
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        logger.info("Cross-zone incremental verification server stopped")
    
    def _run_server(self):
        """运行服务器"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.listen_ip, self.listen_port))
            self.server_socket.listen(5)
            logger.info(f"Server listening on {self.listen_ip}:{self.listen_port}")
            
            while self.is_running:
                try:
                    self.server_socket.settimeout(1.0)
                    client_socket, client_address = self.server_socket.accept()
                    
                    # 为每个连接创建新线程
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    thread.start()
                
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.is_running:
                        logger.error(f"Error accepting connection: {e}")
        
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
    
    def _handle_client(self, client_socket: socket.socket, client_address: Tuple):
        """
        处理客户端连接
        
        参数:
            client_socket: 客户端 socket
            client_address: 客户端地址
        """
        try:
            # 接收数据
            data = self._receive_complete_data(client_socket)
            
            if not data:
                logger.warning(f"No data received from {client_address}")
                return
            
            # 解析消息
            message = CrossZoneMessage.from_dict(data)
            logger.info(f"Received message from {client_address}: {message}")
            
            # 处理消息
            response = self._process_message(message)
            
            # 发送响应（如果需要）
            if response:
                response_data = json.dumps(response)
                client_socket.sendall(response_data.encode())
        
        except Exception as e:
            logger.error(f"Error handling client {client_address}: {e}")
        finally:
            client_socket.close()
    
    def _process_message(self, message: CrossZoneMessage) -> Optional[Dict]:
        """
        处理接收到的消息
        
        参数:
            message: 跨域消息
        
        返回:
            响应数据（如果需要）
        """
        if message.message_type == CrossZoneMessageType.DELTA_NOTIFICATION:
            # 处理 Delta 通知
            return self._handle_delta_notification(message)
        
        elif message.message_type == CrossZoneMessageType.INCREMENTAL_CHECK_REQUEST:
            # 处理增量检测请求
            return self._handle_incremental_check_request(message)
        
        elif message.message_type == CrossZoneMessageType.CASCADE_UPDATE:
            # 处理级联更新
            return self._handle_cascade_update(message)
        
        else:
            logger.warning(f"Unknown message type: {message.message_type}")
            return None
    
    def _handle_delta_notification(self, message: CrossZoneMessage) -> Optional[Dict]:
        """处理 Delta 通知"""
        notification = DeltaNotification.from_dict(message.payload)
        
        logger.info(f"Received delta notification from {notification.zone}")
        logger.info(f"  Delta operations: {len(notification.delta_ops)}")
        logger.info(f"  Affected external zones: {notification.affected_external_zones}")
        
        # 保存通知
        self.received_notifications.append(notification)
        
        # 返回确认
        return {
            'status': 'received',
            'zone': self.zone_name,
            'message_id': message.message_id
        }
    
    def _handle_incremental_check_request(self, message: CrossZoneMessage) -> Dict:
        """处理增量检测请求"""
        payload = message.payload
        check_domain = payload['check_domain']
        property_type = PropertyType(payload['property_type'])
        affected_subgraph = nx.node_link_graph(payload['affected_subgraph'])
        
        logger.info(f"Received incremental check request for {check_domain}, property: {property_type.value}")
        
        # 执行检测（这里需要根据实际情况调用相应的检测函数）
        # 简化实现：返回成功状态
        result = {
            'status': 'completed',
            'zone': self.zone_name,
            'check_domain': check_domain,
            'property_type': property_type.value,
            'check_passed': True,
            'errors': [],
            'message_id': message.message_id
        }
        
        return result
    
    def _handle_cascade_update(self, message: CrossZoneMessage) -> Optional[Dict]:
        """处理级联更新"""
        logger.info(f"Received cascade update from {message.source_zone}")
        
        # 这里可以触发本地的增量验证
        # 简化实现：返回确认
        return {
            'status': 'received',
            'zone': self.zone_name,
            'message_id': message.message_id
        }
    
    def cross_zone_incremental_verify(self,
                                     old_records: List[ResourceRecord],
                                     new_records: List[ResourceRecord],
                                     check_config: Dict[PropertyType, Callable]) -> Dict:
        """
        执行跨域增量验证
        
        参数:
            old_records: 旧记录列表
            new_records: 新记录列表
            check_config: 检测配置
        
        返回:
            验证结果（包含跨域通知信息）
        """
        # 1. 执行本地增量验证
        local_results = self.incremental_verify(old_records, new_records, check_config)
        
        # 2. 识别受影响的外部域
        affected_external_zones = self.identify_affected_external_zones(self.delta_operations)
        
        # 3. 发送 Delta 通知
        notification_results = {}
        if affected_external_zones:
            logger.info(f"Affected external zones: {affected_external_zones}")
            notification_results = self.send_delta_notification(
                self.delta_operations,
                affected_external_zones
            )
        
        # 4. 合并结果
        local_results['cross_zone'] = {
            'affected_external_zones': list(affected_external_zones),
            'notification_results': notification_results,
            'notifications_sent': len(notification_results),
            'notifications_successful': sum(1 for v in notification_results.values() if v)
        }
        
        return local_results


def demonstrate_cross_zone_incremental_verification():
    """演示跨域增量验证"""
    print("=" * 70)
    print("跨域增量验证演示")
    print("=" * 70)
    
    # 创建两个域的配置
    # 域 1: example.com
    records_example = [
        ResourceRecord('example.com.', 'NS', 'ns1.example.com.'),
        ResourceRecord('example.com.', 'NS', 'ns2.example.com.'),
        ResourceRecord('ns1.example.com.', 'A', '192.0.2.1'),
        ResourceRecord('ns2.example.com.', 'A', '192.0.2.2'),
    ]
    
    # 域 2: test.com
    records_test = [
        ResourceRecord('test.com.', 'NS', 'ns1.test.com.'),
        ResourceRecord('ns1.test.com.', 'A', '192.0.2.10'),
    ]
    
    # 创建验证器
    graphs_example = build_multi_graph_from_records(records_example, 'example.com.')
    verifier_example = CrossZoneIncrementalVerifier(
        graphs_example,
        'example.com.',
        '127.0.0.1',
        9001
    )
    
    graphs_test = build_multi_graph_from_records(records_test, 'test.com.')
    verifier_test = CrossZoneIncrementalVerifier(
        graphs_test,
        'test.com.',
        '127.0.0.1',
        9002
    )
    
    # 注册外部域
    verifier_example.register_external_zone('test.com.', '127.0.0.1', 9002)
    verifier_test.register_external_zone('example.com.', '127.0.0.1', 9001)
    
    print(f"\n域配置:")
    print(f"  example.com: 监听 127.0.0.1:9001")
    print(f"  test.com: 监听 127.0.0.1:9002")
    
    # 启动服务器
    print(f"\n启动服务器...")
    verifier_example.start_server()
    verifier_test.start_server()
    
    time.sleep(1)  # 等待服务器启动
    
    # 模拟修改
    print(f"\n" + "=" * 70)
    print("场景: 修改 example.com 的 NS 记录")
    print("=" * 70)
    
    old_records = [ResourceRecord('ns1.example.com.', 'A', '192.0.2.1')]
    new_records = [ResourceRecord('ns1.example.com.', 'A', '192.0.2.11')]
    
    # 执行跨域增量验证
    from core.check_properties import check_domain_overflow, check_miss_glue_record
    
    check_config = {
        PropertyType.DOMAIN_OVERFLOW: check_domain_overflow,
        PropertyType.MISSING_GLUE: check_miss_glue_record,
    }
    
    results = verifier_example.cross_zone_incremental_verify(
        old_records,
        new_records,
        check_config
    )
    
    print(f"\n验证结果:")
    print(f"  Delta 操作数: {results.get('delta_operations', 0)}")
    print(f"  本地检测项数: {len(results.get('checks', {}))}")
    
    if 'cross_zone' in results:
        cross_zone = results['cross_zone']
        print(f"\n跨域信息:")
        print(f"  受影响的外部域: {cross_zone['affected_external_zones']}")
        print(f"  发送的通知数: {cross_zone['notifications_sent']}")
        print(f"  成功的通知数: {cross_zone['notifications_successful']}")
    
    # 停止服务器
    time.sleep(1)
    verifier_example.stop_server()
    verifier_test.stop_server()
    
    print("\n" + "=" * 70)
    print("演示完成")
    print("=" * 70)


if __name__ == '__main__':
    demonstrate_cross_zone_incremental_verification()

from enum import Enum


# 定义 RR类型，是属于IN、还是CH
class QueryClass(Enum):
    CLASS_IN = 1
    CLASS_CH = 2
    CLASS_HS = 3



class QueryType(Enum):
    SOA = 0  # 授权开始记录，定义了DNS区域的权威信息
    NS = 1  # 名称服务器记录，DNS的核心组成部分
    A = 2  # IPv4地址记录，基础DNS解析
    AAAA = 3  # IPv6地址记录，随着IPv6的普及越来越重要
    CNAME = 4  # 规范名称记录，用于别名
    DNAME = 5  # 非规范名称记录，用于复杂的域名重定向
    MX = 6  # 邮件交换记录，用于电子邮件系统
    TXT = 7  # 文本记录，常用于存储任意文本信息
    PTR = 8  # 指针记录，常用于反向DNS查找
    SRV = 9  # 服务记录，用于指定服务的确切位置
    SPF = 10  # 发送策略框架记录，用于电子邮件防伪造
    RRSIG = 11  # 公钥签名记录，用于DNSSEC
    NSEC = 12  # 存在性证明记录，用于DNSSE



_type_to_string = {rr_type: rr_type.name for rr_type in QueryType}
_string_to_type = {rr_type.name: rr_type for rr_type in QueryType}


def query_type_to_string(type_: QueryType) -> str:
    return _type_to_string[type_]


def string_to_query_type(type_str: str) -> QueryType:
    type_str = type_str.upper()
    return _string_to_type.get(type_str, QueryType)


# 示例用法
# rr_type = QueryType.A
# print(f"Enum to String: {query_type_to_string(rr_type)}")  # 输出: Enum to String: A
#
# type_str = "mx"
# rr_type = string_to_query_type(type_str)
# print(f"String to Enum: {rr_type}")  # 输出: String to Enum: RRType.MX

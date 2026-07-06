import networkx as nx
from entity.resource_record import ResourceRecord


class ZoneGraph:
    def __init__(self, origin, rr_list):
        self.origin = origin
        self.all_graph = nx.DiGraph(origin=origin)
        self.glue_graph = nx.DiGraph(origin=origin)
        self.cname_graph = nx.DiGraph(origin=origin)
        self.dname_graph = nx.DiGraph(origin=origin)
        self.build_all_graph(rr_list)

    def build_all_graph(self, record_list: list[ResourceRecord]):
        for record in record_list:
            domain_name, query_type, value = record.get_record_tuple()

            self.all_graph.add_edge(domain_name, value, query_type=query_type)

            # ================== 处理 glue graph ==================
            if query_type in {"NS", "A", "AAAA"}:
                self.glue_graph.add_edge(domain_name, value, query_type=query_type)

            # ================== 处理 cname graph ==================
            if query_type == "CNAME":
                self.cname_graph.add_edge(domain_name, value, query_type=query_type)

            # ================== 处理 dname graph ==================
            if query_type == "DNAME":
                self.dname_graph.add_edge(domain_name, value, query_type=query_type)

    def visualize(self, graph):
        # 定义节点的位置，可以是自动布局，也可以是自定义的
        pos = nx.spring_layout(graph)
        # 绘制图
        nx.draw(graph, pos, with_labels=True)
        # 绘制边的标签
        edge_labels = nx.get_edge_attributes(graph, 'query_type')
        nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_color='red')
        # 显示图形
        plt.show()
        # 保存图形

    def get_all_graph(self):
        return self.all_graph

    def get_origin(self):
        return self.origin


    def get_glue_graph(self):
        return self.glue_graph

    def get_cname_graph(self):
        return self.cname_graph

    def get_dname_graph(self):
        return self.dname_graph

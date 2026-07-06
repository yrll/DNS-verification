from enums.rr_enum import string_to_query_type, query_type_to_string


class ResourceRecord:
    def __init__(self, domain_name, query_type: str, value: str):
        self.domain_name = domain_name
        # self.query_type = string_to_query_type(query_type)
        self.query_type = query_type.upper()
        self.value = value

    def __str__(self):
        return f"{self.domain_name}  {self.query_type}  {self.value}"

    def get_record_tuple(self):
        # 返回一个包含domain_name, query_type, value的元组
        # return self.domain_name, query_type_to_string(self.query_type), self.value
        return self.domain_name, self.query_type, self.value

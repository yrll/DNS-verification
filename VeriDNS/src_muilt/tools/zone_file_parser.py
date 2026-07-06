import re
import threading
from entity.resource_record import ResourceRecord


class ZoneFileParser:
    def __init__(self, zone_name: str, zone_file_path: str, origin: str = None):
        self.zone_name = zone_name.lower()
        self.origin = origin
        self.zone_file_path = zone_file_path
        self.records = self.read_zone_file(zone_file_path)
        # self.records = self.read_zone_file_threaded(zone_file_path)
        
        
    
    
    def read_zone_file(self, zone_file_path: str) -> list:
        record_list = []
        origin_server = self.origin
        pattern = re.compile(r"((\S+).*\s+(a|aaaa|cname|dname|ns|mx|txt)\s+([\s\S]+))")

        try:
            with open(zone_file_path, 'r') as f:
                lines = f.read().lower().splitlines()

            for line in lines:
                line = line.strip()

                matcher = pattern.match(line)
                if matcher:
                    record = self.parse_resource_record(matcher, origin_server)
                    if record:
                        record_list.append(record)
        except FileNotFoundError:
            print(f"File not found: {zone_file_path}")
        
        return record_list

    def parse_resource_record(self, matcher: re.Match, origin_server: str) -> ResourceRecord:
        domain_name = matcher.group(2).lower()
        query_class = matcher.group(3).lower()
        value = matcher.group(4).strip().lower()

        if query_class in {"cname", "dname", "ns"}:
            if domain_name == "@":
                domain_name = origin_server
            if not domain_name.endswith("."):
                domain_name += "." + origin_server

            if value == "@":
                value = origin_server
            if not value.endswith("."):
                value += "." + origin_server
        return ResourceRecord(domain_name, query_class, value)

    def get_records(self) -> list[ResourceRecord]:
        return self.records
     # 使用生成器来逐个产生记录
    
    def get_origin(self) -> str:
        return self.origin





    def read_zone_file_threaded(self, zone_file_path: str) -> list:
        record_list = []
        origin_server = self.origin
        pattern = re.compile(r"((\S+).*\s+(a|aaaa|cname|dname|ns|mx|txt)\s+([\s\S]+))")

        def process_lines(lines, record_list):
            for line in lines:
                line = line.strip()
                matcher = pattern.match(line)
                if matcher:
                    record = self.parse_resource_record(matcher, origin_server)
                    if record:
                        record_list.append(record)

        try:
            with open(zone_file_path, 'r') as f:
                lines = f.read().lower().splitlines()

            # Split lines into chunks for parallel processing
            num_threads = 4  # Adjust as needed
            chunk_size = len(lines) // num_threads
            threads = []

            for i in range(num_threads):
                start = i * chunk_size
                end = start + chunk_size if i < num_threads - 1 else len(lines)
                chunk_lines = lines[start:end]
                thread = threading.Thread(target=process_lines, args=(chunk_lines, record_list))
                threads.append(thread)
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

        except FileNotFoundError:
            print(f"File not found: {zone_file_path}")
        
        return record_list
    
    
    

   
'''
class ZoneFileParser:
    def __init__(self, zone_name: str, zone_file_path: str, origin: str = None):
        self.zone_name = zone_name.lower()
        self.origin = origin
        self.zone_file_path = zone_file_path
        self.records = self.read_zone_file(zone_file_path)

    def read_zone_file(self, zone_file_path: str) -> list:
        # if self.origin is None or self.origin == "":
        #     self.origin = self.zone_name[:-4]
        record_list = []
        origin_server = self.origin
        pattern = re.compile(r"((\S+).*\s+(a|aaaa|cname|dname|ns|mx|txt)\s+([\s\S]+))")

        try:
            with open(zone_file_path, 'r') as f:
                lines = f.read().lower().splitlines()

            for line in lines:
                line = line.strip()
                # if line.startswith("$origin"):
                #     origin_server = line.split()[1]
                #     if not origin_server.endswith("."):
                #         origin_server += "."
                #     self.origin = origin_server
                #     continue

                matcher = pattern.match(line)
                if matcher:
                    record = self.parse_resource_record(matcher, origin_server)
                    if record:
                        record_list.append(record)
        except FileNotFoundError:
            print(f"File not found: {zone_file_path}")

        return record_list

    def parse_resource_record(self, matcher: re.Match, origin_server: str) -> ResourceRecord:
        domain_name = matcher.group(2).lower()
        query_class = matcher.group(3).lower()
        value = matcher.group(4).strip().lower()

        if query_class in {"cname", "dname", "ns"}:
            if domain_name == "@":
                domain_name = origin_server
            if not domain_name.endswith("."):
                domain_name += "." + origin_server

            if value == "@":
                value = origin_server
            if not value.endswith("."):
                value += "." + origin_server
        return ResourceRecord(domain_name, query_class, value)

    def get_records(self) -> list[ResourceRecord]:
        return self.records

    def get_origin(self) -> str:
        return self.origin

'''
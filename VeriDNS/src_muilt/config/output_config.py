import json
import os


class Output:
    def __init__(self, log_file_name="output.json"):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.path.join(project_root, "log")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        # 设置完整的日志文件路径
        self.log_file_path = os.path.join(log_dir, log_file_name)

    def debug(self, message: str):
        # 实际应用中，你可能需要配置一个真正的调试日志记录器
        print(message)  # 打印调试信息

    def error_info(self, property: str, domain_name: str, error_message: dict):
        # 准备错误信息字典
        error_info = {
            "Property": property,
            "domain_name": domain_name,
            "error_message": error_message
        }
        # 打开日志文件，追加错误信息
        with open(self.log_file_path, 'a') as f:
            # 将字典转换为JSON字符串，并写入文件
            # 使用'\n'确保每个错误信息在文件中占一行
            json.dump(error_info, f, indent=4)
            f.write('\n')

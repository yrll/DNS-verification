# log_config.py
import logging
import logging.config
import os

project_root = os.path.dirname(os.path.abspath(__file__))
# 假设 logging.conf 文件已经正确配置了所有的 logger、handler 和 formatter
# logging.config.fileConfig(os.path.join(project_root, 'logging.conf'))

def setup_logging(log_file=None):
    """设置日志配置"""
    if log_file:
        with open(os.path.join(project_root, 'logging.conf'), 'rt') as f:
            config_str = f.read()
            config_str = config_str.replace('LOG_FILE.log', log_file)
        config_file = os.path.join(project_root, 'tmp_logging.conf')
        with open(config_file, 'wt') as f:
            f.write(config_str)
        logging.config.fileConfig(config_file, disable_existing_loggers=False)
        os.remove(config_file)  # 删除临时配置文件
    else:
        logging.config.fileConfig(os.path.join(project_root, 'logging.conf'), disable_existing_loggers=False)
    return logging.getLogger(log_file)
    
    
# 在模块导入时执行日志配置
# setup_logging()



# # 创建一个全局的 logger
# logger = logging.getLogger(__name__)


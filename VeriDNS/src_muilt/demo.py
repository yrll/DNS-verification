# 在其他地方导入logger
from config.log_config import setup_logging

# 自定义log文件名
logger = setup_logging(log_file="a.log")

# 在需要记录日志的地方调用logger，并传入自定义的log文件名
logger.info("This is an info message.")
logger.error("This is an error message.", exc_info=True)




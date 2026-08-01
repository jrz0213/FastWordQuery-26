import os
import logging
from logging.handlers import RotatingFileHandler

# 将此变量设置为 True 即可默认开启日志
ENABLE_LOGGING = False

class TruncatingFormatter(logging.Formatter):
    """
    自定义的日志格式化器，用于自动截断过长的日志消息
    """
    def __init__(self, fmt=None, max_len=500):
        super().__init__(fmt)
        self.max_len = max_len

    def format(self, record):
        # 先把消息和参数拼接成最终的字符串
        msg = record.getMessage()
        
        # 如果长度超过限制，进行截断并加上提示
        if len(msg) > self.max_len:
            msg = msg[:self.max_len] + f" ... [后续内容过长已自动截断，原长 {len(msg)} 字符]"
            
        # 临时替换 record 的信息以便父类按照格式（fmt）生成最终文本
        original_msg = record.msg
        original_args = record.args
        record.msg = msg
        record.args = None
        
        result = super().format(record)
        
        # 恢复现场（防止影响其他可能存在的 Handler）
        record.msg = original_msg
        record.args = original_args
        
        return result


logger = logging.getLogger('FastWordQuery_Log')
logger.propagate = False

def set_logging_state(enable: bool):
    """
    统一管理日志开关的底层接口
    """
    global ENABLE_LOGGING
    ENABLE_LOGGING = enable
    
    # 清除所有现有的处理器 (Handlers)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        
    if enable:
        logger.setLevel(logging.INFO)
        log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fwq-logger.log')
        fh = RotatingFileHandler(log_path, maxBytes=1024*1024, backupCount=1, encoding='utf-8')
        fmt = '%(asctime)s | %(levelname)s | %(message)s'
        fh.setFormatter(TruncatingFormatter(fmt, max_len=500))  # 设定截断字数
        logger.addHandler(fh)
        logger.info("[系统控制] 日志记录已开启。")
    else:
        logger.setLevel(logging.WARNING)
        logger.addHandler(logging.NullHandler())

# 首次导入时初始化执行一次
if not logger.handlers:
    set_logging_state(ENABLE_LOGGING)
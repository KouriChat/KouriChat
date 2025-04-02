"""
日志工具模块
提供日志记录功能，包括:
- 日志配置管理
- 日志文件轮转
- 日志清理
- 多级别日志记录
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional

class LoggerConfig:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.log_dir = os.path.join(root_dir, "logs")
        self.ensure_log_dir()

    def ensure_log_dir(self):
        """确保日志目录存在"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def get_log_file(self):
        """获取日志文件路径"""
        current_date = datetime.now().strftime("%Y%m%d")
        return os.path.join(self.log_dir, f"bot_{current_date}.log")

    def setup_logger(self, name: Optional[str] = None, level: int = logging.INFO):
        """配置日志记录器"""
        # 创建或获取日志记录器
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False  # 修改为False，防止日志消息向上传播导致重复记录
        
        # 移除所有已有的handler，防止重复
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        # 修改日志格式：[日期时间] - 级别 - 消息
        console_formatter = logging.Formatter(
            '[%(asctime)s] - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # 创建文件处理器
        file_handler = RotatingFileHandler(
            self.get_log_file(),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        # 修改文件日志格式：[日期时间] - 名称 - 级别 - 消息
        file_formatter = logging.Formatter(
            '[%(asctime)s] - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # 设置特定模块的日志级别，减少冗余日志
        logging.getLogger('openai').setLevel(logging.WARNING)  # 减少openai库的日志输出
        logging.getLogger('httpx').setLevel(logging.WARNING)  # 减少http请求的日志输出
        
        # 设置API请求相关日志级别
        if name == 'api_client':
            logging.getLogger('api_client').setLevel(logging.WARNING)
        
        return logger

    def cleanup_old_logs(self, days: int = 7):
        """清理指定天数之前的日志文件"""
        try:
            current_date = datetime.now()
            for filename in os.listdir(self.log_dir):
                if not filename.startswith("bot_") or not filename.endswith(".log"):
                    continue
                
                file_path = os.path.join(self.log_dir, filename)
                file_date_str = filename[4:12]  # 提取日期部分 YYYYMMDD
                try:
                    file_date = datetime.strptime(file_date_str, "%Y%m%d")
                    days_old = (current_date - file_date).days
                    
                    if days_old > days:
                        os.remove(file_path)
                        print(f"已删除旧日志文件: {filename}")
                except ValueError:
                    continue
        except Exception as e:
            print(f"清理日志文件失败: {str(e)}")

# 添加一个兼容函数，用于获取日志记录器
def get_logger(name: Optional[str] = None, level: int = logging.INFO):
    """
    获取一个日志记录器实例。这是一个兼容函数，用于与依赖于get_logger函数的模块兼容。
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        
    Returns:
        logger: 日志记录器实例
    """
    # 创建或获取日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 如果没有处理器，添加一个简单的控制台处理器
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        # 修改为新的日志格式
        formatter = logging.Formatter(
            '[%(asctime)s] - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger 
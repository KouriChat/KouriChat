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
        logger.propagate = True  # 确保日志能正确传播
        
        # 移除所有已有的handler，防止重复
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
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
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

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


def debuggerLogger(name: Optional[str] = None, level: int = logging.DEBUG):
    """调试日志记录器"""
    logger = LoggerConfig(".").setup_logger(name, level)
    return logger

def infoLogger(name: Optional[str] = None, level: int = logging.INFO):
    """信息日志记录器"""
    logger = LoggerConfig(".").setup_logger(name, level)
    return logger
    
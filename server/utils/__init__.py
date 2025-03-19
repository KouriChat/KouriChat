"""工具模块

提供各种通用工具类和函数，包括：
- IO操作工具
- 日志工具
- 其他实用工具
"""
import os
from .Io_util import IoUtil
from .logger_util import LoggerConfig, debuggerLogger, infoLogger
from .Io_util import IoUtil

def dir_path():
    """获取项目根目录路径
    
    通过查找特定标志文件（server_readme.md）来确定根目录位置
    
    Returns:
        str: 项目根目录的绝对路径
    """
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # 检查是否存在标志文件
    flag_files = ['requirements.txt']
    for file in flag_files:
        if os.path.exists(os.path.join(current_dir, file)):
            return current_dir
            
    raise FileNotFoundError('无法找到项目根目录，请确保存在 requirements.txt 文件')


__all__ = [
    'IoUtil',  # IO操作工具类
    'LoggerConfig',  # 日志配置类
    'debuggerLogger',  # 调试日志记录器
    'infoLogger',  # 信息日志记录器
    'IoUtil',  # IO操作工具类
    'dir_path'  # 目录路径验证函数
]
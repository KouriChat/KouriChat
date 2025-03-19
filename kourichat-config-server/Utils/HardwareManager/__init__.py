import psutil
import os
import time
from typing import Dict, Any
from pathlib import Path


class HardwareManager:
    """硬件资源管理器，用于监控系统资源使用情况"""
    
    _last_net_io = None
    _last_net_time = None
    
    @staticmethod
    def get_cpu_usage() -> float:
        """获取CPU使用率（0-100，保留1位小数）
        
        Returns:
            float: CPU使用率百分比
        """
        return round(psutil.cpu_percent(interval=1), 1)
    
    @staticmethod
    def get_memory_usage() -> Dict[str, float]:
        """获取内存使用情况
        
        Returns:
            Dict[str, float]: 包含内存使用率和详细信息的字典
            {
                'total': 总内存（GB）,
                'used': 已使用内存（GB）,
                'percent': 内存使用率百分比（0-100，保留1位小数）
            }
        """
        memory = psutil.virtual_memory()
        return {
            'total': round(memory.total / (1024 ** 3), 2),  # GB
            'used': round(memory.used / (1024 ** 3), 2),    # GB
            'percent': round(memory.percent, 1)
        }
    
    @classmethod
    def get_network_speed(cls) -> Dict[str, float]:
        """获取网络速度（kb/s）
        
        Returns:
            Dict[str, float]: 包含上传和下载速度的字典
            {
                'upload': 上传速度（kb/s）,
                'download': 下载速度（kb/s）
            }
        """
        current_net = psutil.net_io_counters()
        current_time = time.time()
        
        # 初始化或重置计数器
        if cls._last_net_io is None or cls._last_net_time is None:
            cls._last_net_io = current_net
            cls._last_net_time = current_time
            return {'upload': 0.0, 'download': 0.0}
        
        # 计算时间差（秒）
        time_diff = current_time - cls._last_net_time
        
        # 计算速度（kb/s）
        upload_speed = (current_net.bytes_sent - cls._last_net_io.bytes_sent) / 1024 / time_diff
        download_speed = (current_net.bytes_recv - cls._last_net_io.bytes_recv) / 1024 / time_diff
        
        # 更新上次的值
        cls._last_net_io = current_net
        cls._last_net_time = current_time
        
        return {
            'upload': round(upload_speed, 2),
            'download': round(download_speed, 2)
        }
    
    @staticmethod
    def get_disk_usage() -> Dict[str, float]:
        """获取当前程序所在磁盘的使用情况
        
        Returns:
            Dict[str, float]: 包含磁盘使用情况的字典
            {
                'total': 总容量（GB）,
                'used': 已使用（GB）,
                'percent': 使用率百分比（0-100，保留2位小数）
            }
        """
        current_path = Path(os.getcwd()).resolve()
        disk_usage = psutil.disk_usage(str(current_path.anchor))
        
        return {
            'total': round(disk_usage.total / (1024 ** 3), 2),
            'used': round(disk_usage.used / (1024 ** 3), 2),
            'percent': round(disk_usage.percent, 2)
        }
    
    @classmethod
    def get_system_info(cls) -> Dict[str, Any]:
        """获取系统信息，按指定格式返回
        
        Returns:
            Dict[str, Any]: 包含系统信息的字典，格式如下：
            {
                "status": "success",
                "message": "获取系统信息成功",
                "data": {
                    "cpu_percent": CPU使用率,
                    "memory": {
                        "total": 总内存,
                        "used": 已用内存,
                        "percent": 内存使用率
                    },
                    "disk": {
                        "total": 总容量,
                        "used": 已用容量,
                        "percent": 使用率
                    },
                    "network": {
                        "upload": 上传速度,
                        "download": 下载速度
                    }
                }
            }
        """
        try:
            return {
                "status": "success",
                "message": "获取系统信息成功",
                "data": {
                    "cpu_percent": cls.get_cpu_usage(),
                    "memory": cls.get_memory_usage(),
                    "disk": cls.get_disk_usage(),
                    "network": cls.get_network_speed()
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"获取系统信息失败: {str(e)}",
                "data": {
                    "cpu_percent": 0,
                    "memory": {
                        "total": 0,
                        "used": 0,
                        "percent": 0
                    },
                    "disk": {
                        "total": 0,
                        "used": 0,
                        "percent": 0
                    },
                    "network": {
                        "upload": 0,
                        "download": 0
                    }
                }
            }

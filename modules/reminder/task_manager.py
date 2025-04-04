"""
任务管理器 - 负责管理定时任务
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from utils.console import print_status  # 添加这行

logger = logging.getLogger('main')

class TaskManager:
    def __init__(self):
        """初始化任务管理器"""
        self.scheduler = BackgroundScheduler()
        self.active_tasks: Dict[str, dict] = {}
        self.scheduler.start()
        print_status("任务管理器已启动", "success", "CHECK")  # 添加启动提示
        logger.info("任务管理器已启动")

    def add_task(self, task_id: str, target_time: datetime, callback, args=None) -> bool:
        """
        添加定时任务
        Args:
            task_id: 任务ID
            target_time: 目标时间
            callback: 回调函数
            args: 回调函数参数
        """
        try:
            self.scheduler.add_job(
                callback,
                trigger=DateTrigger(run_date=target_time),
                args=args or [],
                id=task_id
            )
            
            # 添加任务信息显示
            time_diff = target_time - datetime.now()
            minutes = int(time_diff.total_seconds() / 60)
            
            print("\n" + "=" * 80)
            print(f"创建定时任务")
            print("-" * 80)
            print(f"任务ID: {task_id}")
            print(f"执行时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')} ({minutes}分钟后)")
            if args:
                print(f"任务参数: {args}")
            print("=" * 80 + "\n")
            
            logger.info(f"成功添加任务: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加任务失败: {str(e)}")
            print_status(f"添加任务失败: {str(e)}", "error", "CROSS")
            return False

    def remove_task(self, task_id: str):
        """移除任务"""
        try:
            self.scheduler.remove_job(task_id)
            print_status(f"已移除任务: {task_id}", "info", "INFO")
            logger.info(f"已移除任务: {task_id}")
        except Exception as e:
            logger.error(f"移除任务失败: {str(e)}")
            print_status(f"移除任务失败: {str(e)}", "error", "CROSS")

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        print_status("任务管理器已关闭", "warning", "WARNING")
        logger.info("任务管理器已关闭") 
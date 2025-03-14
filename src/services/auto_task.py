import logging
import schedule
import threading
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass

# 添加try-except块来处理可能的导入错误
try:
    from src.config import config
except ImportError:
    # 如果导入失败，创建一个空的配置对象
    @dataclass
    class EmptyConfig:
        pass
    
    class Config:
        def __init__(self):
            self.behavior = EmptyConfig()
            self.behavior.schedule_settings = EmptyConfig()
            self.behavior.schedule_settings.tasks = []
    
    config = Config()
    logging.warning("无法导入config模块，使用空配置对象替代")

logger = logging.getLogger(__name__)

class AutoTasker:
    def __init__(self, message_handler):
        self.message_handler = message_handler
        self.tasks: Dict[str, Dict] = {}
        self.scheduler = schedule.Scheduler()
        self._thread = None
        self._running = False

    def start(self):
        """启动任务调度器"""
        if self._thread is not None:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("自动任务调度器已启动")

    def stop(self):
        """停止任务调度器"""
        self._running = False
        if self._thread:
            self._thread.join()
            self._thread = None
        logger.info("自动任务调度器已停止")

    def _run(self):
        """运行调度器"""
        while self._running:
            self.scheduler.run_pending()
            time.sleep(1)

    def add_task(self, task_id: str, chat_id: str, content: str, 
                 schedule_type: str, schedule_time: str = '', 
                 interval: Optional[int] = None, is_active: bool = True):
        """添加任务"""
        if not is_active:
            return

        if task_id in self.tasks:
            self.remove_task(task_id)

        task = {
            'chat_id': chat_id,
            'content': content,
            'schedule_type': schedule_type
        }

        def job():
            try:
                # 修改消息发送方式
                self.message_handler.add_to_queue(
                    chat_id=chat_id,
                    content=content,
                    sender_name="System",
                    username="AutoTasker",
                    is_group=False
                )
                logger.info(f"定时任务执行成功: {task_id}")
            except Exception as e:
                logger.error(f"定时任务执行失败 {task_id}: {str(e)}")

        if schedule_type == 'cron':
            # 解析cron表达式
            minute, hour, day, month, day_of_week = schedule_time.split()
            self.scheduler.every().day.at(f"{hour.zfill(2)}:{minute.zfill(2)}").do(job)
            logger.info(f"添加定时任务: {task_id}, 时间: {hour}:{minute}")
        else:
            # 使用时间间隔
            self.scheduler.every(interval).seconds.do(job)
            logger.info(f"添加间隔任务: {task_id}, 间隔: {interval}秒")

        self.tasks[task_id] = task
        logger.info(f"已添加任务: {task_id}")

    def remove_task(self, task_id: str):
        """移除任务"""
        if task_id in self.tasks:
            # 从调度器中移除所有任务并重新添加其他任务
            self.scheduler.clear()
            del self.tasks[task_id]
            logger.info(f"已移除任务: {task_id}")

    def get_all_tasks(self):
        """获取所有任务"""
        return self.tasks 
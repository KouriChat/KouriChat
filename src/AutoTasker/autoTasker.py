from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging
import yaml
import os

logger = logging.getLogger(__name__)

class AutoTasker:
    def __init__(self, message_handler, task_file_path="src/config/config.yaml", auto_load=True):
        """
        初始化自动任务管理器
        
        Args:
            message_handler: 消息处理器实例，用于发送消息
            task_file_path: 任务配置文件路径
            auto_load: 是否自动加载任务配置文件
        """
        self.message_handler = message_handler
        self.task_file_path = task_file_path
        self.scheduler = BackgroundScheduler()
        self.tasks = {}
        
        # 确保任务文件目录存在
        os.makedirs(os.path.dirname(task_file_path), exist_ok=True)
        
        # 加载已存在的任务（如果auto_load为True）
        if auto_load:
            self.load_tasks()
        
        # 启动调度器
        self.scheduler.start()
        logger.info("AutoTasker 初始化完成")

    def load_tasks(self):
        """从文件加载任务配置"""
        try:
            if os.path.exists(self.task_file_path):
                with open(self.task_file_path, 'r', encoding='utf-8') as f:
                    tasks_data = yaml.load(f, Loader=yaml.FullLoader)
                
                # 检查配置文件结构
                if "categories" in tasks_data and "schedule_settings" in tasks_data["categories"]:
                    if "settings" in tasks_data["categories"]["schedule_settings"] and "tasks" in tasks_data["categories"]["schedule_settings"]["settings"]:
                        tasks = tasks_data["categories"]["schedule_settings"]["settings"]["tasks"]["value"]
                        if tasks:
                            for task in tasks:
                                self.add_task(
                                    task_id=task["task_id"],
                                    chat_id=task['chat_id'],
                                    content=task['content'],
                                    schedule_type=task['schedule_type'],
                                    schedule_time=task['schedule_time'],
                                    is_active=task['is_active']
                                )
                            logger.info(f"成功加载 {len(tasks)} 个任务")
                        else:
                            logger.debug("没有找到任务配置")
                    else:
                        logger.debug("配置文件中没有找到 tasks 设置")
                else:
                    logger.debug("配置文件中没有找到 schedule_settings 配置")
        except KeyError:
            # 静默处理 KeyError，这通常是因为配置结构不完整
            logger.debug("配置文件结构不完整，无法加载任务")
        except Exception as e:
            # 其他异常仍然记录，但使用 warning 级别而不是 error
            logger.warning(f"加载任务时遇到问题: {str(e)}")

    def save_tasks(self):
        """保存任务配置到文件"""
        try:
            tasks_data = [
                {
                    'task_id': task_id,
                    'chat_id': task['chat_id'],
                    'content': task['content'],
                    'schedule_type': task['schedule_type'],
                    'schedule_time': task['schedule_time'],
                    'is_active': task['is_active']
                }
                for task_id, task in self.tasks.items()
            ]
            with open(self.task_file_path, 'r', encoding='utf-8') as f:
                configYaml = yaml.load(f, Loader=yaml.FullLoader)
            configYaml["categories"]["schedule_settings"]["settings"]["tasks"]["value"] = tasks_data
            with open(self.task_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(configYaml, f, allow_unicode=True)
            logger.info("任务配置已保存")
        except Exception as e:
            logger.error(f"保存任务失败: {str(e)}")

    def add_task(self, task_id, chat_id, content, schedule_type, schedule_time,is_active=True):
        """
        添加新任务
        
        Args:
            task_id: 任务ID
            chat_id: 接收消息的聊天ID
            content: 消息内容
            schedule_type: 调度类型 ('cron' 或 'interval')
            schedule_time: 调度时间 (cron表达式 或 具体时间)
            is_active: 是否激活任务
        """
        try:
            if schedule_type == 'cron':
                trigger = CronTrigger.from_crontab(schedule_time)
            elif schedule_type == 'interval':
                trigger = IntervalTrigger(seconds=int(schedule_time))
            else:
                raise ValueError(f"不支持的调度类型: {schedule_type}")

            # 创建任务执行函数
            def task_func():
                try:
                    if self.tasks[task_id]['is_active']:
                        self.message_handler.add_to_auto_task_queue(
                            chat_id=chat_id,
                            content=content
                        )
                        logger.info(f"执行定时任务 {task_id}")
                except Exception as e:
                    logger.error(f"执行任务 {task_id} 失败: {str(e)}")

            # 添加任务到调度器
            job = self.scheduler.add_job(
                task_func,
                trigger=trigger,
                id=task_id
            )

            # 保存任务信息
            self.tasks[task_id] = {
                'chat_id': chat_id,
                'content': content,
                'schedule_type': schedule_type,
                'schedule_time': schedule_time,
                'is_active': is_active,
                'job': job
            }

            self.save_tasks()
            logger.info(f"添加任务成功: {task_id}")
            
        except Exception as e:
            logger.error(f"添加任务失败: {str(e)}")
            raise

    def remove_task(self, task_id):
        """删除任务"""
        try:
            if task_id in self.tasks:
                self.tasks[task_id]['job'].remove()
                del self.tasks[task_id]
                self.save_tasks()
                logger.info(f"删除任务成功: {task_id}")
            else:
                logger.warning(f"任务不存在: {task_id}")
        except Exception as e:
            logger.error(f"删除任务失败: {str(e)}")

    def update_task(self, task_id, **kwargs):
        """更新任务配置"""
        try:
            if task_id not in self.tasks:
                raise ValueError(f"任务不存在: {task_id}")

            task = self.tasks[task_id]
            
            # 更新任务参数
            for key, value in kwargs.items():
                if key in task:
                    task[key] = value

            # 如果需要更新调度
            if 'schedule_type' in kwargs or 'schedule_time' in kwargs:
                self.remove_task(task_id)
                self.add_task(
                    task_id=task_id,
                    chat_id=task['chat_id'],
                    content=task['content'],
                    schedule_type=task['schedule_type'],
                    schedule_time=task['schedule_time'],
                    is_active=task['is_active']
                )
            else:
                self.save_tasks()
                
            logger.info(f"更新任务成功: {task_id}")
            
        except Exception as e:
            logger.error(f"更新任务失败: {str(e)}")
            raise

    def toggle_task(self, task_id):
        """切换任务的激活状态"""
        try:
            if task_id in self.tasks:
                self.tasks[task_id]['is_active'] = not self.tasks[task_id]['is_active']
                self.save_tasks()
                status = "激活" if self.tasks[task_id]['is_active'] else "暂停"
                logger.info(f"任务 {task_id} 已{status}")
            else:
                logger.warning(f"任务不存在: {task_id}")
        except Exception as e:
            logger.error(f"切换任务状态失败: {str(e)}")

    def get_task(self, task_id):
        """获取任务信息"""
        return self.tasks.get(task_id)

    def get_all_tasks(self):
        """获取所有任务信息"""
        return {
            task_id: {
                k: v for k, v in task_info.items() if k != 'job'
            }
            for task_id, task_info in self.tasks.items()
        }

    def __del__(self):
        """清理资源"""
        if hasattr(self, 'scheduler'):
            self.scheduler.shutdown()

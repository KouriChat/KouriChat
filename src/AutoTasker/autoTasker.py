from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging
import json
import os

logger = logging.getLogger(__name__)

class AutoTasker:
    def __init__(self, message_handler, task_file_path="src/config/config.json"):
        """
        初始化自动任务管理器
        
        Args:
            message_handler: 消息处理器实例，用于发送消息
            task_file_path: 任务配置文件路径
        """
        self.message_handler = message_handler
        self.task_file_path = task_file_path
        self.scheduler = BackgroundScheduler()
        self.tasks = {}
        
        # 确保任务文件目录存在
        try:
            os.makedirs(os.path.dirname(task_file_path), exist_ok=True)
        except Exception as e:
            logger.error(f"创建任务目录失败: {str(e)}")
        
        # 加载已存在的任务
        try:
            self.load_tasks()
        except Exception as e:
            logger.error(f"加载任务失败: {str(e)}")
        
        # 启动调度器
        try:
            self.scheduler.start()
            logger.info("AutoTasker 初始化完成")
        except Exception as e:
            logger.error(f"启动调度器失败: {str(e)}")

    def load_tasks(self):
        """从文件加载任务配置"""
        try:
            if os.path.exists(self.task_file_path):
                with open(self.task_file_path, 'r', encoding='utf-8') as f:
                    tasks_data = json.load(f)
                
                # 检查配置文件结构
                if not isinstance(tasks_data, dict):
                    logger.error("任务配置文件格式错误")
                    return
                
                # 检查必要的配置路径
                if "categories" not in tasks_data:
                    logger.error("任务配置文件缺少categories字段")
                    return
                
                if "schedule_settings" not in tasks_data["categories"]:
                    logger.error("任务配置文件缺少schedule_settings字段")
                    return
                
                if "settings" not in tasks_data["categories"]["schedule_settings"]:
                    logger.error("任务配置文件缺少settings字段")
                    return
                
                if "tasks" not in tasks_data["categories"]["schedule_settings"]["settings"]:
                    logger.error("任务配置文件缺少tasks字段")
                    return
                
                if "value" not in tasks_data["categories"]["schedule_settings"]["settings"]["tasks"]:
                    logger.error("任务配置文件缺少value字段")
                    return
                
                tasks_list = tasks_data["categories"]["schedule_settings"]["settings"]["tasks"]["value"]
                if not isinstance(tasks_list, list):
                    logger.error("任务列表格式错误")
                    return
                
                for task in tasks_list:
                    try:
                        # 检查任务必要字段
                        required_fields = ['task_id', 'chat_id', 'content', 'schedule_type', 'schedule_time']
                        if not all(field in task for field in required_fields):
                            logger.warning(f"任务缺少必要字段: {task}")
                            continue
                        
                        self.add_task(
                            task_id=task["task_id"],
                            chat_id=task['chat_id'],
                            content=task['content'],
                            schedule_type=task['schedule_type'],
                            schedule_time=task['schedule_time'],
                            is_active=task.get('is_active', True)
                        )
                    except Exception as task_error:
                        logger.error(f"加载单个任务失败: {str(task_error)}")
                        continue
                
                logger.info(f"成功加载 {len(self.tasks)} 个任务")
            else:
                logger.warning(f"任务配置文件不存在: {self.task_file_path}")
        except Exception as e:
            logger.error(f"加载任务失败: {str(e)}")
            # 不抛出异常，让程序继续运行

    def save_tasks(self):
        """保存任务配置到文件"""
        try:
            # 准备任务数据
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
            
            # 检查配置文件是否存在
            if not os.path.exists(self.task_file_path):
                logger.warning(f"配置文件不存在，将创建新文件: {self.task_file_path}")
                # 创建基本配置结构
                configJson = {
                    "categories": {
                        "schedule_settings": {
                            "title": "定时任务配置",
                            "settings": {
                                "tasks": {
                                    "value": tasks_data,
                                    "type": "array",
                                    "description": "定时任务列表"
                                }
                            }
                        }
                    }
                }
            else:
                # 读取现有配置
                try:
                    with open(self.task_file_path, 'r', encoding='utf-8') as f:
                        configJson = json.load(f)
                except json.JSONDecodeError:
                    logger.error("配置文件格式错误，将创建新文件")
                    configJson = {
                        "categories": {
                            "schedule_settings": {
                                "title": "定时任务配置",
                                "settings": {
                                    "tasks": {
                                        "value": tasks_data,
                                        "type": "array",
                                        "description": "定时任务列表"
                                    }
                                }
                            }
                        }
                    }
                except Exception as read_error:
                    logger.error(f"读取配置文件失败: {str(read_error)}")
                    return
            
            # 确保配置文件结构完整
            if "categories" not in configJson:
                configJson["categories"] = {}
            
            if "schedule_settings" not in configJson["categories"]:
                configJson["categories"]["schedule_settings"] = {
                    "title": "定时任务配置",
                    "settings": {}
                }
            
            if "settings" not in configJson["categories"]["schedule_settings"]:
                configJson["categories"]["schedule_settings"]["settings"] = {}
            
            if "tasks" not in configJson["categories"]["schedule_settings"]["settings"]:
                configJson["categories"]["schedule_settings"]["settings"]["tasks"] = {
                    "value": [],
                    "type": "array",
                    "description": "定时任务列表"
                }
            
            # 更新任务数据
            configJson["categories"]["schedule_settings"]["settings"]["tasks"]["value"] = tasks_data
            
            # 保存配置
            try:
                with open(self.task_file_path, 'w', encoding='utf-8') as f:
                    json.dump(configJson, f, ensure_ascii=False, indent=4)
                logger.info("任务配置已保存")
            except Exception as write_error:
                logger.error(f"写入配置文件失败: {str(write_error)}")
        
        except Exception as e:
            logger.error(f"保存任务失败: {str(e)}")

    def add_task(self, task_id, chat_id, content, schedule_type, schedule_time, is_active=True):
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
            # 验证参数
            if not task_id:
                logger.error("任务ID不能为空")
                return
            
            if not chat_id:
                logger.error("聊天ID不能为空")
                return
            
            if not content:
                logger.error("消息内容不能为空")
                return
            
            if schedule_type not in ['cron', 'interval']:
                logger.error(f"不支持的调度类型: {schedule_type}")
                return
            
            if not schedule_time:
                logger.error("调度时间不能为空")
                return
            
            # 创建触发器
            try:
                if schedule_type == 'cron':
                    trigger = CronTrigger.from_crontab(schedule_time)
                elif schedule_type == 'interval':
                    # 确保interval是整数
                    try:
                        seconds = int(schedule_time)
                        if seconds <= 0:
                            logger.error(f"间隔时间必须大于0: {schedule_time}")
                            return
                        trigger = IntervalTrigger(seconds=seconds)
                    except ValueError:
                        logger.error(f"无效的间隔时间: {schedule_time}")
                        return
                else:
                    logger.error(f"不支持的调度类型: {schedule_type}")
                    return
            except Exception as trigger_error:
                logger.error(f"创建触发器失败: {str(trigger_error)}")
                return

            # 创建任务执行函数
            def task_func():
                try:
                    if task_id in self.tasks and self.tasks[task_id]['is_active']:
                        # 检查message_handler是否有add_to_queue方法
                        if not hasattr(self.message_handler, 'add_to_queue'):
                            logger.error(f"消息处理器缺少add_to_queue方法")
                            return
                        
                        self.message_handler.add_to_queue(
                            chat_id=chat_id,
                            content=content,
                            sender_name="System",
                            username="AutoTasker",
                            is_group=False
                        )
                        logger.info(f"执行定时任务 {task_id}")
                except Exception as e:
                    logger.error(f"执行任务 {task_id} 失败: {str(e)}")

            # 如果任务已存在，先移除
            if task_id in self.tasks:
                try:
                    self.tasks[task_id]['job'].remove()
                    logger.info(f"移除现有任务: {task_id}")
                except Exception as remove_error:
                    logger.error(f"移除现有任务失败: {str(remove_error)}")

            # 添加任务到调度器
            try:
                job = self.scheduler.add_job(
                    task_func,
                    trigger=trigger,
                    id=task_id
                )
            except Exception as add_job_error:
                logger.error(f"添加任务到调度器失败: {str(add_job_error)}")
                return

            # 保存任务信息
            self.tasks[task_id] = {
                'chat_id': chat_id,
                'content': content,
                'schedule_type': schedule_type,
                'schedule_time': schedule_time,
                'is_active': is_active,
                'job': job
            }

            # 保存任务配置
            try:
                self.save_tasks()
            except Exception as save_error:
                logger.error(f"保存任务配置失败: {str(save_error)}")
            
            logger.info(f"添加任务成功: {task_id}")
            
        except Exception as e:
            logger.error(f"添加任务失败: {str(e)}")
            # 不抛出异常，让程序继续运行

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

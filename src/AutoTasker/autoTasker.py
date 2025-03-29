from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging
import yaml
import os
import json
import shutil
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class AutoTasker:
    def __init__(self, message_handler, task_file_path="src/config/config.yaml"):
        self.message_handler = message_handler
        self.task_file_path = task_file_path
        self.json_task_file = "src/config/auto_tasks.json"  # 新增JSON任务文件
        self.scheduler = BackgroundScheduler()
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._is_initializing = True  # 新增初始化标志
        
        # 确保目录存在
        os.makedirs(os.path.dirname(task_file_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.json_task_file), exist_ok=True)
        
        # 初始化流程
        self._clear_all_tasks(silent=True)  # 静默清空所有任务
        self.load_tasks()  # 加载任务
        self.scheduler.start()
        logger.info("AutoTasker 初始化完成")
        self._is_initializing = False

    def _clear_all_tasks(self, silent=False):
        """清空所有任务"""
        self.scheduler.remove_all_jobs()
        self.tasks.clear()
        if not silent:
            logger.info("已清空所有任务")

    def load_tasks(self):
        """从文件加载任务配置"""
        try:
            # 优先从JSON文件加载
            if os.path.exists(self.json_task_file) and os.path.getsize(self.json_task_file) > 0:
                self._load_from_json()
            else:
                self._load_from_yaml()
        except Exception as e:
            logger.error(f"加载任务失败: {str(e)}")

    def _load_from_json(self):
        """从JSON文件加载任务"""
        with open(self.json_task_file, 'r', encoding='utf-8') as f:
            tasks_data = json.load(f)
        
        task_count = 0
        for task_id, task_data in tasks_data.items():
            success = self._add_task_during_init(
                task_id=str(task_id),
                chat_id=str(task_data['chat_id']),
                content=task_data['content'],
                schedule_type=task_data['schedule_type'],
                schedule_time=task_data.get('schedule_time', ''),
                is_active=task_data.get('is_active', True)
            )
            if success:
                task_count += 1
        logger.info(f"从JSON文件加载 {task_count}/{len(tasks_data)} 个任务")

    def _load_from_yaml(self):
        """从YAML文件加载任务"""
        if not os.path.exists(self.task_file_path):
            return
            
        with open(self.task_file_path, 'r', encoding='utf-8') as f:
            tasks_data = yaml.load(f, Loader=yaml.FullLoader) or {}

        task_count = 0
        if "categories" in tasks_data and "schedule_settings" in tasks_data["categories"]:
            tasks = tasks_data["categories"]["schedule_settings"]["settings"].get("tasks", {}).get("value", [])
            if tasks and isinstance(tasks, list):
                for task in tasks:
                    if all(k in task for k in ["task_id", "chat_id", "content", "schedule_type"]):
                        success = self._add_task_during_init(
                            task_id=str(task["task_id"]),
                            chat_id=str(task["chat_id"]),
                            content=task["content"],
                            schedule_type=task["schedule_type"],
                            schedule_time=task["schedule_time"],
                            is_active=task.get("is_active", True)
                        )
                        if success:
                            task_count += 1
                logger.info(f"从YAML文件加载 {task_count}/{len(tasks)} 个任务")
        
        # 将YAML任务保存到JSON文件
        if task_count > 0:
            self._save_to_json()

    def _add_task_during_init(self, task_id, chat_id, content, schedule_type, schedule_time, is_active=True):
        """初始化专用的任务添加方法"""
        try:
            # 创建触发器
            if schedule_type == "cron":
                trigger = CronTrigger.from_crontab(schedule_time)
            elif schedule_type == "interval":
                trigger = IntervalTrigger(seconds=int(schedule_time))
            else:
                logger.error(f"不支持的调度类型: {schedule_type}")
                return False

            # 任务执行函数
            def task_func():
                try:
                    task = self.tasks.get(task_id)
                    if task and task.get("is_active", False):
                        self.message_handler.add_auto_task_message({
                            "chat_id": task["chat_id"],
                            "content": task["content"]
                        })

                        logger.info(f"执行任务 {task_id} -> {task['chat_id']}")
                except Exception as e:
                    logger.error(f"执行任务 {task_id} 失败: {str(e)}")

            # 添加任务到调度器
            job = self.scheduler.add_job(
                task_func,
                trigger=trigger,
                id=task_id,
                replace_existing=True
            )

            # 保存任务信息
            self.tasks[task_id] = {
                "chat_id": chat_id,
                "content": content,
                "schedule_type": schedule_type,
                "schedule_time": schedule_time,
                "is_active": is_active,
                "job": job,
            }
            return True

        except Exception as e:
            logger.error(f"添加任务失败: {str(e)}")
            return False

    def add_task(self, task_id, chat_id, content, schedule_type, schedule_time, is_active=True):
        """添加新任务"""
        try:
            # 清理现有任务（如果是运行时添加）
            if not self._is_initializing and task_id in self.tasks:
                logger.info(f"任务ID已存在: {task_id}，将覆盖")
                self.remove_task(task_id, save_config=False)

            # 使用初始化方法添加任务
            success = self._add_task_during_init(
                task_id=str(task_id),
                chat_id=str(chat_id),
                content=content,
                schedule_type=schedule_type,
                schedule_time=schedule_time,
                is_active=is_active
            )

            # 保存配置
            if success and not self._is_initializing:
                self._save_to_json()
                self._update_yaml_config()

            return success

        except Exception as e:
            logger.error(f"添加任务失败: {str(e)}")
            return False

    def remove_task(self, task_id, save_config=True):
        """移除任务"""
        try:
            if task_id in self.tasks:
                # 从调度器移除
                try:
                    self.scheduler.remove_job(str(task_id))
                except Exception as e:
                    if not self._is_initializing:
                        logger.debug(f"移除任务失败(可能不存在): {str(e)}")

                # 从内存移除
                del self.tasks[task_id]

                # 保存配置
                if save_config and not self._is_initializing:
                    self._save_to_json()
                    self._update_yaml_config()

                logger.info(f"删除任务成功: {task_id}")
                return True
            else:
                logger.warning(f"任务不存在: {task_id}")
                return False
        except Exception as e:
            logger.error(f"删除任务失败: {str(e)}")
            return False

    def _save_to_json(self):
        """保存任务到JSON文件"""
        try:
            tasks_to_save = {
                task_id: {
                    "chat_id": task["chat_id"],
                    "content": task["content"],
                    "schedule_type": task["schedule_type"],
                    "schedule_time": task["schedule_time"],
                    "is_active": task.get("is_active", True)
                }
                for task_id, task in self.tasks.items()
            }

            # 备份旧文件
            if os.path.exists(self.json_task_file):
                shutil.copy2(self.json_task_file, f"{self.json_task_file}.bak")

            with open(self.json_task_file, 'w', encoding='utf-8') as f:
                json.dump(tasks_to_save, f, indent=2, ensure_ascii=False)

            logger.info(f"已保存 {len(tasks_to_save)} 个任务到JSON文件")

        except Exception as e:
            logger.error(f"保存JSON任务失败: {str(e)}")

    def _update_yaml_config(self):
        """更新YAML配置文件"""
        try:
            config = self._get_current_yaml_config()
            
            # 构建任务列表
            tasks_list = [
                {
                    "task_id": task_id,
                    "chat_id": task["chat_id"],
                    "content": task["content"],
                    "schedule_type": task["schedule_type"],
                    "schedule_time": task["schedule_time"],
                    "is_active": task.get("is_active", True)
                }
                for task_id, task in self.tasks.items()
            ]

            # 更新配置结构
            if "categories" not in config:
                config["categories"] = {}
            if "schedule_settings" not in config["categories"]:
                config["categories"]["schedule_settings"] = {}
            if "settings" not in config["categories"]["schedule_settings"]:
                config["categories"]["schedule_settings"]["settings"] = {}
            if "tasks" not in config["categories"]["schedule_settings"]["settings"]:
                config["categories"]["schedule_settings"]["settings"]["tasks"] = {"value": []}

            config["categories"]["schedule_settings"]["settings"]["tasks"]["value"] = tasks_list

            # 保存更新
            with open(self.task_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True)

            logger.info(f"已同步 {len(tasks_list)} 个任务到YAML配置")

        except Exception as e:
            logger.error(f"更新YAML配置失败: {str(e)}")

    def _get_current_yaml_config(self):
        """获取当前YAML配置"""
        try:
            if os.path.exists(self.task_file_path):
                with open(self.task_file_path, 'r', encoding='utf-8') as f:
                    return yaml.load(f, Loader=yaml.FullLoader) or {}
        except Exception:
            pass
        return {}

    def __del__(self):
        """清理资源"""
        if hasattr(self, "scheduler"):
            self.scheduler.shutdown()

"""
定时任务消息适配器
负责与消息处理器对接，实现非侵入式集成
"""
import logging
from typing import Callable
from .time_recognition import TimeRecognitionService

logger = logging.getLogger('main')

class ReminderMessageAdapter:
    def __init__(self, get_message_handler: Callable):
        """
        初始化适配器
        Args:
            get_message_handler: 获取消息处理器实例的方法
        """
        self.get_handler = get_message_handler
        self.time_service = TimeRecognitionService()
        
    def register_hooks(self):
        """注册消息处理钩子"""
        handler = self.get_handler()
        # 注册预处理钩子
        if hasattr(handler, 'add_preprocess_hook'):
            handler.add_preprocess_hook(self._time_check_hook)
            
    # 在_time_check_hook方法中添加条件判断
    def _time_check_hook(self, content: str, chat_id: str, sender_name: str, **kwargs):
        """时间检查钩子函数"""
        try:
            # 添加语音请求判断
            if '语音' in content:  # 与<mcsymbol name="VoiceHandler" filename="voice.py" path="src/handlers/voice.py" startline="19" type="class"></mcsymbol>的触发条件保持一致
                return  # 跳过时间识别
                
            time_info = self.time_service.recognize_time(content)
            if time_info:
                target_time, reminder_content = time_info
                logger.info(f"检测到提醒请求 - 用户: {sender_name}")
                self._create_reminder(chat_id, target_time, reminder_content, sender_name)
        except Exception as e:
            logger.error(f"时间提醒处理失败: {str(e)}")

    def _create_reminder(self, chat_id: str, target_time, content: str, sender: str):
        """创建提醒任务"""
        handler = self.get_handler()
        if hasattr(handler, 'reminder_service'):
            handler.reminder_service.add_reminder(
                chat_id=chat_id,
                target_time=target_time,
                content=content,
                sender_name=sender,
                silent=True
            )
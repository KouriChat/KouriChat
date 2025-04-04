"""
提醒功能混入类
"""
import logging

logger = logging.getLogger('main')

class ReminderMixin:
    """为消息处理器添加提醒功能的混入类"""
    
    def __init__(self):
        # 延迟初始化，避免循环依赖
        self._reminder_service = None
        self._time_service = None
        
    @property
    def reminder_service(self):
        if not self._reminder_service:
            from .reminder_service import ReminderService
            self._reminder_service = ReminderService(self)
        return self._reminder_service
    
    @property
    def time_service(self):
        if not self._time_service:
            from .time_recognition import TimeRecognitionService
            self._time_service = TimeRecognitionService()
        return self._time_service
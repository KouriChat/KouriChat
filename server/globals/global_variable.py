"""

Global variables

全局变量
"""
from typing import Optional
from core import EventBus

class GlobalVariable:
    _var = {} # 通用全局变量，需要使用自行添加
    handlerRegistry = None # 处理器注册器
    eventBus: Optional[EventBus] = None # 事件总线
    eventQueue = None # 事件队列
    eventQueueLock = None # 事件队列锁
    eventQueueCondition = None # 事件队列条件
    
    def __init__(self) -> None:
        pass

    @classmethod
    def set(cls, key, value):
        cls._var[key] = value
    
    @classmethod
    def get(cls, key):
        return cls._var.get(key)
    
    @classmethod
    def delete(cls, key):
        del cls._var[key]
    

    @classmethod
    def clear(cls):
        cls._var.clear()
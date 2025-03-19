from abc import ABC, abstractmethod
from typing import Any, List

class IMessageHandler(ABC):
    """消息处理接口"""
    @abstractmethod
    async def handle_message(self, message: Any) -> Any:
        """处理接收到的消息"""
        pass

class IEventHandler(ABC):
    """事件处理接口"""
    @abstractmethod
    async def handle_event(self, event: Any) -> None:
        """处理事件"""
        pass

class IMemoryProcessor(ABC):
    """记忆处理接口"""
    @abstractmethod
    async def store(self, memory: Any) -> bool:
        """存储记忆"""
        pass

    @abstractmethod
    async def retrieve(self, query: Any) -> List[Any]:
        """检索记忆"""
        pass

class IEmotionProcessor(ABC):
    """情绪处理接口"""
    @abstractmethod
    async def process_emotion(self, context: Any) -> Any:
        """处理情绪"""
        pass
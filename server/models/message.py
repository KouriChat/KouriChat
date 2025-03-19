"""
    消息模型：
        定义了一个消息传递的参数


"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

@dataclass
class TextMessage:
    """文本消息类型
    包含以下字段：
        sender_id: 发送者ID
        sender: 发送者名称
        chat_type: 聊天类型
        character: 角色ID
        message_type: 消息类型
        message_send_time: 消息发送时间
        content: 消息内容
    说明：
        消息类型为text时，content为文本内容
    """
    sender_id: int
    sender: str
    chat_type: str
    character: int
    message_type: str
    message_send_time: str
    content: str
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TextMessage':
        """从字典创建消息实例"""
        return cls(
            sender_id=data['sender_id'],
            sender=data['sender'],
            chat_type=data['chat_type'],
            character=data['character'],
            message_type=data['message_type'],
            message_send_time=data['message_send_time'],
            content=data.get('content', '')
        )

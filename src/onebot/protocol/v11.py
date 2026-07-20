import time
from typing import Dict, Any, List
from .message_segment import array_to_cq

class V11Handler:
    def __init__(self, config):
        try:
            self.self_id = config.onebot.self_id
        except AttributeError:
            self.self_id = 10001000

    def build_private_message_event(self, user_id: str, message: List[Dict[str, Any]], message_id: int) -> Dict[str, Any]:
        """构建私聊消息事件"""
        return {
            "time": int(time.time()),
            "self_id": self.self_id,
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "message_id": message_id,
            "user_id": int(user_id) if str(user_id).isdigit() else 0,
            "message": array_to_cq(message),
            "raw_message": array_to_cq(message),
            "font": 0,
            "sender": {
                "user_id": int(user_id) if str(user_id).isdigit() else 0,
                "nickname": str(user_id),
                "sex": "unknown",
                "age": 0
            }
        }

    def build_group_message_event(self, group_id: str, user_id: str, message: List[Dict[str, Any]], message_id: int) -> Dict[str, Any]:
        """构建群消息事件"""
        return {
            "time": int(time.time()),
            "self_id": self.self_id,
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "message_id": message_id,
            "group_id": int(group_id) if str(group_id).isdigit() else 0,
            "user_id": int(user_id) if str(user_id).isdigit() else 0,
            "message": array_to_cq(message),
            "raw_message": array_to_cq(message),
            "font": 0,
            "sender": {
                "user_id": int(user_id) if str(user_id).isdigit() else 0,
                "nickname": str(user_id),
                "card": str(user_id),
                "sex": "unknown",
                "age": 0,
                "role": "member"
            }
        }

    def build_lifecycle_event(self, sub_type: str = "connect") -> Dict[str, Any]:
        """构建生命周期元事件"""
        return {
            "time": int(time.time()),
            "self_id": self.self_id,
            "post_type": "meta_event",
            "meta_event_type": "lifecycle",
            "sub_type": sub_type
        }

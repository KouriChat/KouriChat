import time
import uuid
from typing import Dict, Any, List

class V12Handler:
    def __init__(self, config):
        try:
            self.self_id = str(config.onebot.self_id)
        except AttributeError:
            self.self_id = "10001000"

    def build_private_message_event(self, user_id: str, message: List[Dict[str, Any]], message_id: str) -> Dict[str, Any]:
        """构建 v12 私聊消息事件"""
        return {
            "id": str(uuid.uuid4()),
            "time": time.time(),
            "type": "message",
            "detail_type": "private",
            "sub_type": "",
            "message_id": str(message_id),
            "message": message,
            "alt_message": "",
            "user_id": str(user_id)
        }

    def build_group_message_event(self, group_id: str, user_id: str, message: List[Dict[str, Any]], message_id: str) -> Dict[str, Any]:
        """构建 v12 群消息事件"""
        return {
            "id": str(uuid.uuid4()),
            "time": time.time(),
            "type": "message",
            "detail_type": "group",
            "sub_type": "",
            "message_id": str(message_id),
            "message": message,
            "alt_message": "",
            "group_id": str(group_id),
            "user_id": str(user_id)
        }

    def build_meta_event(self, detail_type: str = "connect") -> Dict[str, Any]:
        """构建生命周期/连接事件"""
        return {
            "id": str(uuid.uuid4()),
            "time": time.time(),
            "type": "meta",
            "detail_type": detail_type,
            "sub_type": ""
        }

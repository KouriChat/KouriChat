import logging
import asyncio
from typing import Dict, Any, Tuple
from ..protocol.message_segment import array_to_text, extract_image_urls, normalize_message

logger = logging.getLogger('onebot.api')

class ApiHandlers:
    def __init__(self, message_handler, config):
        self.message_handler = message_handler
        self.config = config

    def handle_api_request(self, action: str, params: Dict[str, Any]) -> Tuple[int, Any]:
        """
        处理 API 请求
        返回 (retcode, data)
        """
        handler_name = f"api_{action}"
        if hasattr(self, handler_name):
            try:
                data = getattr(self, handler_name)(params)
                return 0, data
            except ValueError as e:
                logger.warning(f"API 参数错误 [{action}]: {e}")
                return 1400, None
            except Exception as e:
                logger.error(f"API 执行异常 [{action}]: {e}", exc_info=True)
                return 1400, None # 通用错误码
        else:
            logger.warning(f"不支持的 API 动作: {action}")
            return 1404, None # API不存在

    # ------------------
    # 核心 API 实现
    # ------------------

    def api_send_private_msg(self, params: Dict[str, Any]) -> Dict[str, Any]:
        user_id = params.get('user_id')
        if not user_id:
            raise ValueError("缺少参数 user_id")
            
        message = params.get('message')
        if not message:
            raise ValueError("缺少参数 message")

        # 归一化为消息段数组
        segments = normalize_message(message)
        text_content = array_to_text(segments)
        
        # 将操作放入后台线程，避免阻塞当前 WS event loop
        # 这里为了简化，直接用 KouriChat message_handler 的接口
        # KouriChat 内部的 handle_user_message 可能会调用阻塞方法，需要起线程
        
        # 这里可以提取出图片并单独处理，但根据 KouriChat 的逻辑，
        # 图片通过 content 的后缀或者是单独的 handle 传递，这里把文本传递过去即可。
        
        def _send():
            try:
                self.message_handler.handle_user_message(
                    content=text_content,
                    chat_id=str(user_id),
                    sender_name=str(user_id),
                    username=str(user_id),
                    is_group=False,
                    is_image_recognition=False
                )
            except Exception as e:
                logger.error(f"OneBot 调用处理私聊消息失败: {e}")
                
        import threading
        threading.Thread(target=_send, daemon=True).start()

        return {"message_id": 1} # 模拟的 message_id

    def api_send_group_msg(self, params: Dict[str, Any]) -> Dict[str, Any]:
        group_id = params.get('group_id')
        if not group_id:
            raise ValueError("缺少参数 group_id")
            
        message = params.get('message')
        if not message:
            raise ValueError("缺少参数 message")

        segments = normalize_message(message)
        text_content = array_to_text(segments)
        
        # 为了兼容群聊，可能需要模拟一个发信人
        # 很多情况下框架不会发送 user_id，所以使用 'User' 作为默认发送者
        def _send():
            try:
                self.message_handler.handle_user_message(
                    content=text_content,
                    chat_id=str(group_id),
                    sender_name="User", 
                    username="User",
                    is_group=True,
                    is_image_recognition=False
                )
            except Exception as e:
                logger.error(f"OneBot 调用处理群聊消息失败: {e}")
                
        import threading
        threading.Thread(target=_send, daemon=True).start()

        return {"message_id": 2}

    def api_send_msg(self, params: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = params.get('message_type')
        if msg_type == 'private' or params.get('user_id'):
            return self.api_send_private_msg(params)
        elif msg_type == 'group' or params.get('group_id'):
            return self.api_send_group_msg(params)
        else:
            raise ValueError("未知的消息类型或缺少目标 ID")

    def api_get_login_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self_id = self.config.onebot.self_id
            nickname = self.config.onebot.nickname
        except AttributeError:
            self_id = 10001000
            nickname = "KouriChat"
            
        return {
            "user_id": self_id,
            "nickname": nickname
        }

    def api_get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "online": True,
            "good": True
        }

    def api_get_version_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "app_name": "KouriChat-OneBot",
            "app_version": "1.0.0",
            "protocol_version": "v11"
        }

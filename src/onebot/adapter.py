import logging
import asyncio
from typing import Dict, Any, Tuple
from .protocol.v11 import V11Handler
from .protocol.v12 import V12Handler
from .api.handlers import ApiHandlers
from .event.emitter import EventEmitter
from .protocol.message_segment import normalize_message

logger = logging.getLogger('onebot.adapter')

class OneBotAdapter:
    def __init__(self, config, message_handler, event_emitter: EventEmitter):
        self.config = config
        self.message_handler = message_handler
        self.event_emitter = event_emitter
        
        self.v11 = V11Handler(config)
        self.v12 = V12Handler(config)
        self.api_handlers = ApiHandlers(message_handler, config)
        
        # 为了从 KouriChat 内部捕获回复，我们需要稍微 monkey patch 一下 message_handler，或者在
        # 这里暴露出一个 send_reply_hook 让 KouriChat 代码调用。
        # 考虑到不破坏原结构，我们在 main.py 里将一个自定义函数赋给 LLM 回复的后续处理中，
        # 不过更简单的方法是，我们在 wxauto 的 send_message 被调用时拦截，或者直接在这里提供
        # on_reply_v11 / on_reply_v12 函数给外部调用。
        
        # 由于 KouriChat 使用 wxauto 直接发送，我们可以修改 KouriChat
        # 发送回复的地方，加入： if onebot_adapter: onebot_adapter.on_ai_reply(...)
        
    def dispatch_api(self, protocol_version: str, action: str, params: Dict[str, Any]) -> Tuple[int, Any]:
        """
        分发 API 调用
        返回 (retcode, data)
        """
        logger.debug(f"[{protocol_version}] 收到 API 调用: {action}, 参数: {params}")
        
        # V11 和 V12 的 action 名字可能有区别，为了简化，映射为统一内部 action
        internal_action = action
        if protocol_version == 'v12':
            if action == 'send_message':
                if params.get('detail_type') == 'private':
                    internal_action = 'send_private_msg'
                elif params.get('detail_type') == 'group':
                    internal_action = 'send_group_msg'
            elif action == 'get_self_info':
                internal_action = 'get_login_info'
            elif action == 'get_version':
                internal_action = 'get_version_info'

        return self.api_handlers.handle_api_request(internal_action, params)

    def on_ai_reply(self, chat_id: str, content: str, is_group: bool):
        """
        当 KouriChat 生成了 AI 回复时调用此方法。
        我们需要将其封装为 v11 和 v12 事件推送到所有的 Event WebSocket 客户端。
        这里的思路是：模拟收到自己发送出去的消息，或者直接推送到前端。
        通常，主动下发消息不需要再次推送事件（除非开启了 echo），但为了让 Web 界面或其它
        客户端知道机器人发了话，这里我们推送一个"自己发送的消息"事件。
        """
        try:
            self_id_v11 = getattr(self.config.onebot, 'self_id', 10001000)
            self_id_v12 = str(self_id_v11)
            
            msg_id_v11 = int(asyncio.get_event_loop().time() * 1000) % 2147483647
            msg_id_v12 = str(msg_id_v11)
            
            message_segments = normalize_message(content)
            
            v11_event = None
            v12_event = None

            if not is_group:
                v11_event = self.v11.build_private_message_event(str(chat_id), message_segments, msg_id_v11)
                v11_event["user_id"] = self_id_v11 # 自己发的
                v11_event["target_id"] = int(chat_id) if str(chat_id).isdigit() else 0
                
                v12_event = self.v12.build_private_message_event(str(chat_id), message_segments, msg_id_v12)
                v12_event["user_id"] = self_id_v12
            else:
                v11_event = self.v11.build_group_message_event(str(chat_id), str(self_id_v11), message_segments, msg_id_v11)
                v12_event = self.v12.build_group_message_event(str(chat_id), str(self_id_v11), message_segments, msg_id_v12)
            
            # 推送事件 (对于 v11 客户端推送 v11 事件，但目前 emitter 不分版本，这里做简化，只推送 v11)
            # 完整实现中，emitter 应该记录 client 的 protocol_version
            if v11_event:
                self.event_emitter.emit(v11_event)
        except Exception as e:
            logger.error(f"处理 AI 回复推送失败: {e}", exc_info=True)

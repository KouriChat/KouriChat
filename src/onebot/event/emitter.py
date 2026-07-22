import asyncio
import logging
import json
import time
from typing import Set, Dict, Any

logger = logging.getLogger('onebot.emitter')

class EventEmitter:
    def __init__(self):
        # 存储所有连接的 websocket 客户端
        # client_type 取值为 'api', 'event', 'universal'
        self.clients: Dict[Any, str] = {}
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    def add_client(self, websocket: Any, client_type: str):
        """添加一个 WebSocket 客户端"""
        self.clients[websocket] = client_type
        logger.info(f"添加新客户端, 类型: {client_type}, 当前总连接数: {len(self.clients)}")

    def remove_client(self, websocket: Any):
        """移除一个 WebSocket 客户端"""
        if websocket in self.clients:
            del self.clients[websocket]
            logger.info(f"移除客户端, 当前总连接数: {len(self.clients)}")

    def emit(self, event_dict: Dict[str, Any]):
        """
        向所有订阅了事件的客户端发送事件。
        由于事件产生通常在其它线程，需要调度到 event loop 中运行。
        """
        if not self.clients:
            return

        payload = json.dumps(event_dict, ensure_ascii=False)
        
        async def _broadcast():
            tasks = []
            for ws, client_type in list(self.clients.items()):
                # 只有 event 和 universal 类型需要接收推送
                if client_type in ('event', 'universal'):
                    try:
                        tasks.append(ws.send(payload))
                    except Exception as e:
                        logger.debug(f"向客户端发送事件失败: {e}")
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast(), self.loop)
        else:
            logger.warning("WebSocket 事件循环未运行，无法发送事件")

    async def heartbeat_loop(self, interval: int, self_id: int):
        """心跳循环"""
        while True:
            await asyncio.sleep(interval)
            if not self.clients:
                continue
            
            # v11 heartbeat
            event = {
                "time": int(time.time()),
                "self_id": self_id,
                "post_type": "meta_event",
                "meta_event_type": "heartbeat",
                "status": {
                    "online": True,
                    "good": True
                },
                "interval": interval * 1000
            }
            # 为了简化，这里直接广播 v11 格式的心跳
            self.emit(event)

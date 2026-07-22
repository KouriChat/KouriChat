import asyncio
import json
import logging
from typing import Dict, Any, Tuple
import websockets
from urllib.parse import urlparse, parse_qs

from .event.emitter import EventEmitter
from .adapter import OneBotAdapter

logger = logging.getLogger('onebot.server')

class OneBotServer:
    def __init__(self, config, message_handler):
        self.config = config
        self.host = getattr(config.onebot, 'host', '0.0.0.0')
        self.port = getattr(config.onebot, 'port', 6700)
        self.access_token = getattr(config.onebot, 'access_token', '')
        self.heartbeat_interval = getattr(config.onebot, 'heartbeat_interval', 30)
        self.self_id = getattr(config.onebot, 'self_id', 10001000)
        
        self.emitter = EventEmitter()
        self.adapter = OneBotAdapter(config, message_handler, self.emitter)
        self.server = None

    def start(self):
        """启动 WebSocket 服务器 (阻塞)"""
        logger.info(f"正在启动 OneBot WebSocket 服务器 (ws://{self.host}:{self.port})")
        asyncio.run(self._run_server())

    async def _run_server(self):
        loop = asyncio.get_running_loop()
        self.emitter.set_loop(loop)
        
        # 启动心跳协程
        if self.heartbeat_interval > 0:
            asyncio.create_task(self.emitter.heartbeat_loop(self.heartbeat_interval, self.self_id))
            
        # 启动 WebSocket 服务
        async with websockets.serve(self._handle_client, self.host, self.port):
            await asyncio.Future()  # 永不返回，除非被取消

    def _verify_token(self, path: str, request_headers) -> bool:
        """鉴权校验"""
        if not self.access_token:
            return True
            
        # 检查 Header
        auth_header = request_headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:] == self.access_token:
            return True
            
        # 检查 Query Parameter
        parsed_url = urlparse(path)
        query = parse_qs(parsed_url.query)
        if "access_token" in query and query["access_token"][0] == self.access_token:
            return True
            
        return False

    def _determine_client_type(self, path: str) -> Tuple[str, str]:
        """根据路径决定客户端类型和协议版本。返回 (client_type, protocol_version)"""
        parsed_url = urlparse(path)
        path = parsed_url.path.rstrip('/')
        
        protocol_version = 'v11'
        
        if path.startswith('/v12'):
            protocol_version = 'v12'
            path = path[4:]
            
        if path in ('/api', '/api/'):
            return 'api', protocol_version
        elif path in ('/event', '/event/'):
            return 'event', protocol_version
        elif path in ('', '/'):
            return 'universal', protocol_version
            
        return 'unknown', protocol_version

    async def _handle_client(self, websocket, path):
        """处理单个 WebSocket 连接"""
        # 鉴权
        if not self._verify_token(path, websocket.request_headers):
            logger.warning(f"鉴权失败: {websocket.remote_address}")
            await websocket.close(1002, "Authentication Failed")
            return

        client_type, protocol_version = self._determine_client_type(path)
        if client_type == 'unknown':
            logger.warning(f"未知的连接路径: {path}")
            await websocket.close(1002, "Unknown Path")
            return

        logger.info(f"新 WebSocket 连接: {websocket.remote_address} - 路径: {path} - 类型: {client_type} ({protocol_version})")
        self.emitter.add_client(websocket, client_type)

        try:
            # 推送 lifecycle/connect 事件
            if client_type in ('event', 'universal'):
                meta_event = None
                if protocol_version == 'v11':
                    meta_event = self.adapter.v11.build_lifecycle_event("connect")
                elif protocol_version == 'v12':
                    meta_event = self.adapter.v12.build_meta_event("connect")
                    
                if meta_event:
                    # 单独发送给刚连接的客户端
                    await websocket.send(json.dumps(meta_event, ensure_ascii=False))

            # 接收消息循环
            if client_type in ('api', 'universal'):
                async for message in websocket:
                    try:
                        req_data = json.loads(message)
                        action = req_data.get('action')
                        params = req_data.get('params', {})
                        echo = req_data.get('echo')
                        
                        if not action:
                            continue
                            
                        # 分发处理
                        retcode, resp_data = self.adapter.dispatch_api(protocol_version, action, params)
                        
                        # 构建响应包
                        response = {
                            "status": "ok" if retcode == 0 else "failed",
                            "retcode": retcode,
                            "data": resp_data,
                            "message": "",
                        }
                        if echo is not None:
                            response["echo"] = echo
                            
                        await websocket.send(json.dumps(response, ensure_ascii=False))
                    except json.JSONDecodeError:
                        logger.warning(f"无效的 JSON 数据从 {websocket.remote_address}")
                        await websocket.send(json.dumps({
                            "status": "failed",
                            "retcode": 1400,
                            "data": None,
                            "message": "Invalid JSON"
                        }))
                    except Exception as e:
                        logger.error(f"处理 API 调用时发生异常: {e}", exc_info=True)
            else:
                # Event 客户端只收不发，但也需要保持连接并消耗可能的 ping 包
                async for _ in websocket:
                    pass

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket 客户端断开连接: {websocket.remote_address}")
        except Exception as e:
            logger.error(f"WebSocket 连接异常: {e}", exc_info=True)
        finally:
            self.emitter.remove_client(websocket)

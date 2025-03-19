import asyncio
from typing import Any, Dict, Optional

"""Socket通信适配器
    实现基于Socket的网络通信 
    待实现
"""

class SocketAdapter():
   
    
    def __init__(self, host: str = '127.0.0.1', port: int = 8000):
        """初始化Socket适配器
        
        Args:
            host: 主机地址
            port: 端口号
        """
        self.host = host
        self.port = port
        self.server = None
        self.clients = set()
        self.running = False
        
    async def close(self) -> None:
        """关闭Socket服务器"""
        self.running = False
        if self.server:
            self.server.close()
            self.server = None
            
        # 关闭所有客户端连接
        for client in self.clients:
            if not client.is_closing():
                client.close()
        self.clients.clear()

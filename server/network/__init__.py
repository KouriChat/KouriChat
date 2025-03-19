# 网络层初始化文件

"""
网络通信模块负责网络通信，以socket通信模块，http通信模块组成，负责对接各类框架
网络通信模块仅负责网络通信，不负责业务逻辑
"""

import asyncio
from typing import Tuple
from network.routes.flask_routes import FlaskAdapter
from network.routes.socket_routes import SocketAdapter

class NetworkManager:
    """网络管理器类
    
    负责管理所有网络适配器的初始化和启动
    """
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, flask_host: str = '127.0.0.1', 
                 flask_port: int = 8080,
                 socket_host: str = '127.0.0.1', 
                 socket_port: int = 8000):
        """初始化所有网络适配器
        
        Args:
            flask_host: Flask服务器主机地址
            flask_port: Flask服务器端口号
            socket_host: Socket服务器主机地址
            socket_port: Socket服务器端口号
        """
        if not self._initialized:
            self.flask_adapter: FlaskAdapter
            self.socket_adapter: SocketAdapter
            NetworkManager._initialized = True
            
            self.flask_adapter, self.socket_adapter = NetworkAdapterFactory.create_adapters(
                flask_host, flask_port, socket_host, socket_port
            )
    
    async def start_servers(self) -> None:
        """启动所有服务器"""
        if not self.flask_adapter or not self.socket_adapter:
            raise RuntimeError("网络适配器尚未初始化，请先调用initialize方法")
            
        # 启动Flask服务器
        async def start_flask():
            loop = asyncio.get_event_loop()

            await loop.run_in_executor(
                None, 
                self.flask_adapter.app.run, 
                self.flask_adapter.host, 
                self.flask_adapter.port
            )
            
        self._flask_task = asyncio.create_task(start_flask())
        
        try:
            await self._flask_task
        except asyncio.CancelledError:
            await self.shutdown()
            
    async def shutdown(self) -> None:
        """优雅关闭所有服务器"""
        if hasattr(self, '_flask_task'):
            self._flask_task.cancel()
            try:
                await self._flask_task
            except asyncio.CancelledError:
                pass
        
        # 关闭Flask服务器
        if self.flask_adapter:
            self.flask_adapter.shutdown()
        
        # 关闭Socket服务器
        if self.socket_adapter:
            await self.socket_adapter.close()

class NetworkAdapterFactory:
    """网络适配器工厂类
    
    负责初始化和管理所有网络适配器实例
    """
    
    @staticmethod
    def create_adapters(flask_host: str = '127.0.0.1', 
                       flask_port: int = 8080,
                       socket_host: str = '127.0.0.1',
                       socket_port: int = 8000) -> Tuple[FlaskAdapter, SocketAdapter]:
        """创建所有网络适配器实例
        
        Args:
            flask_host: Flask服务器主机地址
            flask_port: Flask服务器端口号
            socket_host: Socket服务器主机地址
            socket_port: Socket服务器端口号
            
        Returns:
            Tuple[FlaskAdapter, SocketAdapter]: 返回初始化好的Flask和Socket适配器实例
        """
        # 初始化Flask适配器
        flask_adapter = FlaskAdapter(host=flask_host, port=flask_port)
        
        # 初始化Socket适配器
        socket_adapter = SocketAdapter(host=socket_host, port=socket_port)
        
        return flask_adapter, socket_adapter
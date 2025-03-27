import asyncio
from typing import Any, Dict, Optional, List, Callable
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from werkzeug.serving import make_server
from threading import Thread

from yaml import Token

from utils import token_config

from .http_routes.base_routes import BaseRoutes
from .http_routes.message_routes import MessageRoutes
from .http_routes.config_routes import ConfigRoutes
from .http_routes.system_routes import SystemRoutes
from .http_routes.resource_routes import ResourceRoutes

class FlaskAdapter():
    """Flask通信适配器
    
    实现基于Flask的网络通信，提供HTTP API接口
    """
    
    def __init__(self, host: str = '127.0.0.1', port: int = 8080):
        """初始化Flask适配器
        
        Args:
            host: 主机地址
            port: 端口号
        """
        super().__init__()
        self.host = host
        self.port = port
        self.app: Flask = Flask(__name__)
        CORS(self.app)
        self.server = None
        # self.routes = {}
        # token 解析器
        self.token_config = token_config.TokenConfig()
        # 配置静态文件夹
        self.configure_static_folder()

        # 路由白名单
        self.white_list = [
            '/',
            '/is_first',
            '/login',
            '/init_password'
        ]

        # 注册路由
        self.base_routes = BaseRoutes(self.app)
        self.message_routes = MessageRoutes(self.app)
        self.config_routes = ConfigRoutes(self.app)
        self.system_routes = SystemRoutes(self.app)
        self.rescource_routes = ResourceRoutes(self.app)
        
        # 请求拦截器
        @self.app.before_request
        def before_request():
            """ token 检查 """
            if request.path in self.white_list:
                return

            # 从请求头中获取token
            token = request.headers.get('Authorization')

            # 检查token是否有效
            if not token:
                return jsonify({
                   'status': 'error',
                   'message': '未登录'
                }), 401

            # 检查token是否过期
            if not self.token_config.verify_token(token):
                return jsonify({
                  'status': 'error',
                  'message': '登录过期'
                }), 401

            # 允许通过
            return

        # # 响应拦截器
        # @self.app.after_request
        # def after_request(response):
        #     return response

        # # 错误处理
        # @self.app.errorhandler(404)
        # def not_found(error):
        #     return jsonify({
        #         'status': 'error',
        #         'message': 'Not Found'
        #     }), 404

        # @self.app.errorhandler(500)
        # def internal_server_error(error):
        #     return jsonify({
        #        'status': 'error',
        #        'message': 'Internal Server Error'
        #     }), 500

        
        """web端接口"""
        """ web 端接口尽量与之前的接口保持一致"""
        

    def configure_static_folder(self):
        """配置静态文件夹"""
        self.app.static_folder = 'static'

    def shutdown(self) -> None:
        """关闭Flask服务器"""
        if self.server:
            self.server.shutdown()
            self.server = None


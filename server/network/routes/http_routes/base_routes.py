from flask import jsonify,request
from config import SettingReader
from utils import token_config 

setting = SettingReader()
config = setting.get_config()
token_config = token_config.TokenConfig()

class BaseRoutes:
    def __init__(self, app):
        self.app = app
        self.register_routes()
        
    def register_routes(self):
        @self.app.route('/', methods=['GET'])
        def index():
            return jsonify({
                'status': 'ok',
                'message': 'KouriChat server is running'
            }), 200

        """
        
        # 登录        
        @self.app.route('/login',methods=['POST'])

        # 初始化密码
        @self.app.route('/init_password',methods=['POST','GET'])
        
        # 登出
        @self.app.route('/logout',methods=['GET'])
        
        """

        @self.app.route('/login',methods=['POST'])
        def login():
            """登录接口
            接收客户端的登录请求，必须包含以下字段：
                - password: 登录密码
                - remember_me: 是否记住登录状态（可选）
            Returns:
                - status: 状态，success 或 error
                - message: 消息
            """
            from flask import session
            from datetime import timedelta
            import hashlib

            def hash_password(password):
                return hashlib.sha256(password.encode()).hexdigest()

            # 检查是否需要初始化密码
            if not config['categories']['auth_settings']['settings']['admin_password']['value']:
                return jsonify({
                    'status': 'error',
                    'message': '需要先初始化密码'
                }), 403
            data = request.get_json()
            password = data.get('password')
            remember_me = data.get('remember_me', False)

            if not password:
                return jsonify({
                    'status': 'error',
                    'message': '密码不能为空'
                }), 400

            # 验证密码
            stored_hash = config['categories']['auth_settings']['settings']['admin_password']['value']
            if hash_password(password) == stored_hash:
                
                # 生成token
                token = token_config.generate_token('admin')
                return jsonify({
                    'status': 'success',
                    'message': '登录成功',
                    'token': token
                }), 200

            return jsonify({
                'status': 'error',
                'message': '密码错误'
            }), 401

        
        @self.app.route('/init_password',methods=['POST'])
        def init_password():
            """初始化密码接口
            接收客户端的初始化密码请求，必须包含以下字段：
                - password: 登录密码
            Returns:
                - status: 状态，success 或 error
                - message: 消息
            """
            from flask import session
            from datetime import timedelta
            import hashlib

            def hash_password(password):
                return hashlib.sha256(password.encode()).hexdigest()

            # 检查是否已经初始化过密码
            if config['categories']['auth_settings']['settings']['admin_password']['value']:
                return jsonify({
                   'status': 'error',
                  'message': '密码已经初始化过了'  
                })

            data = request.get_json()
            password = data.get('password')

            if not password:
                return jsonify({
                   'status': 'error',
                   'message': '密码不能为空'
                }), 400

            # 初始化密码
            config['categories']['auth_settings']['settings']['admin_password']['value'] = hash_password(password)
            setting.set_config(config)

            # 生成token
            token = token_config.generate_token('admin')
            return jsonify({
               'status':'success',
               'message': 'init password success',
                'token': token
            }), 200

        
        @self.app.route('/logout',methods=['GET'])
        def logout():
            return jsonify({
             'status': 'ok',
             'message': 'logout success'
            }), 200

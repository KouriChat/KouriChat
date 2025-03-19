from flask import jsonify,request
from config import SettingReader
from config.token_config import TokenConfig

setting = SettingReader()
config = setting.get_config()
token_config = TokenConfig()

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
                session.clear()  # 清除旧会话
                session['logged_in'] = True
                if remember_me:
                    session.permanent = True
                    self.app.permanent_session_lifetime = timedelta(days=30)
                
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

        
        @self.app.route('/init_password',methods=['POST','GET'])
        def init_password():
            return jsonify({
              'status': 'ok',
              'message': 'init password success'
            }), 200
        

        @self.app.route('/logout',methods=['GET'])
        def logout():
            return jsonify({
             'status': 'ok',
             'message': 'logout success'
            }), 200

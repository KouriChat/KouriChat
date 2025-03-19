from flask import jsonify, request

class ConfigRoutes:
    def __init__(self, app):
        self.app = app
        self.register_routes()

    def register_routes(self):
        @self.app.route('/config_manager/config',methods=['GET'])
        def config():
            """获取配置接口
            接收客户端的获取配置请求，无需字段：
            Returns:
                - status: 状态，success 或 error
                - message: 消息
                - data: 配置数据

                - 成功: {'status':'success','message': '获取配置成功','data': {}} 200
                - 失败: {'status':'error','message': '获取配置失败'} 400
            """
            from config import SettingReader
            setting = SettingReader()
            config = setting.get_config()
            return jsonify({
                'status':'success',
                'message': '获取配置成功',
                'data': config
            }), 200

        @self.app.route('/config_manager/save',methods=['POST'])
        def save():
            """保存配置接口
            接收客户端的保存配置请求，必须包含以下字段：
                - config: 完整配置数据
            Returns:
                - status: 状态，success 或 error
                - message: 消息

                - 成功: {'status':'success','message': '保存配置成功'} 200
                - 失败: {'status':'error','message': '保存配置失败'} 400
            """
            from config import SettingReader
            setting = SettingReader()
            data = request.get_json()
            config = data.get('config')
            if not config:
                return jsonify({
                   'status':'error',
                   'message': '保存配置失败'
                }), 400
            setting.set_config(config)
            return jsonify({
               'status':'success',
              'message': '保存配置成功'
            }), 200

        @self.app.route('/config_manager/get_all_config',methods=['GET'])
        def get_all_config():
            """获取所有配置接口
            接收客户端的获取所有配置请求，无需字段：
            Returns:
                - status: 状态，success 或 error
                - message: 消息
                - data: 配置数据

                - 成功: {'status':'success','message': '获取配置成功','data': configData} 200
                - 失败: {'status':'error','message': '获取配置失败'} 400
            """
            from config import SettingReader
            setting = SettingReader()
            config = setting.get_config()
            
            return jsonify({
               'status':'success',
               'message': '获取配置成功',
                'data': config
            }), 200


        """
        TODO: 无法确定必要性，请前端酌情考虑
        # 快速设置
        @self.app.route('config_manager/quick_setup',methods=['GET'])
        # 保存快速设置
        @self.app.route('config_manager/save_quick_setup',methods=['POST'])
        """

        """
            TODO: 一键写入人设配置
            @self.app.route('config_manager/people_write_config',methods=['POST'])
        """

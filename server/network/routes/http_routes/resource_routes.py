import os
from pathlib import Path
from flask import jsonify, request
from utils import IoUtil
from werkzeug.utils import secure_filename

class ResourceRoutes:
    def __init__(self, app):
        self.app = app
        self.resource_manager_routes()

    def resource_manager_routes(self):
        @self.app.route('/resource_manager/upload_background', methods=['POST'])
        def upload_background():
                """ 上传背景图片
                接收客户端的保存配置请求，必须包含以下字段：
                - background: 图片文件

                Returns:
                    - status: 状态，success 或 error
                    - message: 消息
                    - data: 配置数据

                    - 成功: {'status':'success','message': '背景图片更新成功，请重新加载','data': {}} 200
                    - 失败: 
                        - {'status':'error','message': '上传失败,未上传文件'} 400
                        - {'status':'error','message': '上传失败', 'error': err} 400
                """
                
                try:
                        if 'background' not in request.files:
                                return jsonify({
                                        'status':'error',
                                        'message': '上传失败,未上传文件'
                                }), 400
                        file = request.files['background']
                        if file:
                                # 确保文件名不为空并进行安全处理
                                filename = secure_filename(file.filename) if file.filename else ''
                                # 更改文件名为 ‘background.png’
                                filename = 'background.png'

                                file.save(os.path.join('static', 'background', filename))
                                return jsonify({
                                      'status':'success',
                                      'message': '背景图片更新成功，请重新加载'
                                }), 200
                except Exception as e:
                        return jsonify({
                               'status':'error',
                               'message': '上传失败',
                               'error': str(e)
                        }), 400

        @self.app.route('/resource_manager/get_background', methods=['GET'])
        def get_background():
                """ 获取背景图片
                接收客户端的获取背景图片请求，无需字段：
                Returns:
                    - status: 状态，success 或 error
                    - message: 消息
                    - data: 配置数据

                    - 成功: {'status':'success','message': '获取背景图片成功','data': {}} 200
                """

                # 返回文件路径
                return jsonify({
                       'status':'success',
                       'message': '获取背景图片成功',
                        'data': 'static/background/background.png'
                }), 200
               
        @self.app.route('/resource_manager/get_available_avatars', methods=['GET'])
        def get_available_avatars():
                """ 获取可用头像
                接收客户端的获取可用头像请求，无需字段：
                Returns:
                    - status: 状态，success 或 error
                    - message: 消息
                    - avactarList: 头像列表

                    - 成功: {'status':'success','message': '获取可用头像成功','data': {}} 200
                """
                # 返回文件路径下所有文件名jian
                io = IoUtil()
                avactarList = io.get_all_files('./static/avatar')
                return jsonify({
                      'status':'success',
                      'message': '获取可用头像成功',
                      'avactarList': avactarList
                }), 200

        @self.app.route('/resource_manager/load_avatar_content', methods=['GET'])
        def load_avatar_content():
                """ 加载头像内容
                接收客户端的加载头像内容请求，必须包含以下字段：
                - avatar: 头像文件名

                Returns:
                    - status: 状态，success 或 error
                    - message: 消息
                    - data: 配置数据
                    - 成功: {'status':'success','message': '加载头像内容成功','data': {}} 200
                """
                # 返回文件路径
                avatar = request.args.get('avatar')
                return jsonify({
                      'status':'success',
                      'message': '加载头像内容成功',
                        'data':f'static/avatar/${avatar}'
                }), 200
        

        # # ### 加载头像表情  TODO: 表情包文件应迁移至 wxauto 模块
        # # - **URL**: `/load_avatar_emojis`
        # # - **方法**: `GET`, `POST`
        # # - **描述**: 加载头像相关的表情包
        # @self.app.route('/resource_manager/load_avatar_emojis', methods=['GET', 'POST'])

        # # ### 删除头像表情
        # # - **URL**: `/delete_avatar_emojis`
        # # - **方法**: `POST`
        # # - **描述**: 删除头像相关的表情包
        # @self.app.route('/resource_manager/delete_avatar_emojis', methods=['POST'])

        # # ### 上传表情包压缩文件 TODO: 表情包文件应迁移至 wxauto 模块
        # # - **URL**: `/upload_avatarEmoji_zip`
        # # - **方法**: `POST`
        # # - **描述**: 上传表情包ZIP文件
        # @self.app.route('/resource_manager/upload_avatarEmoji_zip', methods=['POST'])
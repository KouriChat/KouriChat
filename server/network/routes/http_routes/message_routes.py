import os
from flask import request, jsonify
from werkzeug.utils import secure_filename

class MessageRoutes:
    def __init__(self, app):
        self.app = app
        self.register_routes()
        
    def register_routes(self):
        @self.app.route('/message/text', methods=['POST'])
        def receive_message():
            """纯文本接收消息接口
            
            接收客户端发送的消息，消息格式为JSON，必须包含以下字段:
            - sender_id: int 发送者ID
            - sender: str 发送者名称
            - chat_type: str 聊天类型(group || private)
            - character: int 角色ID (0: 系统角色)   TODO: 角色ID映射
            - message_type: str 消息类型(text)  TODO: 消息类型映射 消息类型应当具备
            - message_send_time: str 消息发送时间(格式:YYYY-MM-DD HH:mm:ss)
            
            Returns:
                JSON响应:
                - 成功: {'status': 'ok', 'message': '消息接收成功', 'received_content': str}
                - 失败: {'status': 'error', 'message': str}
            """
            # 记录请求基本信息
            print(f"收到请求: {request.method} {request.url}")
            print("请求头:", dict(request.headers))
            
            # 检查Content-Type
            if not request.is_json:
                print("错误：请求未携带application/json头")
                return jsonify({'status': 'error', 'message': '请使用application/json内容类型'}), 400
            
            try:
                data = request.get_json()
                print("原始请求体:", request.get_data(as_text=True))
                
                # 验证必需字段
                required_fields = ['sender_id', 'sender', 'chat_type', 'character', 
                                'message_type', 'message_send_time']
                for field in required_fields:
                    if field not in data:
                        return jsonify({
                            'status': 'error',
                            'message': f'缺少必需字段: {field}'
                        }), 400
                        
                # 验证字段类型
                if not isinstance(data['sender_id'], int):
                    return jsonify({'status': 'error', 'message': 'sender_id必须为整数'}), 400
                if not isinstance(data['sender'], str):
                    return jsonify({'status': 'error', 'message': 'sender必须为字符串'}), 400
                if data['chat_type'] != 'group':
                    return jsonify({'status': 'error', 'message': 'chat_type必须为group或者private'}), 400
                if not isinstance(data['character'], int):
                    return jsonify({'status': 'error', 'message': 'character必须为整数'}), 400
                if data['message_type'] != 'text':
                    return jsonify({'status': 'error', 'message': 'message_type必须为text'}), 400
                
            except Exception as e:
                print(f"JSON解析错误: {str(e)}")
                return jsonify({'status': 'error', 'message': '无效的JSON格式'}), 400

            # 递交事件总线
            # TODO: 事件总线

            return jsonify({
                'status': 'ok',
                'message': '消息接收成功',
                'received_content': "我喜欢你"
            }), 200
    
        @self.app.route('/message/image', methods=['POST'])
        def receive_image():
            """图片接收消息接口
            
            请求格式：multipart/form-data
            表单字段:
            - image: 图片文件
            - sender_id: int 发送者ID
            - sender: str 发送者名称
            - chat_type: str 聊天类型(group || private)
            - character: int 角色ID
            - message_type: str 消息类型(image)
            - message_send_time: str 消息发送时间
            
            Returns:
                JSON响应
                - 成功: {'status': 'ok','message': '图片上传成功','image_path': str}
                - 失败: {'status': 'error','message': str}
            """
            try:
                # 检查是否包含文件
                if 'image' not in request.files:
                    return jsonify({
                        'status': 'error',
                        'message': '未找到图片文件'
                    }), 400
                    
                image_file = request.files['image']
                if image_file.filename == '':
                    return jsonify({
                        'status': 'error',
                        'message': '未选择图片文件'
                    }), 400
                
                # 验证文件类型
                if not (image_file.content_type and image_file.content_type.startswith('image/')):
                    return jsonify({
                        'status': 'error',
                        'message': '不支持的文件类型'
                    }), 400
                
                # 验证其他字段
                required_fields = ['sender_id', 'sender', 'chat_type', 
                                'character', 'message_type', 'message_send_time']
                for field in required_fields:
                    if field not in request.form:
                        return jsonify({
                            'status': 'error',
                            'message': f'缺少必需字段: {field}'
                        }), 400
                
                # 保存图片文件
                # TODO: 配置图片保存路径
                save_path = "uploads/images"
                if not os.path.exists(save_path):
                    os.makedirs(save_path)
                    
                filename = secure_filename(image_file.filename)
                file_path = os.path.join(save_path, filename)
                image_file.save(file_path)
                
                # 构建消息数据
                message_data = {
                    'sender_id': int(request.form['sender_id']),
                    'sender': request.form['sender'],
                    'chat_type': request.form['chat_type'],
                    'character': int(request.form['character']),
                    'message_type': 'image',
                    'message_send_time': request.form['message_send_time'],
                    'image_path': file_path
                }
                
                # TODO: 发送到事件总线处理
                
                return jsonify({
                    'status': 'ok',
                    'message': '图片上传成功',
                    'image_path': file_path
                }), 200
                
            except Exception as e:
                print(f"处理图片上传错误: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': f'图片上传失败: {str(e)}'
                }), 500

        @self.app.route('/message/voice', methods=['POST'])
        def receive_voice():
            """语音接收消息接口

            请求格式：multipart/form-data
            表单字段:
            - voice: 语音文件
            - sender_id: int 发送者ID
            - sender: str 发送者名称
            - chat_type: str 聊天类型(group || private)
            - character: int 角色ID
            - message_type: str 消息类型(voice)
            - message_send_time: str 消息发送时间

            Returns:
                JSON响应
                - 成功: {'status': 'ok','message': '语音上传成功','voice_path': str}
                - 失败: {'status': 'error','message': str}
            """
            try:
                # 检查是否包含文件
                if 'voice' not in request.files:
                    return jsonify({
                       'status': 'error',
                       'message': '未找到语音文件'
                    }), 400

                voice_file = request.files['voice']
                if voice_file.filename == '':
                    return jsonify({
                        'status': 'error',
                        'message': '未选择语音文件'
                    }), 400

                # 验证文件类型
                if not (voice_file.content_type and voice_file.content_type.startswith('audio/')):
                    return jsonify({
                        'status': 'error',
                        'message': '不支持的文件类型'
                    }), 400

                # 验证其他字段
                required_fields = ['sender_id', 'sender', 'chat_type', 
                                'character', 'message_type', 'message_send_time']
                for field in required_fields:
                    if field not in request.form:
                        return jsonify({
                            'status': 'error',
                            'message': f'缺少必需字段: {field}'
                        }), 400

                # 保存语音文件
                # TODO: 配置语音保存路径
                save_path = "uploads/voices"
                if not os.path.exists(save_path):
                    os.makedirs(save_path)

                filename = secure_filename(voice_file.filename)
                file_path = os.path.join(save_path, filename)
                voice_file.save(file_path)

                # 构建消息数据
                message_data = {
                    'sender_id': int(request.form['sender_id']),
                    'sender': request.form['sender'],
                    'chat_type': request.form['chat_type'],
                    'character': int(request.form['character']),
                    'message_type': 'voice',
                    'message_send_time': request.form['message_send_time'],
                    'voice_path': file_path
                }

                # TODO: 发送到事件总线处理

                return jsonify({
                    'status': 'ok',
                    'message': '语音上传成功',
                    'voice_path': file_path
                }), 200

            except Exception as e:
                print(f"处理语音上传错误: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': f'语音上传失败: {str(e)}'
                }), 500

        @self.app.route('/message/file', methods=['POST'])
        def receive_file():
        
            """文件接收消息接口

            请求格式：multipart/form-data
            表单字段:
            - file: 文件
            - sender_id: int 发送者ID
            - sender: str 发送者名称
            - chat_type: str 聊天类型(group || private)
            - character: int 角色ID
            - message_type: str 消息类型(file)
            - message_send_time: str 消息发送时间

            Returns:
                JSON响应
                - 成功: {'status': 'ok','message': '文件上传成功','file_path': str}
                - 失败: {'status': 'error','message': str}
            """
            try:
                # 检查是否包含文件
                if 'file' not in request.files:
                    return jsonify({
                     'status': 'error',
                     'message': '未找到文件'
                    }), 400

                file = request.files['file']
                if file.filename == '':
                    return jsonify({
                    'status': 'error',
                    'message': '未选择文件'
                    }), 400

                # 验证文件类型
                if not (file.content_type and file.content_type.startswith('application/')):
                    return jsonify({
                   'status': 'error',
                   'message': '不支持的文件类型'
                    }), 400

                # 验证message_type参数
                if request.form.get('message_type')!= 'file':
                    return jsonify({
                   'status': 'error',
                   'message':'message_type必须为file'
                    }), 400

                # 验证其他字段
                required_fields = ['sender_id','sender', 'chat_type', 'character','message_send_time']
                for field in required_fields:
                    if field not in request.form:
                        return jsonify({
                  'status': 'error',
                  'message': f'缺少必需字段: {field}'
                    }), 400

                # 保存文件
                # TODO: 配置文件保存路径
                save_path = "uploads/files"
                if not os.path.exists(save_path):
                    os.makedirs(save_path)

                filename = secure_filename(file.filename)
                file_path = os.path.join(save_path, filename)
                file.save(file_path)

                # 构建消息数据
                message_data = {
                   'sender_id': int(request.form['sender_id']),
                   'sender': request.form['sender'],
                    'chat_type': request.form['chat_type'],
                    'character': int(request.form['character']),
                   'message_type': 'file',
                    'file_path': file_path
                }

                # TODO: 发送到事件总线处理

                return jsonify({
                  'status': 'ok',
                  'message': '文件上传成功',
                    'file_path': file_path
                }), 200

            except Exception as e:
                print(f"处理文件上传错误: {str(e)}")
                return jsonify({
                 'status': 'error',
                 'message': f'文件上传失败: {str(e)}'
                }), 500


    # @self.app.route('/message/command',methods=['POST'])  预留 为客户端操作后端提供接口  TODO
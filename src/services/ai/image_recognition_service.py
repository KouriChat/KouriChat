"""
图像识别 AI 服务模块
提供与图像识别 API 的交互功能，包括:
- 图像识别
- 文本生成
- API请求处理
- 错误处理
"""

import base64
import logging
import requests
from typing import Optional
import os

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class ImageRecognitionService:
    def __init__(self, api_key: str, base_url: str, temperature: float, model: str):
        self.api_key = api_key
        self.base_url = base_url
        # 确保 temperature 在有效范围内
        self.temperature = min(max(0.0, temperature), 1.0)  # 限制在 0-1 之间
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        self.model = model  # "moonshot-v1-8k-vision-preview"
        
        if temperature > 1.0:
            logger.warning(f"Temperature值 {temperature} 超出范围，已自动调整为 1.0")

    def recognize_image(self, image_path: str, is_emoji: bool = False) -> str:
        """使用 Moonshot AI 识别图片内容并返回文本"""
        try:
            # 验证图片路径
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return "抱歉，图片文件不存在"

            # 验证文件大小
            file_size = os.path.getsize(image_path) / (1024 * 1024)  # 转换为MB
            if file_size > 100:  # API限制为100MB
                logger.error(f"图片文件过大 ({file_size:.2f}MB): {image_path}")
                return "抱歉，图片文件太大了"

            # 读取并编码图片
            try:
                with open(image_path, 'rb') as img_file:
                    image_content = base64.b64encode(img_file.read()).decode('utf-8')
            except Exception as e:
                logger.error(f"读取图片文件失败: {str(e)}")
                return "抱歉，读取图片时出现错误"

            # 设置提示词
            text_prompt = "请描述这个图片" if not is_emoji else "这是一张微信聊天的图片截图，请描述这个聊天窗口左边的聊天用户用户发送的最后一张表情，不要去识别聊天用户的头像"
            
            # 准备请求数据
            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_content}"
                                }
                            },
                            {
                                "type": "text",
                                "text": text_prompt
                            }
                        ]
                    }
                ],
                "temperature": self.temperature
            }

            # 发送请求
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                    timeout=30  # 添加超时设置
                )
                
                # 检查响应状态
                if response.status_code != 200:
                    logger.error(f"API请求失败 - 状态码: {response.status_code}, 响应: {response.text}")
                    return "抱歉，图片识别服务暂时不可用"
                    
                # 处理响应
                result = response.json()
                if 'choices' not in result or not result['choices']:
                    logger.error(f"API响应格式异常: {result}")
                    return "抱歉，无法解析图片内容"
                    
                recognized_text = result['choices'][0]['message']['content']

                # 处理表情包识别结果
                if is_emoji:
                    if "最后一张表情包是" in recognized_text:
                        recognized_text = recognized_text.split("最后一张表情包是", 1)[1].strip()
                    recognized_text = "发送了表情包：" + recognized_text
                else:
                    recognized_text = "发送了图片：" + recognized_text

                logger.info(f"Moonshot AI图片识别结果: {recognized_text}")
                return recognized_text

            except requests.exceptions.Timeout:
                logger.error("API请求超时")
                return "抱歉，图片识别服务响应超时"
            except requests.exceptions.RequestException as e:
                logger.error(f"API请求异常: {str(e)}")
                return "抱歉，图片识别服务出现错误"
            except Exception as e:
                logger.error(f"处理API响应失败: {str(e)}")
                return "抱歉，处理图片识别结果时出现错误"

        except Exception as e:
            logger.error(f"图片识别过程失败: {str(e)}", exc_info=True)
            return "抱歉，图片识别过程出现错误"

    def chat_completion(self, messages: list, **kwargs) -> Optional[str]:
        """发送聊天请求到 Moonshot AI"""
        try:
            data = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get('temperature', self.temperature)
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content']

        except Exception as e:
            logger.error(f"Moonshot AI 聊天请求失败: {str(e)}")
            return None 
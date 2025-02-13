"""
Moonshot AI服务模块
提供与Moonshot API的交互功能，包括:
- 图像识别
- 文本生成
- API请求处理
- 错误处理
"""

import base64
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

class MoonShotAI:
    def __init__(self, api_key: str, base_url: str, temperature: float):
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        self.model = "moonshot-v1-8k-vision-preview"

    def recognize_image(self, image_path: str, is_emoji: bool = False) -> str:
        """使用 Moonshot AI 识别图片内容并返回文本"""
        try:
            # 读取并编码图片
            with open(image_path, 'rb') as img_file:
                image_content = base64.b64encode(img_file.read()).decode('utf-8')

            # 设置提示词
            text_prompt = "请描述这个图片" if not is_emoji else "请描述这个聊天窗口的最后一张表情包"
            
            # 准备请求数据
            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}},
                            {"type": "text", "text": text_prompt}
                        ]
                    }
                ],
                "temperature": self.temperature
            }

            # 发送请求
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            
            # 处理响应
            result = response.json()
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

        except Exception as e:
            logger.error(f"调用Moonshot AI识别图片失败: {str(e)}")
            return ""

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
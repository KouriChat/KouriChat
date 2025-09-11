"""
联网识别服务

负责识别消息中的联网搜索需求
"""

import json
import os
import logging
import sys
import ast
from datetime import datetime
from typing import Dict
from openai import OpenAI

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from src.services.ai.llm_service import LLMService
from src.autoupdate.updater import Updater
from data.config import config

logger = logging.getLogger('main')

class SearchRecognitionService:
    def __init__(self, llm_service: LLMService):
        """
        初始化搜索需求识别服务

        Args:
            llm_service: LLM服务实例，用于搜索需求识别
        """
        self.llm_service = llm_service
        self.intent_recognition_settings = {
            "api_key": config.intent_recognition.api_key,
            "base_url": config.intent_recognition.base_url,
            "model": config.intent_recognition.model,
            "temperature": config.intent_recognition.temperature
        }
        self.updater = Updater()
        self.client = OpenAI(
            api_key=self.intent_recognition_settings["api_key"],
            base_url=self.intent_recognition_settings["base_url"],
            default_headers={
                "Content-Type": "application/json",
                "User-Agent": self.updater.get_version_identifier(),
                "X-KouriChat-Version": self.updater.get_current_version()
            }
        )
        self.config = self.llm_service.config

        # 从文件读取提示词
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 读取
        with open(os.path.join(current_dir, "prompt.md"), "r", encoding="utf-8") as f:
            self.sys_prompt = f.read().strip()

    def recognize(self, message: str) -> Dict:
        """
        识别消息中的搜索需求

        Args:
            message: 用户消息
        
        Returns:
            Dict: {"search_required": true/false, "search_query": ""}
        """
        current_model = self.intent_recognition_settings["model"]
        logger.info(f"调用模型{current_model}进行联网意图识别...")
        current_time = datetime.now()        
        messages = [{"role": "system", "content": self.sys_prompt}]
        current_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(current_dir, "example_message.json"), 'r', encoding='utf-8') as f:
            data = json.load(f)
        for example in data.values():
            messages.append({
                "role": example["input"]["role"],
                "content": example["input"]["content"]
            })
            messages.append({
                "role": example["output"]["role"],
                "content": str(example["output"]["content"])
            })
        messages.append({
            "role": "user",
            "content": f"时间：{current_time.strftime('%Y-%m-%d %H:%M:%S')}\n消息：{message}"
        })

        request_config = {
            "model": self.intent_recognition_settings["model"],
            "messages": messages,
            "temperature": self.intent_recognition_settings["temperature"],
            "max_tokens": self.config["max_token"],
        }

        while True:
            response = self.client.chat.completions.create(**request_config)
            response_content = response.choices[0].message.content
            
            # 针对 Gemini 模型的回复进行预处理
            if response_content.startswith("```json") and response_content.endswith("```"):
                response_content = response_content[7:-3].strip()
            # 替换 true 或 false 为大写，这是为了确保响应字符串能够被解析为 Python 字面量
            # Python 中的布尔值是大写，而 json 中是小写
            response_content = response_content.replace('true', 'True').replace('false', 'False')
            try:
                response_content = ast.literal_eval(response_content)
                if (
                    isinstance(response_content, dict)
                    and "search_required" in response_content
                    and "search_query" in response_content
                ):
                    return response_content
            except (ValueError, SyntaxError): 
                logger.warning("识别搜索需求失败，进行重试...")


'''
单独对模块进行调试时，可以使用该代码
'''
if __name__ == '__main__':
    llm_service = LLMService(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        model=config.llm.model,
        max_token=1024,
        temperature=0.8,
        max_groups=5
    )
    test = SearchRecognitionService(llm_service)
    res = test.recognize("昨天有什么重要的财经事件？")
    for key, value in res.items():
        print(f"键: {key}, 值: {value}, 类型: {type(value).__name__}")
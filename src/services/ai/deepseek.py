"""
DeepSeek AI服务模块
提供与DeepSeek API的交互功能，包括:
- 管理API连接
- 处理对话上下文
- 发送API请求
- 处理API响应
"""

import logging
from typing import List, Dict, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

class DeepSeekAI:
    def __init__(self, api_key: str, base_url: str, model: str, 
                 max_token: int, temperature: float, max_groups: int):
        """
        初始化 DeepSeek AI 客户端
        
        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
            max_token: 最大token数
            temperature: 温度参数
            max_groups: 最大对话组数
        """
        self.model = model
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        
        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"Content-Type": "application/json"}
        )
        
        # 对话上下文管理
        self.chat_contexts: Dict[str, List[Dict[str, str]]] = {}

    def _manage_context(self, user_id: str, message: str, is_assistant: bool = False):
        """管理对话上下文"""
        if user_id not in self.chat_contexts:
            self.chat_contexts[user_id] = []

        role = "assistant" if is_assistant else "user"
        self.chat_contexts[user_id].append({"role": role, "content": message})

        # 保持对话历史在限定长度内
        while len(self.chat_contexts[user_id]) > self.max_groups * 2:
            if len(self.chat_contexts[user_id]) >= 2:
                del self.chat_contexts[user_id][0:2]  # 每次删除一组对话
            else:
                del self.chat_contexts[user_id][0]

    def get_response(self, message: str, user_id: str, system_prompt: str) -> str:
        """
        获取 API 回复
        
        Args:
            message: 用户消息
            user_id: 用户ID
            system_prompt: 系统提示词
            
        Returns:
            str: API 回复内容
        """
        try:
            logger.info(f"调用 DeepSeek API - 用户ID: {user_id}, 消息: {message}")
            
            # 添加用户消息到上下文
            self._manage_context(user_id, message)

            try:
                # 准备消息列表
                messages = [
                    {"role": "system", "content": system_prompt},
                    *self.chat_contexts[user_id][-self.max_groups * 2:]
                ]

                # 调用API
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_token,
                    stream=False
                )
            except Exception as api_error:
                logger.error(f"API调用失败: {str(api_error)}")
                return "抱歉主人，我现在有点累，请稍后再试..."

            if not response.choices:
                logger.error("API返回空choices: %s", response)
                return "抱歉主人，服务响应异常，请稍后再试"

            reply = response.choices[0].message.content
            logger.info(f"API响应 - 用户ID: {user_id}")
            logger.info(f"响应内容: {reply}")
            
            # 添加助手回复到上下文
            self._manage_context(user_id, reply, is_assistant=True)
            
            return reply

        except Exception as e:
            logger.error(f"DeepSeek调用失败: {str(e)}", exc_info=True)
            return "抱歉主人，刚刚不小心睡着了..."

    def clear_context(self, user_id: str):
        """清除指定用户的对话上下文"""
        if user_id in self.chat_contexts:
            del self.chat_contexts[user_id]
            logger.info(f"已清除用户 {user_id} 的对话上下文")

    def get_context(self, user_id: str) -> List[Dict[str, str]]:
        """获取指定用户的对话上下文"""
        return self.chat_contexts.get(user_id, []) 
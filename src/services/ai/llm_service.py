"""
LLM AI 服务模块
提供与LLM API的完整交互实现，包含以下核心功能：
- API请求管理
- 上下文对话管理
- 响应安全处理
- 智能错误恢复
"""

import logging
import re
import os
import random
import json  # 新增导入
import time  # 新增导入
import pathlib
import requests
from typing import Dict, List, Optional, Tuple, Union
from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type
)

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class LLMService:
    def __init__(self, api_key: str, base_url: str, model: str,
                 max_token: int, temperature: float, max_groups: int):
        """
        强化版AI服务初始化

        :param api_key: API认证密钥
        :param base_url: API基础URL
        :param model: 使用的模型名称
        :param max_token: 最大token限制
        :param temperature: 创造性参数(0~2)
        :param max_groups: 最大对话轮次记忆
        :param system_prompt: 系统级提示词
        """
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "Content-Type": "application/json",
                "User-Agent": "MyDreamBot/1.0"
            }
        )
        self.config = {
            "model": model,
            "max_token": max_token,
            "temperature": temperature,
            "max_groups": max_groups,
        }
        self.chat_contexts: Dict[str, List[Dict]] = {}

        # 安全字符白名单（可根据需要扩展）
        self.safe_pattern = re.compile(r'[\x00-\x1F\u202E\u200B]')

        # 如果是 Ollama，获取可用模型列表
        if 'localhost:11434' in base_url:
            self.available_models = self.get_ollama_models()
        else:
            self.available_models = []

    def _manage_context(self, user_id: str, message: str, role: str = "user"):
        """
        上下文管理器（支持动态记忆窗口）

        :param user_id: 用户唯一标识
        :param message: 消息内容
        :param role: 角色类型(user/assistant)
        """
        if user_id not in self.chat_contexts:
            self.chat_contexts[user_id] = []

        # 添加新消息
        self.chat_contexts[user_id].append({"role": role, "content": message})

        # 维护上下文窗口
        while len(self.chat_contexts[user_id]) > self.config["max_groups"] * 2:
            # 优先保留最近的对话组
            self.chat_contexts[user_id] = self.chat_contexts[user_id][-self.config["max_groups"]*2:]

    def _sanitize_response(self, raw_text: str) -> str:
        """
        响应安全处理器
        1. 移除控制字符
        2. 标准化换行符
        3. 防止字符串截断异常
        """
        try:
            cleaned = re.sub(self.safe_pattern, '', raw_text)
            return cleaned.replace('\r\n', '\n').replace('\r', '\n')
        except Exception as e:
            logger.error(f"Response sanitization failed: {str(e)}")
            return "响应处理异常，请重新尝试"

    def _filter_thinking_content(self, content: str) -> str:
        """
        过滤思考内容，支持不同模型的返回格式
        1. R1格式: 思考过程...\n\n\n最终回复
        2. Gemini格式: <think>思考过程</think>\n\n最终回复
        """
        try:
            # 过滤 Gemini 格式 (<think>思考过程</think>)
            filtered_content = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL)
            
            # 过滤 R1 格式 (思考过程...\n\n\n最终回复)
            # 查找三个连续换行符
            triple_newline_match = re.search(r'\n\n\n', filtered_content)
            if triple_newline_match:
                # 只保留三个连续换行符后面的内容（最终回复）
                filtered_content = filtered_content[triple_newline_match.end():]
            
            return filtered_content.strip()
        except Exception as e:
            logger.error(f"过滤思考内容失败: {str(e)}")
            return content  # 如果处理失败，返回原始内容

    def _validate_response(self, response: dict) -> bool:
        """
        放宽检验
        API响应校验
        只要能获取到有效的回复内容就返回True
        """
        try:
            # 尝试获取回复内容
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices and isinstance(choices, list):
                    first_choice = choices[0]
                    if isinstance(first_choice, dict):
                        # 尝试不同的响应格式
                        # 格式1: choices[0].message.content
                        if isinstance(first_choice.get("message"), dict):
                            content = first_choice["message"].get("content")
                            if content and isinstance(content, str):
                                return True
                        
                        # 格式2: choices[0].content
                        content = first_choice.get("content")
                        if content and isinstance(content, str):
                            return True
                        
                        # 格式3: choices[0].text
                        text = first_choice.get("text")
                        if text and isinstance(text, str):
                            return True

            logger.warning("无法从响应中获取有效内容")
            return False
            
        except Exception as e:
            logger.error(f"验证响应时发生错误: {str(e)}")
            return False

    def get_response(self, message: str, user_id: str, system_prompt: str, previous_context: List[Dict] = None, core_memory: str = None) -> str:
        """
        完整请求处理流程
        Args:
            message: 用户消息
            user_id: 用户ID
            system_prompt: 系统提示词（人设）
            previous_context: 历史上下文（可选）
            core_memory: 核心记忆（可选）
        """
        try:
            # —— 阶段1：输入验证 ——
            if not message.strip():
                return "Error: Empty message received"

            # —— 阶段2：上下文更新 ——
            # 只在程序刚启动时（上下文为空时）加载外部历史上下文
            if previous_context and user_id not in self.chat_contexts:
                logger.info(f"程序启动初始化：加载历史上下文，共 {len(previous_context)} 条消息")
                self.chat_contexts[user_id] = previous_context.copy()
            
            # 添加当前消息到上下文
            self._manage_context(user_id, message)

            # —— 阶段3：构建请求参数 ——
            # 读取基础Prompt
            try:
                # 从当前文件位置(llm_service.py)向上导航到项目根目录
                current_dir = os.path.dirname(os.path.abspath(__file__))  # src/services/ai
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))  # 项目根目录
                base_prompt_path = os.path.join(project_root, "data", "base", "base.md")
                
                with open(base_prompt_path, "r", encoding="utf-8") as f:
                    base_content = f.read()
            except Exception as e:
                logger.error(f"基础Prompt文件读取失败: {str(e)}")
                base_content = ""
            
            # 构建完整提示词: base + 核心记忆 + 人设
            if core_memory:
                final_prompt = f"{base_content}\n\n{core_memory}\n\n{system_prompt}"
                logger.debug("提示词顺序：base.md + 核心记忆 + 人设")
            else:
                final_prompt = f"{base_content}\n\n{system_prompt}"
                logger.debug("提示词顺序：base.md + 人设")
            
            # 构建消息列表
            messages = [
                {"role": "system", "content": final_prompt},
                *self.chat_contexts.get(user_id, [])[-self.config["max_groups"] * 2:]
            ]

            # 为 Ollama 构建消息内容
            chat_history = self.chat_contexts.get(user_id, [])[-self.config["max_groups"] * 2:]
            history_text = "\n".join([
                f"{msg['role']}: {msg['content']}" 
                for msg in chat_history
            ])
            ollama_message = {
                "role": "user",
                "content": f"{final_prompt}\n\n对话历史：\n{history_text}\n\n用户问题：{message}"
            }

            # 检查是否是 Ollama API
            is_ollama = 'localhost:11434' in str(self.client.base_url)

            if is_ollama:
                # Ollama API 格式
                request_config = {
                    "model": self.config["model"].split('/')[-1],  # 移除路径前缀
                    "messages": [ollama_message],  # 将消息包装在列表中
                    "stream": False,
                    "options": {
                        "temperature": self.config["temperature"],
                        "max_tokens": self.config["max_token"]
                    }
                }

                # 使用 requests 库向 Ollama API 发送 POST 请求
                try:
                    response = requests.post(
                        f"{str(self.client.base_url)}",
                        json=request_config,
                        headers={"Content-Type": "application/json"}
                    )
                    response.raise_for_status()
                    response_data = response.json()
                    
                    # 检查响应中是否包含 message 字段
                    if response_data and "message" in response_data:
                        raw_content = response_data["message"]["content"]
                        
                        # 处理 R1 特殊格式，可能包含 reasoning_content 字段
                        if isinstance(response_data["message"], dict) and "reasoning_content" in response_data["message"]:
                            logger.debug("检测到 R1 格式响应，将分离思考内容")
                            # 只使用 content 字段内容，忽略 reasoning_content
                            raw_content = response_data["message"]["content"]
                            
                        logger.debug("Ollama API响应内容: %s", raw_content)
                    else:
                        raise ValueError("错误的API响应结构")
                        
                    clean_content = self._sanitize_response(raw_content)
                    # 过滤思考内容
                    filtered_content = self._filter_thinking_content(clean_content)
                    self._manage_context(user_id, filtered_content, "assistant")
                    return filtered_content
                    
                except Exception as e:
                    logger.error(f"Ollama API请求失败: {str(e)}")
                    raise

            else:
                # 主要 api 请求（重要）
                # 标准 OpenAI 格式
                request_config = {
                    "model": self.config["model"],  # 模型名称
                    "messages": messages,  # 消息列表
                    "temperature": self.config["temperature"],  # 温度参数
                    "max_tokens": self.config["max_token"],  # 最大 token 数
                    "top_p": 0.95,  # top_p 参数
                    "frequency_penalty": 0.2  # 频率惩罚参数
                }

                # 使用 OpenAI 客户端发送请求
                response = self.client.chat.completions.create(**request_config)
                # 验证 API 响应结构
                if not self._validate_response(response.model_dump()):
                    raise ValueError("错误的API响应结构")

                # 获取原始内容
                raw_content = response.choices[0].message.content
                # 清理响应内容
                clean_content = self._sanitize_response(raw_content)
                # 过滤思考内容
                filtered_content = self._filter_thinking_content(clean_content)
                # 管理上下文
                self._manage_context(user_id, filtered_content, "assistant")
                # 返回过滤后的内容
                return filtered_content or ""

        except Exception as e:
            error_message = f"Error: {str(e)}"
            logger.error("大语言模型服务调用失败: %s", str(e), exc_info=True)
            return error_message

    def clear_history(self, user_id: str) -> bool:
        """
        清空指定用户的对话历史
        """
        if user_id in self.chat_contexts:
            del self.chat_contexts[user_id]
            logger.info("已清除用户 %s 的对话历史", user_id)
            return True
        return False

    def analyze_usage(self, response: dict) -> Dict:
        """
        用量分析工具
        """
        usage = response.get("usage", {})
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "estimated_cost": (usage.get("total_tokens", 0) / 1000) * 0.02  # 示例计价
        }

    def chat(self, messages: list, **kwargs) -> str:
        """
        发送聊天请求并获取回复

        Args:
            messages: 消息列表，每个消息是包含 role 和 content 的字典
            **kwargs: 额外的参数配置
            
        Returns:
            str: AI的回复内容
        """
        try:
            response = self.client.chat.completions.create(
                model=self.config["model"],
                messages=messages,
                temperature=kwargs.get('temperature', self.config["temperature"]),
                max_tokens=self.config["max_token"]
            )
            
            if not self._validate_response(response.model_dump()):
                raise ValueError("Invalid API response structure")
            
            raw_content = response.choices[0].message.content    
            # 清理和过滤响应内容
            clean_content = self._sanitize_response(raw_content)
            filtered_content = self._filter_thinking_content(clean_content)
                
            return filtered_content or ""
            
        except Exception as e:
            logger.error(f"Chat completion failed: {str(e)}")
            return ""

    def get_ollama_models(self) -> List[Dict]:
        """获取本地 Ollama 可用的模型列表"""
        try:
            response = requests.get('http://localhost:11434/api/tags')
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [
                    {
                        "id": model['name'],
                        "name": model['name'],
                        "status": "active",
                        "type": "chat",
                        "context_length": 16000  # 默认上下文长度
                    }
                    for model in models
                ]
            return []
        except Exception as e:
            logger.error(f"获取Ollama模型列表失败: {str(e)}")
            return []

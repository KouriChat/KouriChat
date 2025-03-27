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
from typing import Dict, List, Optional
from openai import APIError, APITimeoutError
from src.services.ai.llms.openai_llm import OpenAILLM

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class LLMService:
    def __init__(self, api_key: str, base_url: str, model: str,
                max_token: int, temperature: float, max_groups: int,
                sys_prompt: str = None):
        """
        强化版AI服务初始化

        :param api_key: API认证密钥
        :param base_url: API基础URL
        :param model: 使用的模型名称
        :param max_token: 最大token限制
        :param temperature: 创造性参数(0~2)
        :param max_groups: 最大对话轮次记忆
        """
        # 记录配置信息
        logger.info(f"LLMService初始化 - 模型: {model}, URL: {base_url}")

        # 使用OpenAILLM作为内核，启用单例模式
        self.llm = OpenAILLM(
            logger=logger,
            model_name=model,
            url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_token,
            max_context_messages=max_groups,
            n_ctx=4096,  # 默认上下文长度
            system_prompt=sys_prompt,
            singleton=True  # 使用单例模式
        )

        self.config = {
            "model": model,
            "max_token": max_token,
            "temperature": temperature,
            "max_groups": max_groups,
        }

        # 安全字符白名单（可根据需要扩展）
        self.safe_pattern = re.compile(r'[\x00-\x1F\u202E\u200B]')

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

    def get_response(self, message: str, user_id: str, system_prompt: str) -> str:
        """
        完整请求处理流程
        """
        try:
            # —— 阶段1：输入验证 ——
            if not message.strip():
                logger.warning("收到空消息请求")
                return "嗯...我好像收到了空白消息呢（歪头）"

            # —— 阶段2：构建请求参数 ——
            # 拼接基础Prompt
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

            # 合并系统提示词
            full_system_prompt = f"{system_prompt}\n{base_content}"

            # 设置系统提示词
            if self.llm.system_prompt != full_system_prompt:
                # 重置上下文并设置新的系统提示词
                self.llm.context = []
                if full_system_prompt:
                    self.llm.context.append({"role": "system", "content": full_system_prompt})
                    self.llm.system_prompt = full_system_prompt

            # 使用OpenAILLM处理请求
            response = self.llm.handel_prompt(message, user_id)

            # 清理响应内容
            clean_content = self._sanitize_response(response)

            # 移除[memory_number:...]标记
            clean_content = re.sub(r'\s*\[memory_number:.*?\]$', '', clean_content)

            # 返回清理后的内容
            return clean_content or ""

        except APIError as e:
            logger.error(f"API错误: {str(e)}, 请检查网络配置")
            return "API服务暂时不可用，请稍后再试。"

        except APITimeoutError as e:
            logger.error(f"API超时: {str(e)}, 请检查网络配置")
            return "请求超时，请检查网络连接后重试。"

        except Exception as e:
            logger.error("大语言模型服务调用失败: %s", str(e), exc_info=True)
            return random.choice([
                "好像有些小状况，请再试一次吧～",
                "信号好像不太稳定呢（皱眉）",
                "思考被打断了，请再说一次好吗？"
            ])

    def clear_history(self, user_id: str) -> bool:
        """
        清空指定用户的对话历史
        """
        try:
            # 重置LLM上下文，只保留系统提示
            system_prompt = None
            if self.llm.context and self.llm.context[0]["role"] == "system":
                system_prompt = self.llm.context[0]["content"]

            self.llm.context = []
            if system_prompt:
                self.llm.context.append({"role": "system", "content": system_prompt})

            logger.info("已清除用户对话历史")
            return True
        except Exception as e:
            logger.error(f"清除历史失败: {str(e)}")
            return False

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
            # 临时设置上下文
            original_context = self.llm.context.copy()
            self.llm.context = messages[:-1]  # 除了最后一条用户消息

            # 处理最后一条用户消息
            response = self.llm.handel_prompt(messages[-1]["content"])

            # 恢复原始上下文
            self.llm.context = original_context

            return response

        except Exception as e:
            logger.error(f"Chat completion failed: {str(e)}")
            return ""

    def generate(self, message: str, system_prompt: str = None, user_id: str = None) -> str:
        """
        生成AI回复内容

        :param message: 用户消息
        :param system_prompt: 可选的系统提示词，为空则使用默认提示词
        :param user_id: 用户ID，用于上下文识别
        :return: AI回复内容
        """
        try:
            # 构建完整的系统提示词
            full_system_prompt = ""
            if self.llm.system_prompt:
                full_system_prompt = self.llm.system_prompt
            if system_prompt:
                full_system_prompt = full_system_prompt + "\n" + system_prompt if full_system_prompt else system_prompt

            # 设置系统提示词
            if self.llm.system_prompt != full_system_prompt:
                # 重置上下文并设置新的系统提示词
                self.llm.context = []
                if full_system_prompt:
                    self.llm.context.append({"role": "system", "content": full_system_prompt})
                    self.llm.system_prompt = full_system_prompt

            # 使用OpenAILLM处理请求
            response = self.llm.handel_prompt(message, user_id)

            # 清理响应内容
            clean_content = self._sanitize_response(response)

            # 移除[memory_number:...]标记
            clean_content = re.sub(r'\s*\[memory_number:.*?\]$', '', clean_content)

            # 返回清理后的内容
            return clean_content or ""

        except APIError as e:
            logger.error(f"API错误: {str(e)}, 请检查网络配置")
            return "API服务暂时不可用，请稍后再试。"

        except APITimeoutError as e:
            logger.error(f"API超时: {str(e)}, 请检查网络配置")
            return "请求超时，请检查网络连接后重试。"

        except Exception as e:
            logger.error("大语言模型服务调用失败: %s", str(e), exc_info=True)
            return random.choice([
                "好像有些小状况，请再试一次吧～",
                "信号好像不太稳定呢（皱眉）",
                "思考被打断了，请再说一次好吗？"
            ])

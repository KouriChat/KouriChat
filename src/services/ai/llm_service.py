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
from zhdate import ZhDate
import datetime
import requests
from typing import Dict, List, Optional, Tuple, Union
from openai import OpenAI
from src.autoupdate.updater import Updater
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type
)

# 导入emoji库用于处理表情符号
import emoji

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class LLMService:
    def __init__(self, api_key: str, base_url: str, model: str,
                 max_token: int, temperature: float, max_groups: int, auto_model_switch: bool = False):
        """
        强化版AI服务初始化

        :param api_key: API认证密钥
        :param base_url: API基础URL
        :param model: 使用的模型名称
        :param max_token: 最大token限制
        :param temperature: 创造性参数(0~2)
        :param max_groups: 最大对话轮次记忆
        :param system_prompt: 系统级提示词
        :param auto_model_switch: 是否启用自动模型切换
        """
        # 创建 Updater 实例获取版本信息
        updater = Updater()
        version = updater.get_current_version()
        version_identifier = updater.get_version_identifier()

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "Content-Type": "application/json",
                "User-Agent": version_identifier,
                "X-KouriChat-Version": version
            }
        )
        self.config = {
            "model": model,
            "max_token": max_token,
            "temperature": temperature,
            "max_groups": max_groups,
            "auto_model_switch": auto_model_switch
        }
        self.original_model = model
        self.chat_contexts: Dict[str, List[Dict]] = {}

        # 安全字符白名单（可根据需要扩展）
        self.safe_pattern = re.compile(r'[\x00-\x1F\u202E\u200B]')

        # 如果是 Ollama，获取可用模型列表
        if 'localhost:11434' in base_url:
            self.ollama_models = self.get_ollama_models()
        else:
            self.ollama_models = []

        self.available_models = self._get_available_models()

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
    
    def _build_time_context(self, user_id: str) -> str:
        """构建时间上下文信息"""
        if user_id not in self.chat_contexts or len(self.chat_contexts[user_id]) < 2:
            return "这是你们今天的第一次对话。"
    
        try:
            # 获取最后两条消息的时间
            recent_messages = self.chat_contexts[user_id][-2:]
        
            last_msg_time = None
            current_time = datetime.datetime.now()
        
            for msg in reversed(recent_messages):
                if 'timestamp' in msg:
                    last_msg_time = datetime.datetime.fromisoformat(msg['timestamp'])
                    break
        
            if last_msg_time:
                time_diff = current_time - last_msg_time
                seconds = int(time_diff.total_seconds())
            
                if seconds < 60:
                    time_desc = f"距离上条消息仅过去了{seconds}秒"
                elif seconds < 3600:
                    minutes = seconds // 60
                    time_desc = f"距离上条消息过去了{minutes}分钟"
                else:
                    hours = seconds // 3600
                    time_desc = f"距离上条消息过去了{hours}小时"
                
                return f"{time_desc}，请根据时间的流逝，调整回答内容。"
        
        except Exception as e:
            logger.error(f"构建时间上下文失败: {str(e)}")
    
        return "请注意时间的连续性。"

    def _sanitize_response(self, raw_text: str) -> str:
        """
        响应安全处理器
        1. 移除控制字符
        2. 标准化换行符
        3. 防止字符串截断异常
        4. 处理emoji表情符号，确保跨平台兼容性
        """
        try:
            # 移除控制字符
            cleaned = re.sub(self.safe_pattern, '', raw_text)

            # 标准化换行符
            cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')

            # 处理emoji表情符号
            cleaned = self._process_emojis(cleaned)

            return cleaned
        except Exception as e:
            logger.error(f"Response sanitization failed: {str(e)}")
            return "响应处理异常，请重新尝试"

    def _process_emojis(self, text: str) -> str:
        """处理文本中的emoji表情符号，确保跨平台兼容性"""
        try:
            # 先将Unicode表情符号转换为别名再转回，确保标准化
            return emoji.emojize(emoji.demojize(text))
        except Exception:
            return text  # 如果处理失败，返回原始文本

    def _filter_thinking_content(self, content: str) -> str:
        """
        过滤思考内容，支持不同模型的返回格式
        1. R1格式: 思考过程...\n\n\n最终回复
        2. Gemini格式: <think>思考过程</think>\n\n最终回复
        """
        try:
            # 使用分割替代正则表达式处理 Gemini 格式
            if '<think>' in content and '</think>' in content:
                parts = content.split('</think>')
                # 只保留最后一个</think>后的内容
                filtered_content = parts[-1].strip()
            else:
                filtered_content = content

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
            # 调试：打印完整响应结构
            logger.debug(f"API响应结构: {json.dumps(response, default=str, indent=2)}")

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

            logger.warning("无法从响应中获取有效内容，完整响应: %s", json.dumps(response, default=str))
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
        # —— 阶段1：输入验证 ——
        if not message.strip():
            return "Error: Empty message received"

        # —— 阶段2：上下文更新 ——
        # 只在程序刚启动时（上下文为空时）加载外部历史上下文
        if previous_context and user_id not in self.chat_contexts:
            logger.info(f"程序启动初始化：为用户 {user_id} 加载历史上下文，共 {len(previous_context)} 条消息")
            # 确保上下文只包含当前用户的历史信息
            self.chat_contexts[user_id] = previous_context.copy()

        # 添加当前消息到上下文
        self._manage_context(user_id, message)

        # —— 阶段3：构建请求参数 ——
        # 时间间隔
        time_context = self._build_time_context(user_id)
        
        # 获取当前时间并格式化
        now = datetime.datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekdays[now.weekday()]
        current_time_str = now.strftime(f"%Y年%m月%d日 %H:%M:%S {weekday}")
        # 获取农历日期
        try:
            lunar_date = ZhDate.from_datetime(now)
            lunar_date_str = lunar_date.chinese() # 这会生成类似 "甲辰龙年腊月廿三" 的字符串
        except Exception as e:
            logger.error(f"获取农历日期失败: {str(e)}")
            lunar_date_str = "未知" # 如果失败则提供一个默认值        
        time_prompt = f"当前时间是 {current_time_str}，{lunar_date_str}。你必须根据当前时间来生成你的回复内容。 {time_context} ，你的活动要符合当前时间段"
        
        # 读取基础Prompt
        try:
            # 从当前文件位置(llm_service.py)向上导航到项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))  # src/services/ai
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))  # 项目根目录
            base_prompt_path = os.path.join(project_root, "src", "base", "base.md")

            with open(base_prompt_path, "r", encoding="utf-8") as f:
                base_content = f.read()
        except Exception as e:
            logger.error(f"基础Prompt文件读取失败: {str(e)}")
            base_content = ""

        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # 项目根目录
            worldview_path = os.path.join(project_root, "src", "base", "worldview.md")
            with open(worldview_path, "r", encoding="utf-8") as f:
                worldview_content = f.read()
        except FileNotFoundError as e:
            logger.error(f"世界观文件缺失: {str(e)}")
        except Exception as e:
            logger.error(f"加载世界观时出现异常: {str(e)}")
            worldview_content = ""

        # 构建系统提示词: base + 世界观 + 核心记忆 + 人设
        if not worldview_content and not core_memory:
            character_prompt = f"{base_content}\n\n你所扮演的角色介绍如下：\n{system_prompt}"
        elif worldview_content and not core_memory:
            character_prompt = f"{base_content}\n\n你所饰演的角色所处世界的世界观为：\n{worldview_content}\n\n你所扮演的角色介绍如下：\n{system_prompt}"
        elif not worldview_content and core_memory:
            character_prompt = f"{base_content}\n\n你所饰演角色所具备的核心记忆为：\n{core_memory}\n\n你所扮演的角色介绍如下：\n{system_prompt}"
        else: character_prompt = f"{base_content}\n\n你所饰演的角色所处世界的世界观为：\n{worldview_content}你所饰演角色所具备的核心记忆为：\n{core_memory}\n\n你所扮演的角色介绍如下：\n{system_prompt}"

        # 构建最终的系统提示词，将时间信息放在最前面
        final_prompt = f"{time_prompt}\n\n{character_prompt}"
        logger.debug("最终提示词结构：当前时间 + (base.md + 世界观 + 记忆 + 人设)")

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

        # —— 阶段4：执行API请求（带重试机制和自动模型切换）——
        max_retries = 3
        last_error = None
        current_model = self.config["model"]
        models_tried = []
        
        logger.info(f"准备发送API请求 - 用户: {user_id}, 模型: {self.config['model']}")

        for attempt in range(max_retries):
            try:
                models_tried.append(current_model)
                if is_ollama:
                    # Ollama API 格式
                    request_config = {
                        "model": current_model.split('/')[-1],  # 移除路径前缀
                        "messages": [ollama_message],  # 将消息包装在列表中
                        "stream": False,
                        "options": {
                            "temperature": self.config["temperature"],
                            "max_tokens": self.config["max_token"]
                        }
                    }

                    # 使用 requests 库向 Ollama API 发送 POST 请求
                    # 创建 Updater 实例获取版本信息
                    updater = Updater()
                    version = updater.get_current_version()
                    version_identifier = updater.get_version_identifier()

                    response = requests.post(
                        f"{str(self.client.base_url)}",
                        json=request_config,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": version_identifier,
                            "X-KouriChat-Version": version
                        }
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
                    else:
                        raise ValueError(f"错误的API响应结构: {json.dumps(response_data, default=str)}")

                else:
                    # 标准 OpenAI 格式
                    request_config = {
                        "model": current_model,  # 模型名称
                        "messages": messages,  # 消息列表
                        "temperature": self.config["temperature"],  # 温度参数
                        "max_tokens": self.config["max_token"],  # 最大 token 数
                        "frequency_penalty": 0.2  # 频率惩罚参数
                    }

                    # 使用 OpenAI 客户端发送请求
                    response = self.client.chat.completions.create(**request_config)

                    # 验证 API 响应结构
                    if not self._validate_response(response.model_dump()):
                        raise ValueError(f"错误的API响应结构: {json.dumps(response.model_dump(), default=str)}")

                    # 获取原始内容
                    raw_content = response.choices[0].message.content

                # 清理响应内容
                clean_content = self._sanitize_response(raw_content)
                # 过滤思考内容
                filtered_content = self._filter_thinking_content(clean_content)

                # 检查响应内容是否为错误消息
                if filtered_content.strip().lower().startswith("error"):
                    raise ValueError(f"错误响应: {filtered_content}")

                # 成功获取有效响应，更新上下文并返回
                self._manage_context(user_id, filtered_content, "assistant")
                # 如果使用了备用模型，记录日志
                if current_model != self.original_model:
                    logger.info(f"使用备用模型 {current_model} 成功获取响应")
                return filtered_content or ""

            except Exception as e:
                last_error = f"Error: {str(e)}"
                logger.warning(f"模型 {current_model} API请求失败 (尝试 {attempt+1}/{max_retries}): {str(e)}")

                # 如果启用了自动切换模型且这不是最后一次尝试
                if self.config["auto_model_switch"] and attempt < max_retries - 1:
                    next_model = self._get_next_model(current_model)
                    if next_model and next_model not in models_tried:
                        logger.info(f"自动切换到模型: {next_model}")
                        current_model = next_model
                        continue

                # 如果这不是最后一次尝试，则继续
                if attempt < max_retries - 1:
                    continue

        # 所有重试都失败后，记录最终错误并返回
        if self.config.get("auto_model_switch", False):
            logger.error(f"所有模型 {models_tried} 均失败: {last_error}")
        else:
            logger.error(f"所有重试尝试均失败: {last_error}")
        return last_error

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
            **kwargs: 额外的参数配置，包括 model、temperature 等

        Returns:
            str: AI的回复内容
        """
        try:
            # 使用传入的model参数，如果没有则使用默认模型
            model = kwargs.get('model', self.config["model"])
            logger.info(f"使用模型: {model} 发送聊天请求")

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=kwargs.get('temperature', self.config["temperature"]),
                max_tokens=self.config["max_token"]
            )

            if not self._validate_response(response.model_dump()):
                error_msg = f"错误的API响应结构: {json.dumps(response.model_dump(), default=str)}"
                logger.error(error_msg)
                return f"Error: {error_msg}"

            raw_content = response.choices[0].message.content
            # 清理和过滤响应内容
            clean_content = self._sanitize_response(raw_content)
            filtered_content = self._filter_thinking_content(clean_content)

            return filtered_content or ""

        except Exception as e:
            logger.error(f"Chat completion failed: {str(e)}")
            return f"Error: {str(e)}"

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

    def get_config(self) -> Dict:
        """
        获取当前LLM服务的配置参数
        方便外部服务（如记忆服务）获取最新配置

        Returns:
            Dict: 包含当前配置的字典
        """
        return self.config.copy()  # 返回配置的副本以防止外部修改
    
    def _get_available_models(self) -> List[str]:
        """
        通过API动态获取当前提供商支持的聊天模型列表
        
        Returns:
            List[str]: 可用的聊天模型列表
        """
        try:
            base_url = str(self.client.base_url).lower()
            
            # 特殊处理Ollama
            if 'localhost:11434' in base_url:
                return [model['id'] for model in self.ollama_models]
            
            # 使用OpenAI标准的v1/models端点获取模型列表
            logger.debug(f"正在从 {self.client.base_url} 获取可用模型列表...")
            
            try:
                # 使用OpenAI客户端获取模型列表
                models_response = self.client.models.list()
                
                # 过滤出聊天模型
                chat_models = []
                for model in models_response.data:
                    model_id = model.id
                    
                    # 过滤聊天模型的关键词
                    chat_keywords = [
                        'chat', 'gpt', 'claude', 'deepseek', 'kourichat', 'grok',
                        'llama', 'mistral', 'qwen', 'yi', 'baichuan'
                    ]
                    
                    # 排除非聊天模型的关键词
                    exclude_keywords = [
                        'embedding', 'whisper', 'tts', 'dall-e', 'vision',
                        'moderation', 'edit', 'completion', 'instruct',
                        'image', 'search', 'weblens', 'tool'
                    ]
                    
                    model_lower = model_id.lower()
                    
                    # 检查是否包含聊天关键词且不包含排除关键词
                    is_chat_model = (
                        any(keyword in model_lower for keyword in chat_keywords) and
                        not any(keyword in model_lower for keyword in exclude_keywords)
                    )
                    
                    if is_chat_model:
                        chat_models.append(model_id)
                
                if chat_models:
                    # 对模型进行优先级排序，DeepSeek系列优先
                    sorted_models = self._sort_models_by_priority(chat_models)
                    logger.debug(f"成功获取到 {len(sorted_models)} 个聊天模型: {sorted_models}")
                    return sorted_models
                else:
                    logger.warning("未找到聊天模型，使用当前模型作为唯一选项")
                    return [self.original_model]
                    
            except Exception as api_error:
                logger.warning(f"通过API获取模型列表失败: {str(api_error)}")
                
	                # API调用失败时的后备方案：根据base_url推测可能的模型
                return self._get_fallback_models(base_url)
                
        except Exception as e:
            logger.error(f"获取可用模型列表失败: {str(e)}")
            # 最终后备方案：只返回当前模型
            return [self.original_model]
        
    def _sort_models_by_priority(self, models: List[str]) -> List[str]:
        """
        按优先级对模型进行排序
	        优先级顺序：Grok-4 > Grok-3 > Grok-2 > DeepSeek > KouriChat > Qwen > GPT > Claude > 其他
        
        Args:
            models: 原始模型列表
            
        Returns:
            List[str]: 按优先级排序后的模型列表
        """
        def get_model_priority(model_name: str) -> int:
            """获取模型的优先级数字，数字越小优先级越高"""
            model_lower = model_name.lower()
            
            # Grok系列 - 最高优先级
            if 'grok' in model_lower:
                if '4' in model_lower:
                    return 1  # Grok-4 最优先
                elif '3' in model_lower:
                    if 'fast' in model_lower:
                        return 2  # Grok-3-fast 次优先
                    else:
                        return 3  # Grok-3 第三优先
                elif '2' in model_lower:
                    return 4  # Grok-2 第四优先
                elif '1.5' in model_lower:
                    return 5  # Grok-1.5 第五优先
                else:
                    return 6  # 其他 Grok 模型
            
            # DeepSeek系列 - 第二优先级（稳定快速）
            elif 'deepseek' in model_lower:
                if 'r1' in model_lower or 'reasoner' in model_lower:
                    return 7  # DeepSeek R1/Reasoner
                elif 'v3' in model_lower:
                    return 8  # DeepSeek V3
                else:
                    return 9  # 其他 DeepSeek 模型
            
            # KouriChat系列 - 第三优先级
            elif 'kourichat' in model_lower:
                if 'r1' in model_lower:
                    return 10  # KouriChat R1
                elif 'v3' in model_lower:
                    return 11  # KouriChat V3
                else:
                    return 12  # 其他 KouriChat 模型
            
            # Qwen系列 - 第四优先级
            elif 'qwen' in model_lower:
                if 'plus' in model_lower:
                    return 13  # Qwen Plus
                elif 'turbo' in model_lower:
                    return 14  # Qwen Turbo
                else:
                    return 15  # 其他 Qwen 模型
            
            # GPT系列 - 第五优先级
            elif 'gpt' in model_lower:
                if '4o' in model_lower:
                    return 16  # GPT-4o 系列
                elif '4' in model_lower:
                    return 17  # 其他 GPT-4 系列
                elif '5' in model_lower:
                    return 18  # GPT-5 系列
                else:
                    return 19  # 其他 GPT 模型
            
            # Claude系列 - 第六优先级（速度较慢）
            elif 'claude' in model_lower:
                return 20
            
            # 其他模型 - 最低优先级
            else:
                return 21
        
        # 按优先级排序
        sorted_models = sorted(models, key=get_model_priority)
        
        logger.debug(f"模型优先级排序结果: {sorted_models}")
        return sorted_models
    
    def _get_fallback_models(self, base_url: str) -> List[str]:
        """
        当API调用失败时的后备模型列表
        
        Args:
            base_url: API基础URL
            
        Returns:
            List[str]: 后备模型列表
        """
        fallback_models = []
        if 'kourichat.com' in base_url:
            fallback_models = [
                "grok-4", "grok-3", "grok-3-fast", "grok-2", "grok-1.5", "grok",
                "deepseek-r1", "deepseek-v3", "deepseek-chat",
                "kourichat-r1", "kourichat-v3",
                "qwen-plus-latest", "qwen-turbo-latest"
            ]
        elif 'deepseek.com' in base_url:
            fallback_models = ["deepseek-reasoner", "deepseek-chat"]
        elif 'openai.com' in base_url:
            fallback_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
        elif 'api.moonshot.cn' in base_url:
            fallback_models = ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
        elif 'api.siliconflow.cn' in base_url:
            fallback_models = ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"]
        else:
            # 通用后备列表
            fallback_models = [self.original_model]

        return self._sort_models_by_priority(fallback_models)

    def _get_next_model(self, current_model: str) -> Optional[str]:
        """
        获取下一个可用的模型
        
        Args:
            current_model: 当前使用的模型
            
        Returns:
            Optional[str]: 下一个可用的模型，如果没有则返回None
        """
        if not self.available_models:
            return None

        # 如果当前模型不在可用模型列表中（比如配置了错误的模型名）
        # 直接返回第一个可用的模型
        if current_model not in self.available_models:
            logger.info(f"当前模型 '{current_model}' 不在可用模型列表中，切换到第一个可用模型")
            return self.available_models[0]

        current_index = self.available_models.index(current_model)
        next_index = (current_index + 1) % len(self.available_models)
        
        # 如果只有一个模型，返回None表示没有其他模型可用
        if len(self.available_models) == 1:
            return None
        
        # 如果循环回到当前模型，说明已经尝试了所有模型
        if next_index == current_index:
            return None
            
        return self.available_models[next_index]

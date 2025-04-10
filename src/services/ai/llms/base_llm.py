import logging
from abc import ABC, abstractmethod
from typing import Callable, List, Dict, Optional, Tuple
from logging import Logger
from .llm import online_llm
from datetime import datetime
import re
import threading


class BaseLLM(online_llm):
    """
    大模型基类，提供通用的上下文管理和响应生成功能
    """
    def __init__(
        self, 
        logger: Logger,
        model_name: str, 
        url: str, 
        api_key: str, 
        n_ctx: int, 
        temperature: float,
        max_context_messages: int = 10,  # 这里表示最大对话对数量
        system_prompt: Optional[str] = None,
        singleton: bool = True
    ):
        """
        初始化大模型基类
        
        Args:
            logger: 日志记录器
            model_name: 模型名称
            url: API地址
            api_key: API密钥
            n_ctx: 上下文长度
            temperature: 温度参数
            max_context_messages: 上下文对话对最大数量
            system_prompt: 系统提示词
            singleton: 是否为单例模式
        """
        # 检查max_context_messages类型
        if not isinstance(max_context_messages, int):
            try:
                max_context_messages = int(max_context_messages)
            except ValueError:
                logger.error("max_context_messages必须是整数类型，当前值无法转换为整数。")
                raise        
        # 预处理URL，移除末尾的斜杠
        if url and url.endswith('/'):
            url = url.rstrip('/')
            logger.info(f"BaseLLM: URL末尾斜杠已移除: {url}")
            
        super().__init__(
            model_name,
            url,
            api_key,
            n_ctx,
            temperature,
            singleton
        )
        self.logger = logger
        self.max_context_messages = max_context_messages
        self.context: List[Dict[str, str]] = []
        self._context_handler = None
        
        # 添加系统提示
        if system_prompt:
            self.context.append({"role": "system", "content": system_prompt})
            self.system_prompt = system_prompt
        else:
            self.system_prompt = None
        
        # 初始化用户上下文字典，用于管理不同用户的对话上下文
        self.user_contexts = {}
        
        # 2025-03-17 修复适配获取最近时间
        self.user_recent_chat_time = {}
        
        # 添加流式输出和打断相关的属性
        self.stream_enabled = True  # 是否启用流式输出
        self.interrupts = {}  # 用户ID -> 是否需要打断当前生成
        self.partial_responses = {}  # 用户ID -> 已生成的部分响应
        self.interrupt_lock = threading.Lock()  # 打断操作的线程锁
        
        # 用于处理二次合并的分隔符
        self.message_separator = "\n---\n"
    
    def context_handler(self, func: Callable[[str, str, str], None]):
        """
        装饰器：注册上下文处理函数
        
        Args:
            func: 处理函数，接收用户ID、用户输入和AI回复三个参数
        """
        self._context_handler = func
        return func
    
    def _build_prompt(self, current_prompt: str) -> List[Dict[str, str]]:
        """
        构建提示词，处理一些特殊的命令前缀标记
        
        Args:
            current_prompt: 当前输入的提示词
            
        Returns:
            处理后的提示词列表，包含角色和内容
        """
        try:
            # 检查是否有命令前缀（例如system:）
            commands = {
                "system:": "system",
                "assistant:": "assistant",
                "user:": "user"
            }
            
            role = "user"  # 默认角色
            content = current_prompt
            
            # 检查命令前缀
            for prefix, cmd_role in commands.items():
                if current_prompt.lower().startswith(prefix):
                    role = cmd_role
                    content = current_prompt[len(prefix):].lstrip()
                    break
                    
            # 如果是用户角色，可以添加用户ID标记以便在流式输出中识别
            if role == "user" and hasattr(self, 'current_user_id') and self.current_user_id:
                # 在消息中嵌入用户ID，以便在处理时识别
                content = f"[用户ID]{self.current_user_id}[/用户ID]\n{content}"
                    
            # 返回处理后的提示词列表
            return [(role, content)]
            
        except Exception as e:
            self.logger.error(f"构建提示词失败: {str(e)}")
            # 返回默认格式的提示词
            return [("user", current_prompt)]
    
    def _update_context(self, user_prompt: str, assistant_response: str, user_id: str = None) -> None:
        """
        更新上下文历史
        
        Args:
            user_prompt: 用户输入
            assistant_response: 助手回复
            user_id: 用户ID，默认为None表示使用默认用户
        """
        # 使用默认用户ID，如果未提供
        context_key = user_id if user_id else "default"
        
        # 确保用户上下文存在
        if context_key not in self.user_contexts:
            self.user_contexts[context_key] = []
            # 如果有系统提示词，添加到上下文
            if self.system_prompt:
                self.user_contexts[context_key].append({"role": "system", "content": self.system_prompt})
                
        # 添加新的对话到上下文
        self.user_contexts[context_key].append({"role": "user", "content": user_prompt})
        self.user_contexts[context_key].append({"role": "assistant", "content": assistant_response})
        
        # 计算当前对话对数量（不包括system prompt）
        message_count = len(self.user_contexts[context_key])
        system_offset = 1 if any(msg["role"] == "system" for msg in self.user_contexts[context_key]) else 0
        pair_count = (message_count - system_offset) // 2
        
        self.logger.debug(f"[上下文管理] 用户 {context_key} 更新后上下文总消息数: {message_count}, 对话对数: {pair_count}, 最大限制: {self.max_context_messages}")
        
        # 如果超出对话对数量限制，移除最早的对话对
        if pair_count > self.max_context_messages:
            # 计算需要移除的对话对数量
            excess_pairs = pair_count - self.max_context_messages
            # 每对包含两条消息
            excess_messages = excess_pairs * 2
            
            self.logger.warning(f"[上下文截断] 用户 {context_key} 超出限制，需要移除 {excess_pairs} 对对话（{excess_messages} 条消息）")
            
            # 保存被移除的消息用于处理
            start_idx = system_offset
            removed_messages = self.user_contexts[context_key][start_idx:start_idx+excess_messages]
            
            # 记录被移除的消息
            for idx, msg in enumerate(removed_messages):
                content_preview = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]
                self.logger.debug(f"[移除消息 {idx}] 角色: {msg['role']}, 内容: {content_preview}")
            
            # 更新上下文，保留system prompt
            if system_offset > 0:
                self.user_contexts[context_key] = [self.user_contexts[context_key][0]] + self.user_contexts[context_key][start_idx+excess_messages:]
            else:
                self.user_contexts[context_key] = self.user_contexts[context_key][excess_messages:]
            
            # 如果设置了上下文处理函数，处理被移除的消息
            if self._context_handler and removed_messages:
                # 成对处理被移除的用户输入和AI回复
                for i in range(0, len(removed_messages), 2):
                    if i+1 < len(removed_messages):
                        user_msg = removed_messages[i]["content"]
                        ai_msg = removed_messages[i+1]["content"]
                        try:
                            self._context_handler(context_key, user_msg, ai_msg)
                        except Exception as e:
                            self.logger.error(f"上下文处理函数执行失败: {str(e)}")
    
    def handle_interrupt(self, user_id: str, new_message: str) -> None:
        """
        处理用户的中断请求，保存部分生成的内容以供后续处理
        
        Args:
            user_id: 用户ID
            new_message: 用户的新消息
        """
        with self.interrupt_lock:
            # 设置中断标志
            self.interrupts[user_id] = True
            
            # 记录新消息，用于后续合并处理
            if user_id not in self.partial_responses:
                self.partial_responses[user_id] = {
                    "partial_response": "",
                    "new_messages": []
                }
            
            self.partial_responses[user_id]["new_messages"].append(new_message)
            self.logger.info(f"用户 {user_id} 的生成过程被新消息中断，已保存新消息")

    def get_merged_prompt(self, user_id: str, original_prompt: str) -> str:
        """
        获取合并了部分响应和新消息的提示词
        
        Args:
            user_id: 用户ID
            original_prompt: 原始提示词
            
        Returns:
            合并后的提示词
        """
        if user_id not in self.partial_responses:
            return original_prompt
            
        partial_data = self.partial_responses[user_id]
        partial_response = partial_data.get("partial_response", "")
        new_messages = partial_data.get("new_messages", [])
        
        if not partial_response or not new_messages:
            return original_prompt
            
        # 合并部分响应和所有新消息
        merged_prompt = f"""以下是一次未完成的回复和用户的新消息，请综合考虑所有内容后给出完整回复：

AI助手之前的回复(未完成): 
{partial_response}

用户的新消息: 
{self.message_separator.join(new_messages)}

请综合考虑上述对话，生成一个完整且连贯的回复。
"""
        self.logger.info(f"为用户 {user_id} 创建了合并后的提示词，包含 {len(new_messages)} 条新消息和部分响应")
        
        # 清除已处理的数据
        self.partial_responses[user_id] = {
            "partial_response": "",
            "new_messages": []
        }
        
        return merged_prompt

    def check_and_clear_interrupt(self, user_id: str) -> bool:
        """
        检查并清除用户的中断标志
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否有中断
        """
        with self.interrupt_lock:
            interrupted = self.interrupts.get(user_id, False)
            if interrupted:
                self.interrupts[user_id] = False
            return interrupted

    def add_partial_response(self, user_id: str, content: str) -> None:
        """
        添加部分生成的响应
        
        Args:
            user_id: 用户ID
            content: 部分响应内容
        """
        with self.interrupt_lock:
            if user_id not in self.partial_responses:
                self.partial_responses[user_id] = {
                    "partial_response": "",
                    "new_messages": []
                }
            self.partial_responses[user_id]["partial_response"] = content

    def handel_prompt(self, prompt: str, user_id: str = None) -> str:
        """
        处理聊天提示，构建请求上下文并调用API获取响应
        
        Args:
            prompt: 用户提交的提示文本
            user_id: 用户ID，默认为None表示使用默认用户
        
        Returns:
            API响应文本
        """
        try:
            # 设置默认用户ID
            if user_id is None:
                user_id = "default"
                
            # 存储当前用户ID，用于_build_prompt方法使用
            self.current_user_id = user_id
                
            # 检查是否需要处理之前的中断
            merged_prompt = prompt
            if user_id in self.partial_responses and self.partial_responses[user_id].get("new_messages"):
                merged_prompt = self.get_merged_prompt(user_id, prompt)
                self.logger.info(f"检测到用户 {user_id} 有未处理的中断，使用合并后的提示词")
            
            # 将用户ID添加到上下文键中
            context_key = user_id
            
            # 构建或获取用户上下文
            if context_key not in self.user_contexts:
                self.user_contexts[context_key] = []
                # 添加系统提示词（如果存在）
                if self.system_prompt:
                    self.user_contexts[context_key].append({"role": "system", "content": self.system_prompt})
                
            # 构建完整提示（处理命令前缀标记）
            processed_prompt = self._build_prompt(merged_prompt)
            
            # 复制一份当前上下文用于API请求
            current_context = self.user_contexts[context_key].copy()
            
            # 添加用户当前提问
            for role, content in processed_prompt:
                current_context.append({"role": role, "content": content})
            
            # 日志记录当前上下文
            self.logger.debug(f"[API请求] 用户: {user_id}, 提示: {merged_prompt[:100]}...")
            self.logger.debug(f"[上下文] 当前上下文消息数: {len(current_context)}")
            
            for idx, msg in enumerate(current_context):
                content_preview = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
                self.logger.debug(f"[上下文消息 {idx}] 角色: {msg['role']}, 内容: {content_preview}")
            
            # 添加重试逻辑
            max_retries = 3
            retry_count = 0
            response = None
            last_error = None
            
            while retry_count < max_retries:
                try:
                    # 检查是否有中断请求
                    if self.check_and_clear_interrupt(user_id):
                        self.logger.warning(f"用户 {user_id} 的生成过程被新消息中断")
                        # 返回特殊标记，告知调用方这是一个中断，不应直接使用此响应
                        return "__INTERRUPTED__"
                    
                    # 这里需要子类实现具体的API调用逻辑
                    response = self.generate_response(current_context)
                    
                    # 检查返回是否为错误信息
                    if any(error_text in response for error_text in ["API调用失败", "Connection error", "服务暂时不可用"]):
                        self.logger.warning(f"API返回错误信息: {response[:100]}...")
                        last_error = response
                        retry_count += 1
                        if retry_count < max_retries:
                            self.logger.warning(f"进行第 {retry_count+1} 次重试...")
                            continue
                    else:
                        # 成功获取响应，跳出循环
                        break
                        
                except Exception as e:
                    self.logger.error(f"API调用错误: {str(e)}")
                    last_error = str(e)
                    retry_count += 1
                    if retry_count < max_retries:
                        self.logger.warning(f"进行第 {retry_count+1} 次重试...")
                        continue
                    else:
                        response = f"API调用失败: {str(e)}"
                        break
            
            # 如果所有重试都失败，返回最后的错误
            if response is None and last_error:
                response = f"多次尝试后仍然失败: {last_error}"
            
            # 后处理：移除可能的完全重复内容
            if response and not any(error_text in response for error_text in ["API调用失败", "Connection error", "服务暂时不可用", "多次尝试后仍然失败"]):
                original_response_len = len(response)
                response = self._remove_immediate_duplicate(response)
                if len(response) != original_response_len:
                    self.logger.warning(f"检测到并移除了响应中的重复内容。原始长度: {original_response_len}, 清理后长度: {len(response)}")
            
            # 只有在成功获取有效响应时才更新上下文
            if not any(error_text in response for error_text in ["API调用失败", "Connection error", "服务暂时不可用", "多次尝试后仍然失败"]):
                # 使用_update_context方法更新上下文
                self._update_context(prompt, response, user_id)
                
                # 关键修复点：立即调用上下文管理，确保每次对话后检查并截断上下文
                self.logger.debug(f"[上下文管理] 开始管理上下文长度，最大允许对话对数: {self.max_context_messages}")
                self._manage_context_length(context_key)
                
                # 打印更新后的上下文信息
                post_manage_context = self.user_contexts[context_key]
                self.logger.debug(f"[上下文管理后] 更新后的上下文消息数: {len(post_manage_context)}")
            else:
                self.logger.warning(f"检测到API错误响应，不更新上下文: {response[:100]}...")
            
            self.logger.info(f"[API响应] 最终回复: {response[:150]}...")
            
            # 更新最近交互时间
            if hasattr(self, 'user_recent_chat_time'):
                self.user_recent_chat_time[user_id if user_id else "default"] = datetime.now()
                
            return response
            
        except Exception as e:
            self.logger.error(f"处理提示时出错: {str(e)}")
            return f"处理您的请求时出现错误: {str(e)}"
    
    def _remove_immediate_duplicate(self, text: str) -> str:
        """简单的后处理，移除形如 'ABAB' 变成 'AB' 的完全重复。"""
        n = len(text)
        if n < 2:
            return text
        # 检查字符串是否由两个相同的连续部分组成
        if n % 2 == 0:
            half = n // 2
            if text[:half] == text[half:]:
                self.logger.info(f"检测到响应内容完全重复，已进行清理。")
                return text[:half]
        # 未来可以根据需要添加更复杂的重复检测逻辑，例如检测部分重复或基于语义的重复
        return text
    
    def _manage_context_length(self, context_key):
        """管理特定用户的上下文长度"""
        if context_key not in self.user_contexts:
            return
        
        context = self.user_contexts[context_key]
        
        # 计算当前对话对数量（不包括system prompt）
        message_count = len(context)
        system_offset = 1 if any(msg["role"] == "system" for msg in context) else 0
        pair_count = (message_count - system_offset) // 2
        
        self.logger.warning(f"[上下文管理详情] 用户 {context_key} 的上下文总消息数: {message_count}, 对话对数: {pair_count}, 最大限制: {self.max_context_messages}")
        
        # 如果超出对话对数量限制，进行智能上下文管理
        if pair_count > self.max_context_messages:
            # 1. 评分函数 - 计算每个对话对的重要性
            def score_conversation_pair(user_msg, ai_msg):
                score = 0
                
                # 关键词重要性
                important_keywords = ['在实验室', '在家', '睡觉', '工作', '时间', '地点', 
                                   '今天', '昨天', '明天', '早上', '下午', '晚上']
                for keyword in important_keywords:
                    if keyword in user_msg["content"] or keyword in ai_msg["content"]:
                        score += 10
                
                # 时间相关性
                time_patterns = [r'昨[天晚]', r'今[天晚]', r'(\d+)点', 
                               r'早上|上午|中午|下午|晚上']
                for pattern in time_patterns:
                    if re.search(pattern, user_msg["content"]) or re.search(pattern, ai_msg["content"]):
                        score += 15
                
                # 上下文转换标记
                if "--- 场景转换 ---" in user_msg["content"]:
                    score += 20
                
                # 问答对的完整性
                if "?" in user_msg["content"] or "？" in user_msg["content"]:
                    score += 5
                
                # 消息长度因素（较短的对话可能不太重要）
                msg_length = len(user_msg["content"]) + len(ai_msg["content"])
                if msg_length < 10:
                    score -= 5
                elif msg_length > 100:
                    score += 5
                
                return score
            
            # 2. 对对话对进行评分和排序
            conversation_pairs = []
            for i in range(system_offset, len(context), 2):
                if i + 1 < len(context):
                    user_msg = context[i]
                    ai_msg = context[i + 1]
                    score = score_conversation_pair(user_msg, ai_msg)
                    conversation_pairs.append({
                        'user_msg': user_msg,
                        'ai_msg': ai_msg,
                        'score': score,
                        'index': i
                    })
            
            # 按分数排序
            conversation_pairs.sort(key=lambda x: x['score'], reverse=True)
            
            # 3. 保留最重要的对话对
            retain_pairs = conversation_pairs[:self.max_context_messages]
            retain_pairs.sort(key=lambda x: x['index'])  # 恢复原始顺序
            
            # 4. 构建新的上下文
            new_context = []
            if system_offset > 0:
                new_context.append(context[0])  # 保留system prompt
            
            for pair in retain_pairs:
                new_context.append(pair['user_msg'])
                new_context.append(pair['ai_msg'])
            
            # 5. 处理被移除的对话对
            removed_pairs = conversation_pairs[self.max_context_messages:]
            if removed_pairs and self._context_handler:
                for pair in removed_pairs:
                    try:
                        self._context_handler(
                            context_key,
                            pair['user_msg']['content'],
                            pair['ai_msg']['content']
                        )
                    except Exception as e:
                        self.logger.error(f"处理移除的上下文对话失败: {str(e)}")
            
            # 6. 更新上下文
            self.user_contexts[context_key] = new_context
            self.logger.warning(f"[上下文优化完成] 保留了 {len(retain_pairs)} 对最重要的对话")
            
            # 7. 添加上下文摘要
            summary = self._generate_context_summary(new_context)
            if summary:
                self.user_contexts[context_key].insert(
                    system_offset,
                    {"role": "system", "content": f"当前对话要点：{summary}"}
                )
    
    def _generate_context_summary(self, context):
        """生成上下文摘要"""
        try:
            # 提取关键信息
            key_info = {
                'location': None,
                'time': None,
                'activity': None
            }
            
            # 定义模式
            patterns = {
                'location': r'在(实验室|家|学校|公司|办公室)',
                'time': r'([早中下晚][上午饭]|凌晨|\d+点)',
                'activity': r'(工作|学习|睡觉|休息|实验|写代码|看书)'
            }
            
            # 从最近的消息开始分析
            for msg in reversed(context):
                if msg['role'] != 'system':
                    content = msg['content']
                    
                    # 提取位置信息
                    if not key_info['location']:
                        location_match = re.search(patterns['location'], content)
                        if location_match:
                            key_info['location'] = location_match.group()
                    
                    # 提取时间信息
                    if not key_info['time']:
                        time_match = re.search(patterns['time'], content)
                        if time_match:
                            key_info['time'] = time_match.group()
                    
                    # 提取活动信息
                    if not key_info['activity']:
                        activity_match = re.search(patterns['activity'], content)
                        if activity_match:
                            key_info['activity'] = activity_match.group()
                    
                    # 如果所有信息都已获取，退出循环
                    if all(key_info.values()):
                        break
            
            # 生成摘要
            summary_parts = []
            if key_info['time']:
                summary_parts.append(f"时间：{key_info['time']}")
            if key_info['location']:
                summary_parts.append(f"地点：{key_info['location']}")
            if key_info['activity']:
                summary_parts.append(f"活动：{key_info['activity']}")
            
            return '，'.join(summary_parts) if summary_parts else None
        
        except Exception as e:
            self.logger.error(f"生成上下文摘要失败: {str(e)}")
            return None
    
    def generate_response(self, messages: List[Dict[str, str]]) -> str:
        """
        调用API生成回复，需要在子类中实现
        
        Args:
            messages: 完整的消息列表
            
        Returns:
            模型生成的回复
        """
        raise NotImplementedError("子类必须实现_generate_response方法")

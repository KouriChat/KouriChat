import logging
from abc import ABC, abstractmethod
from typing import Callable, List, Dict, Optional, Tuple
from logging import Logger
from .llm import online_llm
from datetime import datetime
import re


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
        
        # 2025-03-17 修复适配获取最近时间
        self.user_recent_chat_time = {}
    
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
        构建完整的提示消息列表
        
        Args:
            current_prompt: 当前用户输入的提示
            
        Returns:
            包含上下文历史和当前提示的消息列表
        """
        messages = self.context.copy()
        messages.append({"role": "user", "content": current_prompt})
        
        # 添加详细日志
        self.logger.debug(f"[上下文跟踪] 构建提示，当前上下文消息数: {len(messages)}")
        for idx, msg in enumerate(messages):
            # 限制长度以免日志过长
            content_preview = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            self.logger.debug(f"[上下文消息 {idx}] 角色: {msg['role']}, 内容: {content_preview}")
        
        return messages
    
    def _update_context(self, user_prompt: str, assistant_response: str) -> None:
        """
        更新上下文历史
        
        Args:
            user_prompt: 用户输入
            assistant_response: 助手回复
        """
        # 添加新的对话到上下文
        self.context.append({"role": "user", "content": user_prompt})
        self.context.append({"role": "assistant", "content": assistant_response})
        
        # 计算当前对话对数量（不包括system prompt）
        message_count = len(self.context)
        system_offset = 1 if self.system_prompt else 0
        pair_count = (message_count - system_offset) // 2
        
        self.logger.debug(f"[上下文管理] 更新后上下文总消息数: {message_count}, 对话对数: {pair_count}, 最大限制: {self.max_context_messages}")
        
        # 如果超出对话对数量限制，移除最早的对话对
        if pair_count > self.max_context_messages:
            # 计算需要移除的对话对数量
            excess_pairs = pair_count - self.max_context_messages
            # 每对包含两条消息
            excess_messages = excess_pairs * 2
            
            self.logger.warning(f"[上下文截断] 超出限制，需要移除 {excess_pairs} 对对话（{excess_messages} 条消息）")
            
            # 保存被移除的消息用于处理
            start_idx = system_offset
            removed_messages = self.context[start_idx:start_idx+excess_messages]
            
            # 记录被移除的消息
            for idx, msg in enumerate(removed_messages):
                content_preview = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]
                self.logger.debug(f"[移除消息 {idx}] 角色: {msg['role']}, 内容: {content_preview}")
            
            # 更新上下文，保留system prompt
            if self.system_prompt:
                self.context = [self.context[0]] + self.context[start_idx+excess_messages:]
            else:
                self.context = self.context[excess_messages:]
            
            # 如果设置了上下文处理函数，处理被移除的消息
            if self._context_handler and removed_messages:
                # 成对处理被移除的用户输入和AI回复
                for i in range(0, len(removed_messages), 2):
                    if i+1 < len(removed_messages):
                        user_msg = removed_messages[i]["content"]
                        ai_msg = removed_messages[i+1]["content"]
                        try:
                            self._context_handler(user_msg, ai_msg)
                        except Exception as e:
                            self.logger.error(f"上下文处理函数执行失败: {str(e)}")
    
    def handel_prompt(self, prompt: str, user_id: str = None) -> str:
        """
        处理用户输入并返回响应
        
        Args:
            prompt: 用户输入
            user_id: 用户ID
            
        Returns:
            str: 助手回复
        """
        try:
            self.logger.debug(f"[处理提示] 收到输入: {prompt}")
            
            # 使用用户ID构建上下文键
            context_key = user_id if user_id else "default"
            
            # 如果没有为此用户初始化上下文，则创建
            if not hasattr(self, 'user_contexts'):
                self.user_contexts = {}
            
            # 获取或创建此用户的上下文
            if context_key not in self.user_contexts:
                # 新用户，初始化上下文
                if self.system_prompt:
                    self.user_contexts[context_key] = [{"role": "system", "content": self.system_prompt}]
                else:
                    self.user_contexts[context_key] = []
            
            # 获取当前用户的上下文
            current_context = self.user_contexts[context_key].copy()
            
            # 添加用户请求前的识别标记，帮助模型区分新旧内容
            prompt_with_marker = f"[当前用户问题] {prompt}"
            current_context.append({"role": "user", "content": prompt_with_marker})
            
            # 构建完整提示
            self.logger.debug(f"[上下文跟踪] 构建提示，当前上下文消息数: {len(current_context)}")
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
                # 更新用户上下文，用原始prompt而不是带标记的
                self.user_contexts[context_key].append({"role": "user", "content": prompt})
                self.user_contexts[context_key].append({"role": "assistant", "content": response})
                
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

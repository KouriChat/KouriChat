"""
消息处理模块
负责处理聊天消息，包括:
- 消息队列管理
- 消息分发处理
- API响应处理
- 多媒体消息处理
- 对话结束处理
"""

from datetime import datetime
import logging
import threading
import time
from wxauto import WeChat
import random
import os
from src.services.ai.llm_service import LLMService
from src.config import config
import re
import jieba
import asyncio

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')


class MessageHandler:
    def __init__(self, root_dir, llm: LLMService, robot_name, prompt_content, image_handler, emoji_handler, voice_handler, memory_handler, wx=None, is_debug=False, is_qq=False):
        self.root_dir = root_dir
        self.robot_name = robot_name
        self.prompt_content = prompt_content
        self.debug = is_debug
        # 添加消息缓存相关属性
        self.message_cache = {}  # 用户消息缓存
        self.last_message_time = {}  # 用户最后发送消息的时间
        self.message_timer = {}  # 用户消息处理定时器
        # 使用 DeepSeekAI 替换直接的 OpenAI 客户端
        self.deepseek = llm
        # 消息队列相关
        self.user_queues = {}
        self.queue_lock = threading.Lock()
        self.chat_contexts = {}

        # 微信实例
        self.wx = wx
        self.is_debug = is_debug
        self.is_qq = is_qq

        # 添加 handlers
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler
        self.memory_handler = memory_handler
        
        # 从配置文件获取角色名称
        try:
            # 导入所需的类
            from src.handlers.memories.group_chat_memory import GroupChatMemory
            from src.config import config
            
            # 从 AVATAR_DIR 获取角色名称
            avatar_dir = config.behavior.context.avatar_dir
            if not avatar_dir:
                logger.warning("未找到角色目录配置，使用默认名称")
                avatar_name = "default"
            else:
                # 获取目录的最后一部分作为角色名称
                avatar_name = os.path.basename(avatar_dir)
                
            # 清理角色名称，只保留有效字符
            safe_avatar_name = "".join(c for c in avatar_name if c.isalnum() or c in (' ', '-', '_'))
            if not safe_avatar_name:
                safe_avatar_name = "default"
                
            # 从配置文件中获取监听列表
            try:
                # 尝试通过属性方式访问
                try:
                    listen_list = config.categories.user_settings.settings.listen_list.value
                except AttributeError:
                    # 备选方案：当属性访问失败时，尝试字典方式访问
                    listen_list = config.categories.get("user_settings", {}).get("settings", {}).get("listen_list", {}).get("value", [])
                
                if not listen_list:
                    logger.warning("配置文件中的 listen_list 为空，使用空列表")
                    listen_list = []
                else:
                    logger.info(f"从配置文件读取到监听列表: {listen_list}")
            except Exception as e:
                logger.warning(f"无法从配置文件读取 listen_list: {str(e)}，使用空列表")
                listen_list = []
            
            group_chats = []
            
            # 如果有微信实例，检查每个监听对象是否为群聊
            if wx and listen_list:
                for chat_id in listen_list:
                    try:
                        # 使用微信API检查是否为群聊
                        if wx.GetWeChatWindow(chat_id):
                            is_group = wx.IsGroupChat(chat_id)
                            if is_group:
                                group_chats.append(chat_id)
                                logger.info(f"识别到群聊: {chat_id}")
                    except Exception as e:
                        logger.error(f"检查群聊状态失败: {chat_id}, 错误: {str(e)}")
            
            # 添加群聊记忆处理器
            self.group_chat_memory = GroupChatMemory(
                root_dir=root_dir,
                avatar_name=safe_avatar_name,
                group_chats=group_chats,  # 传入已识别的群聊列表
                api_wrapper=memory_handler.api_wrapper if hasattr(memory_handler, 'api_wrapper') and memory_handler is not None else None
            )
            
        except Exception as e:
            logger.error(f"初始化群聊记忆失败: {str(e)}")
            # 导入 GroupChatMemory 类（确保在这里也能访问到）
            from src.handlers.memories.group_chat_memory import GroupChatMemory
            # 使用默认值初始化
            self.group_chat_memory = GroupChatMemory(
                root_dir=root_dir, 
                avatar_name="default", 
                group_chats=[],
                api_wrapper=memory_handler.api_wrapper if hasattr(memory_handler, 'api_wrapper') else None
            )
        
        # 添加群聊消息处理队列
        self.group_message_queues = {}
        self.group_queue_lock = threading.Lock()
        self.at_message_timestamps = {}  # 存储@消息的时间戳
        
        self.unanswered_counters = {}
        self.unanswered_timers = {}
        self.last_reply_time = {}  # 添加last_reply_time属性跟踪最后回复时间
        self.MAX_MESSAGE_LENGTH = 500

        # 初始化群聊@消息缓存
        self.group_at_cache = {}  # 群聊@消息缓存，格式: {group_id: [{'sender_name': name, 'content': content, 'timestamp': time}, ...]}
        self.group_at_timer = {}  # 群聊@消息定时器

        logger.info(f"消息处理器初始化完成，机器人名称：{self.robot_name}")

    def get_api_response(self, message: str, user_id: str, group_id: str = None, sender_name: str = None) -> str:
        """获取API回复"""
        try:
            # 使用正确的属性名和方法名
            if not hasattr(self, 'deepseek') or self.deepseek is None:
                logger.error("LLM服务未初始化，无法生成回复")
                return "系统错误：LLM服务未初始化"
            
            # 使用正确的属性名称调用方法
            try:
                # 修改：检查URL末尾是否有斜杠，并记录日志
                if hasattr(self.deepseek.llm, 'url') and self.deepseek.llm.url.endswith('/'):
                    # 尝试在本地临时修复URL
                    fixed_url = self.deepseek.llm.url.rstrip('/')
                    self.deepseek.llm.url = fixed_url
                
                # 调用API获取响应
                response = self.deepseek.llm.handel_prompt(message, user_id)
                
                # 简化API响应日志，只记录响应长度
                if response:
                    response_length = len(response)
                    # 只记录一次响应长度，避免重复日志
                    logger.info(f"API响应: {response_length}字符")
                else:
                    logger.error("收到空响应")
                
                # 增加异常检测，避免将错误信息存入记忆
                if response and (
                    "API调用失败" in response or 
                    "Connection error" in response or
                    "服务暂时不可用" in response or
                    "Error:" in response or
                    "错误:" in response or
                    "认证错误" in response
                ):
                    logger.error(f"API调用返回错误: {response}")
                    
                    # 增加错误类型的分类
                    if "Connection error" in response or "连接错误" in response:
                        logger.error("网络连接错误 - 请检查网络连接和API地址配置")
                        return f"抱歉，我暂时无法连接到API服务器。请检查网络连接和API地址配置。"
                    
                    elif "认证错误" in response or "API密钥" in response:
                        logger.error("API认证错误 - 请检查API密钥是否正确")
                        return f"抱歉，API认证失败。请检查API密钥配置。"
                    
                    elif "模型" in response and ("错误" in response or "不存在" in response):
                        logger.error("模型错误 - 模型名称可能不正确或不可用")
                        return f"抱歉，无法使用指定的AI模型。请检查模型名称配置。"
                    
                    else:
                        return f"抱歉，我暂时无法回应。错误信息：{response}"
                    
                return response
                
            except Exception as api_error:
                error_msg = str(api_error)
                logger.error(f"API调用异常: {error_msg}")
                
                # 增加异常处理的详细分类
                if "Connection" in error_msg or "connect" in error_msg.lower():
                    logger.error(f"网络连接错误 - 请检查网络连接和API地址")
                    return f"API调用失败: 无法连接到服务器。请检查网络连接和API地址配置。"
                
                elif "authenticate" in error_msg.lower() or "authorization" in error_msg.lower() or "auth" in error_msg.lower():
                    logger.error(f"API认证错误 - 请检查API密钥是否正确")
                    return f"API调用失败: 认证错误。请检查API密钥配置。"
                
                elif "not found" in error_msg.lower() or "404" in error_msg:
                    logger.error(f"API资源不存在 - 请检查API地址和路径是否正确")
                    return f"API调用失败: 请求的资源不存在。请检查API地址和路径。"
                
                else:
                    return f"API调用出错：{error_msg}"
                
        except Exception as e:
            logger.error(f"获取API回复失败: {str(e)}")
            # 降级处理：使用简化的提示
            try:
                return f"抱歉，我暂时无法回应，请稍后再试。(错误: {str(e)[:50]}...)"
            except Exception as fallback_error:
                logger.error(f"降级处理也失败: {str(fallback_error)}")
                return f"服务暂时不可用，请稍后重试。"

    def handle_user_message(self, content: str, chat_id: str, sender_name: str,
                            username: str, is_group: bool = False, is_image_recognition: bool = False, 
                            is_self_message: bool = False, is_at: bool = False):
        """统一的消息处理入口"""
        try:
            # 验证并修正用户ID
            if not username or username == "System":
                username = chat_id.split('@')[0] if '@' in chat_id else chat_id
                if username == "filehelper":
                    username = "FileHelper"
                sender_name = sender_name or username

            # 如果是自己发送的消息并且是图片或表情包，直接跳过处理
            if is_self_message and (content.endswith('.jpg') or content.endswith('.png') or content.endswith('.gif')):
                logger.info(f"检测到自己发送的图片或表情包，跳过保存和识别: {content}")
                return None

            # 检查是否是群聊消息
            if is_group:
                logger.info(f"处理群聊消息: 群ID={chat_id}, 发送者={sender_name}, 内容={content[:30]}...")
                # 传递is_at参数
                return self._handle_group_message(content, chat_id, sender_name, username, is_at)

            # 处理私聊消息的逻辑保持不变
            actual_content = self._clean_message_content(content)
            logger.info(f"收到私聊消息: {actual_content}")
            
            if not hasattr(self, '_last_message_times'):
                self._last_message_times = {}
            self._last_message_times[username] = datetime.now()

            if is_self_message:
                self._send_self_message(content, chat_id)
                return None

            content_length = len(actual_content)
            
            should_cache = True
            if should_cache:
                return self._cache_message(content, chat_id, sender_name, username, is_group, is_image_recognition)
            
            return self._handle_uncached_message(content, chat_id, sender_name, username, is_group, is_image_recognition)

        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return None

    def _handle_group_message(self, content: str, group_id: str, sender_name: str, username: str, is_at: bool = False):
        """处理群聊消息"""
        try:
            # 优先使用传入的is_at参数，如果main.py已经正确检测并传入
            is_at_from_param = is_at
            
            # 检查是否包含引用消息
            quoted_content = None
            quoted_sender = None
            # 微信引用消息格式通常是: "引用 xxx 的消息"或"回复 xxx 的消息"
            quote_match = re.search(r'(?:引用|回复)\s+([^\s]+)\s+的(?:消息)?[:：]?\s*(.+?)(?=\n|$)', content)
            if quote_match and is_at_from_param:
                quoted_sender = quote_match.group(1)
                quoted_content = quote_match.group(2).strip()
                logger.info(f"检测到引用消息 - 引用者: {quoted_sender}, 内容: {quoted_content}")
                # 从原始消息中移除引用部分
                content = re.sub(r'(?:引用|回复)\s+[^\s]+\s+的(?:消息)?[:：]?\s*.+?(?=\n|$)', '', content).strip()
            
            # 备用检测：如果传入参数为False，再尝试本地检测
            if not is_at_from_param:
                # 检查是否@机器人 - 在消息清理前确定
                # 常见的空格字符：普通空格、不间断空格、零宽空格、特殊的微信空格等
                robot_at_patterns = [
                    f"@{self.robot_name} ",  # 普通空格
                    f"@{self.robot_name}\u2005",  # 特殊的微信空格
                    f"@{self.robot_name}\u00A0",  # 不间断空格
                    f"@{self.robot_name}\u200B",  # 零宽空格
                    f"@{self.robot_name}\u3000"   # 全角空格
                ]
                
                # 使用正则表达式进行更精确的匹配
                at_pattern = re.compile(f"@{re.escape(self.robot_name)}[\\s\u2005\u00A0\u200B\u3000]")
                is_at_local = bool(at_pattern.search(content)) or any(pattern in content for pattern in robot_at_patterns)
                
                # 提取原始@部分以供后续处理
                at_match = re.search(f"(@{re.escape(self.robot_name)}[\\s\u2005\u00A0\u200B\u3000])", content)
                at_content = at_match.group(1) if at_match else ''
            else:
                # 直接使用传入的参数
                is_at_local = True
                at_content = ""  # 不需要再提取，因为main.py已经处理过
            
            # 使用传入参数和本地检测的综合结果
            is_at_final = is_at_from_param or is_at_local
            
            # 清理消息内容
            actual_content = self._clean_message_content(content)
            
            # 使用最终的@状态进行日志记录和后续处理
            logger.info(f"收到群聊消息 - 群: {group_id}, 发送者: {sender_name}, 内容: {actual_content}, 是否@: {is_at_final}")
            
            # 保存所有群聊消息到群聊记忆，不论是否@
            timestamp = self.group_chat_memory.add_message(group_id, sender_name, actual_content, is_at_final)
            logger.debug(f"消息已保存到群聊记忆: {group_id}, 时间戳: {timestamp}")
            
            # 如果是@消息，加入处理队列并进行回复
            if is_at_final:
                logger.info(f"检测到@消息: {actual_content}, 发送者: {sender_name}")
                self.at_message_timestamps[f"{group_id}_{timestamp}"] = timestamp
                
                # 明确记录实际@人的用户信息
                actual_sender_name = sender_name  # 确保使用实际发送消息的人的名称
                actual_username = username  # 确保使用实际发送消息的人的ID
                
                # 决定是否缓存@消息或立即处理
                return self._cache_group_at_message(actual_content, group_id, actual_sender_name, actual_username, timestamp)
            else:
                logger.debug(f"非@消息，仅保存到记忆: {actual_content[:30]}...")
                
            return None
            
        except Exception as e:
            logger.error(f"处理群聊消息失败: {str(e)}", exc_info=True)
            return None

    def _cache_group_at_message(self, content: str, group_id: str, sender_name: str, username: str, timestamp: str):
        """缓存群聊@消息，在短时间内多个用户@机器人时合并处理"""
        current_time = time.time()
        
        # 初始化群聊缓存
        if group_id not in self.group_at_cache:
            self.group_at_cache[group_id] = []
        
        # 取消现有定时器
        if group_id in self.group_at_timer and self.group_at_timer[group_id]:
            self.group_at_timer[group_id].cancel()
        
        # 添加到群聊@消息缓存
        self.group_at_cache[group_id].append({
            'content': content,
            'sender_name': sender_name,
            'username': username,
            'timestamp': timestamp,
            'added_time': current_time
        })
        
        # 设置新的定时器，等待2秒处理缓存的群聊@消息
        wait_time = 2.0  # 2秒等待时间
        timer = threading.Timer(wait_time, self._process_cached_group_at_messages, args=[group_id])
        timer.daemon = True
        timer.start()
        self.group_at_timer[group_id] = timer
        
        logger.info(f"缓存群聊@消息: 群: {group_id}, 发送者: {sender_name}, 等待时间: {wait_time:.1f}秒")
        return None

    def _process_cached_group_at_messages(self, group_id: str):
        """处理缓存的群聊@消息"""
        try:
            if group_id not in self.group_at_cache or not self.group_at_cache[group_id]:
                return None
            
            at_messages = self.group_at_cache[group_id]
            logger.info(f"处理群聊缓存@消息: 群: {group_id}, 消息数: {len(at_messages)}")
            
            # 如果只有一条消息，直接处理
            if len(at_messages) == 1:
                msg = at_messages[0]
                return self._handle_at_message(msg['content'], group_id, msg['sender_name'], msg['username'], msg['timestamp'])
            
            # 处理多条消息情况
            # 按时间排序
            at_messages.sort(key=lambda x: x.get('added_time', 0))
            
            # 收集所有发送者名称和内容
            senders = []
            contents = []
            # 使用最后一条消息的时间戳和用户名
            last_timestamp = at_messages[-1]['timestamp']
            last_username = at_messages[-1]['username']
            
            for msg in at_messages:
                senders.append(msg['sender_name'])
                contents.append(msg['content'])
            
            # 去重发送者名称
            unique_senders = list(dict.fromkeys(senders))
            
            # 合并内容，使用分隔符区分不同用户的内容
            merged_content = ""
            for i, content in enumerate(contents):
                if i > 0:
                    merged_content += "\n---\n"
                merged_content += f"{senders[i]}说: {content}"
            
            # 构建上下文，获取最近的群聊对话记录
            context_messages = self.group_chat_memory.get_context_messages(group_id, last_timestamp)
            
            # 过滤和清理上下文消息
            filtered_context = []
            current_time = datetime.now()
            
            if context_messages:
                for msg in context_messages:
                    # 跳过缓存中的消息
                    if any(cached_msg['timestamp'] == msg["timestamp"] for cached_msg in at_messages):
                        continue
                        
                    # 检查消息时间（限制在6小时内）
                    try:
                        msg_time = datetime.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                        if (current_time - msg_time).total_seconds() > 21600:  # 6小时 = 21600秒
                            continue
                    except (ValueError, TypeError):
                        continue
                    
                    # 清理消息内容
                    human_message = self._clean_memory_content(msg["human_message"])
                    assistant_message = self._clean_memory_content(msg["assistant_message"]) if msg["assistant_message"] else None
                    
                    if human_message:
                        filtered_context.append({
                            "sender_name": msg["sender_name"],
                            "human_message": human_message,
                            "assistant_message": assistant_message
                        })
            
            # 限制上下文消息数量
            filtered_context = filtered_context[-3:]  # 只保留最近3条消息
            
            # 构建上下文字符串
            context = ""
            if filtered_context:
                context_parts = []
                for msg in filtered_context:
                    # 添加发送者消息
                    context_parts.append(f"{msg['sender_name']}: {msg['human_message']}")
                    # 如果有机器人回复，也添加进去
                    if msg["assistant_message"]:
                        context_parts.append(f"{self.robot_name}: {msg['assistant_message']}")
                
                if context_parts:
                    context = "<context>" + "\n".join(context_parts) + "</context>\n\n"
            
            # 构建API请求内容，明确标识这是多用户@的合并消息
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            api_content = f"<time>{current_time}</time>\n<group>{group_id}</group>\n<multiple_senders>{', '.join(unique_senders)}</multiple_senders>\n{context}<input>{merged_content}</input>"
            
            # 在日志中明确记录群聊多人@情况
            logger.info(f"多人@消息请求AI响应 - 群: {group_id}, 发送者们: {', '.join(unique_senders)}, 内容长度: {len(merged_content)}")
            
            # 获取AI回复
            reply = self.get_api_response(api_content, last_username)
            
            # 如果成功获取回复
            if reply:
                # 清理回复内容
                reply = self._clean_ai_response(reply)
                
                # 在回复中@所有发送消息的用户
                at_prefix = " ".join([f"@{sender}\u2005" for sender in unique_senders])
                if not reply.startswith(at_prefix):
                    reply = f"{at_prefix} {reply}"
                
                # 分割消息并获取过滤后的内容
                split_messages = self._split_message_for_sending(reply)
                
                # 使用memory_content更新群聊记忆
                if 'memory_content' in split_messages:
                    memory_content = split_messages['memory_content']
                    self.group_chat_memory.update_assistant_response(group_id, last_timestamp, memory_content)
                else:
                    # 如果没有memory_content字段，则使用过滤动作和表情后的回复
                    filtered_reply = self._filter_action_emotion(reply)
                    self.group_chat_memory.update_assistant_response(group_id, last_timestamp, filtered_reply)
                
                # 发送消息
                if not self.is_debug:
                    self._send_split_messages(split_messages, group_id)
                
                # 清除缓存
                self.group_at_cache[group_id] = []
                
                return split_messages['parts']
            
            # 清除缓存
            self.group_at_cache[group_id] = []
            return None
            
        except Exception as e:
            logger.error(f"处理群聊缓存@消息失败: {str(e)}", exc_info=True)
            # 清除缓存，防止错误消息卡在缓存中
            if group_id in self.group_at_cache:
                self.group_at_cache[group_id] = []
            return None

    def _handle_at_message(self, content: str, group_id: str, sender_name: str, username: str, timestamp: str):
        """处理@消息"""
        try:
            # 记录实际的@消息发送者信息
            logger.info(f"处理@消息 - 群ID: {group_id}, 发送者: {sender_name}, 用户ID: {username}")

            # 检查是否包含引用消息
            quoted_content = None
            quoted_sender = None
            quote_match = re.search(r'(?:引用|回复)\s+([^\s]+)\s+的(?:消息)?[:：]?\s*(.+?)(?=\n|$)', content)
            if quote_match:
                quoted_sender = quote_match.group(1)
                quoted_content = quote_match.group(2).strip()
                logger.info(f"检测到引用消息 - 引用者: {quoted_sender}, 内容: {quoted_content}")
                # 从原始消息中移除引用部分
                content = re.sub(r'(?:引用|回复)\s+[^\s]+\s+的(?:消息)?[:：]?\s*.+?(?=\n|$)', '', content).strip()
                
                # 如果引用内容为空，尝试从群聊记忆中获取
                if quoted_content and hasattr(self, 'group_chat_memory'):
                    # 获取引用消息的上下文
                    quoted_context = self.group_chat_memory.get_message_by_content(group_id, quoted_content)
                    if quoted_context:
                        logger.info(f"找到引用消息的上下文: {quoted_context}")
                        # 将引用内容添加到当前消息的上下文中
                        content = f"(引用消息: {quoted_sender} 说: {quoted_content})\n{content}"
            
            # 获取最近的群聊上下文消息，限制数量和时间范围
            context_messages = self.group_chat_memory.get_context_messages(group_id, timestamp)
            
            # 过滤和清理上下文消息
            filtered_context = []
            current_time = datetime.now()
            
            if context_messages:
                for msg in context_messages:
                    if msg["timestamp"] == timestamp:  # 跳过当前消息
                        continue
                        
                    # 检查消息时间（限制在6小时内）
                    try:
                        msg_time = datetime.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                        if (current_time - msg_time).total_seconds() > 21600:  # 6小时 = 21600秒
                            continue
                    except (ValueError, TypeError):
                        continue
                    
                    # 清理消息内容
                    human_message = self._clean_memory_content(msg["human_message"])
                    assistant_message = self._clean_memory_content(msg["assistant_message"]) if msg["assistant_message"] else None
                    
                    if human_message:
                        filtered_context.append({
                            "sender_name": msg["sender_name"],
                            "human_message": human_message,
                            "assistant_message": assistant_message
                        })
            
            # 限制上下文消息数量
            filtered_context = filtered_context[-3:]  # 只保留最近3条消息
            
            # 构建上下文字符串
            context = ""
            if filtered_context:
                context_parts = []
                for msg in filtered_context:
                    # 添加发送者消息
                    context_parts.append(f"{msg['sender_name']}: {msg['human_message']}")
                    # 如果有机器人回复，也添加进去
                    if msg["assistant_message"]:
                        context_parts.append(f"{self.robot_name}: {msg['assistant_message']}")
                
                if context_parts:
                    context = "<context>" + "\n".join(context_parts) + "</context>\n\n"
            
            # 构建API请求内容，明确标识当前@发送者
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            api_content = f"<time>{current_time}</time>\n<group>{group_id}</group>\n<sender>{sender_name}</sender>\n{context}<input>{content}</input>"
            
            # 在日志中明确记录谁@了机器人
            logger.info(f"@消息请求AI响应 - 发送者: {sender_name}, 用户ID: {username}, 内容: {content[:30]}...")
            
            # 获取AI回复，确保传递正确的用户标识
            reply = self.get_api_response(api_content, username)
            
            # 如果成功获取回复
            if reply:
                # 清理回复内容
                reply = self._clean_ai_response(reply)
                
                # 在回复中显式提及发送者，确保回复的是正确的人
                if not reply.startswith(f"@{sender_name}"):
                    reply = f"@{sender_name} {reply}"
                
                # 分割消息并获取过滤后的内容
                split_messages = self._split_message_for_sending(reply)
                
                # 使用memory_content更新群聊记忆
                if 'memory_content' in split_messages:
                    memory_content = split_messages['memory_content']
                    self.group_chat_memory.update_assistant_response(group_id, timestamp, memory_content)
                else:
                    # 如果没有memory_content字段，则使用过滤动作和表情后的回复
                    filtered_reply = self._filter_action_emotion(reply)
                    self.group_chat_memory.update_assistant_response(group_id, timestamp, filtered_reply)
                
                # 发送消息
                if not self.is_debug:
                    self._send_split_messages(split_messages, group_id)
                
                return split_messages['parts']
            
            return None
            
        except Exception as e:
            logger.error(f"处理@消息失败: {str(e)}")
            return None

    def _clean_message_content(self, content: str) -> str:
        """清理消息内容，去除时间戳和前缀"""
        # 匹配并去除时间戳和前缀
        patterns = [
            r'^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)?\s+ta私聊对你说\s*',
            r'^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s+ta私聊对你说\s*',
            r'^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)\s+ta(私聊|在群聊里)对你说\s*',
            r'^.*?ta私聊对你说\s*',
            r'^.*?ta在群聊里对你说\s*'  # 添加群聊消息模式
        ]
        
        actual_content = content
        
        # 保存@信息
        at_match = re.search(r'(@[^\s]+)', actual_content)
        at_content = at_match.group(1) if at_match else ''
        
        # 清理时间戳和前缀
        for pattern in patterns:
            if re.search(pattern, actual_content):
                actual_content = re.sub(pattern, '', actual_content)
                break
        
        # 如果有@信息且在清理过程中被移除，重新添加到开头
        if at_content and at_content not in actual_content:
            actual_content = f"{at_content} {actual_content}"
        
        return actual_content.strip()

    def _cache_message(self, content: str, chat_id: str, sender_name: str, username: str, 
                      is_group: bool, is_image_recognition: bool) -> None:
        """缓存消息并设置定时器"""
        current_time = time.time()
        
        # 取消现有定时器
        if username in self.message_timer and self.message_timer[username]:
            self.message_timer[username].cancel()
        
        # 添加到消息缓存
        if username not in self.message_cache:
            self.message_cache[username] = []
        
        # 提取实际内容
        actual_content = self._clean_message_content(content)
        
        self.message_cache[username].append({
            'content': content,
            'chat_id': chat_id,
            'sender_name': sender_name,
            'is_group': is_group,
            'is_image_recognition': is_image_recognition,
            'timestamp': current_time
        })
        
        # 设置新的定时器
        wait_time = self._calculate_wait_time(username, len(self.message_cache[username]))
        timer = threading.Timer(wait_time, self._process_cached_messages, args=[username])
        timer.daemon = True
        timer.start()
        self.message_timer[username] = timer
        
        # 简化日志，只显示缓存内容和等待时间
        logger.info(f"缓存消息: {actual_content} | 等待时间: {wait_time:.1f}秒")
        
        return None

    def _calculate_wait_time(self, username: str, msg_count: int) -> float:
        """计算消息等待时间"""
        base_wait_time = 3.0
        typing_speed = self._estimate_typing_speed(username)
        
        if msg_count == 1:
            wait_time = base_wait_time + 5.0
        else:
            estimated_typing_time = min(4.0, typing_speed * 20)  # 假设用户输入20个字符
            wait_time = base_wait_time + estimated_typing_time
            
        # 简化日志，只在debug级别显示详细计算过程
        logger.debug(f"消息等待时间计算: 基础={base_wait_time}秒, 打字速度={typing_speed:.2f}秒/字, 结果={wait_time:.1f}秒")
        
        return wait_time

    def _process_cached_messages(self, username: str):
        """处理缓存的消息"""
        try:
            if not self.message_cache.get(username):
                return None
            
            messages = self.message_cache[username]
            messages.sort(key=lambda x: x.get('timestamp', 0))
            
            # 获取最近的对话记录作为上下文
            context = self._get_conversation_context(username)
            
            # 合并消息内容
            raw_contents = []
            first_timestamp = None
            
            for msg in messages:
                content = msg['content']
                if not first_timestamp:
                    # 提取第一条消息的时间戳
                    timestamp_match = re.search(r'\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?', content)
                    if timestamp_match:
                        first_timestamp = timestamp_match.group()
                
                # 清理消息内容
                cleaned_content = self._clean_message_content(content)
                if cleaned_content:
                    raw_contents.append(cleaned_content)
            
            # 使用 \ 作为句子分隔符合并消息
            content_text = ' $ '.join(raw_contents)
            
            # 格式化最终消息
            first_timestamp = first_timestamp or datetime.now().strftime('%Y-%m-%d %H:%M')
            merged_content = f"[{first_timestamp}]ta 私聊对你说：{content_text}"
            
            if context:
                merged_content = f"{context}\n\n(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容)\n\n{merged_content}"
            
            # 处理合并后的消息
            last_message = messages[-1]
            result = self._handle_uncached_message(
                merged_content,
                last_message['chat_id'],
                last_message['sender_name'],
                username,
                last_message['is_group'],
                any(msg.get('is_image_recognition', False) for msg in messages)
            )
            
            # 清理缓存和定时器
            self.message_cache[username] = []
            if username in self.message_timer and self.message_timer[username]:
                self.message_timer[username].cancel()
                self.message_timer[username] = None
            
            return result

        except Exception as e:
            logger.error(f"处理缓存消息失败: {str(e)}", exc_info=True)
            return None
            
    def _get_conversation_context(self, username: str) -> str:
        """获取对话上下文"""
        try:
            # 构建更精确的查询，包含用户ID和当前时间信息，以获取更相关的记忆
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            query = f"与用户 {username} 相关的最近重要对话 {current_time}"
            
            # 获取相关记忆
            recent_history = self.memory_handler.get_relevant_memories(
                query, 
                username,
                top_k=10  # 增加获取的记忆数量，后续会基于质量筛选
            )
            
            if recent_history and len(recent_history) > 0:
                # 根据记忆质量排序和筛选
                # 筛选标准：
                # 1. 尽量选择长度适中的对话（不太短也不太长）
                # 2. 优先选择更复杂的对话（含有特定信息的）
                
                # 简单评分函数
                def memory_quality_score(mem):
                    if not mem.get('message') or not mem.get('reply'):
                        return 0
                    
                    msg_len = len(mem['message'])
                    reply_len = len(mem['reply'])
                    
                    # 太短的对话质量低
                    if msg_len < 5 or reply_len < 10:
                        return 0
                    
                    # 太长的对话也不理想
                    if msg_len > 500 or reply_len > 1000:
                        return 10
                    
                    # 基础分数
                    score = min(100, (msg_len + reply_len) / 10)
                    
                    # 包含特定用户名或对话元素的加分
                    if username.lower() in mem['message'].lower() or username.lower() in mem['reply'].lower():
                        score += 15
                    
                    # 包含问答格式的加分
                    if "?" in mem['message'] or "？" in mem['message']:
                        score += 10
                        
                    return score
                
                # 按质量排序
                sorted_memories = sorted(recent_history, key=memory_quality_score, reverse=True)
                
                # 选取最高质量的记忆（最多5条）
                quality_memories = sorted_memories[:5]
                logger.info(f"从 {len(recent_history)} 条记忆中筛选出 {len(quality_memories)} 条高质量记忆")
                
                # 构建上下文
                context_parts = []
                for idx, hist in enumerate(quality_memories):
                    if hist.get('message') and hist.get('reply'):
                        context_parts.append(f"对话{idx+1}:\n用户: {hist['message']}\nAI: {hist['reply']}")
                
                if context_parts:
                    return "以下是之前的对话记录：\n\n" + "\n\n".join(context_parts)
            
            return ""
            
        except Exception as e:
            logger.error(f"获取记忆历史记录失败: {str(e)}")
            return ""

    def _estimate_typing_speed(self, username: str) -> float:
        """估计用户的打字速度（秒/字符）"""
        # 如果没有足够的历史消息，使用默认值
        if username not in self.message_cache or len(self.message_cache[username]) < 2:
            # 根据用户ID是否存在于last_message_time中返回不同的默认值
            # 如果是新用户，给予更长的等待时间
            if username not in self.last_message_time:
                typing_speed = 0.2  # 新用户默认速度：每字0.2秒
            else:
                typing_speed = 0.15  # 已知用户默认速度：每字0.15秒
            
            logger.info(f"用户打字速度: {typing_speed:.2f}秒/字符")
            return typing_speed
        
        # 获取最近的两条消息
        messages = self.message_cache[username]
        if len(messages) < 2:
            typing_speed = 0.15
            logger.info(f"用户打字速度: {typing_speed:.2f}秒/字符")
            return typing_speed
        
        # 按时间戳排序，确保我们比较的是连续的消息
        recent_msgs = sorted(messages, key=lambda x: x.get('timestamp', 0))[-2:]
        
        # 计算时间差和字符数
        time_diff = recent_msgs[1].get('timestamp', 0) - recent_msgs[0].get('timestamp', 0)
        
        # 获取实际内容（去除时间戳和前缀）
        content = recent_msgs[0].get('content', '')
        
        # 定义系统提示词模式
        time_prefix_pattern = r'^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)?\s+ta私聊对你说\s+'
        time_prefix_pattern2 = r'^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s+ta私聊对你说\s+'
        time_prefix_pattern3 = r'^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)\s+ta(私聊|在群聊里)对你说\s*'
        reminder_pattern = r'\((?:上次的对话内容|以上是历史对话内容)[^)]*\)'
        context_pattern = r'对话\d+:\n用户:.+\nAI:.+'
        system_patterns = [
            # 旧的精确字数限制提示
            r'\n\n请注意：你的回复应当与用户消息的长度相当，控制在约\d+个字符和\d+个句子左右。',
            # 新的提示词变体
            r'\n\n请简短回复，控制在一两句话内。',
            r'\n\n请注意保持自然的回复长度，与用户消息风格协调。',
            r'\n\n请保持简洁明了的回复。',
            # 其他系统提示词
            r'\(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容\)',
            r'请你回应用户的结束语'
        ]
        
        # 先去除基本的时间戳和前缀
        if re.search(time_prefix_pattern, content):
            content = re.sub(time_prefix_pattern, '', content)
        elif re.search(time_prefix_pattern2, content):
            content = re.sub(time_prefix_pattern2, '', content)
        elif re.search(time_prefix_pattern3, content):
            content = re.sub(time_prefix_pattern3, '', content)
        
        # 去除其他系统提示词
        content = re.sub(reminder_pattern, '', content)
        content = re.sub(context_pattern, '', content, flags=re.DOTALL)
        
        for pattern in system_patterns:
            content = re.sub(pattern, '', content)
        
        # 计算过滤后的实际用户内容长度
        filtered_content = content.strip()
        char_count = len(filtered_content)
        
        # 如果时间差或字符数无效，使用默认值
        if time_diff <= 0 or char_count <= 0:
            typing_speed = 0.15
            logger.info(f"用户打字速度: {typing_speed:.2f}秒/字符")
            return typing_speed
        
        # 计算打字速度（秒/字）
        typing_speed = time_diff / char_count
        
        # 应用平滑因子，避免极端值
        # 如果我们有历史记录的打字速度，将其纳入考虑
        if hasattr(self, '_typing_speeds') and username in self._typing_speeds:
            prev_speed = self._typing_speeds[username]
            # 使用加权平均，新速度权重0.4，历史速度权重0.6
            typing_speed = 0.4 * typing_speed + 0.6 * prev_speed
        
        # 存储计算出的打字速度
        if not hasattr(self, '_typing_speeds'):
            self._typing_speeds = {}
        self._typing_speeds[username] = typing_speed
        
        # 限制在合理范围内：0.2秒/字 到 1.2秒/字
        typing_speed = max(0.2, min(1.2, typing_speed))
        
        # 只输出最终的打字速度
        logger.info(f"用户打字速度: {typing_speed:.2f}秒/字符")
        
        return typing_speed

    def _calculate_response_length_ratio(self, user_message_length: int) -> float:
        """计算回复长度与用户消息的比例"""
        # 基础比例从1.0开始，表示回复长度与用户消息长度相同
        base_ratio = 1.0
        
        # 根据用户消息长度动态调整比例，但保持在接近1.0的范围内
        if user_message_length < 10:  # 非常短的消息
            ratio = base_ratio * 1.5  # 短消息略微长一点
        elif user_message_length < 30:  # 较短的消息
            ratio = base_ratio * 1.3
        elif user_message_length < 50:  # 中等长度
            ratio = base_ratio * 1.2
        elif user_message_length < 100:  # 较长消息
            ratio = base_ratio * 1.1
        else:  # 很长的消息
            ratio = base_ratio * 1.0  # 对于长消息保持1:1比例
        
        # 限制最大比例，确保不会过长
        return min(ratio, 1.5)

    def _handle_voice_request(self, content, chat_id, sender_name, username, is_group):
        """处理语音请求"""
        logger.info("处理语音请求")
        reply = self.get_api_response(content, chat_id)
        if "</think>" in reply:
            reply = reply.split("</think>", 1)[1].strip()

        voice_path = self.voice_handler.generate_voice(reply)
        if voice_path:
            try:
                self.wx.SendFiles(filepath=voice_path, who=chat_id)
            except Exception as e:
                logger.error(f"发送语音失败: {str(e)}")
                if is_group:
                    reply = f"@{sender_name} {reply}"
                self.wx.SendMsg(msg=reply, who=chat_id)
            finally:
                try:
                    os.remove(voice_path)
                except Exception as e:
                    logger.error(f"删除临时语音文件失败: {str(e)}")
        else:
            if is_group:
                reply = f"@{sender_name} {reply}"
            self.wx.SendMsg(msg=reply, who=chat_id)
        return reply

    def _handle_random_image_request(self, content, chat_id, sender_name, username, is_group):
        """处理随机图片请求"""
        logger.info("处理随机图片请求")
        image_path = self.image_handler.get_random_image()
        if image_path:
            try:
                self.wx.SendFiles(filepath=image_path, who=chat_id)
                reply = "给主人你找了一张好看的图片哦~"
            except Exception as e:
                logger.error(f"发送图片失败: {str(e)}")
                reply = "抱歉主人，图片发送失败了..."
            finally:
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as e:
                    logger.error(f"删除临时图片失败: {str(e)}")

            if is_group:
                reply = f"@{sender_name} {reply}"
            self.wx.SendMsg(msg=reply, who=chat_id)
            return reply
        return None

    def _handle_image_generation_request(self, content, chat_id, sender_name, username, is_group):
        """处理图像生成请求"""
        logger.info("处理画图请求")
        image_path = self.image_handler.generate_image(content)
        if image_path:
            try:
                self.wx.SendFiles(filepath=image_path, who=chat_id)
                reply = "这是按照主人您的要求生成的图片\\(^o^)/~"
            except Exception as e:
                logger.error(f"发送生成图片失败: {str(e)}")
                reply = "抱歉主人，图片生成失败了..."
            finally:
                try:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception as e:
                    logger.error(f"删除临时图片失败: {str(e)}")

            if is_group:
                reply = f"@{sender_name} {reply}"
            self.wx.SendMsg(msg=reply, who=chat_id)
            return reply
        return None

    def _filter_action_emotion(self, text):
        """处理动作描写和颜文字，确保格式一致"""
        # 1. 先移除文本中的引号，避免引号包裹非动作文本
        text = text.replace('"', '').replace('"', '').replace('"', '')
        
        # 2. 保护已经存在的括号内容
        protected_parts = {}
        
        # 匹配所有类型的括号及其内容
        bracket_pattern = r'[\(\[（【][^\(\[（【\)\]）】]*[\)\]）】]'
        brackets = list(re.finditer(bracket_pattern, text))
        
        # 保护已有的括号内容
        for i, match in enumerate(brackets):
            placeholder = f"__PROTECTED_{i}__"
            protected_parts[placeholder] = match.group()
            text = text.replace(match.group(), placeholder)
        
        # 3. 保护颜文字 - 使用更宽松的匹配规则
        if not hasattr(self, '_emoticon_chars_set'):
            self._emoticon_chars_set = set(
                '（()）~～‿⁀∀︿⌒▽△□◇○●ˇ＾∇＿゜◕ω・ノ丿╯╰つ⊂＼／┌┐┘└°△▲▽▼◇◆○●◎■□▢▣▤▥▦▧▨▩♡♥ღ☆★✡⁂✧✦❈❇✴✺✹✸✷✶✵✳✲✱✰✯✮✭✬✫✪✩✨✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁✀✿✾✽✼✻✺✹✸✷✶✵✴✳✲✱✰✯✮✭✬✫✪✩✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁❤♪♫♬♩♭♮♯°○◎●◯◐◑◒◓◔◕◖◗¤☼☀☁☂☃☄★☆☎☏⊙◎☺☻☯☭♠♣♧♡♥❤❥❣♂♀☿❀❁❃❈❉❊❋❖☠☢☣☤☥☦☧☨☩☪☫☬☭☮☯☸☹☺☻☼☽☾☿♀♁♂♃♄♆♇♈♉♊♋♌♍♎♏♐♑♒♓♔♕♖♗♘♙♚♛♜♝♞♟♠♡♢♣♤♥♦♧♨♩♪♫♬♭♮♯♰♱♲♳♴♵♶♷♸♹♺♻♼♽♾♿⚀⚁⚂⚃⚄⚆⚇⚈⚉⚊⚋⚌⚍⚎⚏⚐⚑⚒⚓⚔⚕⚖⚗⚘⚙⚚⚛⚜⚝⚞⚟*^_^')
        
        emoji_patterns = [
            # 括号类型的颜文字
            r'\([\w\W]{1,10}?\)',  # 匹配较短的括号内容
            r'（[\w\W]{1,10}?）',  # 中文括号
            
            # 符号组合类型
            r'[＼\\\/\*\-\+\<\>\^\$\%\!\?\@\#\&\|\{\}\=\;\:\,\.]{2,}',  # 常见符号组合
            
            # 常见表情符号
            r'[◕◑◓◒◐•‿\^▽\◡\⌒\◠\︶\ω\´\`\﹏\＾\∀\°\◆\□\▽\﹃\△\≧\≦\⊙\→\←\↑\↓\○\◇\♡\❤\♥\♪\✿\★\☆]{1,}',
            
            # *号组合
            r'\*[\w\W]{1,5}?\*'  # 星号强调内容
        ]
        
        for pattern in emoji_patterns:
            emojis = list(re.finditer(pattern, text))
            for i, match in enumerate(emojis):
                # 避免处理过长的内容，可能是动作描写而非颜文字
                if len(match.group()) <= 15 and not any(p in match.group() for p in protected_parts.values()):
                    # 检查是否包含足够的表情符号字符
                    chars_count = sum(1 for c in match.group() if c in self._emoticon_chars_set)
                    if chars_count >= 2 or len(match.group()) <= 5:
                        placeholder = f"__EMOJI_{i}__"
                        protected_parts[placeholder] = match.group()
                        text = text.replace(match.group(), placeholder)
        
        # 4. 处理分隔符 - 保留原样
        parts = text.split('$')
        new_parts = []
        
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:  # 跳过空部分
                continue
                
            # 直接添加部分，不添加括号
            new_parts.append(part)
        
        # 5. 特殊处理：同时兼容原来的 \ 分隔符
        if len(new_parts) == 1:  # 如果没有找到 $ 分隔符，尝试处理 \ 分隔符
            parts = text.split('\\')
            if len(parts) > 1:  # 确认有实际分隔
                new_parts = []
                for i, part in enumerate(parts):
                    part = part.strip()
                    if not part:
                        continue
                    # 直接添加部分，不添加括号
                    new_parts.append(part)
        
        # 6. 重新组合文本
        result = " $ ".join(new_parts)
        
        # 7. 恢复所有保护的内容
        for placeholder, content in protected_parts.items():
            result = result.replace(placeholder, content)
            
        return result

    def _clean_memory_content(self, content: str) -> str:
        """清理记忆内容，移除不必要的格式和标记"""
        if not content:
            return ""
        
        # 移除时间戳和前缀
        patterns = [
            r'^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?\)?\s+',  # 时间戳格式
            r'^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?\]\s+',    # 带方括号的时间戳
            r'^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?\)\s+', # 带说明的时间戳
            r'^.*?ta(私聊|在群聊里)对你说\s*',  # 对话前缀
            r'<time>.*?</time>\s*',  # XML风格时间标记
            r'<group>.*?</group>\s*',  # 群组标记
            r'<sender>.*?</sender>\s*',  # 发送者标记
            r'<input>(.*?)</input>',  # 保留input标记内的内容
            r'<context>.*?</context>\s*'  # 上下文标记
        ]
        
        # 应用所有模式
        cleaned_content = content
        for pattern in patterns:
            if re.search(pattern, cleaned_content):
                if 'input' in pattern:
                    # 对于input标记，保留其内容
                    match = re.search(pattern, cleaned_content)
                    if match:
                        cleaned_content = match.group(1)
                else:
                    # 对于其他模式，直接移除
                    cleaned_content = re.sub(pattern, '', cleaned_content)
        
        # 移除引用格式
        cleaned_content = re.sub(r'\(引用消息:.*?\)\s*', '', cleaned_content)
        
        # 移除多余的空白字符
        cleaned_content = re.sub(r'\s+', ' ', cleaned_content)
        
        # 移除@标记
        cleaned_content = re.sub(r'@[^\s]+\s*', '', cleaned_content)
        
        # 移除代码块标记
        cleaned_content = re.sub(r'```.*?```', '', cleaned_content, flags=re.DOTALL)
        
        # 移除多行环境中的多余换行符
        cleaned_content = re.sub(r'\n+', ' ', cleaned_content)
        
        return cleaned_content.strip()
            
    def _clean_ai_response(self, response: str) -> str:
        """清理AI回复中的所有系统标记和提示词"""
        if not response:
            return ""
        
        # 移除所有XML样式的标记
        response = re.sub(r'<[^>]+>', '', response)
        
        # 清理其他系统标记和提示词
        patterns_to_remove = [
            r'\[系统提示\].*?\[/系统提示\]',
            r'\[系统指令\].*?\[/系统指令\]',
            r'记忆\d+:\s*\n用户:.*?\nAI:.*?(?=\n\n|$)',
            r'以下是之前的对话记录：.*?(?=\n\n)',
            r'\(以上是历史对话内容[^)]*\)',
            r'memory_number:.*?(?=\n|$)',
            r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?\]',
            r'请注意：.*?(?=\n|$)',
            r'请(?:简短|简洁)回复.*?(?=\n|$)',
            r'请.*?控制在.*?(?=\n|$)',
            r'请你回应用户的结束语',
            r'^你：|^对方：|^AI：',
            r'ta(?:私聊|在群聊里)对你说[：:]\s*',
        ]
        
        for pattern in patterns_to_remove:
            response = re.sub(pattern, '', response, flags=re.DOTALL|re.IGNORECASE)
        
        # 移除多余的空白字符
        response = re.sub(r'\s+', ' ', response)
        return response.strip()

    def _filter_punctuation(self, text: str, is_last_sentence: bool = False) -> str:
        """
        过滤标点符号，保留问号、感叹号、省略号、书名号、括号、引号
        如果是最后一句，并过滤掉句尾的句号
        """
        if not text:
            return ""
        
        # 定义需要保留的标点符号集合
        keep_punctuation = set(['?', '!', '？', '！', '…', '《', '》', '(', ')', '（', '）', '"', '"', ''', ''', '「', '」'])
        
        # 需要过滤的标点符号（除了保留的那些）
        filter_punctuation = set(['。', '，', '、', '：', '；', '·', '~', ',', '.', ':', ';'])
        
        # 如果是最后一句，且以句号结尾，移除句尾的句号
        if is_last_sentence and text[-1] in ['。', '.']:
            text = text[:-1]
        
        # 处理文本中的标点
        result = ""
        for char in text:
            if char in filter_punctuation:
                # 过滤掉需要过滤的标点
                continue
            result += char
        
        return result
        
    def _process_for_sending_and_memory(self, content: str) -> dict:
        """
        处理AI回复，添加$和￥分隔符，过滤标点符号
        返回处理后的分段消息和存储到记忆的内容
        """
        if not content:
            return {"parts": [], "memory_content": "", "total_length": 0, "sentence_count": 0}
        
        # 检查是否包含表情符号或特殊字符
        has_emoji = bool(re.search(r'[\U00010000-\U0010ffff\u2600-\u26FF\u2700-\u27BF]', content))
        
        # 对于包含表情符号的内容，使用不同的处理策略
        if has_emoji:
            # 直接使用句子作为分割单位，不再使用标点符号分割
            # 可能包含表情符号的句子，按照换行符或者句号分割
            sentences = re.split(r'([。！？\.\!\?\n])', content)
            
            # 重组句子
            complete_sentences = []
            for i in range(0, len(sentences)-1, 2):
                if i+1 < len(sentences):
                    # 将句子和标点符号重新组合
                    sentence = sentences[i] + sentences[i+1]
                    complete_sentences.append(sentence)
            
            # 处理最后一个可能没有标点的片段
            if len(sentences) % 2 == 1 and sentences[-1].strip():
                complete_sentences.append(sentences[-1])
                
            # 如果没有成功分割，则将整个内容作为一句话处理
            if not complete_sentences:
                complete_sentences = [content]
                
            # 直接将每个句子作为一部分，不进行标点过滤
            processed_parts = []
            memory_parts = []
            
            for i, sentence in enumerate(complete_sentences):
                clean_sentence = sentence.strip()
                if clean_sentence:
                    # 清理句子内部的分隔符
                    clean_sentence = clean_sentence.replace(' $ ', ' ').replace('$ ', ' ').replace(' $', ' ')
                    
                    # 添加到处理结果
                    processed_parts.append(clean_sentence)
                    
                    # 为记忆内容准备，最后一句添加￥
                    if i == len(complete_sentences) - 1:
                        memory_parts.append(clean_sentence + "￥")
                    else:
                        memory_parts.append(clean_sentence)
            
            # 为记忆内容添加$分隔符
            memory_content = " $ ".join(memory_parts)
            
            return {
                "parts": processed_parts,
                "memory_content": memory_content,
                "total_length": sum(len(part) for part in processed_parts),
                "sentence_count": len(processed_parts)
            }
        
        # 没有表情符号的情况，使用原来的处理逻辑
        # 使用正则表达式识别句子
        sentences = re.split(r'([。！？\.\!\?])', content)
        
        # 重组句子
        complete_sentences = []
        for i in range(0, len(sentences)-1, 2):
            if i+1 < len(sentences):
                # 将句子和标点符号重新组合
                sentence = sentences[i] + sentences[i+1]
                complete_sentences.append(sentence)
        
        # 处理最后一个可能没有标点的片段
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            complete_sentences.append(sentences[-1])
        
        # 如果没有分离出句子，则视为一个完整句子
        if not complete_sentences and content.strip():
            complete_sentences = [content]
        
        # 处理每个句子，添加分隔符，过滤标点
        processed_parts = []
        memory_parts = []
        
        # 将每个句子作为单独的部分处理
        for i, sentence in enumerate(complete_sentences):
            is_last = i == len(complete_sentences) - 1
            # 过滤标点符号
            filtered_sentence = self._filter_punctuation(sentence, is_last)
            
            # 如果句子不为空，添加到处理结果中
            if filtered_sentence.strip():
                # 处理记忆内容，给最后一句添加￥
                memory_sentence = filtered_sentence
                if is_last:
                    memory_sentence = memory_sentence + "￥"
                
                processed_parts.append(filtered_sentence)
                memory_parts.append(memory_sentence)
        
        # 为记忆内容添加$分隔符
        memory_content = " $ ".join(memory_parts)
        
        return {
            "parts": processed_parts,
            "memory_content": memory_content,
            "total_length": sum(len(part) for part in processed_parts),
            "sentence_count": len(processed_parts)
        }

    def _split_message_for_sending(self, text):
        """将消息分割成适合发送的多个部分"""
        if not text:
            return {'parts': [], 'total_length': 0, 'sentence_count': 0}
        
        # 使用新的处理函数
        processed = self._process_for_sending_and_memory(text)
        
        # 添加更详细的日志，用于调试
        logger.info(f"消息分割: 原文 \"{text[:100]}...\"")
        logger.info(f"消息分割: 分成了 {len(processed['parts'])} 个部分")
        
        for i, part in enumerate(processed['parts']):
            logger.info(f"消息分割部分 {i+1}: \"{part}\"")
        
        if 'memory_content' in processed:
            logger.info(f"记忆内容: \"{processed['memory_content'][:100]}...\"")
        
        return {
            'parts': processed['parts'],
            'total_length': processed['total_length'],
            'sentence_count': processed['sentence_count'],
            'memory_content': processed['memory_content']
        }

    def _send_split_messages(self, messages, chat_id):
        """发送分割后的消息，不进行重试和失败检查"""
        if not messages or not isinstance(messages, dict):
            return False
        
        # 记录已发送的消息，防止重复发送
        sent_messages = set()
        
        # 计算自然的发送间隔
        base_interval = 0.5  # 基础间隔时间（秒）
        
        # 检查消息内容是否已经包含@标记，避免重复@
        first_part = messages['parts'][0] if messages['parts'] else ""
        already_has_at = bool(re.search(r'^@[^\s]+', first_part))
        
        # 检查是否是群聊消息（通过chat_id是否包含群聊标识）
        is_group_chat = False
        sender_name = None
        
        # 只有当消息不包含@标记时才尝试添加
        if not already_has_at:
            # 从chat_id中提取群聊信息
            if hasattr(self, 'group_chat_memory'):
                is_group_chat = chat_id in self.group_chat_memory.group_chats
                if is_group_chat:
                    # 从最近的群聊消息中获取发送者名称
                    recent_messages = self.group_chat_memory.get_memory_from_file(chat_id, limit=1)
                    if recent_messages:
                        sender_name = recent_messages[0].get('sender_name')
        
        for i, part in enumerate(messages['parts']):
            if part not in sent_messages and part.strip():
                # 处理消息中的$分隔符
                processed_part = part
                
                # 移除消息开头的$符号
                if processed_part.startswith('$'):
                    processed_part = processed_part[1:].strip()
                
                # 移除消息中间的$ 符号
                processed_part = processed_part.replace(' $ ', ' ').replace('$ ', ' ').replace(' $', ' ')
                
                # 模拟真实用户输入行为
                time.sleep(base_interval)  # 基础间隔
                
                # 只有在第一条消息、是群聊、有发送者名称且消息不已经包含@时才添加@
                if i == 0 and is_group_chat and sender_name and not already_has_at:
                    send_content = f"@{sender_name}\u2005{processed_part}"
                else:
                    send_content = processed_part
                
                # 发送消息，不检查结果
                logger.info(f"发送消息片段 {i+1}/{len(messages['parts'])}: {send_content[:20]}...")
                
                # 不捕获异常，不检查结果，假设所有消息都已成功发送
                self.wx.SendMsg(send_content, chat_id)
                sent_messages.add(part)
                
                # 根据消息长度动态调整下一条消息的等待时间
                wait_time = base_interval + random.uniform(0.3, 0.7) * (len(processed_part) / 50)
                time.sleep(wait_time)
        
        # 所有消息都假设已成功发送
        return True

    def get_private_api_response(self, message, user_id, memory_id=None, current_time=None):
        """获取私聊API响应"""
        try:
            deepseek_response = self.get_api_response(message, user_id)
            
            # 如果API响应为空或出错，直接返回
            if not deepseek_response or not isinstance(deepseek_response, str):
                logger.error(f"API响应为空或格式错误: {deepseek_response}")
                return '抱歉，我暂时无法回应，请稍后再试。'
                
            # 清理API回复，移除系统标记和提示词
            cleaned_response = self._clean_ai_response(deepseek_response)
            
            # 处理回复，添加$和￥分隔符，过滤标点符号
            processed = self._process_for_sending_and_memory(cleaned_response)
            
            # 如果设置了memory_id，更新记忆
            if hasattr(self, 'memory_handler') and memory_id:
                try:
                    # 使用memory_content作为存储内容
                    memory_content = processed.get('memory_content', cleaned_response)
                    # 使用修改后的API响应更新记忆
                    self.memory_handler.update_memory(memory_id, memory_content)
                    logger.info(f"记忆已更新: {memory_id}")
                except Exception as memory_e:
                    logger.error(f"更新记忆失败: {str(memory_e)}")
            
            # 返回分割后的消息对象，以便主函数处理发送
            return {
                'parts': processed.get('parts', [cleaned_response]),
                'total_length': processed.get('total_length', len(cleaned_response)),
                'sentence_count': processed.get('sentence_count', 1)
            }
            
        except Exception as e:
            logger.error(f"获取私聊API响应失败: {str(e)}")
            return '抱歉，处理您的消息时出现了错误，请稍后再试。'

    def set_replying_status(self, is_replying):
        """设置所有处理器的回复状态"""
        try:
            # 设置图像识别服务的状态
            if hasattr(self, 'image_recognition_service') and self.image_recognition_service:
                self.image_recognition_service.set_replying_status(is_replying)
                
            # 设置图片处理器的状态
            if hasattr(self, 'image_handler') and self.image_handler:
                self.image_handler.set_replying_status(is_replying)
                
            # 设置表情包处理器的状态
            if hasattr(self, 'emoji_handler') and self.emoji_handler:
                self.emoji_handler.set_replying_status(is_replying)
                
        except Exception as e:
            logger.error(f"设置回复状态时出错: {str(e)}")

    def process_message(self, message, who, source="wechat"):
        """处理接收到的微信消息"""
        try:
            # 设置所有处理器为"正在回复"状态
            self.set_replying_status(True)
            
            # 检查消息类型
            if isinstance(message, dict) and "Type" in message:
                # 检查是否是自己发送的消息
                is_self_message = message.get("IsSelf", False)
                
                if message["Type"] == 1:  # 文本消息
                    return self.process_text_message(message["Content"], who, source, is_self_message)
                elif message["Type"] == 3:  # 图片消息
                    return self.process_image_message(message.get("Content", ""), who, is_self_message)
                else:
                    logger.warning(f"未支持的消息类型: {message['Type']}")
                    return "抱歉，暂不支持此类型的消息。"
            else:
                # 直接处理文本内容
                return self.process_text_message(message, who, source, False)
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return "抱歉，处理您的消息时出现了错误，请稍后再试。"
        finally:
            # 确保处理完成后重置回复状态
            self.set_replying_status(False)

    def process_image_message(self, image_path: str, who: str, is_self_message: bool = False):
        """处理图片消息，识别图片内容"""
        try:
            # 如果是自己发送的图片，直接跳过处理
            if is_self_message:
                logger.info(f"检测到自己发送的图片，跳过识别: {image_path}")
                return None
                
            # 获取当前时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 设置所有处理器为"正在回复"状态
            self.set_replying_status(True)
            
            try:
                # 将图片内容添加到服务中进行识别
                def callback(recognition_result):
                    try:
                        # 将识别结果作为普通消息处理
                        if recognition_result:
                            logger.info(f"图片识别结果: {recognition_result[:100]}...")
                            # 构建消息格式
                            formatted_content = f"[{current_time}] ta私聊对你说：{recognition_result}"
                            # 调用API处理识别后的文本
                            response = self.get_api_response(formatted_content, who)
                            
                            # 发送回复
                            if response and not self.is_debug:
                                # 分割并发送消息
                                split_messages = self._split_message_for_sending(response)
                                self._send_split_messages(split_messages, who)
                    except Exception as e:
                        logger.error(f"处理图片识别回调时出错: {str(e)}")
                
                # 使用图像识别服务进行异步识别
                if hasattr(self, 'image_recognition_service') and self.image_recognition_service:
                    result = self.image_recognition_service.recognize_image(image_path, False, callback)
                    logger.info(f"图片识别请求已添加到队列: {result}")
                    return result
                else:
                    logger.error("图像识别服务未初始化")
                    return "抱歉，图片识别服务未准备好"
            finally:
                # 重置回复状态
                self.set_replying_status(False)
                
        except Exception as e:
            logger.error(f"处理图片消息失败: {str(e)}", exc_info=True)
            return "抱歉，处理图片时出现错误"

    def _handle_emoji_message(self, content: str, chat_id: str, user_id: str, is_self_emoji: bool = False):
        """处理表情包请求消息"""
        try:
            # 如果是自己发送的表情包，直接跳过处理
            if is_self_emoji:
                logger.info(f"检测到自己发送的表情包，跳过处理")
                return None
                
            # 获取当前时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 设置所有处理器为"正在回复"状态
            self.set_replying_status(True)
            
            try:
                # 将表情包请求添加到队列中进行处理
                def callback(emoji_path):
                    try:
                        if emoji_path and os.path.exists(emoji_path):
                            logger.info(f"找到表情包: {emoji_path}")
                            # 发送表情包
                            if not self.is_debug:
                                self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                    except Exception as e:
                        logger.error(f"处理表情包回调时出错: {str(e)}")
                
                # 使用表情包处理器进行异步处理
                if hasattr(self, 'emoji_handler') and self.emoji_handler:
                    result = self.emoji_handler.get_emotion_emoji(content, user_id, callback, is_self_emoji)
                    logger.info(f"表情包请求已添加到队列: {result}")
                    return result
                else:
                    logger.error("表情包处理器未初始化")
                    return "抱歉，表情包功能未准备好"
            finally:
                # 重置回复状态
                self.set_replying_status(False)
                
        except Exception as e:
            logger.error(f"处理表情包请求失败: {str(e)}", exc_info=True)
            return "抱歉，处理表情包时出现错误"

    def process_text_message(self, content: str, who: str, source: str = "wechat", is_self_message: bool = False):
        """处理文本消息"""
        try:
            # 如果内容为空，直接返回
            if not content or not content.strip():
                return None
                
            # 检查是否是表情包请求
            if hasattr(self, 'emoji_handler') and self.emoji_handler and self.emoji_handler.is_emoji_request(content):
                logger.info(f"检测到表情包请求: {content}")
                return self._handle_emoji_message(content, who, who, is_self_message)
                
            # 检查是否是随机图片请求
            if hasattr(self, 'image_handler') and self.image_handler and self.image_handler.is_random_image_request(content):
                logger.info(f"检测到随机图片请求: {content}")
                return self._handle_random_image_request(content, who, None, who, False)
                
            # 检查是否是图像生成请求
            if hasattr(self, 'image_handler') and self.image_handler and self.image_handler.is_image_generation_request(content):
                logger.info(f"检测到图像生成请求: {content}")
                return self._handle_image_generation_request(content, who, None, who, False)
                
            # 其他处理逻辑...
            
            # 获取API回复
            # 添加历史记忆等
            
            # 调用API获取响应
            response = self.get_api_response(content, who)
            
            # 发送回复消息
            if response and not self.is_debug:
                # 分割并发送消息
                split_messages = self._split_message_for_sending(response)
                self._send_split_messages(split_messages, who)
                
            return response
            
        except Exception as e:
            logger.error(f"处理文本消息失败: {str(e)}", exc_info=True)
            return "抱歉，处理您的消息时出现错误"

    def add_to_queue(self, chat_id, content, sender_name, username, is_group=False):
        """
        将消息添加到处理队列
        
        Args:
            chat_id: 聊天ID
            content: 消息内容
            sender_name: 发送者名称
            username: 用户名
            is_group: 是否是群聊消息
        
        Returns:
            None
        """
        try:
            logger.info(f"添加消息到队列: chat_id={chat_id}, sender={sender_name}, content={content[:30]}")
            return self.handle_user_message(
                content=content,
                chat_id=chat_id,
                sender_name=sender_name,
                username=username,
                is_group=is_group
            )
        except Exception as e:
            logger.error(f"添加消息到队列失败: {str(e)}")
            return None

    def _handle_uncached_message(self, content: str, chat_id: str, sender_name: str, username: str, is_group: bool, is_image_recognition: bool):
        """处理未缓存的消息"""
        try:
            logger.info(f"处理消息 - 聊天ID: {chat_id}, 发送者: {sender_name}, 是否群聊: {is_group}")
            
            # 判断是否为语音请求
            if self._is_voice_request(content):
                logger.info("检测到语音消息请求")
                return self._handle_voice_request(content, chat_id, sender_name, username, is_group)
                
            # 判断是否为随机图片请求
            if self._is_random_image_request(content):
                logger.info("检测到随机图片请求")
                return self._handle_random_image_request(content, chat_id, sender_name, username, is_group)
                
            # 判断是否为图片生成请求
            if self._is_image_generation_request(content):
                logger.info("检测到图片生成请求")
                return self._handle_image_generation_request(content, chat_id, sender_name, username, is_group)

            # 处理普通文本消息
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 添加记忆查询和上下文提取
            relevant_memories = ""
            if self.memory_handler:
                try:
                    # 获取相关记忆
                    memories = self.memory_handler.get_relevant_memories(content, username)
                    if memories and len(memories) > 0:
                        # 构建记忆上下文
                        memory_parts = []
                        for idx, mem in enumerate(memories[:3]):  # 限制为最相关的3条记忆
                            if mem.get('message') and mem.get('reply'):
                                memory_parts.append(f"记忆{idx+1}:\n用户: {mem['message']}\nAI: {mem['reply']}")
                        
                        if memory_parts:
                            relevant_memories = "\n\n与当前对话相关的记忆:\n" + "\n\n".join(memory_parts)
                            logger.info(f"添加相关记忆: {len(memory_parts)}条")
                except Exception as mem_err:
                    logger.error(f"获取记忆失败: {str(mem_err)}")
            
            # 构造完整请求
            full_content = f"[{current_time}] {content} {relevant_memories}"
            
            # 获取API响应
            response = self.get_api_response(full_content, username)
            
            if not response:
                logger.warning(f"API响应为空 - 用户: {username}")
                return None
                
            # 清理API响应内容
            cleaned_response = self._clean_ai_response(response)
            
            # 保存对话到记忆
            if self.memory_handler and content and cleaned_response:
                try:
                    self.memory_handler.remember(content, cleaned_response, username)
                    logger.info("对话已保存到记忆")
                except Exception as mem_err:
                    logger.error(f"保存记忆失败: {str(mem_err)}")
            
            # 处理响应内容
            split_messages = self._split_message_for_sending(cleaned_response)
            
            # 如果不在调试模式，发送消息
            if not self.is_debug:
                self._send_split_messages(split_messages, chat_id)
                
            return split_messages['parts']
            
        except Exception as e:
            logger.error(f"处理文本消息失败: {str(e)}", exc_info=True)
            return "抱歉，处理您的消息时出现错误"
            
    def _is_voice_request(self, content: str) -> bool:
        """判断是否为语音请求"""
        voice_keywords = ["语音回复", "用语音回答", "语音回答", "语音", "语音说"]
        return any(keyword in content for keyword in voice_keywords)
        
    def _is_random_image_request(self, content: str) -> bool:
        """判断是否为随机图片请求"""
        image_keywords = ["随机图片", "随机一张图", "随机发图", "随机图"]
        return any(keyword in content for keyword in image_keywords)
        
    def _is_image_generation_request(self, content: str) -> bool:
        """判断是否为图片生成请求"""
        generate_keywords = ["生成图片", "画一张", "画画", "绘画", "绘制", "帮我画"]
        return any(keyword in content for keyword in generate_keywords)

    def QQ_handle_text_message(self, content: str, qqid: str, sender_name: str):
        """处理 QQ 消息，调用 _handle_uncached_message 方法"""
        try:
            logger.info(f"处理QQ消息 - QQ: {qqid}, 发送者: {sender_name}")
            result = self._handle_uncached_message(
                content=content,
                chat_id=qqid,
                sender_name=sender_name,
                username=qqid,
                is_group=False,
                is_image_recognition=False
            )
            return result if result else ["抱歉，我无法回应您的消息"]
        except Exception as e:
            logger.error(f"处理QQ消息失败: {str(e)}", exc_info=True)
            return ["抱歉，处理您的消息时出现错误"]

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
from services.ai.llm_service import LLMService
from config import config
import re
import jieba

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')


class MessageHandler:
    def __init__(self, root_dir, llm: LLMService, robot_name, prompt_content, image_handler, emoji_handler, voice_handler, memory_handler,
                 is_qq=False, is_debug=False):
        self.root_dir = root_dir
        self.robot_name = robot_name
        self.prompt_content = prompt_content
        self.debug = is_debug
        # 添加消息缓存相关属性
        self.message_cache = {}  # 用户消息缓存
        self.last_message_time = {}  # 用户最后发送消息的时间
        self.message_timer = {}  # 用户消息处理定时器
        # 使用 DeepSeekAI 替换直接的 OpenAI 客户端
        # 2025-03-15修改，把deepseek改为外部注入
        self.deepseek = llm
        # 消息队列相关
        self.user_queues = {}
        self.queue_lock = threading.Lock()
        self.chat_contexts = {}

        # 微信实例
        if not is_qq:
            if is_debug:
                self.wx = None
                logger.info("调试模式跳过微信初始化")
            else:
                self.wx = WeChat()

        # 添加 handlers
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler
        self.memory_handler = memory_handler
        self.unanswered_counters = {}
        self.unanswered_timers = {}  # 新增：存储每个用户的计时器

    def save_message(self, sender_id: str, sender_name: str, message: str, reply: str, is_group: bool = False):
        """保存聊天记录到数据库和记忆"""
        # 确保sender_id不为System
        if sender_id == "System":
            # 尝试从消息内容中识别实际的接收者
            if isinstance(message, str):
                # 如果消息以@开头，提取用户名
                if message.startswith('@'):
                    sender_id = message.split()[0][1:]  # 提取@后的用户名
                else:
                    # 使用默认值或其他标识
                    sender_id = "FileHelper"

        # 保存到记忆 - 移除这一行，避免重复保存
        # 修改（2025/3/14 by Elimir) 打开了记忆这一行，进行测试
        # 修改(2025/3/15 by Elimir) 注释这一行，移除add_short_memory，改成在memory_handler中添加钩子
        # self.memory_handler.add_short_memory(message, reply, sender_id)

    def get_api_response(self, message: str, user_id: str, group_id: str = None, sender_name: str = None) -> str:
        """获取 API 回复（添加历史对话支持和缓存机制）"""
        avatar_dir = os.path.join(self.root_dir, config.behavior.context.avatar_dir)
        prompt_path = os.path.join(avatar_dir, "avatar.md")
        
        # 添加缓存机制，避免频繁读取文件
        if not hasattr(self, '_avatar_content_cache'):
            self._avatar_content_cache = {}
            self._avatar_content_timestamp = {}
        
        # 检查缓存是否有效（10分钟内有效）
        current_time = time.time()
        if prompt_path in self._avatar_content_cache and current_time - self._avatar_content_timestamp.get(prompt_path, 0) < 600:
            original_content = self._avatar_content_cache[prompt_path]
        else:
            try:
                # 读取原始提示内容（人设内容）
                with open(prompt_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
                    # 更新缓存
                    self._avatar_content_cache[prompt_path] = original_content
                    self._avatar_content_timestamp[prompt_path] = current_time
            except Exception as e:
                logger.error(f"读取人设提示文件失败: {str(e)}")
                original_content = "你是一个友好的AI助手。"  # 提供默认值
            
        try:
            # 获取最近的对话历史
            recent_history = self.memory_handler.get_relevant_memories(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",user_id)  # 获取最近5轮对话

            # 构建带有历史记录的上下文
            context = original_content + "\n\n最近的对话记录：\n"
            for hist in recent_history:
                context += f"用户: {hist['message']}\n"
                context += f"AI: {hist['reply']}\n"
            
            # 添加当前用户的输入
            context += f"\n用户: {message}\n"
            
            # 添加性能优化：对超长上下文进行截断
            max_context_length = 8000  # 设置合理的上下文长度限制
            if len(context) > max_context_length:
                logger.warning(f"上下文过长({len(context)}字符)，进行截断")
                # 保留人设部分和最新的对话
                context_parts = context.split("\n\n最近的对话记录：\n")
                if len(context_parts) > 1:
                    # 保留人设和最新的用户输入
                    avatar_part = context_parts[0]
                    user_input_part = f"\n用户: {message}\n"
                    
                    # 计算可用于历史对话的字符数
                    available_chars = max_context_length - len(avatar_part) - len(user_input_part) - 50
                    
                    # 从最近的对话开始，尽可能多地保留对话历史
                    history_lines = context_parts[1].split("\n")
                    history_part = ""
                    for line in reversed(history_lines[:-1]):  # 排除最后的用户输入
                        if len(history_part) + len(line) + 1 <= available_chars:
                            history_part = line + "\n" + history_part
                        else:
                            break
                        
                    # 重新组合上下文
                    context = f"{avatar_part}\n\n最近的对话记录：\n{history_part}{user_input_part}"
            
            # 上下文处理完成
            
            # 添加重试机制
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    return self.deepseek.get_response(message, user_id, context)
                except Exception as retry_error:
                    if attempt < max_retries - 1:
                        logger.warning(f"API调用失败，尝试重试 ({attempt+1}/{max_retries}): {str(retry_error)}")
                        time.sleep(retry_delay * (2 ** attempt))  # 指数退避
                    else:
                        raise  # 最后一次尝试失败，抛出异常
                    
        except Exception as e:
            logger.error(f"获取API回复失败: {str(e)}")
            # 降级处理：使用简化的提示
            try:
                simplified_prompt = f"{original_content}\n\n用户: {message}"
                return self.deepseek.get_response(message, user_id, simplified_prompt)
            except Exception as fallback_error:
                logger.error(f"降级处理也失败: {str(fallback_error)}")
                return f"抱歉，我暂时无法回应，请稍后再试。(错误: {str(e)[:50]}...)"

    def handle_user_message(self, content: str, chat_id: str, sender_name: str,
                            username: str, is_group: bool = False, is_image_recognition: bool = False, is_self_message: bool = False):
        """统一的消息处理入口"""
        try:
            # 验证并修正用户ID
            if not username or username == "System":
                # 从聊天ID中提取用户名，移除可能的群聊标记
                username = chat_id.split('@')[0] if '@' in chat_id else chat_id
                # 如果是文件传输助手，使用特定ID
                if username == "filehelper":
                    username = "FileHelper"
                sender_name = sender_name or username

            # 简化日志输出，只保留基本信息
            logger.info(f"处理消息 - 发送者: {sender_name}, 聊天ID: {chat_id}, 是否群聊: {is_group}")
            
            # 更新用户最后一次消息的时间（无论是用户发送的还是AI自己发送的）
            if not hasattr(self, '_last_message_times'):
                self._last_message_times = {}
            self._last_message_times[username] = datetime.now()

            # 如果是AI自己发送的消息，直接处理而不进入缓存或队列
            if is_self_message:
                logger.info(f"检测到AI自己发送的消息，直接处理")
                # 直接发送消息，不进行AI处理
                self._send_self_message(content, chat_id)
                return None  # 立即返回，不再继续处理

            # 增加重复消息检测
            message_key = f"{chat_id}_{username}_{hash(content)}"
            current_time = time.time()

            # 提取实际消息内容，去除时间戳和前缀
            actual_content = content
            # 匹配并去除时间戳和前缀，如 "(此时时间为2025-03-15 04:37:12) ta私聊对你说 "
            time_prefix_pattern = r'^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)\s+ta私聊对你说\s+'
            actual_content = re.sub(time_prefix_pattern, '', actual_content)
            
            # 获取实际消息内容的长度，用于判断是否需要缓存
            content_length = len(actual_content)
            
            # 判断是否需要缓存消息的条件：
            # 1. 如果是第一条消息且内容较短（可能是问候语或简短提问），启用缓存
            # 2. 如果用户在短时间内发送了多条消息，继续使用缓存
            should_cache = (
                # 条件1: 实际内容较短（少于20个字符）的消息总是缓存
                content_length < 20 or
                # 条件2: 用户在10秒内发送了新消息
                (username in self.last_message_time and current_time - self.last_message_time[username] < 10)
            )
            
            if should_cache:
                # 简化日志输出，减少冗余信息
                cache_reason = "实际内容较短" if content_length < 20 else "短时间内连续消息"
                
                # 取消之前的定时器
                if username in self.message_timer and self.message_timer[username]:
                    self.message_timer[username].cancel()
                    # 简化日志，不再输出取消定时器的详细信息
                
                # 添加到消息缓存
                if username not in self.message_cache:
                    self.message_cache[username] = []
                
                self.message_cache[username].append({
                    'content': content,
                    'chat_id': chat_id,
                    'sender_name': sender_name,
                    'is_group': is_group,
                    'is_image_recognition': is_image_recognition,
                    'timestamp': current_time  # 添加时间戳
                })
                
                # 只在第一条消息时输出日志，减少日志量
                msg_count = len(self.message_cache[username])
                if msg_count == 1:
                    logger.info(f"用户 {username} 开始缓存消息")
                
                # 智能设置定时器时间：根据用户打字速度和消息长度动态调整
                typing_speed = self._estimate_typing_speed(username)
                
                # 修改等待时间计算逻辑，增加基础等待时间，防止提前回复
                if len(self.message_cache[username]) == 1:
                    # 第一条消息，给予更长的等待时间
                    wait_time = 12.0  # 增加到12秒等待时间，给用户足够时间输入后续消息
                else:
                    # 后续消息，根据打字速度和消息长度动态调整，并增加基础等待时间
                    wait_time = 8.0 + min(10.0, len(actual_content) * typing_speed)  # 最多等待18秒
                
                # 设置新的定时器
                timer = threading.Timer(wait_time, self._process_cached_messages, args=[username])
                timer.start()
                self.message_timer[username] = timer
                
                # 更新最后消息时间
                self.last_message_time[username] = current_time
                return None
            
            # 更新最后消息时间
            self.last_message_time[username] = current_time

            # 如果没有需要缓存的消息，直接处理
            if username not in self.message_cache or not self.message_cache[username]:
                logger.info(f"用户 {username} 没有缓存消息，直接处理当前消息")
                # 检查是否为语音请求
                if self.voice_handler.is_voice_request(content):
                    return self._handle_voice_request(content, chat_id, sender_name, username, is_group)

                # 检查是否为随机图片请求
                elif self.image_handler.is_random_image_request(content):
                    return self._handle_random_image_request(content, chat_id, sender_name, username, is_group)

                # 检查是否为图像生成请求，但跳过图片识别结果
                elif not is_image_recognition and self.image_handler.is_image_generation_request(content):
                    return self._handle_image_generation_request(content, chat_id, sender_name, username, is_group)

                # 检查是否为文件处理请求
                elif content and content.lower().endswith(('.txt', '.docx', '.doc', '.ppt', '.pptx', '.xlsx', '.xls')):
                    return self._handle_file_request(content, chat_id, sender_name, username, is_group)

                # 处理普通文本回复
                else:
                    return self._handle_text_message(content, chat_id, sender_name, username, is_group,
                                                 is_image_recognition)
            
            # 如果有缓存的消息，添加当前消息并一起处理
            logger.info(f"用户 {username} 有缓存消息，将当前消息添加到缓存并一起处理")
            self.message_cache[username].append({
                'content': content,
                'chat_id': chat_id,
                'sender_name': sender_name,
                'is_group': is_group,
                'is_image_recognition': is_image_recognition,
                'timestamp': current_time  # 添加时间戳
            })
            return self._process_cached_messages(username)

        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return None

    def _process_cached_messages(self, username: str):
        """处理缓存的消息"""
        try:
            if not self.message_cache.get(username):
                logger.info(f"用户 {username} 没有需要处理的缓存消息")
                return None
            
            # 简化日志输出，只显示总数
            msg_count = len(self.message_cache[username])
            logger.info(f"处理缓存 - 用户: {username}, 消息数: {msg_count}")
            
            # 获取最近的对话记录作为上下文
            recent_history = self.memory_handler.get_relevant_memories(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",username)
            context = ""
            if recent_history:
                # 修改：只添加一次上下文提示词
                context = f"{recent_history[0]['message']}(上次的对话内容，只是提醒)"
                # 简化日志，不再输出加载上下文的详细信息

            # 合并所有缓存的消息，但优先处理新消息
            messages = self.message_cache[username]
            image_messages = [msg for msg in messages if msg.get('is_image_recognition', False)]
            text_messages = [msg for msg in messages if not msg.get('is_image_recognition', False)]
            
            # 简化日志输出，只在有图片消息时才显示分类信息
            if image_messages:
                logger.info(f"消息分类 - 图片: {len(image_messages)}, 文本: {len(text_messages)}")
            
            # 按照图片识别消息优先的顺序合并内容
            combined_messages = image_messages + text_messages
            
            # 智能合并消息内容，检测是否有断句符号
            combined_content = context
            
            # 创建一个列表来存储清理后的消息内容，用于日志显示
            cleaned_messages = []
            
            # 新增：统计用户消息的总字数和句数
            total_chars = 0
            total_sentences = 0
            sentence_endings = {'。', '！', '？', '!', '?', '.'}
            
            for i, msg in enumerate(combined_messages):
                # 获取原始内容
                original_content = msg.get('content', '')
                
                # 预处理消息内容，去除时间戳和前缀
                content = original_content
                
                # 过滤时间戳
                time_pattern = r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]'
                content = re.sub(time_pattern, '', content)
                
                # 过滤通用模式
                general_pattern = r'\[\d[^\]]*\]|\[\d+\]'
                content = re.sub(general_pattern, '', content)
                
                # 过滤消息前缀，如 "(此时时间为2025-03-15 04:37:12) ta私聊对你说 "
                time_prefix_pattern = r'^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)\s+ta私聊对你说\s+'
                content = re.sub(time_prefix_pattern, '', content)
                
                # 移除重复的上下文提示词
                reminder_pattern = r'\(上次的对话内容，只是提醒[^)]*\)'
                content = re.sub(reminder_pattern, '', content)
                
                # 如果内容有变化，记录清理后的内容
                if content != original_content:
                    cleaned_messages.append(content)
                else:
                    cleaned_messages.append(content)  # 即使没有变化也添加，确保所有消息都被记录
                
                # 新增：统计字数
                total_chars += len(content)
                
                # 新增：统计句数
                for char in content:
                    if char in sentence_endings:
                        total_sentences += 1
                
                # 添加到合并内容
                if i > 0 and not content.startswith('\\'):
                    combined_content += " " + content
                else:
                    combined_content += content
            
            # 确保句子数至少为1
            total_sentences = max(1, total_sentences)
            
            # 只输出一次清理后的所有消息内容，使用更简洁的格式
            if cleaned_messages:
                # 如果消息太多，只显示前3条和最后1条
                if len(cleaned_messages) > 4:
                    display_msgs = cleaned_messages[:3] + ["..."] + [cleaned_messages[-1]]
                    logger.info(f"合并消息: {' | '.join(display_msgs)}")
                else:
                    logger.info(f"合并消息: {' | '.join(cleaned_messages)}")
            
            # 使用最后一条消息的参数
            last_message = messages[-1]
            
            # 计算回复长度比例
            response_ratio = self._calculate_response_length_ratio(total_chars)
            target_chars = int(total_chars * response_ratio)
            target_sentences = int(total_sentences * response_ratio)
            
            # 确保目标句子数至少为1
            target_sentences = max(1, target_sentences)
            
            # 在合并内容中添加字数和句数控制提示
            combined_content += f"\n\n请注意：你的回复应当与用户消息的长度相当，控制在约{target_chars}个字符和{target_sentences}个句子左右。"

            # 处理合并后的消息
            logger.info(f"处理合并消息 - 用户: {username}")
            result = self._handle_text_message(
                combined_content,
                last_message['chat_id'],
                last_message['sender_name'],
                username,
                last_message['is_group'],
                any(msg.get('is_image_recognition', False) for msg in messages)
            )

            # 清理缓存
            self.message_cache[username] = []
            if username in self.message_timer:
                self.message_timer[username] = None
            
            return result

        except Exception as e:
            logger.error(f"处理缓存消息失败: {str(e)}", exc_info=True)
            return None

    def _estimate_typing_speed(self, username: str) -> float:
        """估计用户的打字速度（秒/字）"""
        # 如果没有足够的历史消息，使用默认值
        if username not in self.message_cache or len(self.message_cache[username]) < 2:
            # 根据用户ID是否存在于last_message_time中返回不同的默认值
            # 如果是新用户，给予更长的等待时间
            if username not in self.last_message_time:
                return 0.2  # 新用户默认速度：每字0.2秒，增加等待时间
            return 0.15  # 已知用户默认速度：每字0.15秒，增加等待时间
        
        # 获取最近的两条消息
        messages = self.message_cache[username]
        if len(messages) < 2:
            return 0.15
        
        # 按时间戳排序，确保我们比较的是连续的消息
        recent_msgs = sorted(messages, key=lambda x: x.get('timestamp', 0))[-2:]
        
        # 计算时间差和字符数
        time_diff = recent_msgs[1].get('timestamp', 0) - recent_msgs[0].get('timestamp', 0)
        char_count = len(recent_msgs[0].get('content', ''))
        
        # 如果时间差或字符数无效，使用默认值
        if time_diff <= 0 or char_count <= 0:
            return 0.15
        
        # 计算打字速度（秒/字）
        typing_speed = time_diff / char_count
        
        # 应用平滑因子，避免极端值
        # 如果我们有历史记录的打字速度，将其纳入考虑
        if hasattr(self, '_typing_speeds') and username in self._typing_speeds:
            prev_speed = self._typing_speeds[username]
            # 使用加权平均，新速度权重0.3，历史速度权重0.7
            typing_speed = 0.3 * typing_speed + 0.7 * prev_speed
        
        # 存储计算出的打字速度
        if not hasattr(self, '_typing_speeds'):
            self._typing_speeds = {}
        self._typing_speeds[username] = typing_speed
        
        # 限制在合理范围内：0.1秒/字 到 1.0秒/字
        # 增加打字速度范围的下限和上限，使其更适合更长的等待时间
        return max(0.1, min(1.0, typing_speed))

    def _calculate_response_length_ratio(self, user_message_length: int) -> float:
        """计算回复长度与用户消息的比例"""
        # 基础比例从1.0开始，确保回复不会太短
        base_ratio = 1.0
        
        # 根据用户消息长度动态调整比例
        if user_message_length < 10:  # 非常短的消息
            ratio = base_ratio * 3.0  # 回复可以长一些
        elif user_message_length < 30:  # 较短的消息
            ratio = base_ratio * 2.5
        elif user_message_length < 50:  # 中等长度
            ratio = base_ratio * 2.0
        elif user_message_length < 100:  # 较长消息
            ratio = base_ratio * 1.8
        else:  # 很长的消息
            ratio = base_ratio * 1.5
        
        return ratio

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

        # 异步保存消息记录
        threading.Thread(target=self.save_message,
                         args=(username, sender_name, content, reply, is_group)).start()
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

            # 异步保存消息记录
            threading.Thread(target=self.save_message,
                             args=(username, sender_name, content, reply, is_group)).start()
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

            # 异步保存消息记录
            threading.Thread(target=self.save_message,
                             args=(username, sender_name, content, reply, is_group)).start()
            return reply
        return None

    def _filter_action_emotion(self, text):
        """智能过滤括号内的动作和情感描述，保留颜文字"""
        # 缓存常用的颜文字和动作关键词，避免重复创建
        if not hasattr(self, '_emoticon_chars_set'):
            self._emoticon_chars_set = set(
                '（()）~～‿⁀∀︿⌒▽△□◇○●ˇ＾∇＿゜◕ω・ノ丿╯╰つ⊂＼／┌┐┘└°△▲▽▼◇◆○●◎■□▢▣▤▥▦▧▨▩♡♥ღ☆★✡⁂✧✦❈❇✴✺✹✸✷✶✵✳✲✱✰✯✮✭✬✫✪✩✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁✀✿✾✽✼✻✺✹✸✷✶✵✴✳✲✱✰✯✮✭✬✫✪✩✨✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁❤♪♫♬♩♭♮♯°○◎●◯◐◑◒◓◔◕◖◗¤☼☀☁☂☃☄★☆☎☏⊙◎☺☻☯☭♠♣♧♡♥❤❥❣♂♀☿❀❁❃❈❉❊❋❖☠☢☣☤☥☦☧☨☩☪☫☬☭☮☯☸☹☺☻☼☽☾☿♀♁♂♃♄♆♇♈♉♊♋♌♍♎♏♐♑♒♓♔♕♖♗♘♙♚♛♜♝♞♟♠♡♢♣♤♥♦♧♨♩♪♫♬♭♮♯♰♱♲♳♴♵♶♷♸♹♺♻♼♽♾♿⚀⚁⚂⚃⚄⚆⚇⚈⚉⚊⚋⚌⚍⚎⚏⚐⚑⚒⚓⚔⚕⚖⚗⚘⚙⚚⚛⚜⚝⚞⚟')
        
        if not hasattr(self, '_action_keywords'):
            self._action_keywords = {'微笑', '笑', '哭', '叹气', '摇头', '点头', '皱眉', '思考',
                           '无奈', '开心', '生气', '害羞', '紧张', '兴奋', '疑惑', '惊讶',
                           '叹息', '沉思', '撇嘴', '歪头', '摊手', '耸肩', '抱抱', '拍拍',
                           '摸摸头', '握手', '挥手', '鼓掌', '捂脸', '捂嘴', '翻白眼',
                           '叉腰', '双手合十', '竖起大拇指', '比心', '摸摸', '拍肩', '戳戳',
                           '摇晃', '蹦跳', '转圈', '倒地', '趴下', '站起', '坐下'}
    
        # 使用正则表达式缓存
        if not hasattr(self, '_cn_pattern'):
            self._cn_pattern = re.compile(r'（[^）]*）')
            self._en_pattern = re.compile(r'\([^\)]*\)')
    
        def is_emoticon(content):
            """判断是否为颜文字"""
            text = content.strip('（()）')  # 去除外围括号
            if not text:  # 如果去除括号后为空，返回False
                return False
            emoticon_char_count = sum(1 for c in text if c in self._emoticon_chars_set)
            return emoticon_char_count / len(text) > 0.5  # 如果超过50%是颜文字字符则认为是颜文字
    
        def contains_action_keywords(content):
            """检查是否包含动作或情感描述关键词"""
            text = content.strip('（()）')  # 去除外围括号
            # 使用jieba分词，检查是否包含动作关键词
            words = set(jieba.cut(text))
            return bool(words & self._action_keywords)
    
        def smart_filter(match):
            content = match.group(0)
            # 如果是颜文字，保留
            if is_emoticon(content):
                return content
            # 如果包含动作关键词，移除
            elif contains_action_keywords(content):
                return ''
            # 如果无法判断，保留原文
            return content
    
        # 处理中文括号
        text = self._cn_pattern.sub(smart_filter, text)
        # 处理英文括号
        text = self._en_pattern.sub(smart_filter, text)
    
        return text

    def _handle_file_request(self, file_path, chat_id, sender_name, username, is_group):
        """处理文件请求"""
        logger.info(f"处理文件请求: {file_path}")

        try:

            from handlers.file import FileHandler
            files_handler = FileHandler(self.root_dir)

            target_path = files_handler.move_to_files_dir(file_path)
            logger.info(f"文件已转存至: {target_path}")

            # 获取文件类型
            file_type = files_handler.get_file_type(target_path)
            logger.info(f"文件类型: {file_type}")

            # 读取文件内容
            file_content = files_handler.read_file_content(target_path)
            logger.info(f"成功读取文件内容，长度: {len(file_content)} 字符")

            prompt = f"你收到了一个{file_type}文件，文件内容如下:\n\n{file_content}\n\n请帮我分析这个文件的内容，提取关键信息，根据角色设定，给出你的回答。"

            # 获取 AI 回复
            reply = self.get_api_response(prompt, chat_id)
            if "</think>" in reply:
                think_content, reply = reply.split("</think>", 1)
                logger.info("\n思考过程:")
                logger.info(think_content.strip())
                reply = reply.strip()

            # 在群聊中添加@
            if is_group:
                reply = f"@{sender_name} \n{reply}"
            else:
                reply = f"{reply}"

            # 发送回复
            try:
                # 增强型智能分割器
                delayed_reply = []
                current_sentence = []
                ending_punctuations = {'。', '！', '？', '!', '?', '…', '……'}
                split_symbols = {'\\', '|', '￤', '\n', '\\n'}  # 支持多种手动分割符

                for idx, char in enumerate(reply):
                    # 处理手动分割符号（优先级最高）
                    if char in split_symbols:
                        if current_sentence:
                            delayed_reply.append(''.join(current_sentence).strip())
                        current_sentence = []
                        continue

                    current_sentence.append(char)

                    # 处理中文标点和省略号
                    if char in ending_punctuations:
                        # 排除英文符号在短句中的误判（如英文缩写）
                        if char in {'!', '?'} and len(current_sentence) < 4:
                            continue

                        # 处理连续省略号
                        if char == '…' and idx > 0 and reply[idx - 1] == '…':
                            if len(current_sentence) >= 3:  # 至少三个点形成省略号
                                delayed_reply.append(''.join(current_sentence).strip())
                                current_sentence = []
                        else:
                            delayed_reply.append(''.join(current_sentence).strip())
                            current_sentence = []

                # 处理剩余内容
                if current_sentence:
                    delayed_reply.append(''.join(current_sentence).strip())
                delayed_reply = [s for s in delayed_reply if s]  # 过滤空内容

                # 发送分割后的文本回复, 并控制时间间隔
                for part in delayed_reply:
                    self.wx.SendMsg(msg=part, who=chat_id)
                    time.sleep(random.uniform(0.5, 1.5))  # 稍微增加一点随机性

            except Exception as e:
                logger.error(f"发送文件分析结果失败: {str(e)}")
                self.wx.SendMsg(msg="抱歉，文件分析结果发送失败", who=chat_id)

            # 异步保存消息记录
            threading.Thread(target=self.save_message,
                             args=(username, sender_name, prompt, reply, is_group)).start()

            # 重置计数器（如果大于0）
            if self.unanswered_counters.get(username, 0) > 0:
                self.unanswered_counters[username] = 0
                logger.info(f"用户 {username} 的未回复计数器已重置")

            return reply

        except Exception as e:
            logger.error(f"处理文件失败: {str(e)}", exc_info=True)
            error_msg = f"抱歉，文件处理过程中出现错误: {str(e)}"
            if is_group:
                error_msg = f"@{sender_name} {error_msg}"
            self.wx.SendMsg(msg=error_msg, who=chat_id)
            return None

    def _safe_send_msg(self, msg, who, max_retries=None, char_by_char=False):
        """安全发送消息，支持重试和字符逐个发送模式"""
        if not self.wx:
            logger.warning("WeChat对象为None，无法发送消息")
            return False

        # 默认重试次数
        if max_retries is None:
            max_retries = 3

        # 尝试发送消息
        for attempt in range(max_retries):
            try:
                if char_by_char and len(msg) > 1:
                    # 字符逐个发送模式
                    for char in msg:
                        self.wx.SendMsg(msg=char, who=who)
                        time.sleep(0.05)  # 每个字符间隔50毫秒
                    return True
                else:
                    # 普通发送模式
                    self.wx.SendMsg(msg=msg, who=who)
                    return True
            except Exception as e:
                logger.error(f"发送消息失败 (尝试 {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    # 指数退避策略
                    time.sleep(0.5 * (2 ** attempt))
                else:
                    logger.error(f"发送消息最终失败: {msg[:30]}...")
                    return False
        
        return False

    def _handle_text_message(self, content, chat_id, sender_name, username, is_group, is_image_recognition=False):
        """处理普通文本消息"""
        # 添加正则表达式过滤时间戳
        time_pattern = r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]'
        content = re.sub(time_pattern, '', content)

        # 更通用的模式
        general_pattern = r'\[\d[^\]]*\]|\[\d+\]'
        content = re.sub(general_pattern, '', content)

        logger.info("处理普通文本回复")

        # 获取或初始化未回复计数器
        counter = self.unanswered_counters.get(username, 0)

        # 定义结束关键词
        end_keywords = [
            "结束", "再见", "拜拜", "下次聊", "先这样", "告辞", "bye", "晚点聊", "回头见",
            "稍后", "改天", "有空聊", "去忙了", "暂停", "待一会儿", "过一会儿", "晚安", "休息",
            "走了", "撤了", "闪了", "不聊了", "断了", "下线", "离开", "停", "歇", "退"
        ]

        # 检查消息中是否包含结束关键词
        is_end_of_conversation = any(keyword in content for keyword in end_keywords)
        raw_content = content
        # 记录一个raw_content用于存到记忆中
        if is_end_of_conversation:
            # 如果检测到结束关键词，在消息末尾添加提示
            content += "\n请你回应用户的结束语"
            logger.info(f"检测到对话结束关键词，尝试生成更自然的结束语")
        else:
            # 此处修改(2025/03/14 by eliver) 不是结束时则添加记忆到内容中
            memories = self.memory_handler.get_relevant_memories(content, username)
            content += f"\n以上是用户的沟通内容；以下是记忆中检索的内容：{';'.join(memories)}\n请你根据以上内容回复用户的消息。"

        # 获取 API 回复
        # logger.info(f"生成依据内容 {content}")
        reply = self.get_api_response(content, chat_id)
        if "</think>" in reply:
            think_content, reply = reply.split("</think>", 1)
            logger.info("\n思考过程:")
            logger.info(think_content.strip())
            logger.info(reply.strip())
        else:
            logger.info("\nAI回复:")
            logger.info(reply)

            # 过滤括号内的动作和情感描述 - 移除重复调用
        reply = self._filter_action_emotion(reply)

        if is_group:
            reply = f"@{sender_name} {reply}"

        try:
            # 增强型智能分割器 - 优化版
            delayed_reply = []
            current_sentence = []
            ending_punctuations = {'。', '！', '？', '!', '?', '…', '……'}
            split_symbols = {'\\', '|', '￤', '\n', '\\n'}  # 支持多种手动分割符
            last_split_idx = -1  # 记录上一次分割的位置，防止重复分割

            for idx, char in enumerate(reply):
                # 处理手动分割符号（优先级最高）
                if char in split_symbols:
                    if current_sentence and idx > last_split_idx:
                        delayed_reply.append(''.join(current_sentence).strip())
                        last_split_idx = idx
                    current_sentence = []
                    continue

                current_sentence.append(char)

                # 处理中文标点和省略号
                if char in ending_punctuations:
                    # 排除英文符号在短句中的误判（如英文缩写）
                    if char in {'!', '?'} and len(current_sentence) < 4:
                        continue

                    # 处理连续省略号
                    if char == '…' and idx > 0 and reply[idx - 1] == '…':
                        if len(current_sentence) >= 3 and idx > last_split_idx:  # 至少三个点形成省略号
                            delayed_reply.append(''.join(current_sentence).strip())
                            last_split_idx = idx
                            current_sentence = []
                    elif idx > last_split_idx:  # 确保不会在同一位置重复分割
                        delayed_reply.append(''.join(current_sentence).strip())
                        last_split_idx = idx
                        current_sentence = []

            # 处理剩余内容
            if current_sentence:
                delayed_reply.append(''.join(current_sentence).strip())

            # 过滤空内容和去重
            delayed_reply = [s for s in delayed_reply if s]  # 过滤空内容
            # 去除完全相同的相邻句子
            if len(delayed_reply) > 1:
                unique_reply = [delayed_reply[0]]
                for i in range(1, len(delayed_reply)):
                    if delayed_reply[i] != delayed_reply[i - 1]:
                        unique_reply.append(delayed_reply[i])
                delayed_reply = unique_reply

            # 记录已发送的消息，防止重复发送
            sent_messages = set()

            # 发送分割后的文本回复
            for part in delayed_reply:
                if part not in sent_messages:
                    # 计算模拟输入时间：假设每个字符需要0.1秒
                    input_time = len(part) * 0.1
                    # 模拟粘贴文本到输入框的时间
                    time.sleep(0.2)  # 粘贴操作时间
                    # 模拟阅读和点击发送按钮的时间
                    time.sleep(input_time + random.uniform(1, 2))  # 阅读和点击发送按钮的时间

                    # 添加对wx对象的检查
                    if self.wx:
                        self.wx.SendMsg(msg=part, who=chat_id)
                        sent_messages.add(part)
                    else:
                        if self.debug is False:
                            logger.error("WeChat对象为None，无法发送消息")
                            return delayed_reply
                        
                else:
                    logger.info(f"跳过重复内容: {part[:20]}...")

            # 检查回复中是否包含情感关键词并发送表情包
            logger.info("开始检查AI回复的情感关键词")
            emotion_detected = False

            if not hasattr(self.emoji_handler, 'emotion_map'):
                logger.error("emoji_handler 缺少 emotion_map 属性")
                return delayed_reply

            for emotion, keywords in self.emoji_handler.emotion_map.items():
                if not keywords:  # 跳过空的关键词列表
                    continue

                if any(keyword in reply for keyword in keywords):
                    emotion_detected = True
                    logger.info(f"在回复中检测到情感: {emotion}")

                    emoji_path = self.emoji_handler.get_emotion_emoji(reply)
                    if emoji_path:
                        # try:
                        #     self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                        #     logger.info(f"已发送情感表情包: {emoji_path}")
                        # except Exception as e:
                        #     logger.error(f"发送表情包失败: {str(e)}")
                        delayed_reply.append(emoji_path)  #在发送消息队列后增加path，由响应器处理
                    else:
                        logger.warning(f"未找到对应情感 {emotion} 的表情包")
                    break

            if not emotion_detected:
                logger.info("未在回复中检测到明显情感")
        except Exception as e:
            logger.error(f"发送回复失败: {str(e)}")
            return delayed_reply

        # 异步保存消息记录
        threading.Thread(target=self.save_message,
                         args=(username, sender_name, raw_content, reply)).start()
        # 重置计数器（如果大于0）
        if self.unanswered_counters.get(username, 0) > 0:
            self.unanswered_counters[username] = 0
            logger.info(f"用户 {username} 的未回复计数器: {self.unanswered_counters[username]}")

        return delayed_reply

    def increase_unanswered_counter(self, username: str):
        """增加未回复计数器"""
        with self.queue_lock:
            current_time = time.time()

            # 获取上次回复时间
            last_reply_time = getattr(self, '_last_reply_times', {}).get(username, 0)

            # 如果没有_last_reply_times属性，创建它
            if not hasattr(self, '_last_reply_times'):
                self._last_reply_times = {}

            # 检查是否超过30分钟未回复
            if current_time - last_reply_time > 1800:  # 1800秒 = 30分钟
                if username in self.unanswered_counters:
                    self.unanswered_counters[username] += 1
                else:
                    self.unanswered_counters[username] = 1

                # 更新最后回复时间
                self._last_reply_times[username] = current_time
                logger.info(f"用户 {username} 超过30分钟未回复，计数器增加到: {self.unanswered_counters[username]}")

    #以下是onebot QQ方法实现
    def add_to_queue(self, chat_id: str, content: str, sender_name: str,
                     username: str, is_group: bool = False, is_self_message: bool = False):
        """添加消息到队列"""
        with self.queue_lock:
            if chat_id not in self.user_queues:
                self.user_queues[chat_id] = []
            self.user_queues[chat_id].append({
                'content': content,
                'sender_name': sender_name,
                'username': username,
                'is_group': is_group,
                'is_self_message': is_self_message
            })

    def process_messages(self, chat_id: str):
        """处理指定聊天的消息队列"""
        with self.queue_lock:
            if chat_id not in self.user_queues or not self.user_queues[chat_id]:
                return
            message = self.user_queues[chat_id].pop(0)
            
        # 处理消息
        self.handle_user_message(
            message['content'],
            chat_id,
            message['sender_name'],
            message['username'],
            message['is_group'],
            False,  # 不是图像识别
            message['is_self_message']
        )

    def QQ_handle_voice_request(self, content, qqid, sender_name):
        """处理QQ来源的语音请求"""
        logger.info("处理语音请求")
        reply = self.get_api_response(content, qqid)
        if "</think>" in reply:
            reply = reply.split("</think>", 1)[1].strip()

        voice_path = self.voice_handler.generate_voice(reply)
        # 异步保存消息记录
        threading.Thread(target=self.save_message,
                         args=(qqid, sender_name, content, reply, False)).start()
        if voice_path:
            return voice_path
        else:
            return reply

    def QQ_handle_random_image_request(self, content, qqid, sender_name):
        """处理随机图片请求"""
        logger.info("处理随机图片请求")
        image_path = self.image_handler.get_random_image()
        if image_path:
            reply = "给主人你找了一张好看的图片哦~"
            threading.Thread(target=self.save_message, args=(qqid, sender_name, content, reply, False)).start()

            return image_path
            # 异步保存消息记录
        return None

    def QQ_handle_image_generation_request(self, content, qqid, sender_name):
        """处理图像生成请求"""
        logger.info("处理画图请求")
        try:
            image_path = self.image_handler.generate_image(content)
            if image_path:
                reply = "这是按照主人您的要求生成的图片\\(^o^)/~"
                threading.Thread(target=self.save_message,
                                 args=(qqid, sender_name, content, reply, False)).start()

                return image_path
                # 异步保存消息记录
            else:
                reply = "抱歉主人，图片生成失败了..."
                threading.Thread(target=self.save_message,
                                 args=(qqid, sender_name, content, reply, False)).start()
            return None
        except:
            reply = "抱歉主人，图片生成失败了..."
            threading.Thread(target=self.save_message,
                             args=(qqid, sender_name, content, reply, False)).start()
            return None

    def QQ_handle_text_message(self, content, qqid, sender_name):
        """处理普通文本消息"""
        # 添加正则表达式过滤时间戳
        time_pattern = r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]'
        content = re.sub(time_pattern, '', content)

        # 更通用的模式
        general_pattern = r'\[\d[^\]]*\]|\[\d+\]'
        content = re.sub(general_pattern, '', content)

        logger.info("处理普通文本回复")

        # 定义结束关键词
        end_keywords = [
            "结束", "再见", "拜拜", "下次聊", "先这样", "告辞", "bye", "晚点聊", "回头见",
            "稍后", "改天", "有空聊", "去忙了", "暂停", "待一会儿", "过一会儿", "晚安", "休息",
            "走了", "撤了", "闪了", "不聊了", "断了", "下线", "离开", "停", "歇", "退"
        ]

        # 检查消息中是否包含结束关键词
        is_end_of_conversation = any(keyword in content for keyword in end_keywords)
        if is_end_of_conversation:
            # 如果检测到结束关键词，在消息末尾添加提示
            content += "\n请以你的身份回应用户的结束语。"
            logger.info(f"检测到对话结束关键词，尝试生成更自然的结束语")

        # 获取 API 回复, 需要传入 username
        reply = self.get_api_response(content, qqid)
        if "</think>" in reply:
            think_content, reply = reply.split("</think>", 1)
            logger.info("\n思考过程:")
            logger.info(think_content.strip())
            logger.info(reply.strip())
        else:
            logger.info("\nAI回复:")
            logger.info(reply)

            # 过滤括号内的动作和情感描述
        reply = self._filter_action_emotion(reply)

        try:
            # 增强型智能分割器 - 优化版
            delayed_reply = []
            current_sentence = []
            ending_punctuations = {'。', '！', '？', '!', '?', '…', '……'}
            split_symbols = {'\\', '|', '￤', '\n', '\\n'}  # 支持多种手动分割符
            last_split_idx = -1  # 记录上一次分割的位置，防止重复分割

            for idx, char in enumerate(reply):
                # 处理手动分割符号（优先级最高）
                if char in split_symbols:
                    if current_sentence and idx > last_split_idx:
                        delayed_reply.append(''.join(current_sentence).strip())
                        last_split_idx = idx
                    current_sentence = []
                    continue

                current_sentence.append(char)

                # 处理中文标点和省略号
                if char in ending_punctuations:
                    # 排除英文符号在短句中的误判（如英文缩写）
                    if char in {'!', '?'} and len(current_sentence) < 4:
                        continue

                    # 处理连续省略号
                    if char == '…' and idx > 0 and reply[idx - 1] == '…':
                        if len(current_sentence) >= 3 and idx > last_split_idx:  # 至少三个点形成省略号
                            delayed_reply.append(''.join(current_sentence).strip())
                            last_split_idx = idx
                            current_sentence = []
                    elif idx > last_split_idx:  # 确保不会在同一位置重复分割
                        delayed_reply.append(''.join(current_sentence).strip())
                        last_split_idx = idx
                        current_sentence = []

            # 处理剩余内容
            if current_sentence:
                delayed_reply.append(''.join(current_sentence).strip())

            # 过滤空内容和去重
            delayed_reply = [s for s in delayed_reply if s]  # 过滤空内容
            # 去除完全相同的相邻句子
            if len(delayed_reply) > 1:
                unique_reply = [delayed_reply[0]]
                for i in range(1, len(delayed_reply)):
                    if delayed_reply[i] != delayed_reply[i - 1]:
                        unique_reply.append(delayed_reply[i])
                delayed_reply = unique_reply

            # 检查回复中是否包含情感关键词并发送表情包
            logger.info("开始检查AI回复的情感关键词")
            emotion_detected = False

            if not hasattr(self.emoji_handler, 'emotion_map'):
                logger.error("emoji_handler 缺少 emotion_map 属性")
                return delayed_reply  # 直接返回分割后的文本，在控制台打印error

            for emotion, keywords in self.emoji_handler.emotion_map.items():
                if not keywords:  # 跳过空的关键词列表
                    continue

                if any(keyword in reply for keyword in keywords):
                    emotion_detected = True
                    logger.info(f"在回复中检测到情感: {emotion}")

                    emoji_path = self.emoji_handler.get_emotion_emoji(reply)
                    if emoji_path:
                        # try:
                        #     self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                        #     logger.info(f"已发送情感表情包: {emoji_path}")
                        # except Exception as e:
                        #     logger.error(f"发送表情包失败: {str(e)}")
                        delayed_reply.append(emoji_path)  #在发送消息队列后增加path，由响应器处理
                    else:
                        logger.warning(f"未找到对应情感 {emotion} 的表情包")
                    break

            if not emotion_detected:
                logger.info("未在回复中检测到明显情感")
        except Exception as e:
            logger.error(f"消息处理过程中发生错误: {str(e)}")
        # 异步保存消息记录
        threading.Thread(target=self.save_message,
                         args=(qqid, sender_name, content, reply, False)).start()
        return delayed_reply

    def _split_message_for_sending(self, reply):
        """智能分割消息，提高可读性和发送效率"""
        if not reply:
            return []
        
        # 定义分割标记
        ending_punctuations = {'。', '！', '？', '!', '?', '…', '……'}
        split_symbols = {'\\', '|', '￤', '\n', '\\n'}  # 支持多种手动分割符
        
        # 初始化变量
        delayed_reply = []
        current_sentence = []
        last_split_idx = -1  # 记录上一次分割的位置，防止重复分割
        
        # 智能分割
        for idx, char in enumerate(reply):
            # 处理手动分割符号（优先级最高）
            if char in split_symbols:
                if current_sentence and idx > last_split_idx:
                    delayed_reply.append(''.join(current_sentence).strip())
                    last_split_idx = idx
                current_sentence = []
                continue
            
            current_sentence.append(char)
            
            # 处理中文标点和省略号
            if char in ending_punctuations:
                # 排除英文符号在短句中的误判（如英文缩写）
                if char in {'!', '?'} and len(current_sentence) < 4:
                    continue
                
                # 处理连续省略号
                if char == '…' and idx > 0 and reply[idx - 1] == '…':
                    if len(current_sentence) >= 3 and idx > last_split_idx:  # 至少三个点形成省略号
                        delayed_reply.append(''.join(current_sentence).strip())
                        last_split_idx = idx
                        current_sentence = []
                elif idx > last_split_idx:  # 确保不会在同一位置重复分割
                    delayed_reply.append(''.join(current_sentence).strip())
                    last_split_idx = idx
                    current_sentence = []
                
        # 处理剩余内容
        if current_sentence:
            delayed_reply.append(''.join(current_sentence).strip())
        
        # 过滤空内容
        delayed_reply = [s for s in delayed_reply if s]
        
        # 合并过短的消息片段（小于5个字符的片段与前一个合并）
        if len(delayed_reply) > 1:
            merged_reply = [delayed_reply[0]]
            for i in range(1, len(delayed_reply)):
                if len(delayed_reply[i]) < 5 and len(merged_reply[-1]) + len(delayed_reply[i]) < 100:
                    merged_reply[-1] += delayed_reply[i]
                else:
                    merged_reply.append(delayed_reply[i])
            delayed_reply = merged_reply
        
        # 去除完全相同的相邻句子
        if len(delayed_reply) > 1:
            unique_reply = [delayed_reply[0]]
            for i in range(1, len(delayed_reply)):
                if delayed_reply[i] != delayed_reply[i - 1]:
                    unique_reply.append(delayed_reply[i])
            delayed_reply = unique_reply
        
        return delayed_reply

    def _send_split_messages(self, messages, chat_id):
        """发送分割后的消息，支持重试和自然发送节奏"""
        if not messages:
            return False
        
        # 记录已发送的消息，防止重复发送
        sent_messages = set()
        success_count = 0
        
        # 计算自然的发送间隔
        base_interval = 0.5  # 基础间隔时间（秒）
        
        for part in messages:
            if part not in sent_messages:
                # 计算模拟输入时间：根据消息长度动态调整
                input_time = min(len(part) * 0.05, 2.0)  # 最多2秒
                
                # 模拟真实用户输入行为
                time.sleep(base_interval)  # 基础间隔
                
                # 发送消息，支持重试
                success = self._safe_send_msg(part, chat_id)
                
                if success:
                    sent_messages.add(part)
                    success_count += 1
                    
                    # 根据消息长度动态调整下一条消息的等待时间
                    wait_time = base_interval + random.uniform(0.3, 0.7) * (len(part) / 50)
                    time.sleep(wait_time)
                else:
                    logger.error(f"发送消息片段失败: {part[:30]}...")
            else:
                logger.info(f"跳过重复内容: {part[:20]}...")
            
        return success_count > 0

    def _send_self_message(self, content: str, chat_id: str):
        """发送自己的消息（用于自动回复）"""
        try:
            if self.wx:
                self.wx.SendMsg(msg=content, who=chat_id)
                logger.info(f"已发送自动消息到 {chat_id}: {content[:30]}...")
                return True
            else:
                logger.error("WeChat对象为None，无法发送自动消息")
                return False
        except Exception as e:
            logger.error(f"发送自动消息失败: {str(e)}")
            return False

    def auto_send_message(self, listen_list, robot_wx_name, get_personality_summary, is_quiet_time, start_countdown):
        """自动发送消息功能"""
        try:
            # 检查是否在安静时间
            if is_quiet_time():
                logger.info("当前是安静时间，跳过自动发送消息")
                return

            # 获取当前时间
            current_time = datetime.now()
            current_hour = current_time.hour

            # 根据时间段选择不同的问候语模板
            greeting_templates = []
            if 5 <= current_hour < 9:
                greeting_templates = [
                    "早上好啊~今天有什么计划吗？",
                    "早安！希望你今天有个好心情~",
                    "早上好，今天也要元气满满哦！",
                    "早安，昨晚睡得好吗？",
                    "早上好，今天天气怎么样？"
                ]
            elif 11 <= current_hour < 14:
                greeting_templates = [
                    "中午好，吃午饭了吗？",
                    "午安，记得午休一下哦~",
                    "到午饭时间了，今天吃什么好呢？",
                    "中午好，工作顺利吗？",
                    "午安，别忘了休息一下眼睛哦~"
                ]
            elif 17 <= current_hour < 20:
                greeting_templates = [
                    "下午好，今天过得怎么样？",
                    "傍晚好，工作结束了吗？",
                    "晚上好，今天辛苦了~",
                    "晚上好，有什么想聊的吗？",
                    "晚安，今天过得开心吗？"
                ]
            elif 21 <= current_hour < 23:
                greeting_templates = [
                    "晚上好，准备休息了吗？",
                    "晚安，祝你有个好梦~",
                    "夜深了，记得早点休息哦~",
                    "晚安，明天见~",
                    "晚上好，今天辛苦了，好好休息吧~"
                ]
            else:
                # 其他时间段不主动发送消息
                return

            # 遍历监听列表中的用户
            for user_id in listen_list:
                # 跳过机器人自己
                if user_id == robot_wx_name:
                    continue

                # 获取未回复计数器
                counter = self.unanswered_counters.get(user_id, 0)

                # 根据未回复次数决定是否发送消息
                if counter >= 2:  # 连续两次未回复，尝试主动发送消息
                    # 获取用户的个性化摘要
                    personality = get_personality_summary(user_id)
                    
                    # 选择一个随机的问候语模板
                    greeting = random.choice(greeting_templates)
                    
                    # 构建完整消息
                    if personality:
                        # 根据用户个性化信息调整消息
                        message = f"{greeting} {personality}"
                    else:
                        message = greeting
                    
                    # 发送消息
                    success = self._send_self_message(message, user_id)
                    
                    if success:
                        logger.info(f"已向用户 {user_id} 发送自动问候消息")
                        # 重置计数器
                        self.unanswered_counters[user_id] = 0
                        # 启动倒计时（如果提供了函数）
                        if start_countdown:
                            start_countdown(user_id)
                    else:
                        logger.error(f"向用户 {user_id} 发送自动问候消息失败")

        except Exception as e:
            logger.error(f"自动发送消息功能出错: {str(e)}", exc_info=True)

    def increase_unanswered_counter(self, username):
        """增加用户未回复计数器"""
        try:
            if username not in self.unanswered_counters:
                self.unanswered_counters[username] = 0
            
            self.unanswered_counters[username] += 1
            logger.info(f"增加用户 {username} 的未回复计数器: {self.unanswered_counters[username]}")
        except Exception as e:
            logger.error(f"增加未回复计数器失败: {str(e)}")

    def _init_performance_metrics(self):
        """初始化性能监控指标"""
        if not hasattr(self, '_performance_metrics'):
            self._performance_metrics = {
                'api_calls': 0,
                'api_errors': 0,
                'api_response_times': [],
                'message_count': 0,
                'avg_message_length': 0,
                'avg_response_length': 0,
                'start_time': time.time()
            }

    def _update_metrics(self, metric_type, value=None):
        """更新性能指标"""
        if not hasattr(self, '_performance_metrics'):
            self._init_performance_metrics()
        
        if metric_type == 'api_call':
            self._performance_metrics['api_calls'] += 1
        elif metric_type == 'api_error':
            self._performance_metrics['api_errors'] += 1
        elif metric_type == 'api_response_time' and value is not None:
            self._performance_metrics['api_response_times'].append(value)
        elif metric_type == 'message':
            self._performance_metrics['message_count'] += 1
        elif metric_type == 'message_length' and value is not None:
            # 更新平均消息长度
            current_avg = self._performance_metrics['avg_message_length']
            count = self._performance_metrics['message_count']
            self._performance_metrics['avg_message_length'] = (current_avg * (count - 1) + value) / count
        elif metric_type == 'response_length' and value is not None:
            # 更新平均回复长度
            current_avg = self._performance_metrics['avg_response_length']
            count = self._performance_metrics['message_count']
            self._performance_metrics['avg_response_length'] = (current_avg * (count - 1) + value) / count

    def get_performance_stats(self):
        """获取性能统计信息"""
        if not hasattr(self, '_performance_metrics'):
            self._init_performance_metrics()
        
        metrics = self._performance_metrics
        runtime = time.time() - metrics['start_time']
        hours = runtime // 3600
        minutes = (runtime % 3600) // 60
        seconds = runtime % 60
        
        # 计算API响应时间统计
        api_times = metrics['api_response_times']
        avg_api_time = sum(api_times) / len(api_times) if api_times else 0
        
        stats = {
            'runtime': f"{int(hours)}小时{int(minutes)}分{int(seconds)}秒",
            'message_count': metrics['message_count'],
            'api_calls': metrics['api_calls'],
            'api_errors': metrics['api_errors'],
            'api_error_rate': f"{(metrics['api_errors'] / metrics['api_calls'] * 100) if metrics['api_calls'] > 0 else 0:.2f}%",
            'avg_api_response_time': f"{avg_api_time:.2f}秒",
            'avg_message_length': f"{metrics['avg_message_length']:.1f}字符",
            'avg_response_length': f"{metrics['avg_response_length']:.1f}字符",
            'messages_per_hour': f"{(metrics['message_count'] / (runtime / 3600)) if runtime > 0 else 0:.1f}"
        }
        
        return stats

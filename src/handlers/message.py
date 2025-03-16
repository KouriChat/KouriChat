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
        # 2025-03-15修改，把deepseek改为外部注入
        self.deepseek = llm
        # 消息队列相关
        self.user_queues = {}
        self.queue_lock = threading.Lock()
        self.chat_contexts = {}

        # 微信实例
        self.wx = wx
        self.is_debug = is_debug  # 添加调试模式标志
        self.is_qq = is_qq

        # 添加 handlers
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler
        self.memory_handler = memory_handler
        self.unanswered_counters = {}
        self.unanswered_timers = {}  # 新增：存储每个用户的计时器
        self.MAX_MESSAGE_LENGTH = 500

        # 保存到记忆 - 移除这一行，避免重复保存
        # 修改（2025/3/14 by Elimir) 打开了记忆这一行，进行测试
        # 修改(2025/3/15 by Elimir) 注释这一行，移除add_short_memory，改成在memory_handler中添加钩子
        # self.memory_handler.add_short_memory(message, reply, sender_id)

    def get_api_response(self, message: str, user_id: str, group_id: str = None, sender_name: str = None) -> str:
        """获取API回复"""
        try:
            # 使用正确的属性名和方法名
            if not hasattr(self, 'deepseek') or self.deepseek is None:
                logger.warning("LLM服务未初始化，重新创建实例")
                # 在这里通常会初始化LLM
            
            # 修正方法名拼写错误：handel_prompt -> handle_prompt
            response = self.deepseek.llm.handel_prompt(message, user_id)
            return response
                
        except Exception as e:
            logger.error(f"获取API回复失败: {str(e)}")
            # 降级处理：使用简化的提示
            try:
                # 如果出错，可以尝试使用备用方法
                return f"抱歉，我暂时无法回应，请稍后再试。(错误: {str(e)[:50]}...)"
            except Exception as fallback_error:
                logger.error(f"降级处理也失败: {str(fallback_error)}")
                return f"服务暂时不可用，请稍后重试。"

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
            # 匹配并去除时间戳和前缀，如 "(2025-03-15 04:37:12) ta私聊对你说 "
            # 修正：同时支持圆括号和方括号格式的时间戳
            time_prefix_pattern = r'^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)?\s+ta私聊对你说\s+'
            time_prefix_pattern2 = r'^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s+ta私聊对你说\s+'
            
            if re.search(time_prefix_pattern, actual_content):
                actual_content = re.sub(time_prefix_pattern, '', actual_content)
                logger.info(f"去除时间前缀后的内容: {actual_content}")
            elif re.search(time_prefix_pattern2, actual_content):
                actual_content = re.sub(time_prefix_pattern2, '', actual_content)
                logger.info(f"去除方括号时间前缀后的内容: {actual_content}")
            
            # 获取实际消息内容的长度，用于判断是否需要缓存
            content_length = len(actual_content)
            logger.info(f"实际内容长度: {content_length}")
            
            # 修改：始终启用缓存，无论是第一条消息还是后续消息
            # 只有特定情况下才不使用缓存（如AI自己发送的消息）
            should_cache = True
            
            # 对于图片识别结果，记录日志但不改变缓存决定
            if is_image_recognition:
                logger.info(f"图片识别结果，继续使用缓存")
            
            # 记录用户最后一次消息的时间，用于计算打字速度
            self.last_message_time[username] = current_time
            
            if should_cache:
                logger.info(f"启用消息缓存 - 用户: {username}")
                
                # 检查并确保message_timer字典已初始化
                if not hasattr(self, 'message_timer') or self.message_timer is None:
                    self.message_timer = {}
                    logger.warning("消息定时器字典未初始化，已重新创建")
                
                # 取消之前的定时器
                if username in self.message_timer and self.message_timer[username]:
                    try:
                        self.message_timer[username].cancel()
                        logger.info(f"已取消用户 {username} 的现有定时器")
                    except Exception as e:
                        logger.error(f"取消定时器失败: {str(e)}")
                
                # 添加到消息缓存
                if username not in self.message_cache:
                    self.message_cache[username] = []
                    logger.info(f"为用户 {username} 创建新的消息缓存")
                
                self.message_cache[username].append({
                    'content': content,
                    'chat_id': chat_id,
                    'sender_name': sender_name,
                    'is_group': is_group,
                    'is_image_recognition': is_image_recognition,
                    'timestamp': current_time  # 添加时间戳
                })
                
                # 记录缓存消息数量
                msg_count = len(self.message_cache[username])
                logger.info(f"用户 {username} 当前缓存消息数: {msg_count}")
                
                # 智能设置定时器时间：根据用户打字速度和消息长度动态调整
                typing_speed = self._estimate_typing_speed(username)
                logger.info(f"用户 {username} 的估计打字速度: {typing_speed:.3f}秒/字符")
                
                # 修改等待时间计算逻辑，更加智能地根据打字速度和消息长度调整
                # 基础等待时间 + 根据打字速度和消息长度计算的额外等待时间
                base_wait_time = 5.0  # 基础等待时间5秒
                
                # 根据消息数量调整等待时间
                if msg_count == 1:
                    # 第一条消息，给予更长的等待时间
                    wait_time = base_wait_time + 7.0  # 总共12秒
                    logger.info(f"首条消息，设置较长等待时间: {wait_time:.1f}秒")
                else:
                    # 后续消息，根据打字速度和消息长度动态调整
                    # 预估用户输入下一条消息所需的时间
                    estimated_typing_time = min(10.0, content_length * typing_speed)
                    wait_time = base_wait_time + estimated_typing_time
                    logger.info(f"后续消息，根据打字速度设置等待时间: {wait_time:.1f}秒")
                
                # 设置新的定时器
                timer = threading.Timer(wait_time, self._process_cached_messages, args=[username])
                timer.daemon = True  # 设置为守护线程，避免程序退出时阻塞
                timer.start()
                self.message_timer[username] = timer
                logger.info(f"已为用户 {username} 设置新定时器，等待时间: {wait_time:.1f}秒")
                
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
            # 检查消息缓存是否存在
            if not hasattr(self, 'message_cache'):
                logger.error("消息缓存属性不存在，无法处理")
                return None
                
            if not self.message_cache.get(username):
                logger.info(f"用户 {username} 没有需要处理的缓存消息")
                return None
            
            # 详细日志
            msg_count = len(self.message_cache[username])
            total_length = sum(len(msg.get('content', '')) for msg in self.message_cache[username])
            logger.info(f"处理缓存 - 用户: {username}, 消息数: {msg_count}, 总内容长度: {total_length}")
            
            # 获取最近的对话记录作为上下文
            recent_history = self.memory_handler.get_relevant_memories(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",username)
            context = ""
            if recent_history and len(recent_history) > 0 and recent_history[0].get('message'):
                # 构建更丰富的上下文，包含最多30轮对话历史
                context_parts = []
                for idx, hist in enumerate(recent_history):
                    if hist.get('message') and hist.get('reply'):
                        context_parts.append(f"对话{idx+1}:\n用户: {hist['message']}\nAI: {hist['reply']}")
                
                if context_parts:
                    context = "\n\n".join(context_parts)
                    logger.info(f"加载了{len(context_parts)}轮历史对话作为上下文")

            # 合并所有缓存的消息，但优先处理新消息
            messages = self.message_cache[username]
            
            # 按照时间戳排序，确保消息按正确顺序处理
            messages.sort(key=lambda x: x.get('timestamp', 0))
            
            # 分类消息
            image_messages = [msg for msg in messages if msg.get('is_image_recognition', False)]
            text_messages = [msg for msg in messages if not msg.get('is_image_recognition', False)]
            
            # 日志输出消息分类情况
            if image_messages:
                logger.info(f"消息分类 - 图片: {len(image_messages)}, 文本: {len(text_messages)}")
            
            # 按照图片识别消息优先的顺序合并内容
            combined_messages = image_messages + text_messages
            
            # 智能合并消息内容
            # 如果有上下文，只在第一次添加提示词
            if context:
                combined_content = f"{context}\n\n(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容)\n\n"
            else:
                combined_content = ""
            
            # 创建一个列表来存储清理后的消息内容，用于日志显示
            cleaned_messages = []
            
            # 统计用户消息的总字数和句数
            total_chars = 0
            total_sentences = 0
            sentence_endings = {'。', '！', '？', '!', '?', '.'}
            
            # 提取时间戳和前缀的正则表达式
            time_pattern = r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]'
            general_pattern = r'\[\d[^\]]*\]|\[\d+\]'
            time_prefix_pattern = r'^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)?\s+ta私聊对你说\s+'
            time_prefix_pattern2 = r'^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s+ta私聊对你说\s+'
            reminder_pattern = r'\((?:上次的对话内容|以上是历史对话内容)[^)]*\)'
            
            # 首先提取所有消息的实际内容（去除时间戳和前缀）
            raw_contents = []
            for msg in combined_messages:
                # 获取原始内容
                original_content = msg.get('content', '')
                
                # 预处理消息内容，去除时间戳和前缀
                content = original_content
                
                # 过滤时间戳
                content = re.sub(time_pattern, '', content)
                
                # 过滤通用模式
                content = re.sub(general_pattern, '', content)
                
                # 过滤消息前缀
                if re.search(time_prefix_pattern, content):
                    content = re.sub(time_prefix_pattern, '', content)
                elif re.search(time_prefix_pattern2, content):
                    content = re.sub(time_prefix_pattern2, '', content)
                
                # 彻底移除所有上下文提示词
                content = re.sub(reminder_pattern, '', content)
                
                # 记录清理后的内容
                raw_contents.append(content.strip())
                
                # 统计字数
                total_chars += len(content.strip())
                
                # 统计句数
                for char in content:
                    if char in sentence_endings:
                        total_sentences += 1
            
            # 合并清理后的内容，不再添加时间前缀
            merged_content = " ".join(raw_contents)
            cleaned_messages = raw_contents
            
            # 确保句子数至少为1
            total_sentences = max(1, total_sentences)
            
            # 输出清理后的所有消息内容
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
            
            # 将合并后的内容添加到上下文中
            if combined_content:
                combined_content += merged_content
            else:
                combined_content = merged_content
            
            # 在合并内容中添加字数和句数控制提示
            combined_content += f"\n\n请注意：你的回复应当与用户消息的长度相当，控制在约{target_chars}个字符和{target_sentences}个句子左右。"

            # 处理合并后的消息
            logger.info(f"处理合并消息 - 用户: {username}, 内容长度: {len(combined_content)}")
            result = self._handle_text_message(
                combined_content,
                last_message['chat_id'],
                last_message['sender_name'],
                username,
                last_message['is_group'],
                any(msg.get('is_image_recognition', False) for msg in messages)
            )

            # 清理缓存
            logger.info(f"清理用户 {username} 的消息缓存")
            self.message_cache[username] = []
            
            # 检查并清理定时器
            if hasattr(self, 'message_timer') and username in self.message_timer:
                if self.message_timer[username] is not None:
                    try:
                        self.message_timer[username].cancel()
                        logger.info(f"已取消用户 {username} 的定时器")
                    except Exception as e:
                        logger.error(f"取消定时器失败: {str(e)}")
                self.message_timer[username] = None
            
            return result

        except Exception as e:
            logger.error(f"处理缓存消息失败: {str(e)}", exc_info=True)
            return None

    def _estimate_typing_speed(self, username: str) -> float:
        """估计用户的打字速度（秒/字符）"""
        # 如果没有足够的历史消息，使用默认值
        if username not in self.message_cache or len(self.message_cache[username]) < 2:
            # 根据用户ID是否存在于last_message_time中返回不同的默认值
            # 如果是新用户，给予更长的等待时间
            if username not in self.last_message_time:
                logger.info(f"新用户 {username}，使用默认打字速度: 0.2秒/字符")
                return 0.2  # 新用户默认速度：每字0.2秒
            logger.info(f"已知用户 {username}，使用默认打字速度: 0.15秒/字符")
            return 0.15  # 已知用户默认速度：每字0.15秒
        
        # 获取最近的两条消息
        messages = self.message_cache[username]
        if len(messages) < 2:
            logger.info(f"用户 {username} 消息数不足，使用默认打字速度: 0.15秒/字符")
            return 0.15
        
        # 按时间戳排序，确保我们比较的是连续的消息
        recent_msgs = sorted(messages, key=lambda x: x.get('timestamp', 0))[-2:]
        
        # 计算时间差和字符数
        time_diff = recent_msgs[1].get('timestamp', 0) - recent_msgs[0].get('timestamp', 0)
        
        # 获取实际内容（去除时间戳和前缀）
        content = recent_msgs[0].get('content', '')
        time_prefix_pattern = r'^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)?\s+ta私聊对你说\s+'
        time_prefix_pattern2 = r'^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s+ta私聊对你说\s+'
        
        if re.search(time_prefix_pattern, content):
            content = re.sub(time_prefix_pattern, '', content)
        elif re.search(time_prefix_pattern2, content):
            content = re.sub(time_prefix_pattern2, '', content)
            
        char_count = len(content)
        
        # 如果时间差或字符数无效，使用默认值
        if time_diff <= 0 or char_count <= 0:
            logger.info(f"用户 {username} 时间差或字符数无效，使用默认打字速度: 0.15秒/字符")
            return 0.15
        
        # 计算打字速度（秒/字）
        typing_speed = time_diff / char_count
        
        # 应用平滑因子，避免极端值
        # 如果我们有历史记录的打字速度，将其纳入考虑
        if hasattr(self, '_typing_speeds') and username in self._typing_speeds:
            prev_speed = self._typing_speeds[username]
            # 使用加权平均，新速度权重0.3，历史速度权重0.7
            typing_speed = 0.3 * typing_speed + 0.7 * prev_speed
            logger.info(f"用户 {username} 打字速度（平滑后）: {typing_speed:.3f}秒/字符")
        else:
            logger.info(f"用户 {username} 打字速度（首次计算）: {typing_speed:.3f}秒/字符")
        
        # 存储计算出的打字速度
        if not hasattr(self, '_typing_speeds'):
            self._typing_speeds = {}
        self._typing_speeds[username] = typing_speed
        
        # 限制在合理范围内：0.2秒/字 到 1秒/字
        # 调整打字速度范围，使其更合理
        typing_speed = max(0.2, min(1, typing_speed))
        logger.info(f"用户 {username} 最终打字速度: {typing_speed:.3f}秒/字符")
        
        return typing_speed

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
        """安全发送消息，带重试机制"""
        if not msg or not who:
            logger.warning(f"消息或接收人为空，跳过发送")
            return False
            
        # 检查调试模式
        if self.is_debug:
            # 调试模式下直接打印消息而不是发送
            logger.info(f"[调试模式] 发送消息给 {who}: {msg}")
            return True
            
        # 检查wx对象是否可用
        if self.wx is None:
            logger.warning("WeChat对象为None，无法发送消息")
            return False
        
        # 不再特殊处理消息末尾的反斜杠，因为所有反斜杠都已在分割阶段处理
        processed_msg = msg
            
        # 设置重试次数
        if max_retries is None:
            max_retries = 3
            
        # 尝试发送消息
        for attempt in range(max_retries):
            try:
                if self.is_qq:
                    # QQ消息直接返回，不实际发送
                    return True
                else:
                    # 微信消息发送
                    if char_by_char:
                        # 逐字发送
                        for char in processed_msg:
                            self.wx.SendMsg(char, who)
                            time.sleep(random.uniform(0.1, 0.3))
                    else:
                        # 整条发送
                        self.wx.SendMsg(processed_msg, who)
                return True
            except Exception as e:
                logger.error(f"发送消息失败 (尝试 {attempt+1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # 等待一秒后重试
                    
        return False

    def _handle_text_message(self, content, chat_id, sender_name, username, is_group, is_image_recognition=False):
        """处理文本消息"""
        try:
            # 记录消息
            logger.info(f"处理文本消息 - 用户: {username}, 内容: {content[:50]}...")
            
            # 初始化返回值列表
            delayed_reply = []
            
            # 获取记忆
            memories = []
            if self.memory_handler:
                try:
                    # 获取相关记忆
                    memories = self.memory_handler.get_relevant_memories(
                        content, 
                        username if not is_group else chat_id
                    )
                    
                    if memories:
                        logger.info(f"找到相关记忆: {len(memories)} 条")
                    else:
                        logger.info("未找到相关记忆")
                except Exception as mem_err:
                    logger.error(f"获取记忆失败: {str(mem_err)}")
            
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
                if self.memory_handler:
                    memories = self.memory_handler.get_relevant_memories(content, username)
                    if memories:
                        content += f"\n以上是用户的沟通内容；以下是记忆中检索的内容：{';'.join(memories)}\n请你根据以上内容回复用户的消息。"
            
            # 使用正确的方法获取API回复 - 传递用户名以保持上下文关联
            reply = self.get_api_response(content, username)
            
            # 处理思考过程
            if "</think>" in reply:
                think_content, reply = reply.split("</think>", 1)
                # 只在非调试模式或明确设置时记录思考过程
                if not self.is_debug:
                    logger.info("\n思考过程:")
                    logger.info(think_content.strip())
            
            # 调试模式下不记录原始AI回复
            if not self.is_debug:
                logger.info("\nAI回复:")
                logger.info(reply)
            
            # 过滤括号内的动作和情感描述
            reply = self._filter_action_emotion(reply)
            
            # 添加群聊@
            if is_group:
                reply = f"@{sender_name} {reply}"
            
            try:
                # 使用优化后的消息分割方法
                split_messages = self._split_message_for_sending(reply)
                delayed_reply.extend(split_messages)
                
                # 使用优化后的消息发送方法
                # 调试模式下不再在这里显示消息
                if not self.is_debug:
                    self._send_split_messages(split_messages, chat_id)
                
                # 检查是否需要发送表情包
                emoji_path = None
                if self.emoji_handler and hasattr(self.emoji_handler, 'get_emotion_emoji'):
                    try:
                        # 传入原始文本和用户ID进行判断
                        emoji_path = self.emoji_handler.get_emotion_emoji(raw_content, username)
                    except Exception as e:
                        logger.error(f"获取表情包失败: {str(e)}")
                
                # 发送回复
                if emoji_path:
                    try:
                        self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                        delayed_reply.append(emoji_path)
                    except Exception as e:
                        logger.error(f"发送表情包失败: {str(e)}")
            except Exception as e:
                logger.error(f"发送回复失败: {str(e)}")
                return delayed_reply
            
            # 重置计数器（如果大于0）
            if self.unanswered_counters.get(username, 0) > 0:
                self.unanswered_counters[username] = 0
                logger.info(f"用户 {username} 的未回复计数器: {self.unanswered_counters[username]}")
            
            return delayed_reply
        except Exception as e:
            logger.error(f"处理文本消息失败: {str(e)}", exc_info=True)
            error_msg = f"抱歉，处理消息时出现错误"
            if is_group:
                error_msg = f"@{sender_name} {error_msg}"
            
            if self.wx:
                self.wx.SendMsg(msg=error_msg, who=chat_id)
            
            return [error_msg]

    def _check_time_query(self, content: str, username: str) -> tuple:
        """检查是否是时间查询请求"""
        # 时间查询关键词
        time_keywords = [
            "几点了", "现在时间", "当前时间", "现在几点", "时间是", "报时", "几点钟",
            "what time", "current time", "time now", "现在是几点", "告诉我时间",
            "今天日期", "今天几号", "几月几号", "星期几",
            "today's date", "what day", "date today", "几月几日"
        ]
        
        # 更严格的单词匹配，避免将部分词语误判为时间查询
        # 例如"时间"、"几点"这种常见词汇单独判断，要求它们是独立词组
        broad_keywords = ["时间", "几点", "日期"]
        specific_match = any(keyword in content.lower() for keyword in time_keywords)
        
        # 对于宽泛关键词，要求它们是独立词或短语，通过边界检查实现
        broad_match = False
        for keyword in broad_keywords:
            # 检查是否为独立词组，前后有标点、空格或字符串边界
            pattern = r'(^|[\s,，.。!！?？:：;；]){0}($|[\s,，.。!！?？:：;；])'.format(keyword)
            if re.search(pattern, content):
                broad_match = True
                break
        
        # 时间查询条件：匹配特定关键词或独立的宽泛关键词，且不是简单问候语
        is_time_query = (specific_match or broad_match) and not (
                "你好" in content or "早上好" in content or "晚上好" in content or 
                "下午好" in content or "中午好" in content or "嗨" in content)
        
        if is_time_query:
            # 获取当前时间
            now = datetime.now()
            weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekday = weekday_names[now.weekday()]
            
            # 格式化时间回复
            time_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
            reply = f"现在是 {time_str}，{weekday}"
            
            logger.info(f"检测到时间查询请求，回复: {reply}")
            return True, reply
            
        return False, None

    # 注释掉_check_memory_query方法
    # def _check_memory_query(self, content: str, username: str, is_group: bool = False, group_id: str = None, sender_name: str = None) -> tuple:
    #     """检查是否是记忆查询请求"""
    #     # 记忆查询关键词
    #     memory_keywords = [
    #         "记得我", "还记得", "记忆中", "之前说过", "上次说", "之前提到", "之前聊过",
    #         "remember me", "remember what", "我们之前", "我之前跟你", "你之前说",
    #         "你记得", "你还记得", "记得什么", "记得多少", "记得我们", "记得我说过",
    #         "记得我告诉过你", "记得我们讨论过", "记得我们聊过", "记得我问过你"
    #     ]
    #     
    #     # 检查是否包含记忆查询关键词
    #     if any(keyword in content.lower() for keyword in memory_keywords):
    #         # 获取相关记忆
    #         memories = self.memory_handler.get_relevant_memories(content, username)
    #         
    #         if memories:
    #             # 构建记忆回复
    #             memory_text = "\n".join([f"- {mem}" for mem in memories[:3]])  # 最多显示3条记忆
    #             reply = f"根据我的记忆，我们之前聊过这些内容：\n{memory_text}"
    #             
    #             if len(memories) > 3:
    #                 reply += f"\n...还有{len(memories)-3}条相关记忆"
    #         else:
    #             reply = "抱歉，我没有找到与此相关的记忆。"
    #         
    #         logger.info(f"检测到记忆查询请求，回复: {reply[:100]}...")
    #         return True, reply
    #         
    #     return False, None

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
            # 使用统一的消息分割方法
            delayed_reply = self._split_message_for_sending(reply)
            
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
                        delayed_reply.append(emoji_path)  #在发送消息队列后增加path，由响应器处理
                    else:
                        logger.warning(f"未找到对应情感 {emotion} 的表情包")
                    break

            if not emotion_detected:
                logger.info("未在回复中检测到明显情感")
        except Exception as e:
            logger.error(f"消息处理过程中发生错误: {str(e)}")
            delayed_reply = [reply]  # 出错时使用原始回复
            
        # 异步保存消息记录
        threading.Thread(target=self.save_message,
                         args=(qqid, sender_name, content, reply, False)).start()
        return delayed_reply

    def _split_message_for_sending(self, reply):
        """将长消息分割为多条发送"""
        # 如果消息长度小于等于最大长度，直接返回
        if len(reply) <= self.MAX_MESSAGE_LENGTH:
            # 即使消息长度在限制内，也需要检查是否包含反斜杠分隔符
            if '\\' in reply:
                # 按反斜杠分割，但保留颜表情中的反斜杠
                logger.info("检测到消息中有反斜杠分隔符，按分隔符分割")
                # 使用正则表达式保护颜表情中的反斜杠，如 \(^o^)/、(>_<)/等
                # 先替换颜表情中的反斜杠为特殊标记
                protected_reply = re.sub(r'\\(\([^)]*\)|\([^)]*\)/|[oO]_[oO]/|>_</|\^o\^/)', 'EMOJI_BACKSLASH\\1', reply)
                # 分割消息
                parts = protected_reply.split('\\')
                # 恢复颜表情中的反斜杠
                parts = [part.replace('EMOJI_BACKSLASH', '\\') for part in parts]
                # 过滤空消息
                return [part.strip() for part in parts if part.strip()]
            return [reply]
        
        # 检查消息中是否包含反斜杠分隔符
        if '\\' in reply:
            # 按反斜杠分割，但保留颜表情中的反斜杠
            logger.info("检测到消息中有反斜杠分隔符，按分隔符分割")
            # 使用正则表达式保护颜表情中的反斜杠，如 \(^o^)/、(>_<)/等
            # 先替换颜表情中的反斜杠为特殊标记
            protected_reply = re.sub(r'\\(\([^)]*\)|\([^)]*\)/|[oO]_[oO]/|>_</|\^o\^/)', 'EMOJI_BACKSLASH\\1', reply)
            # 分割消息
            parts = protected_reply.split('\\')
            # 恢复颜表情中的反斜杠
            parts = [part.replace('EMOJI_BACKSLASH', '\\') for part in parts]
            # 过滤空消息
            result = [part.strip() for part in parts if part.strip()]
            
            # 进一步处理超长的部分
            final_parts = []
            for part in result:
                if len(part) <= self.MAX_MESSAGE_LENGTH:
                    final_parts.append(part)
                else:
                    # 对超长部分进行进一步分割
                    sub_parts = self._split_long_message(part)
                    final_parts.extend(sub_parts)
            
            logger.info(f"按反斜杠分割后: 共{len(final_parts)}条, 长度: {[len(msg) for msg in final_parts]}")
            return final_parts
        
        # 如果没有反斜杠，则按照原有逻辑分割
        return self._split_long_message(reply)
    
    def _split_long_message(self, message):
        """分割超长消息"""
        messages = []
        current_message = ""
        
        # 优先按自然段落分割（空行）
        paragraphs = re.split(r'\n\s*\n', message)
        
        for paragraph in paragraphs:
            # 如果段落为空，跳过
            if not paragraph.strip():
                continue
            
            # 如果当前段落加上当前消息超过最大长度
            if len(current_message) + len(paragraph) + 1 > self.MAX_MESSAGE_LENGTH:
                # 如果当前消息不为空，添加到消息列表
                if current_message:
                    messages.append(current_message.strip())
                    current_message = ""
                
                # 如果单个段落超过最大长度，需要进一步分割
                if len(paragraph) > self.MAX_MESSAGE_LENGTH:
                    # 按句子分割
                    sentences = re.split(r'(?<=[。！？.!?])', paragraph)
                    temp_message = ""
                    
                    for sentence in sentences:
                        # 如果句子为空，跳过
                        if not sentence.strip():
                            continue
                        
                        # 如果当前消息加上这个句子超过最大长度
                        if len(temp_message) + len(sentence) > self.MAX_MESSAGE_LENGTH:
                            # 如果当前消息不为空，添加到消息列表
                            if temp_message:
                                messages.append(temp_message.strip())
                                temp_message = ""
                            
                            # 如果单个句子超过最大长度，按字符分割
                            if len(sentence) > self.MAX_MESSAGE_LENGTH:
                                for i in range(0, len(sentence), self.MAX_MESSAGE_LENGTH):
                                    messages.append(sentence[i:i+self.MAX_MESSAGE_LENGTH].strip())
                            else:
                                temp_message = sentence
                        else:
                            if temp_message and not temp_message.endswith(('\n', '。', '！', '？', '.', '!', '?')):
                                temp_message += " "
                            temp_message += sentence
                    
                    # 添加最后一条临时消息
                    if temp_message:
                        if current_message and not current_message.endswith('\n'):
                            current_message += "\n"
                        current_message += temp_message
                else:
                    if current_message and not current_message.endswith('\n'):
                        current_message += "\n"
                    current_message = paragraph
            else:
                # 添加段落，确保段落之间有换行
                if current_message and not current_message.endswith('\n'):
                    current_message += "\n"
                if current_message:
                    current_message += paragraph
                else:
                    current_message = paragraph
        
        # 添加最后一条消息
        if current_message:
            messages.append(current_message.strip())
        
        # 确保没有空消息
        messages = [msg for msg in messages if msg.strip()]
        
        # 记录分割结果
        logger.info(f"消息分割结果: 共{len(messages)}条, 长度: {[len(msg) for msg in messages]}")
        
        return messages

    def _send_split_messages(self, messages, chat_id):
        """发送分割后的消息，支持重试和自然发送节奏"""
        if not messages:
            return False
        
        # 记录已发送的消息，防止重复发送
        sent_messages = set()
        success_count = 0
        
        # 计算自然的发送间隔
        base_interval = 0.5  # 基础间隔时间（秒）
        
        for i, part in enumerate(messages):
            # 不再添加续行标记，每条消息都独立发送
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
        """发送自己的消息"""
        try:
            if self.wx:
                self.wx.SendMsg(msg=content, who=chat_id)
                logger.info(f"发送自己的消息: {content[:30]}...")
            else:
                logger.error("微信实例不存在，无法发送消息")
        except Exception as e:
            logger.error(f"发送自己的消息失败: {str(e)}")

    def auto_send_message(self, listen_list, robot_wx_name, get_personality_summary, is_quiet_time, start_countdown):
        """自动发送消息"""
        try:
            # 检查是否在安静时间
            if is_quiet_time():
                logger.info("当前是安静时间，不发送自动消息")
                start_countdown()  # 重新开始倒计时
                return
                
            # 获取人设摘要
            prompt_content = get_personality_summary(self.prompt_content)
            
            # 获取自动消息内容
            from src.config.rag_config import config
            
            # 检查配置是否存在
            if not hasattr(config, 'behavior') or not hasattr(config.behavior, 'auto_message') or not hasattr(config.behavior.auto_message, 'content'):
                logger.error("配置文件中缺少behavior.auto_message.content设置")
                auto_message = "你好，我是AI助手，有什么可以帮助你的吗？"
                logger.info(f"使用默认自动消息: {auto_message}")
            else:
                auto_message = config.behavior.auto_message.content
                logger.info(f"从配置读取的自动消息: {auto_message}")
            
            # 随机选择一个用户
            if not listen_list:
                logger.warning("监听列表为空，无法发送自动消息")
                start_countdown()  # 重新开始倒计时
                return
                
            target_user = random.choice(listen_list)
            logger.info(f"选择的目标用户: {target_user}")
            
            # 检查最近是否有聊天记录（30分钟内）
            from src.handlers.memory import MemoryHandler
            recent_chat = self.memory_handler.get_recent_chat_time(target_user)
            if recent_chat:
                current_time = datetime.now()
                time_diff = current_time - recent_chat
                # 如果30分钟内有聊天，跳过本次主动消息
                if time_diff.total_seconds() < 1800:  # 30分钟 = 1800秒
                    logger.info(f"距离上次与 {target_user} 的聊天不到30分钟，跳过本次主动消息")
                    start_countdown()  # 重新开始倒计时
                    return
            
            # 发送消息
            if self.wx:
                # 确保微信窗口处于活动状态
                try:
                    self.wx.ChatWith(target_user)
                    time.sleep(1)  # 等待窗口激活
                    
                    # 构建系统指令和上下文
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    system_instruction = f"(此时时间为{current_time}) [系统指令] {auto_message}"
                    
                    # 获取AI回复
                    ai_response = self.get_api_response(
                        message=system_instruction,
                        user_id=target_user,
                        sender_name=robot_wx_name
                    )
                    
                    if ai_response:
                        # 将长消息分段发送
                        message_parts = self._split_message_for_sending(ai_response)
                        for part in message_parts:
                            self._safe_send_msg(part, target_user)
                            time.sleep(1)  # 添加短暂延迟避免发送过快
                        
                        logger.info(f"已发送主动消息到 {target_user}: {ai_response[:50]}...")
                        
                        # 保存消息记录
                        self.save_message(
                            sender_id=robot_wx_name,
                            sender_name=robot_wx_name,
                            message=system_instruction,
                            reply=ai_response,
                            is_group=False
                        )
                    else:
                        logger.warning(f"AI未生成有效回复，跳过发送")
                    # 重新开始倒计时
                    start_countdown()
                except Exception as e:
                    logger.error(f"发送自动消息失败: {str(e)}")
                    start_countdown()  # 出错也重新开始倒计时
            else:
                logger.error("WeChat对象为None，无法发送自动消息")
                start_countdown()  # 重新开始倒计时
        except Exception as e:
            logger.error(f"自动发送消息失败: {str(e)}")
            start_countdown()  # 出错也重新开始倒计时

    def increase_unanswered_counter(self, username):
        """增加未回复计数器"""
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

    def process_message_for_user(self, user_id, force=False):
        """处理用户消息队列"""
        with self.queue_lock:
            if not hasattr(self, 'message_queues'):
                self.message_queues = {}  # 初始化消息队列字典
                
            if user_id not in self.message_queues:
                if self.is_debug and force:
                    logger.info(f"调试模式：用户 {user_id} 的消息队列为空")
                    # 在调试模式下，为空队列时直接处理输入
                    if force:
                        return self._handle_text_message(
                            "你好，这是测试消息",  # 默认测试消息
                            "debug_chat",
                            "debug_user",
                            user_id,
                            False
                        )
                return
                
            # 获取队列
            message_data = self.message_queues[user_id]
            messages = message_data["messages"]
            
            if not messages:
                # 清除空队列
                del self.message_queues[user_id]
                return
                
            # 提取信息
            chat_id = message_data.get("chat_id")
            sender_name = message_data.get("sender_name", "用户")
            username = message_data.get("username", user_id)
            is_group = message_data.get("is_group", False)
            
            # 合并消息
            combined_message = " ".join(messages)
            
            # 清空队列
            del self.message_queues[user_id]
        
        # 调试模式下特殊处理
        if self.is_debug:
            logger.info(f"\n[调试模式] 正在处理消息: {combined_message}")
        
        # 处理合并后的消息
        reply = self._handle_text_message(
            combined_message,
            chat_id,
            sender_name,
            username,
            is_group
        )
        
        # 调试模式下确保返回值
        if self.is_debug and not reply:
            return ["[调试模式] 没有生成回复"]
        
        return reply

    def handle_message(self, message: str, user_id: str = None, group_id: str = None, is_debug: bool = False):
        """
        处理接收到的消息
        
        Args:
            message: 接收到的消息内容
            user_id: 发送者ID
            group_id: 群组ID（如果有）
            is_debug: 是否为调试模式
        
        Returns:
            响应消息
        """
        try:
            # 检查是否为重要记忆（集成关键记忆检测）
            if hasattr(self, 'memory_handler') and self.memory_handler:
                self.memory_handler.check_important_memory(message, user_id)
            
            # 获取响应
            response = self.get_api_response(message, user_id, group_id)
            
            # 发送响应
            if is_debug:
                # 调试模式下的处理
                print(f"AI响应: {response}")
            else:
                # 实际生产环境下的发送逻辑
                self.send_response(response, user_id, group_id)
                
            return response
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}")
            return f"处理消息时出错: {str(e)}"

    def send_wx_message(self, response: str, user_id: str, group_id: str = None):
        """发送微信消息"""
        # ... 现有代码保持不变 ...
        
        # 这里可以添加统计或其他处理逻辑
        if hasattr(self, 'memory_handler') and self.memory_handler and hasattr(self.memory_handler, 'short_term_memory'):
            # 仅显示嵌入缓存统计（可选）
            try:
                embedding_model = self.memory_handler.short_term_memory.rag.embedding_model
                if hasattr(embedding_model, 'get_cache_stats'):
                    stats = embedding_model.get_cache_stats()
                    logger.info(f"嵌入缓存统计: 大小={stats['cache_size']}, 命中率={stats['hit_rate_percent']:.1f}%")
            except Exception as e:
                logger.debug(f"获取嵌入缓存统计失败: {str(e)}")

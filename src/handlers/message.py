"""
消息处理模块
负责处理聊天消息，包括:
- 消息队列管理
- 消息分发处理
- API响应处理
- 多媒体消息处理
- 对话结束处理
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from openai import OpenAI
from wxauto import WeChat
from services.database import Session, ChatMessage
import random
import os
from services.ai.llm_service import LLMService
from handlers.memory import MemoryHandler
from config import config
import re
import jieba

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')


class MessageHandler:
    def __init__(self, root_dir, api_key, base_url, model, max_token, temperature,
                 max_groups, robot_name, prompt_content, image_handler, emoji_handler, voice_handler, memory_handler,
                 is_qq=False, is_debug=False):
        self.root_dir = root_dir
        self.api_key = api_key
        self.model = model
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        self.robot_name = robot_name
        self.prompt_content = prompt_content
        # 添加消息缓存相关属性
        self.message_cache = {}  # 用户消息缓存
        self.last_message_time = {}  # 用户最后发送消息的时间
        self.message_timer = {}  # 用户消息处理定时器
        # 使用 DeepSeekAI 替换直接的 OpenAI 客户端
        self.deepseek = LLMService(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_token=max_token,
            temperature=temperature,
            max_groups=max_groups
        )

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
        self.max_retries = 3  # 添加最大重试次数
        self.retry_delay = 1.0  # 添加重试延迟（秒）
        
        # 新增：记录每个用户最后一次消息的时间
        self._last_message_times = {}
        
        # 新增：记录用户的打字速度
        self._typing_speeds = {}
        # 新增：记录每个用户最后一次询问时间的回复
        self._last_time_responses = {}
        # 新增：记录系统时间回复的标记
        self._system_time_flags = {}
        
        # 新增：记录群聊中的用户名
        self._group_user_names = {}

    def save_message(self, sender_id: str, sender_name: str, message: str, reply: str, is_group: bool = False):
        """保存消息到数据库"""
        try:
            # 过滤掉系统提示信息
            system_patterns = [
                r'请注意：你的回复应当与用户消息的长度相当，控制在约\d+个字符和\d+个句子左右。',
                r'注意：请避免生成与以下历史回复相似的内容，确保回复的多样性和新鲜感：',
                r'请确保你的回复与上述历史回复有明显区别，展现新的思路和表达方式。',
                r'请控制你的回复长度，使其与用户消息长度相当，约\d+个字符和\d+个句子左右。',
                r'请以你的身份回应用户的结束语。',
                r'请根据我的性格特点和当前时间生成一个全新的、自然的开场白。',
                r'过去24小时内的对话记录（仅供参考，不要重复之前的对话）：',
                r'我的主要性格特点：',
                r'现在是\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}，作为.*，我想要主动发起一个全新的对话。'
            ]
            
            # 过滤消息和回复中的系统提示
            filtered_message = message
            filtered_reply = reply
            
            for pattern in system_patterns:
                filtered_message = re.sub(pattern, '', filtered_message).strip()
                filtered_reply = re.sub(pattern, '', filtered_reply).strip()
            
            # 如果过滤后消息为空，则不保存
            if not filtered_message and not filtered_reply:
                return
                
            with Session() as session:
                chat_message = ChatMessage(
                    sender_id=sender_id,
                    sender_name=sender_name,
                    message=filtered_message,
                    reply=filtered_reply,
                    is_group=is_group,
                    timestamp=datetime.now()
                )
                session.add(chat_message)
                session.commit()
                logger.debug(f"消息已保存 - 发送者: {sender_name}, 消息长度: {len(filtered_message)}, 回复长度: {len(filtered_reply)}")
        except Exception as e:
            logger.error(f"保存消息失败: {str(e)}")

    def get_api_response(self, message: str, user_id: str, group_id: str = None, sender_name: str = None) -> str:
        """获取 API 回复（添加历史对话支持）"""
        avatar_dir = os.path.join(self.root_dir, config.behavior.context.avatar_dir)
        prompt_path = os.path.join(avatar_dir, "avatar.md")
        original_content = ""

        try:
            # 读取原始提示内容（人设内容）
            with open(prompt_path, "r", encoding="utf-8") as f:
                original_content = f.read()
                logger.debug(f"原始人设提示文件大小: {len(original_content)} bytes")

            # 获取最近的对话历史
            recent_history = self.memory_handler.get_recent_memory(
                user_id, 
                max_count=5, 
                group_id=group_id, 
                sender_name=sender_name
            )  # 获取最近5轮对话

            # 构建带有历史记录的上下文
            context = original_content + "\n\n最近的对话记录：\n"
            for hist in recent_history:
                context += f"用户: {hist['message']}\n"
                context += f"AI: {hist['reply']}\n"

            # 检查消息中是否包含限制句子数量的指令
            sentence_limit_match = re.search(r'限制回复句子数量为(\d+)句', message)
            if sentence_limit_match:
                limit_count = int(sentence_limit_match.group(1))
                # 从原始消息中移除限制指令
                message = re.sub(r'限制回复句子数量为\d+句', '', message).strip()
                # 在上下文中添加限制指令
                context += f"\n请注意：你的回复必须限制在{limit_count}句话以内，不要超过这个限制。\n"
                logger.info(f"检测到句子数量限制指令，限制为{limit_count}句")

            # 添加当前用户的输入
            context += f"\n用户: {message}\n"
            
            # 如果是群聊，添加用户标识
            if group_id and sender_name:
                context += f"\n注意：当前消息来自群聊 {group_id} 中的用户 {sender_name}\n"
                
            logger.debug(f"完整上下文大小: {len(context)} bytes")

            # 调用API获取回复
            return self.deepseek.get_response(message, user_id, context)

        except Exception as e:
            logger.error(f"获取API回复失败: {str(e)}")
            return self.deepseek.get_response(message, user_id, original_content)  # 降级处理

        finally:
            # 恢复原始内容
            try:
                with open(prompt_path, "w", encoding="utf-8") as f:
                    f.write(original_content)
            except Exception as restore_error:
                logger.error(f"恢复提示文件失败: {str(restore_error)}")

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

            logger.info(f"处理消息 - 发送者: {sender_name}, 聊天ID: {chat_id}, 是否群聊: {is_group}, 是否自己的消息: {is_self_message}")
            logger.info(f"消息内容: {content}")
            
            # 更新用户最后一次消息的时间（无论是用户发送的还是AI自己发送的）
            self._last_message_times[username] = datetime.now()
            logger.info(f"更新用户 {username} 的最后消息时间: {self._last_message_times[username].strftime('%Y-%m-%d %H:%M:%S')}")

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
            logger.info(f"实际消息内容: '{actual_content}', 长度: {content_length} 字符")
            
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
                
                # 只在第一条消息和每隔3条消息时输出日志，减少日志量
                msg_count = len(self.message_cache[username])
                if msg_count == 1 or msg_count % 3 == 0:
                    logger.info(f"用户 {username} 的缓存消息数: {msg_count} 条 (原因: {cache_reason})")
                
                # 智能设置定时器时间：根据用户打字速度和消息长度动态调整
                typing_speed = self._estimate_typing_speed(username)
                
                # 修改等待时间计算逻辑，增加基础等待时间，防止提前回复
                if len(self.message_cache[username]) == 1:
                    # 第一条消息，给予更长的等待时间
                    wait_time = 12.0  # 增加到12秒等待时间，给用户足够时间输入后续消息
                else:
                    # 后续消息，根据打字速度和消息长度动态调整，并增加基础等待时间
                    wait_time = 8.0 + min(10.0, len(actual_content) * typing_speed)  # 最多等待18秒
                
                # 简化日志输出
                if msg_count == 1 or msg_count % 3 == 0:
                    logger.info(f"用户 {username} 设置等待时间: {wait_time:.2f}秒 " + 
                               (f"(第一条消息)" if msg_count == 1 else 
                                f"(打字速度: {typing_speed:.3f}秒/字)"))
                
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
                return self._handle_text_message(content, chat_id, sender_name, username, is_group, is_image_recognition)
            
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
            recent_history = self.memory_handler.get_recent_memory(username, max_count=1)
            context = ""
            if recent_history:
                context = f"{recent_history[0]['message']}(上次的对话内容，只是提醒，无需进行互动，处理重点请放在后面的新内容)\n"
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
            
            # 记录用户消息的统计信息
            logger.info(f"用户消息统计 - 总字数: {total_chars}, 总句数: {total_sentences}")
            
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
            
            # 记录计算的回复长度比例和目标长度
            logger.info(f"回复长度比例: {response_ratio:.2f}, 目标字符数: {target_chars}, 目标句子数: {target_sentences}")
            
            # 在合并内容中添加字数和句数控制提示
            combined_content += f"\n\n请注意：你的回复应当与用户消息的长度相当，控制在约{target_chars}个字符和{target_sentences}个句子左右。"

            # 处理合并后的消息
            logger.info(f"开始处理合并消息")
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
            logger.info(f"已清理用户 {username} 的消息缓存")
            
            return result

        except Exception as e:
            logger.error(f"处理缓存消息失败: {str(e)}", exc_info=True)
            return None

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

            # 异步保存消息记录 - 只保存文本回复，不保存图片
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

            # 异步保存消息记录 - 只保存文本回复，不保存图片
            threading.Thread(target=self.save_message,
                             args=(username, sender_name, content, reply, is_group)).start()
            return reply
        return None

    def _filter_action_emotion(self, text):
        """智能过滤括号内的动作和情感描述，保留颜文字"""

        def is_emoticon(text):
            """判断是否为颜文字"""
            # 定义颜文字常用字符
            emoticon_chars = set(
                '（()）~～‿⁀∀︿⌒▽△□◇○●ˇ＾∇＿゜◕ω・ノ丿╯╰つ⊂＼／┌┐┘└°△▲▽▼◇◆○●◎■□▢▣▤▥▦▧▨▩♡♥ღ☆★✡⁂✧✦❈❇✴✺✹✸✷✶✵✳✲✱✰✯✮✭✬✫✪✩✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁✿✾✽✼✻✺✹✸✷✶✵✴✳✲✱✰✯✮✭✬✫✪✩✨✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁❤♪♫♬♩♭♮♯°○◎●◯◐◑◒◓◔◕◖◗¤☼☀☁☂☃☄★☆☎☏⊙◎☺☻☯☭♠♣♧♡♥❤❥❣♂♀☿❀❁❃❈❉❊❋❖☠☢☣☤☥☦☧☨☩☪☫☬☭☮☯☸☹☺☻☼☽☾☿♀♁♂♃♄♆♇♈♉♊♋♌♍♎♏♐♑♒♓♔♕♖♗♘♙♚♛♜♝♞♟♠♡♢♣♤♥♦♧♨♩♪♫♬♭♮♯♰♱♲♳♴♵♶♷♸♹♺♻♼♽♾♿⚀⚁⚂⚃⚄⚆⚇⚈⚉⚊⚋⚌⚍⚎⚏⚐⚑⚒⚓⚔⚕⚖⚗⚘⚙⚚⚛⚜⚝⚞⚟')
            # 检查是否主要由颜文字字符组成
            text = text.strip('（()）')  # 去除外围括号
            if not text:  # 如果去除括号后为空，返回False
                return False
            emoticon_char_count = sum(1 for c in text if c in emoticon_chars)
            return emoticon_char_count / len(text) > 0.5  # 如果超过50%是颜文字字符则认为是颜文字

        def contains_action_keywords(text):
            """检查是否包含动作或情感描述关键词"""
            action_keywords = {'微笑', '笑', '哭', '叹气', '摇头', '点头', '皱眉', '思考',
                               '无奈', '开心', '生气', '害羞', '紧张', '兴奋', '疑惑', '惊讶',
                               '叹息', '沉思', '撇嘴', '歪头', '摊手', '耸肩', '抱抱', '拍拍',
                               '摸摸头', '握手', '挥手', '鼓掌', '捂脸', '捂嘴', '翻白眼',
                               '叉腰', '双手合十', '竖起大拇指', '比心', '摸摸', '拍肩', '戳戳',
                               '摇晃', '蹦跳', '转圈', '倒地', '趴下', '站起', '坐下'}
            text = text.strip('（()）')  # 去除外围括号
            # 使用jieba分词，检查是否包含动作关键词
            words = set(jieba.cut(text))
            return bool(words & action_keywords)

        # 分别处理中文括号和英文括号
        cn_pattern = r'（[^）]*）'
        en_pattern = r'\([^\)]*\)'

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
        text = re.sub(cn_pattern, smart_filter, text)
        # 处理英文括号
        text = re.sub(en_pattern, smart_filter, text)

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
                logger.info(reply.strip())
            else:
                logger.info("\nAI回复:")
                logger.info(reply)

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
        """安全发送消息，包含重试机制，支持逐字发送模式"""
        if max_retries is None:
            max_retries = self.max_retries
            
        for attempt in range(max_retries):
            try:
                if self.wx is None:
                    logger.error("微信对象未初始化")
                    return False
                
                if char_by_char and len(msg) > 3:  # 只对较长消息使用逐字发送
                    # 修复：不再逐字发送，而是一次性发送完整消息
                    # 模拟打字效果，但不实际分割消息
                    typing_time = len(msg) * random.uniform(0.05, 0.1)  # 根据消息长度计算模拟打字时间
                    time.sleep(typing_time)  # 模拟打字时间
                    self.wx.SendMsg(msg=msg, who=who)
                else:
                    # 普通发送模式
                    self.wx.SendMsg(msg=msg, who=who)
                
                return True
            except Exception as e:
                logger.error(f"发送消息失败，第{attempt+1}次重试: {str(e)}")
                if attempt == max_retries - 1:
                    logger.error("消息发送最终失败")
                    return False
                time.sleep(self.retry_delay * (attempt + 1))
        return False

    def _handle_text_message(self, content: str, chat_id: str, sender_name: str, username: str, is_group: bool = False, is_image_recognition: bool = False):
        """处理普通文本消息"""
        try:
            # 保存原始内容用于记忆存储
            raw_content = content
            
            # 添加正则表达式过滤时间戳
            time_pattern = r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]'
            content = re.sub(time_pattern, '', content)

            # 更通用的模式
            general_pattern = r'\[\d[^\]]*\]|\[\d+\]'
            content = re.sub(general_pattern, '', content)
            
            # 过滤消息前缀
            time_prefix_pattern = r'^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)\s+ta私聊对你说\s+'
            content = re.sub(time_prefix_pattern, '', content)
            
            logger.info(f"清理后的消息内容: {content}")

            # 检查是否是询问时间的请求
            is_time_query, time_response = self._check_time_query(content, username)
            if is_time_query:
                logger.info(f"检测到时间查询请求，直接返回系统时间")
                self._system_time_flags[username] = True
                self._last_time_responses[username] = time_response
                self._safe_send_msg(time_response, chat_id)
                return

            logger.info("处理普通文本回复")

            # 对输入内容进行分词处理
            words = list(jieba.cut(content))
            logger.debug(f"分词结果: {words}")
            
            # 检查是否包含字数和句数控制提示
            length_control_pattern = r'请注意：你的回复应当与用户消息的长度相当，控制在约(\d+)个字符和(\d+)个句子左右。'
            length_match = re.search(length_control_pattern, content)
            
            if length_match:
                char_count = int(length_match.group(1))
                sentence_count = int(length_match.group(2))
                content = re.sub(length_control_pattern, '', content).strip()
                logger.info(f"检测到长度控制提示 - 目标字符数: {char_count}, 目标句子数: {sentence_count}")
            else:
                cleaned_content = content
                char_count = len(cleaned_content)
                
                sentence_count = 0
                sentence_endings = {'。', '！', '？', '!', '?', '.'}
                for char in cleaned_content:
                    if char in sentence_endings:
                        sentence_count += 1
                
                sentence_count = max(1, sentence_count)
                
                response_ratio = self._calculate_response_length_ratio(char_count)
                char_count = int(char_count * response_ratio)
                sentence_count = int(sentence_count * response_ratio)
                
                sentence_count = max(1, sentence_count)
                
                logger.info(f"计算长度控制 - 用户消息字符数: {len(cleaned_content)}, 句子数: {sentence_count}")
                logger.info(f"回复长度比例: {response_ratio:.2f}, 目标字符数: {char_count}, 目标句子数: {sentence_count}")

            # 获取或初始化未回复计数器
            counter = self.unanswered_counters.get(username, 0)
                
            # 检查是否包含结束对话的关键词
            end_keywords = ['再见', '拜拜', '晚安', '结束', '退出', '停止', 'bye', 'goodbye', 'exit']
            is_end_of_conversation = any(keyword in content.lower() for keyword in end_keywords)
            
            # 获取最近的回复，用于防止重复回复
            recent_replies = []
            try:
                with Session() as session:
                    recent_messages = session.query(ChatMessage).filter(
                        ChatMessage.sender_id == username
                    ).order_by(ChatMessage.timestamp.desc()).limit(5).all()
                    
                    recent_replies = [msg.reply for msg in recent_messages if msg.reply]
            except Exception as e:
                logger.error(f"获取历史回复失败: {str(e)}")
            
            if is_end_of_conversation:
                content += "\n请你回应用户的结束语"
                logger.info(f"检测到对话结束关键词，尝试生成更自然的结束语")
            
            # 添加防止重复回复的提示
            if recent_replies:
                content += f"\n\n注意：请避免生成与以下历史回复相似的内容，确保回复的多样性和新鲜感：\n"
                for i, reply in enumerate(recent_replies[:5]):
                    content += f"{i+1}. {reply}\n"
                content += "\n请确保你的回复与上述历史回复有明显区别，展现新的思路和表达方式。"
            
            # 添加长度控制提示
            content += f"\n\n请控制你的回复长度，使其与用户消息长度相当，约{char_count}个字符和{sentence_count}个句子左右。"

            # 获取 API 回复
            if is_group:
                reply = self.get_api_response(content, chat_id, chat_id, sender_name)
            else:
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
                # 改进的智能分割器 - 支持反斜杠断句和颜文字识别
                delayed_reply = []
                current_sentence = []
                ending_punctuations = {'。', '！', '？', '!', '?', '…', '……'}
                split_symbols = {'\\', '|', '￤', '\n', '\\n'}  # 支持多种手动分割符
                
                # 颜文字检测正则
                emoticon_pattern = r'[\(\（][^\)\）]{1,10}[\)\）]'
                emoticons = re.findall(emoticon_pattern, reply)
                emoticon_positions = []
                
                # 记录所有颜文字的位置
                for emoticon in emoticons:
                    start_pos = 0
                    while True:
                        pos = reply.find(emoticon, start_pos)
                        if pos == -1:
                            break
                        emoticon_positions.extend(range(pos, pos + len(emoticon)))
                        start_pos = pos + 1
                
                i = 0
                while i < len(reply):
                    char = reply[i]
                    
                    # 检查是否在颜文字中
                    in_emoticon = i in emoticon_positions
                    
                    # 处理手动分割符号（优先级最高）
                    if char in split_symbols and not in_emoticon:
                        if current_sentence:
                            delayed_reply.append(''.join(current_sentence).strip())
                        current_sentence = []
                        i += 1
                        continue
                    
                    current_sentence.append(char)
                    
                    # 处理中文标点和省略号
                    if char in ending_punctuations and not in_emoticon:
                        # 排除英文符号在短句中的误判（如英文缩写）
                        if char in {'!', '?'} and len(current_sentence) < 4:
                            i += 1
                            continue
                        
                        # 处理连续省略号
                        if char == '…' and i > 0 and reply[i-1] == '…':
                            if len(current_sentence) >= 3:  # 至少三个点形成省略号
                                delayed_reply.append(''.join(current_sentence).strip())
                                current_sentence = []
                        else:
                            delayed_reply.append(''.join(current_sentence).strip())
                            current_sentence = []
                    
                    i += 1
                
                # 处理剩余内容
                if current_sentence:
                    delayed_reply.append(''.join(current_sentence).strip())
                
                # 过滤空内容和去重
                delayed_reply = [s for s in delayed_reply if s]
                
                # 记录已发送的消息，防止重复发送
                sent_messages = set()
                
                # 发送分割后的文本回复，使用逐字发送模式
                for part in delayed_reply:
                    if part not in sent_messages:
                        # 不再使用逐字发送模式，直接发送完整消息
                        self.wx.SendMsg(msg=part, who=chat_id)
                        
                        sent_messages.add(part)
                        # 句子之间的等待时间
                        time.sleep(random.uniform(0.5, 1.0))
                    else:
                        logger.info(f"跳过重复内容: {part[:20]}...")

                # 检查回复中是否包含情感关键词并发送表情包
                logger.info("开始检查AI回复的情感关键词")
                emotion_detected = False

                if not hasattr(self.emoji_handler, 'emotion_map'):
                    logger.error("emoji_handler 缺少 emotion_map 属性")
                    return reply

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

            # 异步保存消息记录
            threading.Thread(target=self.save_message,
                             args=(username, sender_name, raw_content, reply, is_group)).start()
            # 重置计数器（如果大于0）
            if self.unanswered_counters.get(username, 0) > 0:
                self.unanswered_counters[username] = 0
                logger.info(f"用户 {username} 的未回复计数器: {self.unanswered_counters[username]}")

            return reply
        except Exception as e:
            logger.error(f"处理文本消息时发生错误: {str(e)}")
            return None

    def _check_time_query(self, content: str, username: str) -> tuple:
        """检查是否是询问时间的请求，如果是则返回当前时间"""
        # 定义询问时间的关键词模式
        time_keywords = [
            r'现在是几点',
            r'现在几点',
            r'几点了',
            r'什么时间',
            r'当前时间',
            r'现在时间',
            r'几点钟',
            r'time now',
            r'what time'
        ]
        
        # 检查是否包含询问时间的关键词
        is_time_query = any(re.search(keyword, content, re.IGNORECASE) for keyword in time_keywords)
        
        if is_time_query:
            # 获取当前时间
            now = datetime.now()
            current_time = now.strftime('%H:%M:%S')
            hour = now.hour
            
            # 根据时间段生成不同的回复
            if 5 <= hour < 12:
                time_period = "早上"
            elif 12 <= hour < 13:
                time_period = "中午"
            elif 13 <= hour < 18:
                time_period = "下午"
            elif 18 <= hour < 22:
                time_period = "晚上"
            else:
                time_period = "深夜"
                
            # 生成回复，包含确切时间
            response = f"现在是{time_period}{current_time}呢\主人~😊"
            
            return True, response
        
        return False, ""
        
    def _check_memory_query(self, content: str, username: str, is_group: bool = False, group_id: str = None, sender_name: str = None) -> tuple:
        """检查是否是询问之前对话内容的请求"""
        # 定义询问记忆的关键词模式
        memory_keywords = [
            r'刚才.*说过什么',
            r'刚才.*聊了什么',
            r'之前.*说过什么',
            r'之前.*聊了什么',
            r'记得.*说过什么',
            r'记得.*聊了什么',
            r'我们.*说过什么',
            r'我们.*聊了什么'
        ]
        
        # 检查是否包含询问记忆的关键词
        is_memory_query = any(re.search(keyword, content, re.IGNORECASE) for keyword in memory_keywords)
        
        if is_memory_query:
            # 检查是否有上一次时间回复的记录
            if username in self._system_time_flags and self._system_time_flags[username]:
                # 如果上一次是系统时间回复，直接引用
                if username in self._last_time_responses:
                    last_time_response = self._last_time_responses[username]
                    # 清除标记，避免重复引用
                    self._system_time_flags[username] = False
                    return True, f"我刚才告诉你{last_time_response[2:]}"  # 去掉前面的"现在是"
            
            # 如果不是时间回复或没有记录，则获取记忆
            if is_group:
                memories = self.memory_handler.get_relevant_memories(content, group_id, group_id, sender_name)
            else:
                memories = self.memory_handler.get_relevant_memories(content, username)
                
            if memories and len(memories) > 0:
                # 选择最近的几条记忆
                recent_memories = memories[:3]
                memory_text = "；".join(recent_memories)
                return True, f"我们刚才聊了这些内容：{memory_text}"
        
        return False, ""

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

    def add_to_queue(self, chat_id: str, content: str, sender_name: str,
                     username: str, is_group: bool = False, is_self_message: bool = False):
        """添加消息到队列（已废弃，保留兼容）"""
        logger.info("直接处理消息，跳过队列")
        return self.handle_user_message(content, chat_id, sender_name, username, is_group, is_self_message=is_self_message)

    def process_messages(self, chat_id: str):
        """处理消息队列中的消息（已废弃，保留兼容）"""
        logger.warning("process_messages方法已废弃，使用handle_message代替")
        pass

    #以下是onebot QQ方法实现
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
                # 异步保存消息记录 - 只保存文本回复，不保存图片
                threading.Thread(target=self.save_message,
                                 args=(qqid, sender_name, content, reply, False)).start()

                return image_path
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

            # 发送分割后的文本回复，不再使用逐字发送模式
            for part in delayed_reply:
                # 直接发送完整消息
                self.qq.send_message(qqid, part)
                # 消息之间添加随机延迟
                time.sleep(random.uniform(0.5, 1.0))

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
                        # 不需要保存表情包记录，因为save_message方法已经添加了过滤逻辑
                    else:
                        logger.warning(f"未找到对应情感 {emotion} 的表情包")
                    break

            if not emotion_detected:
                logger.info("未在回复中检测到明显情感")
        except Exception as e:
            logger.error(f"消息处理过程中发生错误: {str(e)}")
        
        # 异步保存消息记录 - 只保存文本回复，不保存表情包
        # save_message方法已经添加了过滤逻辑，会自动过滤掉表情包路径
        threading.Thread(target=self.save_message,
                        args=(qqid, sender_name, content, reply, False)).start()
            
        return delayed_reply

    def auto_send_message(self, listen_list, robot_wx_name, get_personality_summary, is_quiet_time, start_countdown):
        """自动发送消息的方法"""
        try:
            if is_quiet_time():
                logger.info("当前处于安静时间，跳过自动发送消息")
                start_countdown()
                return

            if not listen_list:
                logger.error("没有可用的聊天对象")
                start_countdown()
                return
                
            # 选择一个用户进行消息发送
            user_id = random.choice(listen_list)
            
            # 检查用户最后消息时间
            current_time = datetime.now()
            should_skip = False
            
            # 检查最近一次与用户的对话时间
            if user_id in self._last_message_times:
                last_msg_time = self._last_message_times[user_id]
                time_diff_minutes = (current_time - last_msg_time).total_seconds() / 60
                
                if time_diff_minutes < 30:  # 小于30分钟
                    logger.info(f"最近一次与用户 {user_id} 的对话在 {time_diff_minutes:.1f} 分钟前，小于半小时，跳过主动发送消息")
                    should_skip = True
            
            if should_skip:
                start_countdown()
                return
                
            # 更新未回复计数器
            if user_id not in self.unanswered_counters:
                self.unanswered_counters[user_id] = 0
            self.unanswered_counters[user_id] += 1

            # 获取最近的对话记录作为上下文
            recent_history = self.memory_handler.get_recent_memory(user_id, max_count=5)
            
            # 格式化记忆，添加时间信息
            cutoff_time = current_time - timedelta(hours=24)
            formatted_memories = []
            recent_replies = []
            
            if recent_history:
                # 提取历史回复
                recent_replies = [memory.get('reply', '') for memory in recent_history if 'reply' in memory]
                logger.info(f"获取到用户 {user_id} 的 {len(recent_replies)} 条历史回复记录")
                
                # 格式化记忆
                for memory in recent_history:
                    # 尝试从记忆中提取时间戳
                    memory_time = None
                    
                    # 检查记忆是否有时间戳属性
                    if hasattr(memory, 'timestamp'):
                        memory_time = datetime.fromtimestamp(memory.timestamp)
                    else:
                        # 尝试从记忆文本中提取时间
                        for key in ['message', 'reply']:
                            if key in memory:
                                time_match = re.search(r'\[(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?)\]', memory[key])
                                if time_match:
                                    try:
                                        time_str = time_match.group(1)
                                        if ':' in time_str.split(' ')[1] and len(time_str.split(' ')[1].split(':')) == 2:
                                            time_str += ':00'  # 添加秒数如果没有
                                        memory_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                                        break
                                    except Exception as e:
                                        logger.error(f"解析时间戳失败: {str(e)}")
                    
                    # 如果找到了时间戳且在24小时内，添加到格式化记忆
                    if memory_time and memory_time > cutoff_time:
                        formatted_memories.append(f"[{memory_time.strftime('%Y-%m-%d %H:%M')}] {memory.get('message', '')}")
            
            # 使用格式化后的记忆文本
            memories_content = "\n".join(formatted_memories) if formatted_memories else "暂无最近对话"
            
            # 获取精简后的性格特点
            personality = get_personality_summary(self.prompt_content)
            
            # 构建优化后的提示信息，明确指出这是新的主动对话
            prompt = f"""现在是{current_time.strftime('%Y-%m-%d %H:%M')}，作为{robot_wx_name}，我想要主动发起一个全新的对话。

            我的主要性格特点：
            {personality}

            过去24小时内的对话记录（仅供参考，不要重复之前的对话）：
            {memories_content}

            请根据我的性格特点和当前时间生成一个全新的、自然的开场白。要求：
            1. 不要直接称呼对方的微信昵称
            2. 可以使用"你"、"您"等称呼
            3. 保持对话的自然性和礼貫性
            4. 不要重复或延续之前的对话内容
            5. 创造性地开启新的话题
            6. 如果新话题主题与之前内容主题类似或一样，则内容以之前对话内容为主，防止出现内容差错"""
            
            # 添加防止重复回复的提示
            if recent_replies:
                prompt += f"\n\n注意：请避免生成与以下历史回复相似的内容，确保回复的多样性和新鲜感：\n"
                # 最多添加5条历史回复作为参考
                for i, reply in enumerate(recent_replies[:5]):
                    prompt += f"{i+1}. {reply}\n"
                prompt += "\n请确保你的回复与上述历史回复有明显区别，展现新的思路和表达方式。"

            # 获取AI回复
            reply_content = self.get_api_response(prompt, robot_wx_name)
            
            logger.info(f"自动发送消息到 {user_id}: {reply_content}")
            
            # 发送消息，使用更可靠的方法
            success = False
            max_retries = 2  # 减少重试次数，提高性能
            
            for attempt in range(max_retries):
                try:
                    # 使用is_self_message=True标记这是AI自己发送的消息
                    self.handle_user_message(
                        content=reply_content,
                        chat_id=user_id,
                        sender_name=robot_wx_name,
                        username=user_id,  # 修改：使用接收者的ID而不是机器人名称
                        is_group=False,
                        is_self_message=True  # 标记为AI自己的消息
                    )
                    
                    # 将对话记录保存到接收者的记忆中
                    self.memory_handler.add_short_memory(
                        f"我主动发起对话：{reply_content}",
                        "等待回复中...",
                        user_id  # 使用接收者的ID
                    )
                    
                    # 更新接收者的最后消息时间
                    self._last_message_times[user_id] = current_time
                    
                    success = True
                    break
                except Exception as e:
                    logger.error(f"发送消息失败，第{attempt+1}次重试: {str(e)}")
                    time.sleep(1)  # 固定等待时间，提高性能
            
            if not success:
                logger.error(f"消息发送最终失败，将在下次尝试")

        except Exception as e:
            logger.error(f"自动发送消息失败: {str(e)}")
        finally:
            # 确保倒计时总是被启动
            start_countdown()

    def _send_self_message(self, content: str, chat_id: str):
        """处理AI自己发送的消息"""
        try:
            logger.info(f"开始处理AI自己的消息 - 接收者: {chat_id}")
            logger.info(f"原始消息内容: {content}")
            
            # 检查最近的话题历史，避免重复
            recent_topics = []
            try:
                recent_history = self.memory_handler.get_recent_memory(chat_id, max_count=5)
                if recent_history:
                    # 提取关键词作为话题标识
                    for history in recent_history:
                        if 'message' in history:
                            words = jieba.cut(history['message'])
                            # 过滤掉停用词和常见词，保留主要名词和动词
                            keywords = [w for w in words if len(w) > 1]
                            if keywords:
                                recent_topics.extend(keywords)
                    logger.info(f"最近讨论的话题关键词: {', '.join(recent_topics[:10])}")
            except Exception as e:
                logger.warning(f"获取历史话题失败: {str(e)}")
            
            # 检查当前消息是否与最近话题过于相似
            current_words = list(jieba.cut(content))
            overlap_count = sum(1 for word in current_words if word in recent_topics)
            if overlap_count > len(current_words) * 0.4:  # 如果重复度超过40%
                logger.warning(f"检测到话题重复度较高: {overlap_count/len(current_words):.2%}")
                # 在消息中添加转移话题的提示
                content += "\\让我们换个话题聊聊吧"
            
            # 消息分割处理
            messages = []
            logger.info("开始进行消息分割处理...")
            
            if '\\' in content:
                # 使用反斜杠分割
                messages = [msg.strip() for msg in content.split('\\') if msg.strip()]
                logger.info(f"使用反斜杠分割得到 {len(messages)} 条消息")
            else:
                # 使用标点符号分割
                current_msg = []
                for char in content:
                    current_msg.append(char)
                    if char in ['。', '！', '？', '.', '!', '?'] and len(current_msg) > 5:
                        messages.append(''.join(current_msg).strip())
                        current_msg = []
                
                if current_msg:
                    messages.append(''.join(current_msg).strip())
                logger.info(f"使用标点符号分割得到 {len(messages)} 条消息")
            
            # 如果没有分割成功，作为单条消息处理
            if not messages:
                messages = [content]
                logger.info("无法分割消息，将作为单条消息处理")
            
            # 发送消息
            total_messages = len(messages)
            success_count = 0
            failure_count = 0
            
            for i, msg in enumerate(messages, 1):
                if not msg:
                    logger.debug(f"跳过空消息 (消息 {i}/{total_messages})")
                    continue
                
                try:
                    logger.info(f"准备发送消息 {i}/{total_messages}: {msg}")
                    
                    # 计算并记录打字时间
                    typing_time = len(msg) * random.uniform(0.05, 0.1)
                    logger.debug(f"模拟打字时间: {typing_time:.2f}秒")
                    time.sleep(typing_time)
                    
                    # 发送消息
                    send_start_time = time.time()
                    success = self._safe_send_msg(msg, chat_id)
                    send_time = time.time() - send_start_time
                    
                    if success:
                        success_count += 1
                        logger.info(f"消息 {i}/{total_messages} 发送成功 (耗时: {send_time:.2f}秒)")
                    else:
                        failure_count += 1
                        logger.error(f"消息 {i}/{total_messages} 发送失败")
                        # 尝试重试一次
                        logger.info("尝试重新发送...")
                        time.sleep(1.0)
                        retry_success = self._safe_send_msg(msg, chat_id)
                        if retry_success:
                            logger.info("重试发送成功")
                            success_count += 1
                        else:
                            logger.error("重试发送失败")
                    
                    # 消息间隔
                    if i < total_messages:
                        delay = random.uniform(0.8, 1.5)
                        logger.debug(f"等待 {delay:.1f} 秒后发送下一条消息")
                        time.sleep(delay)
                    
                except Exception as e:
                    failure_count += 1
                    logger.error(f"处理消息 {i}/{total_messages} 时出错: {str(e)}")
            
            # 发送完成后的统计
            success_rate = (success_count / total_messages) * 100
            logger.info(f"消息发送完成 - 总数: {total_messages}, 成功: {success_count}, "
                       f"失败: {failure_count}, 成功率: {success_rate:.1f}%")
            
            return success_count > 0  # 只要有消息发送成功就返回True
            
        except Exception as e:
            logger.error(f"消息处理过程中发生错误: {str(e)}")
            return False


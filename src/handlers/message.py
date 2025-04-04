"""
消息处理模块
负责处理聊天消息，包括:
- 消息队列管理
- 消息分发处理
- API响应处理
- 多媒体消息处理
"""

import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional
from openai import OpenAI
from wxauto import WeChat
from services.database import Session, ChatMessage
import random
import os
from services.ai.llm_service import LLMService
# 替换旧的记忆处理器导入
from modules.memory.memory_service import MemoryService
from config import config
# 导入
from modules.reminder.time_recognition import TimeRecognitionService
from modules.reminder import ReminderService
# 导入调试命令处理器
from src.handlers.debug import DebugCommandHandler

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class MessageHandler:
    def __init__(self, root_dir, api_key, base_url, model, max_token, temperature, 
                 max_groups, robot_name, prompt_content, image_handler, emoji_handler, voice_handler, memory_service):
        self.root_dir = root_dir
        self.api_key = api_key
        self.model = model
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        self.robot_name = robot_name
        self.prompt_content = prompt_content
        
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
        self.message_queues = {}  # 存储每个用户的消息队列，格式：{queue_key: queue_data}
        self.queue_timers = {}    # 存储每个用户的定时器，格式：{queue_key: timer}
        self.QUEUE_TIMEOUT = 8    # 队列等待时间（秒）
        self.queue_lock = threading.Lock()
        self.chat_contexts = {}
        
        # 微信实例
        self.wx = WeChat()

        # 添加 handlers
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler
        # 使用新的记忆服务
        self.memory_service = memory_service
        # 保存当前角色名 - 修复获取方式
        avatar_path = os.path.join(self.root_dir, config.behavior.context.avatar_dir)
        self.current_avatar = os.path.basename(avatar_path)
        logger.info(f"当前使用角色: {self.current_avatar}")
        
        # 初始化调试命令处理器
        self.debug_handler = DebugCommandHandler(
            root_dir=root_dir,
            memory_service=memory_service,
            llm_service=self.deepseek
        )
        logger.info("调试命令处理器已初始化")
        
        # 初始化时间识别服务（使用已有的 deepseek 实例）
        self.time_recognition = TimeRecognitionService(self.deepseek)
        logger.info("时间识别服务已初始化")

        # 初始化提醒服务（传入自身实例）
        self.reminder_service = ReminderService(self)
        logger.info("提醒服务已初始化")

    def _get_queue_key(self, chat_id: str, sender_name: str, is_group: bool) -> str:
        """生成队列键值
        在群聊中使用 chat_id + sender_name 作为键，在私聊中仅使用 chat_id"""
        return f"{chat_id}_{sender_name}" if is_group else chat_id

    def save_message(self, sender_id: str, sender_name: str, message: str, reply: str, is_system_message: bool = False):
        """保存聊天记录到数据库和短期记忆"""
        try:
            # 保存到数据库
            session = Session()
            chat_message = ChatMessage(
                sender_id=sender_id,
                sender_name=sender_name,
                message=message,
                reply=reply
            )
            session.add(chat_message)
            session.commit()
            session.close()
            
            # 使用新的记忆服务保存对话
            # 获取当前角色名
            avatar_name = self.current_avatar
            # 添加到记忆，传递系统消息标志
            self.memory_service.add_conversation(avatar_name, message, reply, is_system_message)
            
        except Exception as e:
            logger.error(f"保存消息失败: {str(e)}")

    def get_api_response(self, message: str, user_id: str) -> str:
        """获取 API 回复（含记忆增强）"""
        avatar_dir = os.path.join(self.root_dir, config.behavior.context.avatar_dir)
        prompt_path = os.path.join(avatar_dir, "avatar.md")
        # 使用类中已初始化的当前角色名
        avatar_name = self.current_avatar
        
        try:
            # 步骤1：读取原始提示内容
            with open(prompt_path, "r", encoding="utf-8") as f:
                avatar_content = f.read()
                logger.debug(f"角色提示文件大小: {len(avatar_content)} bytes")

            # 步骤2：获取核心记忆
            core_memory = self.memory_service.get_core_memory(avatar_name)
            core_memory_prompt = f"# 核心记忆\n{core_memory}" if core_memory else ""
            logger.debug(f"核心记忆长度: {len(core_memory)}")
            
            # 步骤4：获取历史上下文（仅在程序重启时）
            # 检查是否已经为该用户加载过上下文
            recent_context = None
            if user_id not in self.deepseek.chat_contexts:
                recent_context = self.memory_service.get_recent_context(avatar_name)
                if recent_context:
                    logger.info(f"程序启动：为用户 {user_id} 加载 {len(recent_context)} 条历史上下文消息")
            
            # 调用API，传入人设提示和核心记忆（分开）
            response = self.deepseek.get_response(
                message=message, 
                user_id=user_id, 
                system_prompt=avatar_content, 
                previous_context=recent_context,
                core_memory=core_memory_prompt
            )
            return response

        except Exception as e:
            logger.error(f"获取API响应失败: {str(e)}")
            # 降级处理：使用原始提示，不添加记忆
            return self.deepseek.get_response(message, user_id, self.prompt_content)

    def handle_user_message(self, content: str, chat_id: str, sender_name: str, 
                     username: str, is_group: bool = False, is_image_recognition: bool = False):
        """统一的消息处理入口"""
        try:
            logger.info(f"收到消息 - 来自: {sender_name}" + (" (群聊)" if is_group else ""))
            logger.debug(f"消息内容: {content}")
            
            # 处理调试命令
            if self.debug_handler.is_debug_command(content):
                logger.info(f"检测到调试命令: {content}")
                intercept, response = self.debug_handler.process_command(
                    command=content,
                    current_avatar=self.current_avatar,
                    user_id=chat_id
                )
                
                if intercept:
                    # 发送调试命令的响应
                    if is_group:
                        response = f"@{sender_name} {response}"
                    self.wx.SendMsg(msg=response, who=chat_id)
                    
                    # 不记录调试命令的对话
                    logger.info(f"已处理调试命令: {content}")
                    return None
            
            # 将消息添加到队列，不直接处理
            self._add_to_message_queue(content, chat_id, sender_name, username, is_group, is_image_recognition)
            
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return None

    def _add_to_message_queue(self, content: str, chat_id: str, sender_name: str, 
                            username: str, is_group: bool, is_image_recognition: bool):
        """添加消息到队列并设置定时器"""
        with self.queue_lock:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            queue_key = self._get_queue_key(chat_id, sender_name, is_group)
            
            # 初始化或更新队列
            if queue_key not in self.message_queues:
                logger.info(f"[消息队列] 创建新队列 - 用户: {sender_name}" + (" (群聊)" if is_group else ""))
                self.message_queues[queue_key] = {
                    'messages': [f"[{current_time}]\n{content}"],  # 第一条消息带时间戳
                    'chat_id': chat_id,  # 保存原始chat_id用于发送消息
                    'sender_name': sender_name,
                    'username': username,
                    'is_group': is_group,
                    'is_image_recognition': is_image_recognition,
                    'last_update': time.time()
                }
                logger.debug(f"[消息队列] 首条消息: {content[:50]}...")
            else:
                # 添加新消息到现有队列，后续消息不带时间戳
                self.message_queues[queue_key]['messages'].append(content)
                self.message_queues[queue_key]['last_update'] = time.time()
                msg_count = len(self.message_queues[queue_key]['messages'])
                logger.info(f"[消息队列] 追加消息 - 用户: {sender_name}, 当前消息数: {msg_count}")
                logger.debug(f"[消息队列] 新增消息: {content[:50]}...")

            # 取消现有的定时器
            if queue_key in self.queue_timers and self.queue_timers[queue_key]:
                try:
                    self.queue_timers[queue_key].cancel()
                    logger.debug(f"[消息队列] 重置定时器 - 用户: {sender_name}")
                except Exception as e:
                    logger.error(f"[消息队列] 取消定时器失败: {str(e)}")
                self.queue_timers[queue_key] = None

            # 创建新的定时器
            timer = threading.Timer(
                self.QUEUE_TIMEOUT, 
                self._process_message_queue, 
                args=[queue_key]
            )
            timer.daemon = True
            timer.start()
            self.queue_timers[queue_key] = timer
            logger.info(f"[消息队列] 设置新定时器 - 用户: {sender_name}, {self.QUEUE_TIMEOUT}秒后处理")

    def _process_message_queue(self, queue_key: str):
        """处理消息队列"""
        try:
            with self.queue_lock:
                if queue_key not in self.message_queues:
                    logger.debug("[消息队列] 队列不存在，跳过处理")
                    return

                # 检查是否到达处理时间
                current_time = time.time()
                queue_data = self.message_queues[queue_key]
                last_update = queue_data['last_update']
                sender_name = queue_data['sender_name']
                
                if current_time - last_update < self.QUEUE_TIMEOUT - 0.1:
                    logger.info(f"[消息队列] 等待更多消息 - 用户: {sender_name}, 剩余时间: {self.QUEUE_TIMEOUT - (current_time - last_update):.1f}秒")
                    return

                # 获取并清理队列数据
                queue_data = self.message_queues.pop(queue_key)
                if queue_key in self.queue_timers:
                    self.queue_timers.pop(queue_key)
                
                messages = queue_data['messages']
                chat_id = queue_data['chat_id']  # 使用保存的原始chat_id
                username = queue_data['username']
                sender_name = queue_data['sender_name']
                is_group = queue_data['is_group']
                is_image_recognition = queue_data['is_image_recognition']

                # 合并消息
                combined_message = "\n".join(messages)

                # 打印日志信息
                logger.info(f"[消息队列] 开始处理 - 用户: {sender_name}, 消息数: {len(messages)}")
                logger.info("----------------------------------------")
                logger.info("原始消息列表:")
                for idx, msg in enumerate(messages, 1):
                    logger.info(f"{idx}. {msg}")
                logger.info("\n合并后的消息:")
                logger.info(f"{combined_message}")
                logger.info("----------------------------------------")

                # 检查合并后的消息是否包含时间提醒
                threading.Thread(
                    target=self._check_time_reminder,
                    args=(combined_message, chat_id, sender_name)
                ).start()

                # 检查是否为特殊请求(注释掉了生图功能)
                if self.voice_handler.is_voice_request(combined_message):
                    return self._handle_voice_request(combined_message, chat_id, sender_name, username, is_group)
                elif self.image_handler.is_random_image_request(combined_message):
                    return self._handle_random_image_request(combined_message, chat_id, sender_name, username, is_group)
               # elif not is_image_recognition and self.image_handler.is_image_generation_request(combined_message):
                    #return self._handle_image_generation_request(combined_message, chat_id, sender_name, username, is_group)
                else:
                    return self._handle_text_message(combined_message, chat_id, sender_name, username, is_group)

        except Exception as e:
            logger.error(f"处理消息队列失败: {str(e)}")
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
        
        # 判断是否是系统消息
        is_system_message = sender_name == "System" or username == "System"
        
        # 异步保存消息记录
        threading.Thread(target=self.save_message, 
                       args=(username, sender_name, content, reply, is_system_message)).start()
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
            
            # A判断是否是系统消息
            is_system_message = sender_name == "System" or username == "System"
            
            # 异步保存消息记录
            threading.Thread(target=self.save_message, 
                           args=(username, sender_name, content, reply, is_system_message)).start()
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
            
            # 判断是否是系统消息
            is_system_message = sender_name == "System" or username == "System"
            
            # 异步保存消息记录
            threading.Thread(target=self.save_message, 
                           args=(username, sender_name, content, reply, is_system_message)).start()
            return reply
        return None

    def _handle_text_message(self, content, chat_id, sender_name, username, is_group):
        """处理普通文本消息"""
        # 获取AI回复
        reply = self.get_api_response(content, chat_id)
        logger.info(f"AI回复: {reply}")

        # 处理回复中的思考过程
        if "</think>" in reply:
            think_content, reply = reply.split("</think>", 1)
            logger.debug(f"思考过程: {think_content.strip()}")
        
        # 处理群聊中的回复
        if is_group:
            reply = f"@{sender_name} {reply}"
            logger.debug("已添加群聊@")

        # 判断是否是系统消息
        is_system_message = sender_name == "System" or username == "System"

        # 发送文本消息和表情
        if '$' in reply:
            parts = [p.strip() for p in reply.split('$') if p.strip()]
            for part in parts:
                # 检查当前部分是否包含表情标签
                emotion_tags = self.emoji_handler.extract_emotion_tags(part)
                if emotion_tags:
                    logger.debug(f"消息片段包含表情: {emotion_tags}")
                
                # 清理表情标签并发送文本
                clean_part = part
                for tag in emotion_tags:
                    clean_part = clean_part.replace(f'[{tag}]', '')
                
                if clean_part.strip():
                    self.wx.SendMsg(msg=clean_part.strip(), who=chat_id)
                    logger.debug(f"发送消息: {clean_part[:20]}...")
                
                # 发送该部分包含的表情
                for emotion_type in emotion_tags:
                    try:
                        emoji_path = self.emoji_handler.get_emoji_for_emotion(emotion_type)
                        if emoji_path:
                            self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                            logger.debug(f"已发送表情: {emotion_type}")
                            time.sleep(1)
                    except Exception as e:
                        logger.error(f"发送表情失败 - {emotion_type}: {str(e)}")
                
                time.sleep(random.randint(2, 4))
        else:
            # 处理不包含分隔符的消息
            emotion_tags = self.emoji_handler.extract_emotion_tags(reply)
            if emotion_tags:
                logger.debug(f"消息包含表情: {emotion_tags}")
            
            clean_reply = reply
            for tag in emotion_tags:
                clean_reply = clean_reply.replace(f'[{tag}]', '')
            
            if clean_reply.strip():
                self.wx.SendMsg(msg=clean_reply.strip(), who=chat_id)
                logger.debug(f"发送消息: {clean_reply[:20]}...")
            
            # 发送表情
            for emotion_type in emotion_tags:
                try:
                    emoji_path = self.emoji_handler.get_emoji_for_emotion(emotion_type)
                    if emoji_path:
                        self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                        logger.debug(f"已发送表情: {emotion_type}")
                        time.sleep(1)
                except Exception as e:
                    logger.error(f"发送表情失败 - {emotion_type}: {str(e)}")

        # 异步保存消息记录，标记系统消息
        threading.Thread(target=self.save_message,
                        args=(username, sender_name, content, reply, is_system_message)).start()

        return reply

    def _check_time_reminder(self, content: str, chat_id: str, sender_name: str):
        """检查和处理时间提醒"""
        try:
            # 使用 time_recognition 服务识别时间
            time_infos = self.time_recognition.recognize_time(content)
            if time_infos:
                for target_time, reminder_content in time_infos:
                    logger.info(f"检测到提醒请求 - 用户: {sender_name}")
                    logger.info(f"提醒时间: {target_time}, 内容: {reminder_content}")
                    
                    # 使用 reminder_service 创建提醒
                    success = self.reminder_service.add_reminder(
                        chat_id=chat_id,
                        target_time=target_time,
                        content=reminder_content,
                        sender_name=sender_name,
                        silent=True
                    )
                    
                    if success:
                        logger.info("提醒任务创建成功")
                    else:
                        logger.error("提醒任务创建失败")
                    
        except Exception as e:
            logger.error(f"处理时间提醒失败: {str(e)}")

    def add_to_queue(self, chat_id: str, content: str, sender_name: str,
                    username: str, is_group: bool = False):
        """添加消息到队列（兼容旧接口）"""
        return self._add_to_message_queue(content, chat_id, sender_name, username, is_group, False)
        
    def process_messages(self, chat_id: str):
        """处理消息队列中的消息（已废弃，保留兼容）"""
        # 该方法不再使用，保留以兼容旧代码
        logger.warning("process_messages方法已废弃，使用handle_message代替")
        pass 
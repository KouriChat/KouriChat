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
                 max_groups, robot_name, prompt_content, image_handler, emoji_handler, voice_handler, memory_handler, is_qq=False):
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
            self.wx = WeChat()

        # 添加 handlers
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler
        self.memory_handler = memory_handler
        self.unanswered_counters = {}
        self.unanswered_timers = {}  # 新增：存储每个用户的计时器

    def save_message(self, sender_id: str, sender_name: str, message: str, reply: str):
        """保存聊天记录到数据库和记忆"""
        try:
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
            
            # 保存到记忆 - 移除这一行，避免重复保存
            # self.memory_handler.add_short_memory(message, reply, sender_id)
            logger.info(f"已保存消息到数据库 - 用户ID: {sender_id}")
        except Exception as e:
            logger.error(f"保存消息失败: {str(e)}", exc_info=True)

    def get_api_response(self, message: str, user_id: str) -> str:
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
            recent_history = self.memory_handler.get_recent_memory(user_id, max_count=5)  # 获取最近5轮对话
            
            # 构建带有历史记录的上下文
            context = original_content + "\n\n最近的对话记录：\n"
            for hist in recent_history:
                context += f"用户: {hist['message']}\n"
                context += f"AI: {hist['reply']}\n"
            
            # 添加当前用户的输入
            context += f"\n用户: {message}\n"
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
                    username: str, is_group: bool = False, is_image_recognition: bool = False):
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
                
            logger.info(f"处理消息 - 发送者: {sender_name}, 聊天ID: {chat_id}, 是否群聊: {is_group}")
            logger.info(f"消息内容: {content}")
            
            # 增加重复消息检测
            message_key = f"{chat_id}_{username}_{hash(content)}"
            current_time = time.time()
            
            # 检查是否需要缓存消息
            if username in self.last_message_time and current_time - self.last_message_time[username] < 5:
                # 取消之前的定时器
                if username in self.message_timer and self.message_timer[username]:
                    self.message_timer[username].cancel()
                
                # 添加到消息缓存
                if username not in self.message_cache:
                    self.message_cache[username] = []
                self.message_cache[username].append({
                    'content': content,
                    'chat_id': chat_id,
                    'sender_name': sender_name,
                    'is_group': is_group,
                    'is_image_recognition': is_image_recognition
                })
                
                # 设置新的定时器
                timer = threading.Timer(5.0, self._process_cached_messages, args=[username])
                timer.start()
                self.message_timer[username] = timer
                
                # 更新最后消息时间
                self.last_message_time[username] = current_time
                return None
            
             # 更新最后消息时间
            self.last_message_time[username] = current_time
            
            # 如果没有需要缓存的消息，直接处理
            if username not in self.message_cache or not self.message_cache[username]:
                return self._handle_text_message(content, chat_id, sender_name, username, is_group, is_image_recognition)
            
            # 如果有缓存的消息，添加当前消息并一起处理
            self.message_cache[username].append({
                'content': content,
                'is_image_recognition': is_image_recognition
            })
            return self._process_cached_messages(username)
            
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return None
            # 检查是否是短时间内的重复消息
            if hasattr(self, '_handled_messages'):
                # 清理超过60秒的旧记录
                self._handled_messages = {k: v for k, v in self._handled_messages.items() 
                                     if current_time - v < 60}
                
                if message_key in self._handled_messages:
                    if current_time - self._handled_messages[message_key] < 5:  # 5秒内的重复消息
                        logger.warning(f"MessageHandler检测到短时间内重复消息，已忽略: {content[:20]}...")
                        return None
            
            else:
                self._handled_messages = {}
            # 更新用户最后回复时间
            if not hasattr(self, '_last_reply_times'):
                self._last_reply_times = {}
            self._last_reply_times[username] = time.time()

            # 记录当前消息处理时间
            self._handled_messages[message_key] = current_time
            
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
                return self._handle_text_message(content, chat_id, sender_name, username, is_group)
                
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return None

    def _process_cached_messages(self, username: str):
        """处理缓存的消息"""
        try:
            if not self.message_cache.get(username):
                return None
            
            # 获取最近的对话记录作为上下文
            recent_history = self.memory_handler.get_recent_memory(username, max_count=1)
            context = ""
            if recent_history:
                context = f"{recent_history[0]['message']}(上次的对话内容，只是提醒，无需进行互动，处理重点请放在后面的新内容)\n"
                logger.info(f"加载了用户 {username} 的最近一轮对话记录作为上下文")
            
            # 合并所有缓存的消息，优先处理图片识别消息
            messages = self.message_cache[username]
            image_messages = [msg for msg in messages if msg.get('is_image_recognition', False)]
            text_messages = [msg for msg in messages if not msg.get('is_image_recognition', False)]
            
            # 按照图片识别消息优先的顺序合并内容
            combined_messages = image_messages + text_messages
            combined_content = context + "\n".join([msg['content'] for msg in combined_messages])
            
            # 使用最后一条消息的参数
            last_message = messages[-1]
            
            # 处理合并后的消息
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
                       args=(username, sender_name, content, reply)).start()
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
                           args=(username, sender_name, content, reply)).start()
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
                           args=(username, sender_name, content, reply)).start()
            return reply
        return None


    def _filter_action_emotion(self, text):
        """智能过滤括号内的动作和情感描述，保留颜文字"""
        
        def is_emoticon(text):
            """判断是否为颜文字"""
            # 定义颜文字常用字符
            emoticon_chars = set('（()）~～‿⁀∀︿⌒▽△□◇○●ˇ＾∇＿゜◕ω・ノ丿╯╰つ⊂＼／┌┐┘└°△▲▽▼◇◆○●◎■□▢▣▤▥▦▧▨▩♡♥ღ☆★✡⁂✧✦❈❇✴✺✹✸✷✶✵✳✲✱✰✯✮✭✬✫✪✩✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁✀✿✾✽✼✻✺✹✸✷✶✵✴✳✲✱✰✯✮✭✬✫✪✩✨✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁❤♪♫♬♩♭♮♯°○◎●◯◐◑◒◓◔◕◖◗¤☼☀☁☂☃☄★☆☎☏⊙◎☺☻☯☭♠♣♧♡♥❤❥❣♂♀☿❀❁❃❈❉❊❋❖☠☢☣☤☥☦☧☨☩☪☫☬☭☮☯☸☹☺☻☼☽☾☿♀♁♂♃♄♆♇♈♉♊♋♌♍♎♏♐♑♒♓♔♕♖♗♘♙♚♛♜♝♞♟♠♡♢♣♤♥♦♧♨♩♪♫♬♭♮♯♰♱♲♳♴♵♶♷♸♹♺♻♼♽♾♿⚀⚁⚂⚃⚄⚆⚇⚈⚉⚊⚋⚌⚍⚎⚏⚐⚑⚒⚓⚔⚕⚖⚗⚘⚙⚚⚛⚜⚝⚞⚟')
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
                split_symbols = {'\\', '|', '￤','\n','\\n'}  # 支持多种手动分割符

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
                           args=(username, sender_name, prompt, reply)).start()
            
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
        if is_end_of_conversation:
            # 如果检测到结束关键词，在消息末尾添加提示
            content += "\n请你回应用户的结束语"
            logger.info(f"检测到对话结束关键词，尝试生成更自然的结束语")

        # 获取 API 回复
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
            split_symbols = {'\\', '|', '￤','\n','\\n'}  # 支持多种手动分割符
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
                    if delayed_reply[i] != delayed_reply[i-1]:
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
                    
                    self.wx.SendMsg(msg=part, who=chat_id)
                    sent_messages.add(part)
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
                        try:
                            self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                            logger.info(f"已发送情感表情包: {emoji_path}")
                        except Exception as e:
                            logger.error(f"发送表情包失败: {str(e)}")
                    else:
                        logger.warning(f"未找到对应情感 {emotion} 的表情包")
                    break

            if not emotion_detected:
                logger.info("未在回复中检测到明显情感")

        except Exception as e:
            logger.error(f"消息处理过程中发生错误: {str(e)}")

        # 异步保存消息记录
        threading.Thread(target=self.save_message,
                         args=(username, sender_name, content, reply)).start()
         # 重置计数器（如果大于0）
        if self.unanswered_counters.get(username, 0) > 0:
            self.unanswered_counters[username] = 0
            logger.info(f"用户 {username} 的未回复计数器: {self.unanswered_counters[username]}")


        return reply

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
                    username: str, is_group: bool = False):
        """添加消息到队列（已废弃，保留兼容）"""
        logger.info("直接处理消息，跳过队列")
        return self.handle_user_message(content, chat_id, sender_name, username, is_group)

    def process_messages(self, chat_id: str):
        """处理消息队列中的消息（已废弃，保留兼容）"""
        logger.warning("process_messages方法已废弃，使用handle_message代替")
        pass

    #以下是onebot QQ方法实现
    def QQ_handle_voice_request(self,content,qqid,sender_name) :
        """处理QQ来源的语音请求"""
        logger.info("处理语音请求")
        reply = self.get_api_response(content, qqid)
        if "</think>" in reply:
            reply = reply.split("</think>", 1)[1].strip()

        voice_path = self.voice_handler.generate_voice(reply)
        # 异步保存消息记录
        threading.Thread(target=self.save_message,
                       args=(qqid, sender_name, content, reply)).start()
        if voice_path:
            return voice_path
        else:
            return reply
    
    def QQ_handle_random_image_request(self,content,qqid,sender_name):
        """处理随机图片请求"""
        logger.info("处理随机图片请求")
        image_path = self.image_handler.get_random_image()
        if image_path:
            reply= "给主人你找了一张好看的图片哦~"
            threading.Thread(target=self.save_message,args=(qqid, sender_name,content,reply)).start()

            return image_path
            # 异步保存消息记录
        return None
    def QQ_handle_image_generation_request(self,content,qqid,sender_name):
        """处理图像生成请求"""
        logger.info("处理画图请求")
        try:
            image_path = self.image_handler.generate_image(content)
            if image_path:
                reply= "这是按照主人您的要求生成的图片\\(^o^)/~"
                threading.Thread(target=self.save_message,
                            args=(qqid, sender_name, content,reply)).start()
                
                return image_path
                # 异步保存消息记录
            else:
                reply = "抱歉主人，图片生成失败了..."
                threading.Thread(target=self.save_message,
                            args=(qqid, sender_name, content,reply)).start()
            return None
        except:
            reply = "抱歉主人，图片生成失败了..."
            threading.Thread(target=self.save_message,
                            args=(qqid, sender_name, content,reply)).start()
            return None
    def QQ_handle_text_message(self,content,qqid,sender_name):
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
            split_symbols = {'\\', '|', '￤','\n','\\n'}  # 支持多种手动分割符
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
                    if delayed_reply[i] != delayed_reply[i-1]:
                        unique_reply.append(delayed_reply[i])
                delayed_reply = unique_reply

            # 检查回复中是否包含情感关键词并发送表情包
            logger.info("开始检查AI回复的情感关键词")
            emotion_detected = False

        
            if not hasattr(self.emoji_handler, 'emotion_map'):
                logger.error("emoji_handler 缺少 emotion_map 属性")
                return delayed_reply # 直接返回分割后的文本，在控制台打印error

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
                        delayed_reply.append(emoji_path) #在发送消息队列后增加path，由响应器处理
                    else:
                        logger.warning(f"未找到对应情感 {emotion} 的表情包")
                    break

            if not emotion_detected:
                logger.info("未在回复中检测到明显情感")
        except Exception as e:
            logger.error(f"消息处理过程中发生错误: {str(e)}")
        # 异步保存消息记录
        threading.Thread(target=self.save_message,
                         args=(qqid, sender_name, content, reply)).start()
        return delayed_reply
        


    def auto_send_message(self, listen_list, robot_wx_name, get_personality_summary, is_quiet_time, start_countdown):
        """自动发送消息的方法"""
        try:
            if is_quiet_time():
                logger.info("当前处于安静时间，跳过自动发送消息")
                start_countdown()
                return

            if listen_list:
                user_id = random.choice(listen_list)
                if user_id not in self.unanswered_counters:
                    self.unanswered_counters[user_id] = 0
                self.unanswered_counters[user_id] += 1

                # 获取当前时间和最近对话记录（限制只获取24小时内的对话）
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(hours=24)
                
                # 修改获取记忆的方式，添加时间限制
                memories = self.memory_handler.get_recent_memory(user_id, max_count=3)
                if memories:
                    # 格式化记忆，添加时间信息
                    formatted_memories = []
                    for memory in memories:
                        # 如果记忆有时间戳，检查是否在24小时内
                        if hasattr(memory, 'timestamp'):
                            memory_time = datetime.fromtimestamp(memory.timestamp)
                            if memory_time > cutoff_time:
                                formatted_memories.append(f"[{memory_time.strftime('%Y-%m-%d %H:%M')}] {memory['message']}")
                    memories_text = "\n".join(formatted_memories) if formatted_memories else "暂无最近对话"
                else:
                    memories_text = "暂无最近对话"
                
                # 获取精简后的性格特点
                personality = get_personality_summary(self.prompt_content)
                
                # 构建优化后的提示信息，明确指出这是新的主动对话
                prompt = f"""现在是{current_time.strftime('%Y-%m-%d %H:%M')}，作为{robot_wx_name}，我想要主动发起一个全新的对话。

                我的主要性格特点：
                {personality}

                过去24小时内的对话记录（仅供参考，不要重复之前的对话）：
                {memories_text}

                请根据我的性格特点和当前时间生成一个全新的、自然的开场白。要求：
                1. 不要直接称呼对方的微信昵称
                2. 可以使用"你"、"您"等称呼
                3. 保持对话的自然性和礼貫性
                4. 不要重复或延续之前的对话内容
                5. 创造性地开启新的话题
                6. 如果新话题主题与之前内容主题类似或一样，则内容以之前对话内容为主，防止出现内容差错"""

                # 获取AI回复
                reply_content = self.get_api_response(prompt, robot_wx_name)
                
                logger.info(f"自动发送消息到 {user_id}: {reply_content}")
                max_retries = 3
                retry_delay = 1.0

                for attempt in range(max_retries):
                    try:
                        self.add_to_queue(
                            chat_id=user_id,
                            content=reply_content,
                            sender_name=robot_wx_name,
                            username=user_id,  # 修改：使用接收者的ID
                            is_group=False
                        )
                        # 将对话记录保存到接收者的记忆中
                        self.memory_handler.add_short_memory(
                            f"我主动发起对话：{reply_content}",
                            "等待回复中...",
                            user_id  # 使用接收者的ID
                        )
                        break
                    except Exception as e:
                        logger.error(f"发送消息失败，第{attempt+1}次重试: {str(e)}")
                        if attempt == max_retries - 1:
                            logger.error("消息发送最终失败")
                            return
                        time.sleep(retry_delay * (attempt + 1))
                start_countdown()
            else:
                logger.error("没有可用的聊天对象")
                start_countdown()

        except Exception as e:
            logger.error(f"自动发送消息失败: {str(e)}")
        finally:
            start_countdown()
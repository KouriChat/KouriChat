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
from typing import Dict, List, Optional, Any
from openai import OpenAI
from wxauto import WeChat
from services.database import Session, ChatMessage
import random
import os
from services.ai.deepseek import DeepSeekAI
from handlers.memory import MemoryHandler
from config import config
from services.Weather.Weather import get_location_by_name, get_weather_24h
import re
import json

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self, 
                 root_dir: str,
                 api_key: str,
                 base_url: str,
                 model: str,
                 max_token: int,
                 temperature: float,
                 max_groups: int,
                 robot_name: str,
                 prompt_content: str,
                 image_handler: Any,
                 emoji_handler: Any,
                 voice_handler: Any):
        """
        初始化消息处理器
        
        Args:
            root_dir: 项目根目录
            api_key: API密钥
            base_url: API基础URL
            model: 使用的模型名称
            max_token: 最大token数
            temperature: 温度参数
            max_groups: 最大对话组数
            robot_name: 机器人名称
            prompt_content: 提示词内容
            image_handler: 图片处理器
            emoji_handler: 表情处理器
            voice_handler: 语音处理器
        """
        # 基础配置
        self.root_dir = root_dir
        self.api_key = api_key
        self.model = model
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        self.robot_name = robot_name
        self.prompt_content = prompt_content
        
        # 初始化 DeepSeek AI
        self.deepseek = DeepSeekAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_token=max_token,
            temperature=temperature,
            max_groups=max_groups
        )
        
        # 消息队列相关
        self.user_queues: Dict[str, Dict[str, Any]] = {}
        self.queue_lock = threading.Lock()
        self.chat_contexts: Dict[str, List[Dict[str, str]]] = {}
        
        # 初始化微信实例
        self.wx = WeChat()

        # 初始化各种处理器
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler

        # 初始化记忆处理器
        self.memory_handler = MemoryHandler(
            root_dir=root_dir,
            api_endpoint=base_url  # 使用传入的 base_url
        )

        # 天气关键词列表
        self.weather_keywords = [
            "天气", "下雨", "温度", "气温", 
            "热不热", "冷不冷", "查天气", "今天天气"
        ]

        logger.info("MessageHandler 初始化完成")

    def save_message(self, sender_id: str, sender_name: str, message: str, reply: str):
        """保存聊天记录到数据库和短期记忆"""
        try:
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
            self.memory_handler.add_to_short_memory(message, reply)
        except Exception as e:
            print(f"保存消息失败: {str(e)}")

    def get_api_response(self, message: str, user_id: str) -> str:
        """获取 API 回复（含记忆增强）"""
        # 查询相关记忆
        memories = self.memory_handler.get_relevant_memories(message)

        # 更新prompt文件
        prompt_path = os.path.join(self.root_dir, config.behavior.context.avatar_dir, "avatar.md")
        with open(prompt_path, "r+", encoding="utf-8") as f:
            content = f.read()
            if "#记忆" in content:
                memory_section = "\n".join([m["content"] for m in memories])
                new_content = content.replace("#记忆", f"#记忆\n{memory_section}")
                f.seek(0)
                f.write(new_content)
            f.seek(0)
            full_prompt = f.read()

        # 调用原有API
        return self.deepseek.get_response(message, user_id, full_prompt)

    def is_weather_request(self, message: str) -> bool:
        """检查是否是天气查询请求"""
        try:
            # 去除时间戳
            message = re.sub(r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]', '', message).strip()
            
            # 检查是否包含天气关键词
            for keyword in self.weather_keywords:
                if keyword in message:
                    return True
            return False
        except Exception as e:
            logger.error(f"检查天气请求时出错: {str(e)}")
            return False

    def get_weather_info(self, message: str) -> str:
        """获取天气信息"""
        try:
            # 获取配置中所有城市的天气信息
            weather_info_list = []
            city_list = config.media.weather.city_list
            
            if not city_list:
                return "抱歉，还没有配置要监听的城市，请先在配置页面添加城市。"
            
            logger.debug(f"正在获取以下城市的天气: {city_list}")
            
            for city_name in city_list:
                try:
                    # 获取城市坐标
                    location = config.media.weather.get_city_location(city_name)
                    if not location:
                        logger.warning(f"无法获取城市 {city_name} 的位置信息")
                        continue

                    # 获取天气数据
                    weather_data = get_weather_24h(location)
                    if not weather_data or 'hourly' not in weather_data:
                        logger.warning(f"无法获取城市 {city_name} 的天气数据: {weather_data}")
                        continue

                    # 格式化天气信息
                    hourly = weather_data["hourly"][0]
                    weather_info = {
                        "city": city_name,
                        "time": hourly['fxTime'].split('T')[1][:5],
                        "temperature": hourly['temp'],
                        "weather": hourly['text'],
                        "humidity": hourly['humidity'],
                        "wind_dir": hourly['windDir'],
                        "wind_scale": hourly['windScale']
                    }
                    weather_info_list.append(weather_info)
                    logger.info(f"成功获取 {city_name} 的天气信息")
                    
                except Exception as e:
                    logger.error(f"处理城市 {city_name} 的天气信息时出错: {str(e)}")
                    continue

            if not weather_info_list:
                return "抱歉，获取天气信息失败了"

            # 构建天气描述
            weather_descriptions = []
            for info in weather_info_list:
                desc = f"{info['city']}：\n" \
                       f"- 时间：{info['time']}\n" \
                       f"- 温度：{info['temperature']}℃\n" \
                       f"- 天气：{info['weather']}\n" \
                       f"- 湿度：{info['humidity']}%\n" \
                       f"- 风向：{info['wind_dir']}\n" \
                       f"- 风力：{info['wind_scale']}级"
                weather_descriptions.append(desc)

            # 构建提示词并调用AI
            prompt = f"""
用户询问了天气情况。
当前各个城市的天气情况：
{'\n\n'.join(weather_descriptions)}

请你根据这些天气信息，以符合人设的口吻自然地回复用户。
不要带有时间信息
"""

            # 构建消息列表并调用AI
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message}
            ]

            reply = self.deepseek.chat(messages, temperature=0.9)
            if not reply:
                return '\n\n'.join(weather_descriptions)

            return reply

        except Exception as e:
            logger.error(f"获取天气信息失败: {str(e)}", exc_info=True)
            return "抱歉，获取天气信息时出现错误"

    def process_messages(self, chat_id: str):
        """处理消息队列中的消息"""
        with self.queue_lock:
            if chat_id not in self.user_queues:
                return
            user_data = self.user_queues.pop(chat_id)
            messages = user_data['messages']
            sender_name = user_data['sender_name']
            username = user_data['username']
            is_group = user_data.get('is_group', False)

        messages = messages[-5:]
        merged_message = ' \\ '.join(messages)
        print("\n" + "="*50)
        print(f"收到消息 - 发送者: {sender_name}")
        print(f"消息内容: {merged_message}")
        print("-"*50)

        try:
            # 在现有的条件判断前添加天气查询的判断
            if self.is_weather_request(merged_message):
                logger.info("检测到天气查询请求")
                reply = self.get_weather_info(merged_message)
                
                if is_group:
                    reply = f"@{sender_name} {reply}"
                self.wx.SendMsg(msg=reply, who=chat_id)
                
                # 异步保存消息记录
                threading.Thread(target=self.save_message, 
                               args=(username, sender_name, merged_message, reply)).start()
                return

            # 检查消息是否包含图片识别结果
            is_image_recognition = any("发送了图片：" in msg or "发送了表情包：" in msg for msg in messages)
            if is_image_recognition:
                print("消息类型: 图片识别结果")
            
            # 检查是否为语音请求
            if self.voice_handler.is_voice_request(merged_message):
                logger.info("检测到语音请求")
                reply = self.get_api_response(merged_message, chat_id)
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
                               args=(username, sender_name, merged_message, reply)).start()
                return

            # 检查是否为随机图片请求
            elif self.image_handler.is_random_image_request(merged_message):
                logger.info("检测到随机图片请求")
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
                    return

            # 检查是否为图像生成请求，但跳过图片识别结果
            elif not is_image_recognition and self.image_handler.is_image_generation_request(merged_message):
                logger.info("检测到画图请求")
                image_path = self.image_handler.generate_image(merged_message)
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
                    return

            # 检查是否需要发送表情包
            elif self.emoji_handler.is_emoji_request(merged_message):
                logger.info("检测到表情包请求")
                print("表情包请求")
                emoji_path = self.emoji_handler.get_emotion_emoji(merged_message)
                if emoji_path:
                    try:
                        self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                        logger.info(f"附加情感表情包: {emoji_path}")
                        reply = "给主人发送了一个表情包哦~"
                    except Exception as e:
                        logger.error(f"发送表情包失败: {str(e)}")
                        reply = "抱歉主人，表情包发送失败了..."
                    
                    if is_group:
                        reply = f"@{sender_name} {reply}"
                    self.wx.SendMsg(msg=reply, who=chat_id)
                    return

            # 处理普通文本回复
            else:
                logger.info("处理普通文本回复")
                reply = self.get_api_response(merged_message, chat_id)
                if "</think>" in reply:
                    think_content, reply = reply.split("</think>", 1)
                    print("\n思考过程:")
                    print(think_content.strip())
                    print("\nAI回复:")
                    print(reply.strip())
                else:
                    print("\nAI回复:")
                    print(reply)
                
                if is_group:
                    reply = f"@{sender_name} {reply}"

                if '\\' in reply:
                    parts = [p.strip() for p in reply.split('\\') if p.strip()]
                    for part in parts:
                        self.wx.SendMsg(msg=part, who=chat_id)
                        time.sleep(random.randint(2, 4))
                else:
                    self.wx.SendMsg(msg=reply, who=chat_id)

                # 异步保存消息记录
                threading.Thread(target=self.save_message, 
                               args=(username, sender_name, merged_message, reply)).start()

            print("="*50 + "\n")

        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            print("\n处理消息时出现错误:")
            print(f"错误信息: {str(e)}")
            print("="*50 + "\n")

    def add_to_queue(self, chat_id: str, content: str, sender_name: str, 
                    username: str, is_group: bool = False):
        """添加消息到队列"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_aware_content = f"[{current_time}] {content}"

        with self.queue_lock:
            if chat_id not in self.user_queues:
                self.user_queues[chat_id] = {
                    'timer': threading.Timer(5.0, self.process_messages, args=[chat_id]),
                    'messages': [time_aware_content],
                    'sender_name': sender_name,
                    'username': username,
                    'is_group': is_group
                }
                self.user_queues[chat_id]['timer'].start()
            else:
                self.user_queues[chat_id]['timer'].cancel()
                self.user_queues[chat_id]['messages'].append(time_aware_content)
                self.user_queues[chat_id]['timer'] = threading.Timer(5.0, self.process_messages, args=[chat_id])
                self.user_queues[chat_id]['timer'].start() 
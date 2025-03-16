"""
表情包处理模块
负责处理表情包相关功能，包括:
- 表情包请求识别
- 表情包选择
- 表情包截图
- 文件管理
"""

import os
import random
import logging
import re
from datetime import datetime
import pyautogui
import time
from wxauto import WeChat
from typing import Tuple, Optional
from src.config.rag_config import config

# 基础表情包触发概率配置（巧可酱快来写进前端）
EMOJI_TRIGGER_RATE = 0.3 # 基础触发概率30%
TRIGGER_RATE_INCREMENT = 0.15  # 未触发时概率增加量
MAX_TRIGGER_RATE = 0.8  # 最大触发概率

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class EmojiHandler:
    def __init__(self, root_dir, wx_instance=None, sentiment_analyzer=None):
        self.root_dir = root_dir
        self.wx = wx_instance  # 使用传入的 WeChat 实例
        self.sentiment_analyzer = sentiment_analyzer  # 情感分析器实例
        self.emoji_dir = os.path.join(root_dir, config.behavior.context.avatar_dir, "emojis")
        self.screenshot_dir = os.path.join(root_dir, 'screenshot')
        
        # 情感目录映射 
        # 这个没办法了，要适配原先的目录结构，后续我会改掉的
        # 争取能适配所有的表情包
        self.emotion_dir_map = {
            'Happy': 'happy',
            'Sad': 'sad',
            'Anger': 'angry',
            'Neutral': 'neutral',
            'Surprise': 'neutral',
            'Fear': 'sad',
            'Depress': 'sad',
            'Dislike': 'angry'
        }
        
        # 触发概率状态维护 {user_id: current_prob}
        self.trigger_states = {}
        
        # 确保目录存在
        os.makedirs(self.emoji_dir, exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def is_emoji_request(self, text: str) -> bool:
        """判断是否为表情包请求"""
        emoji_keywords = ["来个表情包", "斗图", "gif", "动图"]
        return any(keyword in text.lower() for keyword in emoji_keywords)

    def _get_emotion_dir(self, emotion_type: str) -> str:
        """将情感分析结果映射到目录"""
        return self.emotion_dir_map.get(emotion_type, 'neutral')

    def _update_trigger_prob(self, user_id: str, triggered: bool):
        """更新触发概率状态"""
        current_prob = self.trigger_states.get(user_id, EMOJI_TRIGGER_RATE)
        
        if triggered:
            # 触发后重置概率
            new_prob = EMOJI_TRIGGER_RATE
        else:
            # 未触发时增加概率（使用指数衰减）
            new_prob = min(current_prob + TRIGGER_RATE_INCREMENT * (1 - current_prob), MAX_TRIGGER_RATE)
        
        self.trigger_states[user_id] = new_prob
        logger.debug(f"用户 {user_id} 触发概率更新: {current_prob:.2f} -> {new_prob:.2f}")

    def should_send_emoji(self, user_id: str) -> bool:
        """判断是否应该发送表情包"""
        current_prob = self.trigger_states.get(user_id, EMOJI_TRIGGER_RATE)
        if random.random() < current_prob:
            self._update_trigger_prob(user_id, True)
            return True
        self._update_trigger_prob(user_id, False)
        return False

    def get_emotion_emoji(self, text: str, user_id: str) -> Optional[str]:
        """根据情感分析结果获取对应表情包"""
        try:
            if not self.sentiment_analyzer:
                logger.warning("情感分析器未初始化")
                return None
                
            # 获取情感分析结果
            result = self.sentiment_analyzer.analyze(text)
            emotion = result.get('sentiment_type', 'Neutral')
            
            # 映射到目录
            target_emotion = self._get_emotion_dir(emotion)
            target_dir = os.path.join(self.emoji_dir, target_emotion)
            
            # 回退机制处理
            if not os.path.exists(target_dir):
                if os.path.exists(self.emoji_dir):
                    logger.warning(f"情感目录 {target_emotion} 不存在，使用根目录")
                    target_dir = self.emoji_dir
                else:
                    logger.error(f"表情包根目录不存在: {self.emoji_dir}")
                    return None

            # 获取有效表情包文件
            emoji_files = [f for f in os.listdir(target_dir)
                          if f.lower().endswith(('.gif', '.jpg', '.png', '.jpeg'))]
            
            if not emoji_files:
                logger.warning(f"目录中未找到表情包: {target_dir}")
                return None
                
            # 判断是否触发
            if not self.should_send_emoji(user_id):
                logger.info(f"未触发表情发送（用户 {user_id}）")
                return None
                
            # 随机选择并返回路径
            selected = random.choice(emoji_files)
            logger.info(f"已选择 {target_emotion} 表情包: {selected}")
            return os.path.join(target_dir, selected)
        except Exception as e:
            logger.error(f"获取表情包失败: {str(e)}", exc_info=True)
            return None

    def capture_emoji_screenshot(self, username: str) -> str:
        """捕获并保存表情包截图"""
        try:
            # 确保目录存在
            emoji_dir = os.path.join(self.root_dir, "data", "emoji_cache")
            os.makedirs(emoji_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"emoji_{username}_{timestamp}.png"
            filepath = os.path.join(emoji_dir, filename)
            
            # 等待表情加载
            time.sleep(0.5)
            
            # 使用 pyautogui 的安全模式
            pyautogui.FAILSAFE = True
            
            # 获取当前活动窗口
            try:
                wx_chat = WeChat()
                wx_chat.ChatWith(username)  # 确保切换到正确的聊天窗口
                chat_window = pyautogui.getWindowsWithTitle(username)[0]
                
                # 确保窗口被前置和激活
                if not chat_window.isActive:
                    chat_window.activate()
                
                # 获取消息区域的位置（右下角）
                window_width = chat_window.width
                window_height = chat_window.height
                
                # 计算表情区域（消息区域的右侧）
                emoji_width = 150
                emoji_height = 150
                emoji_x = chat_window.left + window_width - emoji_width - 50  # 右边缘偏移50像素
                emoji_y = chat_window.top + window_height - emoji_height - 50  # 下边缘偏移50像素
                
                # 截取表情区域
                screenshot = pyautogui.screenshot(region=(emoji_x, emoji_y, emoji_width, emoji_height))
                screenshot.save(filepath)
                
                logger.info(f"表情包已保存: {filepath}")
                return filepath
            except Exception as e:
                logger.error(f"窗口操作失败: {str(e)}")
                return ""
                
        except Exception as e:
            logger.error(f"截图失败: {str(e)}")
            return ""

    def capture_chat_screenshot(self, who: str) -> str:
        """捕获并保存聊天窗口截图"""
        try:
            # 确保截图目录存在
            os.makedirs(self.screenshot_dir, exist_ok=True)
            
            screenshot_path = os.path.join(
                self.screenshot_dir, 
                f'{who}_{datetime.now().strftime("%Y%m%d%H%M%S")}.png'
            )
            
            try:
                # 激活并定位微信聊天窗口
                wx_chat = WeChat()
                wx_chat.ChatWith(who)
                chat_window = pyautogui.getWindowsWithTitle(who)[0]
                
                # 确保窗口被前置和激活
                if not chat_window.isActive:
                    chat_window.activate()
                if not chat_window.isMaximized:
                    chat_window.maximize()
                
                # 获取窗口的坐标和大小
                x, y, width, height = chat_window.left, chat_window.top, chat_window.width, chat_window.height

                time.sleep(1)  # 短暂等待确保窗口已激活

                # 截取指定窗口区域的屏幕
                screenshot = pyautogui.screenshot(region=(x, y, width, height))
                screenshot.save(screenshot_path)
                logger.info(f'已保存截图: {screenshot_path}')
                return screenshot_path
                
            except Exception as e:
                logger.error(f'截取或保存截图失败: {str(e)}')
                return None
                
        except Exception as e:
            logger.error(f'创建截图目录失败: {str(e)}')
            return None

    def cleanup_screenshot_dir(self):
        """清理截图目录"""
        try:
            if os.path.exists(self.screenshot_dir):
                for file in os.listdir(self.screenshot_dir):
                    file_path = os.path.join(self.screenshot_dir, file)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        logger.error(f"删除截图失败 {file_path}: {str(e)}")
        except Exception as e:
            logger.error(f"清理截图目录失败: {str(e)}")

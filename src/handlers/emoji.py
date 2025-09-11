"""
表情包处理模块
负责处理表情包相关功能，包括:
- 表情标签识别
- 表情包选择
- 文件管理
"""

import os
import random
import logging
from typing import Optional
from datetime import datetime
import pyautogui
import time
from wxauto import WeChat
from data.config import config

logger = logging.getLogger('main')

class EmojiHandler:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        # 修改表情包目录路径为avatar目录下的emojis
        self.emoji_dir = os.path.join(root_dir, config.behavior.context.avatar_dir, "emojis")

        # 支持的表情类型
        self.emotion_types = [
    'happy', 'sad', 'angry', 'neutral', 'love', 'funny', 'cute', 'bored', 'shy',
    'embarrassed', 'sleepy', 'lonely', 'hungry', 'comfort', 'surprise', 'confused',
    'playful', 'excited', 'tease', 'hot', 'speechless', 'scared', 'emo_1',
    'emo_2', 'emo_3', 'emo_4', 'emo_5', 'afraid', 'amused', 'anxious',
    'confident', 'cold', 'suspicious', 'loving', 'curious', 'envious',
    'jealous', 'miserable', 'stupid', 'sick', 'ashamed', 'withdrawn',
    'indifferent', 'sorry', 'determined', 'crazy', 'bashful', 'depressed',
    'enraged', 'frightened', 'interested', 'hopeful', 'regretful', 'stubborn',
    'thirsty', 'guilty', 'nervous', 'disgusted', 'proud', 'ecstatic',
    'frustrated', 'hurt', 'tired', 'smug', 'thoughtful', 'pained', 'optimistic',
    'relieved', 'puzzled', 'shocked', 'joyful', 'skeptical', 'bad', 'worried']


        self.screenshot_dir = os.path.join(root_dir, 'screenshot')

    def extract_emotion_tags(self, text: str) -> list:
        """从文本中提取表情标签"""
        tags = []
        start = 0
        while True:
            start = text.find('[', start)
            if start == -1:
                break
            end = text.find(']', start)
            if end == -1:
                break
            tag = text[start+1:end].lower()
            if tag in self.emotion_types:
                tags.append(tag)
                logger.info(f"检测到表情标签: {tag}")
            start = end + 1
        return tags

    def get_emoji_for_emotion(self, emotion_type: str) -> Optional[str]:
        """根据情感类型获取对应表情包"""
        try:
            target_dir = os.path.join(self.emoji_dir, emotion_type)
            logger.info(f"查找表情包目录: {target_dir}")

            if not os.path.exists(target_dir):
                logger.warning(f"情感目录不存在: {target_dir}")
                return None

            emoji_files = [f for f in os.listdir(target_dir)
                          if f.lower().endswith(('.gif', '.jpg', '.png', '.jpeg'))]

            if not emoji_files:
                logger.warning(f"目录中未找到表情包: {target_dir}")
                return None

            selected = random.choice(emoji_files)
            emoji_path = os.path.join(target_dir, selected)
            logger.info(f"已选择 {emotion_type} 表情包: {emoji_path}")
            return emoji_path

        except Exception as e:
            logger.error(f"获取表情包失败: {str(e)}")
            return None

    def capture_and_save_screenshot(self, who: str) -> str:
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

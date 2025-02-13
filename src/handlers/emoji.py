"""
表情包处理模块
负责处理表情包相关功能，包括:
- 表情包请求识别
- 随机表情包选择
- 表情包截图
- 文件管理
"""

# 提取表情包处理相关代码 

import os
import random
import logging
import re
from datetime import datetime
import pyautogui
from wxauto import WeChat

logger = logging.getLogger(__name__)

class EmojiHandler:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.emoji_dir = os.path.join(root_dir, "data", "avatars", "ATRI", "emoji")
        self.screenshot_dir = os.path.join(root_dir, 'screenshot')
        
        # 确保目录存在
        os.makedirs(self.emoji_dir, exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def is_emoji_request(self, text: str) -> bool:
        """判断是否为表情包请求"""
        # 直接请求表情包的关键词
        emoji_keywords = ["表情包", "表情", "斗图", "gif", "动图"]
        
        # 情感表达关键词
        emotion_keywords = ["开心", "难过", "生气", "委屈", "高兴", "伤心",
                          "哭", "笑", "怒", "喜", "悲", "乐", "泪", "哈哈",
                          "呜呜", "嘿嘿", "嘻嘻", "哼", "啊啊", "呵呵", "可爱"]
        
        # 检查直接请求
        if any(keyword in text.lower() for keyword in emoji_keywords):
            return True
            
        # 检查情感表达
        if any(keyword in text for keyword in emotion_keywords):
            return True
            
        return False

    def get_random_emoji(self) -> str:
        """从表情包目录随机获取一个表情包"""
        try:
            if not os.path.exists(self.emoji_dir):
                logger.error(f"表情包目录不存在: {self.emoji_dir}")
                return None
                
            emoji_files = [f for f in os.listdir(self.emoji_dir) 
                          if f.lower().endswith(('.gif', '.jpg', '.png', '.jpeg'))]
            
            if not emoji_files:
                return None
                
            random_emoji = random.choice(emoji_files)
            return os.path.join(self.emoji_dir, random_emoji)
        except Exception as e:
            logger.error(f"获取表情包失败: {str(e)}")
            return None

    def capture_and_save_screenshot(self, who: str) -> str:
        """捕获并保存聊天窗口截图"""
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
            logger.error(f'保存截图失败: {str(e)}')
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
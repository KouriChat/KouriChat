"""
语音处理模块
负责处理语音相关功能，包括:
- 语音请求识别
- TTS语音生成
- 语音文件管理
- 清理临时文件
"""

import os
import logging
import requests
import win32gui
import win32con
import time
import pyautogui
import re
import pyperclip
from PIL import Image
from datetime import datetime
from typing import Optional
import speech_recognition as sr

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class VoiceHandler:
    def __init__(self, root_dir, tts_api_url):
        self.root_dir = root_dir
        self.tts_api_url = tts_api_url
        self.voice_dir = os.path.join(root_dir, "data", "voices")
        
        # 确保语音目录存在
        os.makedirs(self.voice_dir, exist_ok=True)

    def is_voice_request(self, text: str) -> bool:
        """判断是否为语音请求"""
        voice_keywords = ["语音"]
        return any(keyword in text for keyword in voice_keywords)

    def generate_voice(self, text: str) -> Optional[str]:
        """调用TTS API生成语音"""
        try:
            # 确保语音目录存在
            if not os.path.exists(self.voice_dir):
                os.makedirs(self.voice_dir)
                
            # 生成唯一的文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            voice_path = os.path.join(self.voice_dir, f"voice_{timestamp}.wav")
            
            # 调用TTS API
            response = requests.get(f"{self.tts_api_url}?text={text}", stream=True)
            if response.status_code == 200:
                with open(voice_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return voice_path
            else:
                logger.error(f"语音生成失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"语音生成失败: {str(e)}")
            return None

    def cleanup_voice_dir(self):
        """清理语音目录中的旧文件"""
        try:
            if os.path.exists(self.voice_dir):
                for file in os.listdir(self.voice_dir):
                    file_path = os.path.join(self.voice_dir, file)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            logger.info(f"清理旧语音文件: {file_path}")
                    except Exception as e:
                        logger.error(f"清理语音文件失败 {file_path}: {str(e)}")
        except Exception as e:
            logger.error(f"清理语音目录失败: {str(e)}")
            
    def update_wx_instance(self, wx_instance):
        """更新微信实例"""
        self.wx = wx_instance
        logger.info("语音处理器已更新微信实例")
            
    def recognize_voice_message(self, msg_content: str, chat_id: str, api_client=None) -> Optional[str]:
        """
        识别微信语音消息
        
        Args:
            msg_content: 消息内容，通常是"[语音]x秒,未播放"或类似格式
            chat_id: 聊天ID，用于定位窗口
            api_client: 可选的API客户端，用于语音识别
            
        Returns:
            Optional[str]: 识别结果文本，如果识别失败则返回None
        """
        try:
            if not hasattr(self, 'wx') or not self.wx:
                logger.error("微信实例未初始化，无法识别语音消息")
                return None
                
            logger.info(f"开始识别语音消息: {msg_content}")
            
            # 解析语音长度
            duration_match = re.search(r'\[语音\](\d+)秒', msg_content)
            if duration_match:
                duration = int(duration_match.group(1))
                logger.info(f"语音长度: {duration}秒")
            else:
                logger.warning(f"无法解析语音长度: {msg_content}")
                duration = 0  # 默认值
            
            # 尝试激活微信窗口
            success = False
            try:
                if hasattr(self.wx, 'ChatWith') and callable(self.wx.ChatWith):
                    success = self.wx.ChatWith(chat_id)
                    logger.info(f"切换到聊天: {chat_id}, 结果: {success}")
                    time.sleep(0.5)  # 等待窗口切换
            except Exception as e:
                logger.error(f"切换聊天失败: {str(e)}")
                return f"[语音消息: {duration}秒]"  # 出错时返回占位符
            
            # 查找聊天窗口 - 先尝试查找单独的聊天窗口
            chat_hwnd = self.find_chat_window(chat_id)
            
            if not chat_hwnd:
                # 如果找不到聊天小窗口，尝试使用主窗口
                logger.info("未找到聊天小窗口，尝试使用主窗口")
                chat_hwnd = win32gui.FindWindow("WeChatMainWndForPC", None)
                if not chat_hwnd:
                    logger.error("找不到微信窗口")
                    return f"[语音消息: {duration}秒]"
            else:
                logger.info(f"找到聊天小窗口，hwnd: {chat_hwnd}")
                # 激活聊天小窗口
                win32gui.SetForegroundWindow(chat_hwnd)
                time.sleep(0.5)  # 等待窗口激活
            
            # 获取窗口位置
            rect = win32gui.GetWindowRect(chat_hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            logger.info(f"窗口位置和大小: {rect}, 宽: {width}, 高: {height}")
            
            # 确保窗口在前台
            try:
                win32gui.SetForegroundWindow(chat_hwnd)
                time.sleep(1.0)  # 给窗口切换更多时间
                logger.info("已切换窗口到前台")
            except Exception as e:
                logger.error(f"设置窗口前台失败: {str(e)}")
                # 继续执行，尝试点击操作
            
            # 清空剪贴板
            pyperclip.copy('')
            
            # 右键点击最近的语音消息（估算位置）
            # 消息显示区域通常在窗口左侧区域的中下部分
            # 调整点击位置，更靠近底部中央位置，更可能命中最新消息
            
            # 始终设置固定点击位置
            x = rect[0] + int(width * 0.25)  # 水平位置固定为窗口25%处
            y = rect[1] + int(height * 0.70)  # 垂直位置固定为窗口70%处
            
            x0 = x
            y0 = y
            
            logger.info(f"在窗口内右键点击坐标: ({x}, {y})")
            # 左键双击取消选中
            # pyautogui.doubleClick(width*0.5, height * 0.5)
            # 右键点击
            pyautogui.rightClick(x, y)
            time.sleep(1.0)  # 增加等待时间，确保右键菜单显示
            
            # 定位"转文字"选项 - 固定偏移值
            menu_x = x + 10
            menu_y = y + 10
            logger.info(f"尝试点击转文字选项，坐标: ({menu_x}, {menu_y})")
            pyautogui.click(menu_x, menu_y)
            time.sleep(2.0)  # 等待转文字操作
            
            # 转文字完成后直接进行右键复制操作
            # 无论转文字是否成功，都尝试复制可能的文本
            logger.info(f"转文字后右键点击坐标: ({x}, {y+10})")
            pyautogui.rightClick(x, y+10)  # 点击可能的文本位置
            time.sleep(0.8)
            
            # 点击"复制"选项 - 固定偏移值
            copy_x = x + 20
            copy_y = y + 20  # 复制选项通常是菜单的第一项
            logger.info(f"点击复制选项，坐标: ({copy_x}, {copy_y})")
            pyautogui.click(copy_x, copy_y)
            time.sleep(0.8)
            
            # 检查是否获取到文本
            text = pyperclip.paste()
            if text and text.strip() and not text.startswith("[语音]"):
                logger.info(f"成功获取到转写文本: {text}")
                return text
            
            # 如果识别失败，直接返回默认文本
            logger.warning("语音识别未成功")
            return f"[语音消息: {duration}秒]"  # 返回占位文本表示语音长度
        
        except Exception as e:
            logger.error(f"语音消息识别失败: {str(e)}")
            return None
            
    def find_chat_window(self, chat_name: str) -> int:
        """
        查找指定聊天名称的小窗口
        
        Args:
            chat_name: 聊天窗口名称
            
        Returns:
            int: 窗口句柄，如果找不到则返回0
        """
        # 定义查找回调函数
        def enum_windows_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                # 微信聊天窗口的标题通常包含聊天名称
                if chat_name in window_text:
                    window_class = win32gui.GetClassName(hwnd)
                    # 微信聊天窗口类名通常是 "ChatWnd" 或包含 "WeChat"
                    if "ChatWnd" in window_class or "WeChat" in window_class:
                        logger.info(f"找到窗口 - 标题: '{window_text}', 类名: '{window_class}'")
                        results.append(hwnd)
            return True
            
        # 查找所有匹配窗口
        window_handles = []
        win32gui.EnumWindows(enum_windows_callback, window_handles)
        
        if window_handles:
            # 返回第一个匹配窗口
            return window_handles[0]
        
        return 0 
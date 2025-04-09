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
from typing import Optional, Dict
import speech_recognition as sr

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

class VoiceHandler:
    def __init__(self, root_dir, tts_api_url):
        self.root_dir = root_dir
        self.tts_api_url = tts_api_url
        self.voice_dir = os.path.join(root_dir, "data", "voices")
        # 存储窗口句柄
        self.chat_windows: Dict[str, int] = {}
        self.main_window_hwnd: int = 0
        
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
        # 保存主窗口句柄
        self.main_window_hwnd = win32gui.FindWindow("WeChatMainWndForPC", None)
        logger.info(f"语音处理器已更新微信实例，主窗口句柄: {self.main_window_hwnd}")
        
        # 初始化时尝试查找并保存所有已打开的聊天窗口
        def enum_windows_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                window_class = win32gui.GetClassName(hwnd)
                if "ChatWnd" in window_class or "WeChat" in window_class:
                    results.append((window_text, hwnd))
            return True
            
        # 查找所有聊天窗口
        chat_windows = []
        win32gui.EnumWindows(enum_windows_callback, chat_windows)
        
        # 保存找到的窗口句柄
        for window_text, hwnd in chat_windows:
            if window_text:  # 确保窗口有标题
                self.add_chat_window(window_text, hwnd)

    def add_chat_window(self, chat_id: str, hwnd: int):
        """添加聊天窗口句柄"""
        self.chat_windows[chat_id] = hwnd
        logger.info(f"已保存聊天窗口 {chat_id} 的句柄: {hwnd}")
            
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
            
            # 解析语音长度 - 使用更严格的正则表达式，适配多种可能的格式
            # 例如: "[语音]2秒", "[语音]2秒,未播放", "[语音] 2 秒" 等
            duration_match = re.search(r'\[语音\]\s*(\d+)\s*秒', msg_content)
            if not duration_match:
                # 尝试其他可能的格式
                duration_match = re.search(r'\[语音\]\s*(\d+)', msg_content)
                
            if duration_match:
                duration = int(duration_match.group(1))
                logger.info(f"语音长度: {duration}秒")
            else:
                logger.warning(f"无法解析语音长度: {msg_content}")
                # 检查消息内容是否真的是语音消息
                if "[语音]" not in msg_content:
                    logger.error(f"提供的内容不是语音消息: {msg_content}")
                    return None
                duration = 0  # 默认值
            
            # 获取chat_id对应的窗口句柄，如果没有则直接返回
            chat_hwnd = self.chat_windows.get(chat_id, 0)
            
            # 使用窗口句柄
            if chat_hwnd:
                logger.info(f"使用聊天 {chat_id} 的窗口句柄: {chat_hwnd}")
            else:
                logger.info(f"未找到聊天 {chat_id} 的窗口句柄")
                return f"[语音消息: {duration}秒]"
            
            # 激活聊天窗口
            try:
                # 如果窗口最小化，将其恢复
                if win32gui.IsIconic(chat_hwnd):
                    win32gui.ShowWindow(chat_hwnd, win32con.SW_RESTORE)
                    time.sleep(0.2)
                
                # 将窗口置前
                win32gui.SetForegroundWindow(chat_hwnd)
                time.sleep(0.2)
                
                # 确保窗口真的在前台
                win32gui.BringWindowToTop(chat_hwnd)
                time.sleep(0.1)
                
                # 假定 self._current_chat 是为了记录当前聊天，这里我们不需要
                # self._current_chat = chat_id 
                logger.info(f"成功激活缓存的聊天窗口: {chat_id}")
            except Exception as e:
                logger.error(f"激活窗口失败: {str(e)}")
                # 验证窗口句柄是否有效，如果无效则从缓存中移除
                if not win32gui.IsWindow(chat_hwnd):
                    logger.warning(f"缓存的窗口句柄无效，移除: {chat_id}")
                    if chat_id in self.chat_windows:
                        del self.chat_windows[chat_id]
                return f"[语音消息: {duration}秒]"
            
            # 获取窗口位置
            rect = win32gui.GetWindowRect(chat_hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            logger.info(f"窗口位置和大小: {rect}, 宽: {width}, 高: {height}")
            
            # 清空剪贴板
            pyperclip.copy('')
            
            # 始终设置固定点击位置
            x = rect[0] + int(width * 0.22)  # 水平位置固定为窗口22%处
            y = rect[1] + int(height * 0.75)  # 垂直位置固定为窗口75%处
            
            logger.info(f"在窗口内右键点击坐标: ({x}, {y})")
            # 左键双击取消选中
            # pyautogui.doubleClick(width*0.5, height * 0.5)
            # 右键点击
            pyautogui.rightClick(x, y)
            time.sleep(0.2)  # 增加等待时间，确保右键菜单显示
            
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
            time.sleep(0.2)
            
            # 点击"复制"选项 - 固定偏移值
            copy_x = x + 40
            copy_y = y + 20  # 复制选项通常是菜单的第一项
            logger.info(f"点击复制选项，坐标: ({copy_x}, {copy_y})")
            pyautogui.click(copy_x, copy_y)
            time.sleep(0.2)  # 增加等待时间，确保复制操作完成
            
            # 检查是否获取到文本，最多重试3次
            max_retries = 3
            for i in range(max_retries):
                text = pyperclip.paste()
                if text and text.strip() and not text.startswith("[语音]"):
                    logger.info(f"成功获取到转写文本: {text}")
                    return text
                logger.info(f"第{i+1}次尝试获取文本失败，等待后重试...")
                time.sleep(1.0)  # 每次重试前等待1秒
            
            # 如果多次重试后仍然失败，尝试备用方案
            logger.warning("直接复制失败，尝试备用方案")
            # 再次右键点击并尝试复制
            pyautogui.rightClick(x, y+10)
            time.sleep(0.2)
            pyautogui.click(copy_x, copy_y)
            time.sleep(0.2)
            
            # 最后检查一次剪贴板
            text = pyperclip.paste()
            if text and text.strip() and not text.startswith("[语音]"):
                logger.info(f"备用方案成功获取到转写文本: {text}")
                return text
            
            # 如果所有尝试都失败，返回默认文本
            logger.warning("语音识别未成功")
            return f"[语音消息: {duration}秒]"  # 返回占位文本表示语音长度
        
        except Exception as e:
            logger.error(f"语音消息识别失败: {str(e)}")
            return None
            
    def find_chat_window(self, chat_name: str) -> int:
        """
        查找指定聊天名称的小窗口，并保存到窗口句柄字典中
        
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
            # 返回第一个匹配窗口，并保存到字典中
            hwnd = window_handles[0]
            self.add_chat_window(chat_name, hwnd)
            return hwnd
        
        return 0 
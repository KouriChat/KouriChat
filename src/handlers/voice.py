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
from PIL import Image, ImageGrab
import numpy as np
import cv2
from datetime import datetime
from typing import Optional, Tuple
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
        
        # 窗口句柄缓存
        self._window_handles = {}
        
        # 语音转文字相关的配置
        self.max_wait_time = 30  # 最大等待时间（秒）
        self.check_interval = 0.5  # 检查间隔（秒）
        self.min_text_width = 50  # 最小文本宽度（像素）
        
        # 创建临时目录用于存储截图
        self.temp_dir = os.path.join(root_dir, "temp", "voice_recognition")
        os.makedirs(self.temp_dir, exist_ok=True)

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
            
    def find_chat_window(self, chat_name: str) -> int:
        """
        查找指定聊天名称的小窗口
        
        Args:
            chat_name: 聊天窗口名称
            
        Returns:
            int: 窗口句柄，如果找不到则返回0
        """
        # 首先检查缓存
        if chat_name in self._window_handles:
            hwnd = self._window_handles[chat_name]
            if win32gui.IsWindow(hwnd):  # 验证窗口句柄是否有效
                return hwnd
            else:
                # 窗口句柄无效，从缓存中移除
                del self._window_handles[chat_name]
        
        # 定义查找回调函数
        def enum_windows_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
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
            # 缓存并返回第一个匹配窗口
            hwnd = window_handles[0]
            self._window_handles[chat_name] = hwnd
            return hwnd
        
        return 0

    def _locate_voice_message(self, rect: Tuple[int, int, int, int]) -> Optional[Tuple[int, int, int, int]]:
        """
        定位语音消息的位置，直接基于红点位置定义语音条区域
        
        Args:
            rect: 窗口矩形区域 (left, top, right, bottom)
            
        Returns:
            Optional[Tuple[int, int, int, int]]: 语音消息的区域 (x, y, width, height) 或 None
        """
        try:
            # 截取聊天窗口区域
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top
            
            # 保存调试截图
            debug_screenshot_path = os.path.join(self.temp_dir, f"debug_screenshot_{int(time.time())}.png")
            screenshot = ImageGrab.grab(bbox=rect)
            screenshot_np = np.array(screenshot)
            cv2.imwrite(debug_screenshot_path, cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR))
            logger.info(f"保存调试截图: {debug_screenshot_path}")
            
            # 转换为OpenCV格式
            img = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
            img_height, img_width = img.shape[:2]
            
            # 识别红点
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # 定义红色的HSV范围（包括更宽泛的红色范围）
            red_ranges = [
                (np.array([0, 120, 100]), np.array([10, 255, 255])),   # 鲜红色
                (np.array([160, 120, 100]), np.array([180, 255, 255])), # 深红色
                (np.array([0, 100, 100]), np.array([20, 255, 255]))     # 偏橙红色
            ]
            
            # 合并所有红色范围的掩码
            red_mask = np.zeros((img_height, img_width), dtype=np.uint8)
            for lower_red, upper_red in red_ranges:
                red_mask = cv2.bitwise_or(red_mask, cv2.inRange(hsv, lower_red, upper_red))
            
            # 对红点掩码进行形态学操作，去除噪点
            kernel = np.ones((3,3), np.uint8)
            red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
            
            # 保存红点掩码用于调试
            red_mask_path = os.path.join(self.temp_dir, f"debug_red_mask_{int(time.time())}.png")
            cv2.imwrite(red_mask_path, red_mask)
            logger.info(f"保存红点掩码: {red_mask_path}")
            
            # 查找红点轮廓
            red_contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 筛选合适的红点
            voice_candidates = []
            for contour in red_contours:
                rx, ry, rw, rh = cv2.boundingRect(contour)
                
                # 红点大小应该在合理范围内（2-10像素）
                if 2 <= rw <= 10 and 2 <= rh <= 10:
                    # 计算红点的圆形度
                    area = cv2.contourArea(contour)
                    perimeter = cv2.arcLength(contour, True)
                    if perimeter > 0:
                        circularity = 4 * np.pi * area / (perimeter * perimeter)
                        # 圆形度阈值：0.6表示相对圆形的形状
                        if circularity > 0.6:
                            # 直接定义语音条区域（以红点为基准）
                            voice_width = 150  # 固定语音条宽度
                            voice_height = 35  # 固定语音条高度
                            
                            # 计算语音条位置（在红点左侧）
                            x = max(0, rx - voice_width)  # 红点左侧
                            y = max(0, ry - voice_height // 2)  # 垂直居中
                            
                            # 确保y坐标合法
                            y = min(y, img_height - voice_height)
                            
                            voice_candidates.append((x, y, voice_width, voice_height))
                            logger.debug(f"找到语音条候选区域: x={x}, y={y}, w={voice_width}, h={voice_height}, 红点位置: rx={rx}, ry={ry}")
            
            if voice_candidates:
                # 选择最下方的候选区域（最新的消息）
                voice_area = max(voice_candidates, key=lambda x: x[1])
                logger.info(f"最终选择的语音消息区域: {voice_area}")
                
                # 在调试图像上标记选中的区域
                debug_img = img.copy()
                x, y, w, h = voice_area
                cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
                # 标记红点位置
                cv2.circle(debug_img, (x+w, y+h//2), 5, (0, 0, 255), -1)
                result_path = os.path.join(self.temp_dir, f"debug_result_{int(time.time())}.png")
                cv2.imwrite(result_path, debug_img)
                logger.info(f"保存标记结果图像: {result_path}")
                
                return voice_area
            
            # 如果没有找到符合条件的区域，使用默认固定区域
            logger.warning("未找到符合条件的语音消息区域，使用默认区域")
            x = int(width * 0.1)
            w = int(width * 0.3)
            h = 40
            y = int(height * 0.7)
            return (x, y, w, h)
            
        except Exception as e:
            logger.error(f"定位语音消息失败: {str(e)}", exc_info=True)
            x = int(width * 0.1)
            w = int(width * 0.3)
            h = 40
            y = int(height * 0.7)
            logger.info(f"使用默认固定区域: x={x}, y={y}, w={w}, h={h}")
            return (x, y, w, h)

    def _wait_for_text_conversion(self, rect: Tuple[int, int, int, int], voice_area: Tuple[int, int, int, int]) -> bool:
        """
        等待语音转文字完成，使用多重判断机制
        
        Args:
            rect: 窗口矩形区域
            voice_area: 语音消息区域
            
        Returns:
            bool: 是否检测到文字
        """
        try:
            start_time = time.time()
            x, y, w, h = voice_area
            
            # 保存初始状态的图像特征
            initial_screenshot = ImageGrab.grab(bbox=rect)
            initial_np = np.array(initial_screenshot)
            initial_roi = initial_np[y:y+h*2, x:x+w]  # 扩大检测区域到语音条下方
            initial_gray = cv2.cvtColor(initial_roi, cv2.COLOR_RGB2GRAY)
            
            # 计算初始状态的特征
            initial_mean = np.mean(initial_gray)
            initial_std = np.std(initial_gray)
            
            consecutive_detections = 0  # 连续检测到变化的次数
            required_detections = 2     # 需要连续检测到的次数
            
            while time.time() - start_time < self.max_wait_time:
                # 截取当前状态的图像
                current_screenshot = ImageGrab.grab(bbox=rect)
                current_np = np.array(current_screenshot)
                current_roi = current_np[y:y+h*2, x:x+w]  # 扩大检测区域到语音条下方
                current_gray = cv2.cvtColor(current_roi, cv2.COLOR_RGB2GRAY)
                
                # 计算当前状态的特征
                current_mean = np.mean(current_gray)
                current_std = np.std(current_gray)
                
                # 计算差异
                mean_diff = abs(current_mean - initial_mean)
                std_diff = abs(current_std - initial_std)
                
                # 保存调试图像
                debug_path = os.path.join(self.temp_dir, f"debug_conversion_{int(time.time())}.png")
                cv2.imwrite(debug_path, cv2.cvtColor(current_roi, cv2.COLOR_RGB2BGR))
                logger.debug(f"当前状态 - 平均值: {current_mean:.2f}, 标准差: {current_std:.2f}, 差异: {mean_diff:.2f}, {std_diff:.2f}")
                
                # 多重判断条件
                changes_detected = False
                
                # 1. 检测暗色像素数量变化
                dark_pixels = np.sum(current_gray < 100)
                if dark_pixels > (w * h * 0.1):
                    changes_detected = True
                    
                # 2. 检测平均亮度变化
                if mean_diff > 5.0:  # 亮度变化阈值
                    changes_detected = True
                    
                # 3. 检测标准差变化（文字会增加图像的复杂度）
                if std_diff > 3.0:  # 标准差变化阈值
                    changes_detected = True
                    
                # 4. 检测边缘数量变化（文字会产生更多边缘）
                current_edges = cv2.Canny(current_gray, 100, 200)
                edge_pixels = np.sum(current_edges > 0)
                if edge_pixels > (w * h * 0.05):  # 边缘像素比例阈值
                    changes_detected = True
                
                if changes_detected:
                    consecutive_detections += 1
                    logger.debug(f"检测到变化 ({consecutive_detections}/{required_detections})")
                    
                    if consecutive_detections >= required_detections:
                        logger.info("确认检测到转换后的文字")
                        
                        # 保存最终状态的调试图像
                        final_debug_path = os.path.join(self.temp_dir, f"debug_conversion_final_{int(time.time())}.png")
                        cv2.imwrite(final_debug_path, cv2.cvtColor(current_roi, cv2.COLOR_RGB2BGR))
                        
                        return True
                else:
                    consecutive_detections = 0
                
                time.sleep(self.check_interval)
            
            logger.warning("等待转换超时")
            return False
            
        except Exception as e:
            logger.error(f"等待文字转换失败: {str(e)}")
            return False

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
            
            # 查找并激活聊天窗口
            chat_hwnd = self.find_chat_window(chat_id)
            if not chat_hwnd:
                logger.warning("未找到聊天小窗口，尝试使用主窗口")
                chat_hwnd = win32gui.FindWindow("WeChatMainWndForPC", None)
                if not chat_hwnd:
                    logger.error("找不到微信窗口")
                    return f"[语音消息: {duration}秒]"
            
            # 激活窗口
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
                
                logger.info("已切换窗口到前台")
            except Exception as e:
                logger.error(f"设置窗口前台失败: {str(e)}")
                return f"[语音消息: {duration}秒]"
            
            # 获取窗口位置
            rect = win32gui.GetWindowRect(chat_hwnd)
            
            # 定位语音消息
            voice_area = self._locate_voice_message(rect)
            if not voice_area:
                logger.error("无法定位语音消息")
                return f"[语音消息: {duration}秒]"
            
            x, y, w, h = voice_area
            center_x = rect[0] + x + w // 2
            center_y = rect[1] + y + h // 2
            
            # 清空剪贴板
            pyperclip.copy('')
            
            # 右键点击语音消息
            logger.info(f"右键点击语音消息，坐标: ({center_x}, {center_y})")
            pyautogui.rightClick(center_x, center_y)
            time.sleep(0.2)  # 确保右键菜单完全显示
            
            # 点击"转文字"选项（相对位置）
            menu_x = center_x + 10
            menu_y = center_y + 10
            logger.info(f"点击转文字选项，坐标: ({menu_x}, {menu_y})")
            pyautogui.click(menu_x, menu_y)
            time.sleep(0.3)  # 短暂等待转文字开始
            
            # 等待转换完成
            if not self._wait_for_text_conversion(rect, voice_area):
                logger.warning("未检测到转换后的文字")
                return f"[语音消息: {duration}秒]"
            
            # 右键点击转换后的文本位置
            text_x = menu_x
            text_y = menu_y+3  # 文本通常出现在语音消息下方
            logger.info(f"右键点击转换后的文本，坐标: ({text_x}, {text_y})")
            pyautogui.rightClick(text_x, text_y)
            time.sleep(0.3)
            
            # 点击"复制"选项
            copy_x = text_x + 20
            copy_y = text_y + 20
            logger.info(f"点击复制选项，坐标: ({copy_x}, {copy_y})")
            pyautogui.click(copy_x, copy_y)
            time.sleep(0.3)
            
            # 检查是否获取到文本
            text = pyperclip.paste()
            if text and text.strip() and not text.startswith("[语音]"):
                logger.info(f"成功获取到转写文本: {text}")
                return text
            
            # 如果识别失败，返回默认文本
            logger.warning("语音识别未成功")
            return f"[语音消息: {duration}秒]"
        
        except Exception as e:
            logger.error(f"语音消息识别失败: {str(e)}")
            return None 
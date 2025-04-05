"""
微信接口模块
提供与微信交互的接口，包括消息发送、接收和文件操作
"""

import os
import logging
import time
import queue
import traceback
import wxauto
import pythoncom  # 添加pythoncom导入
import random
from typing import Dict, List, Any, Optional, Tuple, Union
import win32gui
import re
import pyautogui
import win32con
import win32api
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger('kourichat')

class WeChat:
    """微信接口类，提供与微信交互的方法"""
    
    def __init__(self):
        """初始化WeChat类"""
        try:
            pythoncom.CoInitialize()  # 初始化COM环境
            self.wx = wxauto.WeChat()
            logger.info("微信接口初始化完成")
            
            # 检查API兼容性
            self._check_api_compatibility()
            
            # 设置图标信息
            self.A_MyIcon = self.IconInfo()
            self.A_MyIcon.Name = self.wx.GetSelfName() if hasattr(self.wx, 'GetSelfName') else "未知机器人"
            
            # 跟踪已添加的监听聊天
            self._listen_chats = set()
            
            # 监听窗口相关
            self._listen_windows = {}  # 存储监听窗口的引用
            self._window_handles = {}  # 存储窗口句柄
            self._current_chat = None  # 当前活动的聊天
            self._window_classes = {}  # 存储窗口类名
            
            # 消息缓存
            self._last_messages = {}  # 存储每个聊天的最后一条消息
            
            # 重连相关
            self._reconnect_attempts = 0
            self._max_reconnect_attempts = 3
            self._reconnect_delay = 10  # 重连等待时间（秒）
            self._last_reconnect_time = 0
            
            logger.info("微信接口初始化完成")
        except Exception as e:
            logger.error(f"微信接口初始化失败: {str(e)}")
            self.wx = None
            self.A_MyIcon = self.IconInfo()
            # 出错时也尝试释放COM
            try:
                pythoncom.CoUninitialize()
            except:
                pass
    
    def _check_api_compatibility(self):
        """检查wxauto API兼容性，记录可用的方法"""
        required_methods = [
            "GetMsgs", "GetAllMessage", "GetLastMessage",
            "SendFiles", "ChatWith", "SendMsg"
        ]
        
        compatibility_report = []
        for method in required_methods:
            if hasattr(self.wx, method):
                compatibility_report.append(f"{method}: 可用")
            else:
                compatibility_report.append(f"{method}: 不可用")
        
        # 记录兼容性报告
        logger.info("WeChat API兼容性检查结果:")
        for report in compatibility_report:
            logger.info(f"  - {report}")
    
    class IconInfo:
        """图标信息类，提供名称等属性"""
        def __init__(self):
            self.Name = "默认机器人"  # 默认名称
    
    def _get_chat_window(self, who: str) -> Optional[Any]:
        """
        获取聊天窗口对象
        
        Args:
            who: 聊天对象名称
            
        Returns:
            Optional[Any]: 聊天窗口对象或None
        """
        try:
            # 如果当前聊天已经是目标聊天，直接获取窗口而不进行切换
            if self._current_chat != who:
                # 切换到指定聊天
                if not self.ChatWith(who):
                    return None
            
            # 获取当前活动的聊天窗口
            windows = wxauto.GetWindowsWithTitle(who)
            if not windows:
                logger.error(f"找不到聊天窗口: {who}")
                return None
            
            # 缓存并返回窗口对象
            window = windows[0]
            self._listen_windows[who] = window
            self._window_handles[who] = window.handle
            return window
            
        except Exception as e:
            logger.error(f"获取聊天窗口失败 {who}: {str(e)}")
            return None
    
    def _ensure_window_active(self, who: str) -> bool:
        """
        确保聊天窗口处于活动状态
        
        Args:
            who: 聊天对象名称
            
        Returns:
            bool: 是否成功
        """
        try:
            if not self.wx:
                logger.error("微信接口未初始化")
                return False
            
            # 检查是否有缓存的窗口句柄
            if who in self._window_handles:
                hwnd = self._window_handles[who]
                if win32gui.IsWindow(hwnd):  # 验证窗口句柄是否有效
                    try:
                        # 如果窗口最小化，将其恢复
                        if win32gui.IsIconic(hwnd):
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            time.sleep(0.2)
                        
                        # 将窗口置前
                        win32gui.SetForegroundWindow(hwnd)
                        time.sleep(0.2)
                        
                        # 确保窗口真的在前台
                        win32gui.BringWindowToTop(hwnd)
                        time.sleep(0.1)
                        
                        self._current_chat = who
                        logger.info(f"成功激活缓存的聊天窗口: {who}")
                        return True
                    except Exception as e:
                        logger.warning(f"激活缓存窗口失败: {str(e)}")
                else:
                    # 窗口句柄无效，从缓存中移除
                    logger.warning(f"缓存的窗口句柄无效，移除: {who}")
                    del self._window_handles[who]
            
            # 如果没有缓存或缓存无效，尝试查找窗口
            def enum_windows_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    window_class = win32gui.GetClassName(hwnd)
                    if who in window_text and ("ChatWnd" in window_class or "WeChat" in window_class):
                        results.append((hwnd, window_class))
                return True
            
            windows = []
            win32gui.EnumWindows(enum_windows_callback, windows)
            
            if windows:
                hwnd, window_class = windows[0]
                # 更新缓存
                self._window_handles[who] = hwnd
                self._window_classes[who] = window_class
                
                # 激活窗口
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    time.sleep(0.2)
                
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.2)
                
                win32gui.BringWindowToTop(hwnd)
                time.sleep(0.1)
                
                self._current_chat = who
                logger.info(f"成功找到并激活聊天窗口: {who}")
                return True
            
            # 如果找不到小窗口，尝试使用ChatWith
            logger.warning(f"找不到聊天小窗口 {who}，尝试使用ChatWith")
            if self.wx.ChatWith(who):
                time.sleep(0.5)  # 等待窗口切换
                self._current_chat = who
                return True
            
            logger.error(f"无法激活聊天窗口: {who}")
            return False
            
        except Exception as e:
            logger.error(f"确保窗口活动状态失败 {who}: {str(e)}", exc_info=True)
            return False
    
    def ChatWith(self, who: str) -> bool:
        """
        切换到指定聊天
        
        Args:
            who: 聊天对象名称
            
        Returns:
            bool: 是否成功
        """
        try:
            if not self.wx:
                logger.error("微信接口未初始化")
                return False
            
            # 如果当前聊天已经是目标聊天，无需切换
            if self._current_chat == who:
                return True
            
            # 优先使用_ensure_window_active方法
            if self._ensure_window_active(who):
                return True
            
            # 如果上述方法都失败，使用wxauto的ChatWith
            result = self.wx.ChatWith(who)
            if result:
                self._current_chat = who
                logger.info(f"使用wxauto切换到聊天: {who}")
                
                # 尝试获取并缓存窗口句柄
                time.sleep(0.5)  # 等待窗口切换完成
                def enum_window_callback(hwnd, results):
                    if win32gui.IsWindowVisible(hwnd):
                        window_text = win32gui.GetWindowText(hwnd)
                        window_class = win32gui.GetClassName(hwnd)
                        if who in window_text and ("ChatWnd" in window_class or "WeChat" in window_class):
                            results.append((hwnd, window_class))
                    return True
                
                windows = []
                win32gui.EnumWindows(enum_window_callback, windows)
                if windows:
                    hwnd, window_class = windows[0]
                    self._window_handles[who] = hwnd
                    self._window_classes[who] = window_class
                    logger.info(f"已缓存新的窗口句柄: {who}")
            
            return result
        except Exception as e:
            logger.error(f"切换聊天失败 {who}: {str(e)}")
            return False
    
    def SendMsg(self, msg: str, who: str = None) -> bool:
        """
        发送文本消息
        
        Args:
            msg: 消息内容
            who: 接收者，如果为None则使用当前聊天
            
        Returns:
            bool: 是否成功
        """
        try:
            if not self.wx:
                logger.error("微信接口未初始化")
                return False
            
            # 确保消息不为空
            if not msg or not msg.strip():
                logger.warning("消息内容为空，跳过发送")
                return False
            
            if who:
                # 如果当前聊天已经是目标聊天，不需要切换
                if self._current_chat != who:
                    logger.info(f"尝试切换聊天到: {who}")
                    # 重试三次切换聊天
                    for attempt in range(3):
                        # 确保窗口处于活动状态
                        if not self._ensure_window_active(who):
                            logger.warning(f"尝试 {attempt+1}: 使用_ensure_window_active切换到聊天 {who} 失败")
                            # 使用基本的ChatWith方法再次尝试
                            if not self.wx.ChatWith(who):
                                logger.warning(f"尝试 {attempt+1}: 使用ChatWith切换到聊天 {who} 也失败了")
                                if attempt == 2:  # 最后一次尝试
                                    logger.error(f"切换到聊天 {who} 失败，无法发送消息")
                                    return False
                                time.sleep(0.5 * (attempt + 1))  # 逐渐增加等待时间
                                continue
                        else:
                            logger.info(f"成功切换到聊天: {who}")
                            break
                    
                    # 等待切换完成
                    time.sleep(0.5)
            
            # 尝试激活微信主窗口
            try:
                # 查找微信主窗口
                wx_windows = win32gui.FindWindow("WeChatMainWndForPC", None)
                if wx_windows:
                    # 如果窗口最小化，则恢复
                    if win32gui.IsIconic(wx_windows):
                        win32gui.ShowWindow(wx_windows, win32con.SW_RESTORE)
                        time.sleep(0.3)
                    
                    # 将窗口设为前台
                    win32gui.SetForegroundWindow(wx_windows)
                    time.sleep(0.3)
                    logger.info("已激活微信主窗口")
                else:
                    logger.warning("找不到微信主窗口")
            except Exception as wx_err:
                logger.warning(f"激活微信主窗口失败: {str(wx_err)}")
            
            # 在发送前再次确保微信聊天窗口是活动的
            if who and hasattr(self, '_window_handles') and who in self._window_handles:
                try:
                    chat_handle = self._window_handles[who]
                    # 如果窗口最小化，则恢复
                    if win32gui.IsIconic(chat_handle):
                        win32gui.ShowWindow(chat_handle, win32con.SW_RESTORE)
                        time.sleep(0.2)
                    
                    # 将聊天窗口设为前台
                    win32gui.SetForegroundWindow(chat_handle)
                    time.sleep(0.2)
                    logger.info(f"已激活聊天窗口: {who}")
                except Exception as win_err:
                    logger.warning(f"激活聊天窗口失败: {str(win_err)}")
            
            # 发送消息前模拟点击聊天窗口，确保焦点在输入框
            try:
                # 模拟点击输入区域
                pyautogui.click(x=500, y=500)  # 尝试点击输入区域的一个大致位置
                time.sleep(0.1)
            except Exception as click_err:
                logger.warning(f"模拟点击失败: {str(click_err)}")
            
            # 记录发送前的最后一条消息，用于后续验证
            try:
                last_messages_before = self.wx.GetAllMessage()
                last_message_count = len(last_messages_before) if last_messages_before else 0
                logger.debug(f"发送前消息数量: {last_message_count}")
            except Exception as e:
                logger.warning(f"获取发送前消息失败，将无法验证发送结果: {str(e)}")
                last_message_count = None
            
            # 发送消息
            result = self.wx.SendMsg(msg)
            if result:
                logger.info(f"发送消息到 {who if who else '当前聊天'}: {msg[:30]}...")
            else:
                logger.warning(f"wxauto.SendMsg返回失败，消息可能未发送: {msg[:30]}...")
            
            # 等待一小段时间，让消息有机会发送
            time.sleep(0.3)
            
            # 验证消息是否已发送
            if last_message_count is not None:
                try:
                    # 检查消息数量是否增加
                    current_messages = self.wx.GetAllMessage()
                    current_count = len(current_messages) if current_messages else 0
                    
                    if current_count > last_message_count:
                        logger.info(f"消息发送成功验证: 消息数增加 {last_message_count} -> {current_count}")
                        return True
                    else:
                        # 这种情况可能是消息已发送但未刷新，或者真的失败了
                        # 我们宁可信其有，因为重试可能会导致多条相同消息
                        logger.info(f"消息可能已发送，但无法确认，假设成功")
                        return True
                except Exception as e:
                    logger.warning(f"验证消息发送结果失败: {str(e)}")
                    # 保守处理，假设成功
                    return True
            
            # 如果无法验证，假设成功
            return True
        except Exception as e:
            logger.error(f"发送消息失败 {msg[:20]}: {str(e)}", exc_info=True)
            return False
    
    def SendFiles(self, file_path: str, who: str = None) -> bool:
        """
        发送文件
        
        Args:
            file_path: 文件路径
            who: 接收者，如果为None则使用当前聊天
            
        Returns:
            bool: 是否成功
        """
        try:
            if not self.wx:
                logger.error("微信接口未初始化")
                return False
            
            # 检查文件路径是否有效
            if not file_path or not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return False
            
            if who:
                # 如果当前聊天已经是目标聊天，不需要切换
                if self._current_chat != who:
                    logger.info(f"尝试切换聊天到: {who}")
                    # 重试三次切换聊天
                    for attempt in range(3):
                        # 确保窗口处于活动状态
                        if not self._ensure_window_active(who):
                            logger.warning(f"尝试 {attempt+1}: 使用_ensure_window_active切换到聊天 {who} 失败")
                            # 使用基本的ChatWith方法再次尝试
                            if not self.wx.ChatWith(who):
                                logger.warning(f"尝试 {attempt+1}: 使用ChatWith切换到聊天 {who} 也失败了")
                                if attempt == 2:  # 最后一次尝试
                                    logger.error(f"切换到聊天 {who} 失败，无法发送文件")
                                    return False
                                time.sleep(0.5 * (attempt + 1))  # 逐渐增加等待时间
                                continue
                        else:
                            logger.info(f"成功切换到聊天: {who}")
                            break
                    
                    # 等待切换完成
                    time.sleep(0.5)
            
            # 尝试激活微信主窗口
            try:
                # 查找微信主窗口
                wx_windows = win32gui.FindWindow("WeChatMainWndForPC", None)
                if wx_windows:
                    # 如果窗口最小化，则恢复
                    if win32gui.IsIconic(wx_windows):
                        win32gui.ShowWindow(wx_windows, win32con.SW_RESTORE)
                        time.sleep(0.3)
                    
                    # 将窗口设为前台
                    win32gui.SetForegroundWindow(wx_windows)
                    time.sleep(0.3)
                    logger.info("已激活微信主窗口")
                else:
                    logger.warning("找不到微信主窗口")
            except Exception as wx_err:
                logger.warning(f"激活微信主窗口失败: {str(wx_err)}")
            
            # 在发送前再次确保微信聊天窗口是活动的
            if who and hasattr(self, '_window_handles') and who in self._window_handles:
                try:
                    chat_handle = self._window_handles[who]
                    # 如果窗口最小化，则恢复
                    if win32gui.IsIconic(chat_handle):
                        win32gui.ShowWindow(chat_handle, win32con.SW_RESTORE)
                        time.sleep(0.2)
                    
                    # 将聊天窗口设为前台
                    win32gui.SetForegroundWindow(chat_handle)
                    time.sleep(0.2)
                    logger.info(f"已激活聊天窗口: {who}")
                except Exception as win_err:
                    logger.warning(f"激活聊天窗口失败: {str(win_err)}")
            
            # 发送消息前模拟点击聊天窗口，确保焦点在输入框
            try:
                # 模拟点击输入区域
                pyautogui.click(x=500, y=500)  # 尝试点击输入区域的一个大致位置
                time.sleep(0.1)
            except Exception as click_err:
                logger.warning(f"模拟点击失败: {str(click_err)}")
            
            # 发送文件
            result = self.wx.SendFiles(file_path)
            if result:
                logger.info(f"发送文件到 {who if who else '当前聊天'}: {file_path}")
            else:
                logger.warning(f"wxauto.SendFiles返回失败，文件可能未发送: {file_path}")
            
            # 发送后等待一小段时间，确保文件被处理
            time.sleep(0.8)  # 文件发送可能需要更长的处理时间
            return result
        except Exception as e:
            logger.error(f"发送文件失败 {file_path}: {str(e)}", exc_info=True)
            return False
    
    def AddListenChat(self, who: str, savepic: bool = False, savefile: bool = False) -> bool:
        """
        添加监听的聊天
        
        Args:
            who: 聊天对象名称
            savepic: 是否保存图片
            savefile: 是否保存文件
            
        Returns:
            bool: 是否成功
        """
        try:
            if not self.wx:
                logger.error("微信接口未初始化")
                return False
            
            # 如果已经在监听，直接返回成功
            if who in self._listen_chats:
                logger.info(f"聊天 {who} 已在监听列表中")
                return True
            
            # 获取并激活聊天窗口
            if not self._ensure_window_active(who):
                logger.error(f"无法切换到聊天 {who}，监听添加失败")
                return False
            
            # 获取当前聊天内容作为基准
            try:
                current_content = self.wx.GetAllMessage()
                if who not in self._last_messages:
                    self._last_messages[who] = current_content
            except Exception as e:
                logger.warning(f"获取初始消息失败，将在下次检查时更新: {str(e)}")
            
            # 添加到监听列表
            self._listen_chats.add(who)
            logger.info(f"成功添加聊天监听: {who}")
            return True
            
        except Exception as e:
            logger.error(f"添加监听失败 {who}: {str(e)}")
            return False
    
    def RemoveListenChat(self, who: str) -> bool:
        """
        移除聊天监听
        
        Args:
            who: 聊天对象名称
            
        Returns:
            bool: 是否成功
        """
        try:
            if who in self._listen_chats:
                self._listen_chats.remove(who)
            if who in self._listen_windows:
                del self._listen_windows[who]
            if who in self._window_handles:
                del self._window_handles[who]
            if self._current_chat == who:
                self._current_chat = None
            logger.info(f"移除聊天监听: {who}")
            return True
        except Exception as e:
            logger.error(f"移除监听失败 {who}: {str(e)}")
            return False
    
    def IsListening(self, who: str) -> bool:
        """
        检查是否已添加监听
        
        Args:
            who: 聊天对象名称
            
        Returns:
            bool: 是否已添加监听
        """
        return who in self._listen_chats
    
    def GetSessionList(self) -> List[str]:
        """
        获取会话列表
        
        Returns:
            List[str]: 会话列表
        """
        try:
            if not self.wx:
                logger.error("微信接口未初始化")
                return []
            
            # 调用wxauto获取会话列表
            sessions = self.wx.GetSessionList()
            return sessions
        except Exception as e:
            logger.error(f"获取会话列表失败: {str(e)}")
            return []
    
    def GetListenMessageQuiet(self) -> Dict:
        """
        静默获取监听消息，出错时不打印错误信息或使用更低级别日志
        
        Returns:
            Dict: 消息字典
        """
        try:
            # 使用GetAllMessage方法（已确认可用）
            if hasattr(self.wx, "GetAllMessage"):
                msgs = self.wx.GetAllMessage()
                if msgs:
                    logger.debug(f"静默模式(GetAllMessage)获取到 {len(msgs)} 条消息")
                    return msgs
            
            # 不再尝试使用GetMsgs和GetLastMessage，因为它们不可用
            return {}
        except Exception as e:
            logger.debug(f"静默获取消息失败: {str(e)}")
            return {}

    def GetListenMessage(self) -> Dict:
        """
        获取监听消息
        
        Returns:
            Dict: 消息字典
        """
        try:
            if not self.wx:
                logger.error("微信接口未初始化")
                return {}
            
            # 只使用GetAllMessage方法（已确认可用）
            if hasattr(self.wx, "GetAllMessage"):
                msgs = self.wx.GetAllMessage()
                if msgs:
                    logger.debug(f"获取到 {len(msgs)} 条消息")
                    return msgs
            
            # 如果GetAllMessage失败，返回空字典
            logger.debug("GetAllMessage方法未返回消息")
            return {}
        except Exception as e:
            logger.error(f"获取消息失败: {str(e)}")
            return {}
    
    def _compare_messages(self, msg1, msg2) -> bool:
        """
        比较两条消息是否相同
        
        Args:
            msg1: 第一条消息
            msg2: 第二条消息
            
        Returns:
            bool: 是否相同
        """
        try:
            # 如果两个对象是同一个，直接返回True
            if msg1 is msg2:
                return True
                
            # 如果是简单的字符串或者基本类型，直接比较
            if isinstance(msg1, (str, int, float, bool)) and isinstance(msg2, (str, int, float, bool)):
                return msg1 == msg2
                
            # 如果是简单的字典或列表，转为JSON字符串比较
            if isinstance(msg1, (dict, list)) and isinstance(msg2, (dict, list)):
                import json
                try:
                    return json.dumps(msg1, sort_keys=True) == json.dumps(msg2, sort_keys=True)
                except:
                    pass
            
            # 如果是对象，尝试比较关键属性
            if hasattr(msg1, 'content') and hasattr(msg2, 'content'):
                if msg1.content != msg2.content:
                    return False
            
            if hasattr(msg1, 'sender') and hasattr(msg2, 'sender'):
                if msg1.sender != msg2.sender:
                    return False
                    
            if hasattr(msg1, 'time') and hasattr(msg2, 'time'):
                if msg1.time != msg2.time:
                    return False
            
            # 尝试使用__eq__方法
            try:
                return msg1 == msg2
            except:
                # 如果上述比较都无法完成，返回False
                return False
                
        except Exception as e:
            logger.error(f"比较消息时出错: {str(e)}")
            return False
    
    def GetInfo(self) -> Dict[str, Any]:
        """
        获取微信信息
        
        Returns:
            Dict[str, Any]: 微信信息
        """
        try:
            if not self.wx:
                return {"name": self.A_MyIcon.Name, "status": "offline"}
            
            return {
                "name": self.A_MyIcon.Name,
                "status": "online",
                "current_chat": self._current_chat,
                "listening_chats": list(self._listen_chats)
            }
        except Exception as e:
            logger.error(f"获取微信信息失败: {str(e)}")
            return {"name": "未知", "status": "error"}

    def initialize_listening(self, listen_list: list) -> bool:
        """
        初始化微信监听，包含重试机制
        
        Args:
            listen_list: 需要监听的聊天列表
            
        Returns:
            bool: 是否成功初始化
        """
        try:
            # 检查微信是否初始化成功
            if not self.wx:
                logger.error("微信接口未初始化")
                return False
                
            # 尝试获取会话列表
            try:
                session_list = self.wx.GetSessionList()
                if not session_list:
                    logger.error("未检测到微信会话列表，请确保微信已登录")
                    return False
                logger.info(f"获取到 {len(session_list)} 个会话")
            except Exception as e:
                logger.error(f"获取会话列表失败: {str(e)}")
                return False
            
            # 备份当前监听状态以便恢复
            old_listen_chats = self._listen_chats.copy()
            
            # 初始化过程要始终重置监听状态
            self._listen_windows.clear()
            self._window_handles.clear()
            self._listen_chats.clear()
            self._last_messages.clear()
            self._current_chat = None
            
            # 记录有效添加计数
            added_count = 0
            skip_count = 0
            error_count = 0
            
            # 循环添加监听对象
            for chat_name in listen_list:
                try:
                    # 检查聊天名称是否在会话列表中
                    chat_exists = False
                    for session in session_list:
                        if isinstance(session, str):
                            if session == chat_name:
                                chat_exists = True
                                break
                        elif hasattr(session, 'name'):
                            if session.name == chat_name:
                                chat_exists = True
                                break
                    
                    if not chat_exists:
                        logger.warning(f"会话列表中找不到聊天: {chat_name}，尝试直接切换")
                        
                    # 尝试切换到该聊天
                    if not self.ChatWith(chat_name):
                        logger.error(f"找不到会话 {chat_name}，跳过监听设置")
                        error_count += 1
                        continue
                    
                    # 短暂暂停确保切换成功
                    time.sleep(0.5)  
                    
                    # 添加监听
                    result = self.AddListenChat(chat_name, savepic=True, savefile=True)
                    if result:
                        added_count += 1
                        logger.info(f"成功添加监听 [{added_count}]: {chat_name}")
                    else:
                        error_count += 1
                        logger.error(f"添加监听失败: {chat_name}")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"处理聊天 {chat_name} 时出错: {str(e)}")
                    continue
            
            # 显示初始化结果统计
            logger.info(f"监听初始化结果: 成功={added_count}, 跳过={skip_count}, 失败={error_count}")
            
            # 只有在成功添加至少一个监听时才算成功
            if added_count > 0:
                # 更新相关时间戳
                self._last_reconnect_time = time.time()
                return True
            else:
                # 恢复原有监听
                self._listen_chats = old_listen_chats
                logger.warning("未能添加任何监听，恢复原有监听状态")
                return False
            
        except Exception as e:
            logger.error(f"初始化微信监听失败: {str(e)}")
            return False

    def check_and_reconnect(self) -> bool:
        """
        检查微信连接状态并在必要时重连
        
        Returns:
            bool: 是否成功连接
        """
        try:
            current_time = time.time()
            
            # 检查是否需要重置重连计数
            if current_time - self._last_reconnect_time > 300:  # 5分钟无错误
                if self._reconnect_attempts > 0:
                    logger.info(f"重置重连尝试计数，之前值为: {self._reconnect_attempts}")
                self._reconnect_attempts = 0
            
            # 检查重连次数
            if self._reconnect_attempts >= self._max_reconnect_attempts:
                logger.error(f"达到最大重连次数({self._max_reconnect_attempts})，等待{self._reconnect_delay}秒后重试...")
                time.sleep(self._reconnect_delay)
                self._reconnect_attempts = 0
                self._last_reconnect_time = current_time
                return False
            
            # 记录重连尝试
            self._reconnect_attempts += 1
            logger.info(f"尝试第 {self._reconnect_attempts}/{self._max_reconnect_attempts} 次重连")
            
            # 尝试重新初始化
            try:
                old_wx = self.wx  # 保存旧的wx对象以便比较
                self.wx = wxauto.WeChat()
                session_list = self.wx.GetSessionList()
                
                if not session_list:
                    logger.error("重连后无法获取会话列表")
                    self._last_reconnect_time = current_time
                    return False
                    
                # 检查是否与之前的微信实例相同
                if old_wx and hasattr(old_wx, 'GetSelfName') and hasattr(self.wx, 'GetSelfName'):
                    old_name = old_wx.GetSelfName()
                    new_name = self.wx.GetSelfName()
                    if old_name == new_name:
                        logger.info(f"重连成功，微信用户相同: {new_name}")
                    else:
                        logger.warning(f"微信用户可能已更改: 从 {old_name} 到 {new_name}")
                
            except Exception as e:
                logger.error(f"创建WeChat实例失败: {str(e)}")
                self._last_reconnect_time = current_time
                return False
            
            # 只重新添加未响应的监听
            listen_problem_chats = []
            for chat in self._listen_chats.copy():
                # 检查聊天是否在会话列表中
                if chat not in session_list:
                    logger.warning(f"无法找到会话 {chat}，可能已被删除")
                    continue
                    
                # 所有聊天都添加到需要重新监听的列表中
                listen_problem_chats.append(chat)
            
            # 如果有问题聊天，重新添加它们的监听
            if listen_problem_chats:
                logger.info(f"重新添加 {len(listen_problem_chats)} 个聊天的监听")
                
                for chat in listen_problem_chats:
                    try:
                        logger.info(f"尝试重新添加监听: {chat}")
                        # 保存当前聊天以便后续恢复
                        current_chat = self._current_chat
                        
                        if self.ChatWith(chat):
                            if chat in self._last_messages:
                                del self._last_messages[chat]  # 清除旧消息缓存
                                
                            self.AddListenChat(chat, savepic=True, savefile=True)
                            logger.info(f"成功重新添加 {chat} 的监听")
                            
                            # 恢复之前的聊天（如果有）
                            if current_chat and current_chat != chat:
                                self.ChatWith(current_chat)
                        else:
                            logger.error(f"无法切换到聊天 {chat}")
                    except Exception as e:
                        logger.error(f"重新添加监听失败 {chat}: {str(e)}")
            else:
                logger.info("所有聊天监听状态正常，无需重新添加")
            
            # 重置重连计数和时间
            self._reconnect_attempts = 0
            self._last_reconnect_time = current_time
            logger.info("微信监听恢复正常")
            return True
            
        except Exception as e:
            logger.error(f"重连过程中发生错误: {str(e)}")
            self._last_reconnect_time = time.time()
            return False

    def needs_reconnect(self) -> bool:
        """
        检查是否需要重新连接
        
        Returns:
            bool: 是否需要重连
        """
        current_time = time.time()
        
        # 避免频繁检查，只有在60秒后才检查
        if current_time - self._last_reconnect_time < 60:  # 至少间隔1分钟
            return False
            
        # 只有在以下情况才需要重连：
        # 1. wx对象为None
        # 2. 无法获取会话列表
        try:
            if not self.wx:
                return True
                
            # 尝试获取会话列表，如果失败则需要重连
            session_list = self.wx.GetSessionList()
            if not session_list:
                logger.warning("无法获取会话列表，可能需要重连")
                return True
                
            # 正常情况下不需要重连
            return False
        except Exception as e:
            logger.error(f"检查连接状态时出错: {str(e)}")
            return True

    def InitAllListenings(self, chat_list):
        """
        一次性初始化所有需要监听的聊天
        
        Args:
            chat_list (list): 需要监听的聊天列表
            
        Returns:
            bool: 是否所有聊天都成功添加了监听
        """
        try:
            # 清除所有现有监听，确保只监听指定的列表
            current_listening = list(self._listen_chats)
            for old_chat in current_listening:
                if old_chat not in chat_list:
                    self.RemoveListenChat(old_chat)
                    logger.info(f"移除了不在监听列表中的聊天: {old_chat}")
            
            # 构建监听列表集合，用于快速查找
            chat_set = set(chat_list)
            
            success_count = 0
            for chat_name in chat_list:
                try:
                    # 检查会话是否存在
                    if not self.ChatWith(chat_name):
                        logger.error(f"找不到会话 {chat_name}")
                        continue
                    
                    # 添加到监听列表 - 确保这是一个有效的监听对象
                    if chat_name not in self._listen_chats:
                        # 尝试添加监听
                        self.AddListenChat(who=chat_name, savepic=True, savefile=True)
                        logger.info(f"成功添加监听: {chat_name}")
                        success_count += 1
                        time.sleep(0.5)  # 添加短暂延迟，避免操作过快
                    else:
                        logger.info(f"聊天 {chat_name} 已在监听列表中")
                        success_count += 1
                    
                except Exception as e:
                    logger.error(f"添加监听失败 {chat_name}: {str(e)}")
                    continue
            
            # 添加GetWeChatWindow方法，避免为不在监听列表中的用户创建新窗口
            if not hasattr(self, 'GetWeChatWindow'):
                def GetWeChatWindow(who: str) -> bool:
                    """
                    检查指定聊天是否应该被监听，防止监听不在列表中的用户
                    
                    Args:
                        who: 聊天对象名称
                        
                    Returns:
                        bool: 是否应该被监听
                    """
                    # 只有在监听列表中的聊天才会返回True
                    if who in chat_set or who in self._listen_chats:
                        # 存在于监听列表，尝试正常获取窗口
                        try:
                            return self._get_chat_window(who) is not None
                        except:
                            return False
                    else:
                        # 不在监听列表中，不获取窗口
                        logger.info(f"忽略不在监听列表中的聊天: {who}")
                        return False
                
                # 将方法添加到实例
                self.GetWeChatWindow = GetWeChatWindow
                logger.info("已添加防止监听非列表用户的保护方法")
            
            # 检查监听列表是否为空
            if not self._listen_chats:
                logger.warning("初始化后监听列表为空，可能存在问题")
                return False
                
            # 记录监听列表完整内容
            logger.info(f"当前监听的聊天列表: {list(self._listen_chats)}")
            
            # 如果所有聊天都成功添加了监听，返回True
            return success_count == len(chat_list)
            
        except Exception as e:
            logger.error(f"初始化所有监听失败: {str(e)}")
            return False 
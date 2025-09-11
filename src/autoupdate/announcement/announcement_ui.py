"""
公告显示组件

提供简单的公告显示功能，可以集成到任何Python应用中。
支持HTML格式的富文本公告。
"""

import logging
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional, Callable
import webbrowser
import threading
import time

from .announcement_manager import get_current_announcement, mark_announcement_as_read

logger = logging.getLogger("autoupdate.announcement")

class AnnouncementWindow:
    """公告显示窗口"""
    
    def __init__(self, parent=None, on_close=None):
        """
        初始化公告窗口
        
        Args:
            parent: 父窗口
            on_close: 关闭回调函数
        """
        self.parent = parent
        self.on_close = on_close
        self.window = None
        self.announcement = None
    
    def show_announcement(self, announcement: Dict[str, Any] = None) -> bool:
        """
        显示公告
        
        Args:
            announcement: 公告信息，如果为None则获取当前公告
            
        Returns:
            bool: 是否成功显示
        """
        try:
            # 获取公告
            if announcement is None:
                announcement = get_current_announcement()
            
            if not announcement:
                logger.debug("No announcement to show")
                return False
            
            # 检查公告是否启用
            if not announcement.get("enabled", False):
                logger.debug("Announcement is disabled")
                return False
            
            self.announcement = announcement
            
            # 创建窗口
            if self.parent:
                self.window = tk.Toplevel(self.parent)
            else:
                self.window = tk.Tk()
            
            # 设置窗口属性
            self.window.title(announcement.get("title", "系统公告"))
            self.window.geometry("600x400")
            self.window.minsize(400, 300)
            
            # 设置窗口图标（如果有）
            try:
                self.window.iconbitmap("icon.ico")
            except:
                pass
            
            # 创建UI元素
            self._create_ui(announcement)
            
            # 设置关闭事件
            self.window.protocol("WM_DELETE_WINDOW", self._on_window_close)
            
            # 如果设置了自动关闭，启动定时器
            if announcement.get("auto_close", False):
                auto_close_time = announcement.get("auto_close_time", 30)  # 默认30秒
                threading.Thread(target=self._auto_close_timer, args=(auto_close_time,), daemon=True).start()
            
            # 标记公告为已读
            mark_announcement_as_read()
            
            # 显示窗口
            self.window.focus_force()
            if not self.parent:
                self.window.mainloop()
            
            return True
            
        except Exception as e:
            logger.error(f"Error showing announcement: {str(e)}")
            return False
    
    def _create_ui(self, announcement: Dict[str, Any]):
        """创建UI元素"""
        # 创建主框架
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标题
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(
            title_frame, 
            text=announcement.get("title", "系统公告"),
            font=("Arial", 16, "bold")
        )
        title_label.pack(side=tk.LEFT)
        
        # 根据优先级设置标题颜色
        priority = announcement.get("priority", "normal")
        if priority == "high":
            title_label.configure(foreground="red")
        elif priority == "low":
            title_label.configure(foreground="gray")
        
        # 创建内容区域
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建文本区域
        text_area = tk.Text(
            content_frame,
            wrap=tk.WORD,
            padx=5,
            pady=5,
            font=("Arial", 11)
        )
        text_area.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(content_frame, command=text_area.yview)
        scrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        text_area.config(yscrollcommand=scrollbar.set)
        
        # 插入公告内容
        content = announcement.get("content", "")
        text_area.insert(tk.END, content)
        
        # 禁用编辑
        text_area.config(state=tk.DISABLED)
        
        # 如果需要显示版本信息
        if announcement.get("show_version_info", False) and "version_info" in announcement:
            version_info = announcement["version_info"]
            version_frame = ttk.Frame(main_frame)
            version_frame.pack(fill=tk.X, pady=(10, 0))
            
            version_label = ttk.Label(
                version_frame,
                text=f"版本: {version_info.get('version', '未知')}",
                font=("Arial", 10)
            )
            version_label.pack(side=tk.LEFT)
        
        # 创建按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 如果有下载链接，添加下载按钮
        if "download_url" in announcement:
            download_button = ttk.Button(
                button_frame,
                text="下载更新",
                command=lambda: webbrowser.open(announcement["download_url"])
            )
            download_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # 如果有详情链接，添加详情按钮
        if "details_url" in announcement:
            details_button = ttk.Button(
                button_frame,
                text="查看详情",
                command=lambda: webbrowser.open(announcement["details_url"])
            )
            details_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # 关闭按钮
        close_button = ttk.Button(
            button_frame,
            text="关闭",
            command=self._on_window_close
        )
        close_button.pack(side=tk.RIGHT)
    
    def _on_window_close(self):
        """窗口关闭事件"""
        if self.on_close:
            self.on_close()
        
        if self.window:
            self.window.destroy()
            self.window = None
    
    def _auto_close_timer(self, seconds: int):
        """自动关闭定时器"""
        time.sleep(seconds)
        if self.window:
            self.window.after(0, self._on_window_close)

def show_announcement_dialog(parent=None, on_close=None, announcement=None) -> bool:
    """
    显示公告对话框
    
    Args:
        parent: 父窗口
        on_close: 关闭回调函数
        announcement: 公告信息，如果为None则获取当前公告
        
    Returns:
        bool: 是否成功显示
    """
    window = AnnouncementWindow(parent, on_close)
    return window.show_announcement(announcement)

def show_if_has_announcement(parent=None, on_close=None) -> bool:
    """
    如果有公告则显示
    
    Args:
        parent: 父窗口
        on_close: 关闭回调函数
        
    Returns:
        bool: 是否成功显示
    """
    announcement = get_current_announcement()
    if announcement and announcement.get("enabled", False):
        return show_announcement_dialog(parent, on_close, announcement)
    return False
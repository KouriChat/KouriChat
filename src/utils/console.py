"""
控制台输出相关的工具函数
包含:
- 状态信息打印
- 横幅打印
等功能
"""

from colorama import Fore, Style
import sys

def print_status(message: str, status: str = "info", icon: str = ""):
    """
    打印带颜色和表情的状态消息
    
    Args:
        message (str): 要打印的消息
        status (str): 状态类型 ("success", "info", "warning", "error")
        icon (str): 消息前的图标
    """
    try:
        colors = {
            "success": Fore.GREEN,
            "info": Fore.BLUE,
            "warning": Fore.YELLOW,
            "error": Fore.RED
        }
        color = colors.get(status, Fore.WHITE)

        # ASCII文本到emoji的映射
        icon_map = {
            "LAUNCH": "🚀",
            "FILE": "📁",
            "CONFIG": "⚙️",
            "CHECK": "✅",
            "CROSS": "❌",
            "CLEAN": "🧹",
            "TRASH": "🗑️",
            "STAR_1": "✨",
            "STAR_2": "🌟",
            "BOT": "🤖",
            "STOP": "🛑",
            "BYE": "👋",
            "ERROR": "💥",
            "SEARCH": "🔍",
            "BRAIN": "🧠",
            "ANTENNA": "📡",
            "CHAIN": "🔗",
            "INTERNET": "🌐",
            "CLOCK": "⏰",
            "SYNC": "🔄",
            "WARNING": "⚠️",
            "+": "📁",
            "*": "⚙️",
            "X": "❌",
            ">>": "🚀",
        }

        safe_icon = icon_map.get(icon, icon)  # 如果找不到映射，保留原始输入
        print(f"{color}{safe_icon} {message}{Style.RESET_ALL}")
    except Exception:
        # 如果出现编码错误，不使用颜色和图标
        print(f"{message}")

def print_banner():
    """
    打印程序启动横幅
    """
    try:
        banner = f"""
{Fore.CYAN}
╔══════════════════════════════════════════════╗
║              KouriChat - AI Chat             ║
║          Created by KouriChat Team           ║
║           Created with ❤️  by umaru          ║
║     https://github.com/KouriChat/KouriChat   ║
╚══════════════════════════════════════════════╝

KouriChat - AI Chat  Copyright (C) 2025,github.com/umaru-233
This program comes with ABSOLUTELY NO WARRANTY; for details please read
https://www.gnu.org/licenses/gpl-3.0.en.html.
该程序是基于GPLv3许可证分发的，因此该程序不提供任何保证；有关更多信息，请参阅GPLv3许可证。
This is free software, and you are welcome to redistribute it
under certain conditions; please read
https://www.gnu.org/licenses/gpl-3.0.en.html.
这是免费软件，欢迎您二次分发它，在某些情况下，请参阅GPLv3许可证。
It's freeware, and if you bought it for money, you've been scammed!
这是免费软件，如果你是花钱购买的，说明你被骗了！
{Style.RESET_ALL}"""
        print(banner)
    except Exception:
        # 如果出现编码错误，使用简单版本
        print("\nKouriChat - AI Chat\n") 

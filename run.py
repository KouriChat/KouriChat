"""
主程序入口文件
负责启动聊天机器人程序，包括:
- 初始化Python路径
- 禁用字节码缓存
- 清理缓存文件
- 启动主程序
"""

import os
import sys
import time
from colorama import init, Fore, Style
import codecs
import locale

# 设置系统默认编码为 UTF-8
if sys.platform.startswith('win'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

# 初始化colorama
init()

def print_banner():
    """打印启动横幅"""
    try:
        banner = f"""
{Fore.CYAN}
╔══════════════════════════════════════════════╗
║          My Dream Moments - AI Chat          ║
║            Created by umaru-233              ║
╚══════════════════════════════════════════════╝
{Style.RESET_ALL}"""
        print(banner)
    except Exception as e:
        # 如果出现编码错误，使用简单版本
        print("\nMy Dream Moments - AI Chat\n")

# 禁止生成__pycache__文件夹
sys.dont_write_bytecode = True

# 将src目录添加到Python路径
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.append(src_path)

def print_status(message: str, status: str = "info", icon: str = ""):
    """打印带颜色和表情的状态消息"""
    try:
        colors = {
            "success": Fore.GREEN,
            "info": Fore.BLUE,
            "warning": Fore.YELLOW,
            "error": Fore.RED
        }
        color = colors.get(status, Fore.WHITE)
        
        # 使用简单的 ASCII 字符替代 emoji
        icon_map = {
            "🚀": ">>",
            "📁": "+",
            "⚙️": "*",
            "✅": "√",
            "❌": "×",
            "🧹": "-",
            "🗑️": "#",
            "✨": "*",
            "🌟": "*",
            "🤖": "[BOT]",
            "🛑": "[STOP]",
            "👋": "bye",
            "💥": "[ERROR]"
        }
        
        safe_icon = icon_map.get(icon, "")
        print(f"{color}{safe_icon} {message}{Style.RESET_ALL}")
    except Exception as e:
        # 如果出现编码错误，不使用颜色和图标
        print(f"{message}")

def initialize_system():
    """初始化系统"""
    try:
        from src.utils.cleanup import cleanup_pycache
        from src.main import main
        
        print_banner()
        print_status("系统初始化中...", "info", ">>")
        print("-" * 50)
        
        # 检查Python路径
        print_status("检查系统路径...", "info", "+")
        if src_path not in sys.path:
            print_status("添加src目录到Python路径", "info", "+")
        print_status("系统路径检查完成", "success", "√")
        
        # 检查缓存设置
        print_status("检查缓存设置...", "info", "*")
        if sys.dont_write_bytecode:
            print_status("已禁用字节码缓存", "success", "√")
        
        # 清理缓存文件
        print_status("清理系统缓存...", "info", "-")
        cleanup_pycache()
        print_status("缓存清理完成", "success", "√")
        
        # 检查必要目录
        print_status("检查必要目录...", "info", "#")
        required_dirs = ['data', 'logs', 'src/config']
        for dir_name in required_dirs:
            dir_path = os.path.join(os.path.dirname(src_path), dir_name)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                print_status(f"创建目录: {dir_name}", "info", "+")
        print_status("目录检查完成", "success", "√")
        
        print("-" * 50)
        print_status("系统初始化完成", "success", "*")
        time.sleep(1)  # 稍微停顿以便用户看清状态
        
        # 启动主程序
        print_status("启动主程序...", "info", "*")
        print("=" * 50)
        main()
        
    except ImportError as e:
        print_status(f"导入模块失败: {str(e)}", "error", "×")
        sys.exit(1)
    except Exception as e:
        print_status(f"初始化失败: {str(e)}", "error", "💥")
        sys.exit(1)

if __name__ == '__main__':
    try:
        print_status("启动聊天机器人...", "info", "[BOT]")
        initialize_system()
    except KeyboardInterrupt:
        print("\n")
        print_status("正在关闭系统...", "warning", "[STOP]")
        print_status("感谢使用，再见！", "info", "bye")
        print("\n")
    except Exception as e:
        print_status(f"系统错误: {str(e)}", "error", "[ERROR]")
        sys.exit(1) 
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
from colorama import init
import codecs
from src.utils.console import print_status, print_banner

# 设置系统默认编码为 UTF-8
if sys.platform.startswith('win'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

# 初始化colorama
init()

# 禁止生成__pycache__文件夹
sys.dont_write_bytecode = True

# 将src目录添加到Python路径
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.append(src_path)

def initialize_system():
    """初始化系统"""
    try:
        from src.utils.cleanup import cleanup_pycache
        from src.main import main

        print_banner()
        print_status("系统初始化中...", "info", "LAUNCH")
        print("-" * 50)

        # 检查Python路径
        print_status("检查系统路径...", "info", "FILE")
        if src_path not in sys.path:
            print_status("添加src目录到Python路径", "info", "FILE")
        print_status("系统路径检查完成", "success", "CHECK")

        # 检查缓存设置
        print_status("检查缓存设置...", "info", "CONFIG")
        if sys.dont_write_bytecode:
            print_status("已禁用字节码缓存", "success", "CHECK")

        # 清理缓存文件
        print_status("清理系统缓存...", "info", "CLEAN")
        try:
            cleanup_pycache()
            
            from src.utils.logger import LoggerConfig
            from src.utils.cleanup import CleanupUtils
            from src.handlers.image import ImageHandler
            from src.handlers.voice import VoiceHandler
            from src.config import config
            
            root_dir = os.path.dirname(src_path)
            logger_config = LoggerConfig(root_dir)
            cleanup_utils = CleanupUtils(root_dir)
            image_handler = ImageHandler(
                root_dir=root_dir,
                api_key=config.llm.api_key,
                base_url=config.llm.base_url,
                image_model=config.media.image_generation.model
            )
            voice_handler = VoiceHandler(
                root_dir=root_dir,
                tts_api_url=config.media.text_to_speech.tts_api_url
            )

            logger_config.cleanup_old_logs()
            cleanup_utils.cleanup_all()
            image_handler.cleanup_temp_dir()
            voice_handler.cleanup_voice_dir()
        except Exception as e:
            print_status(f"清理缓存失败: {str(e)}", "warning", "CROSS")
        print_status("缓存清理完成", "success", "CHECK")

        # 检查必要目录
        print_status("检查必要目录...", "info", "FILE")
        required_dirs = ['data', 'logs', 'src/config']
        for dir_name in required_dirs:
            dir_path = os.path.join(os.path.dirname(src_path), dir_name)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                print_status(f"创建目录: {dir_name}", "info", "FILE")
        print_status("目录检查完成", "success", "CHECK")

        print("-" * 50)
        print_status("系统初始化完成", "success", "STAR_1")
        time.sleep(1)  # 稍微停顿以便用户看清状态

        # 启动主程序
        print_status("启动主程序...", "info", "LAUNCH")
        print("=" * 50)
        main()

    except ImportError as e:
        print_status(f"导入模块失败: {str(e)}", "error", "CROSS")
        sys.exit(1)
    except Exception as e:
        print_status(f"初始化失败: {str(e)}", "error", "ERROR")
        sys.exit(1)

if __name__ == '__main__':
    try:
        print_status("启动聊天机器人...", "info", "BOT")
        initialize_system()
    except KeyboardInterrupt:
        print("\n")
        print_status("正在关闭系统...", "warning", "STOP")
        print_status("感谢使用，再见！", "info", "BYE")
        print("\n")
    except Exception as e:
        print_status(f"系统错误: {str(e)}", "error", "ERROR")
        sys.exit(1) 

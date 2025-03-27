import asyncio
import sys
import os
import logging
from time import sleep

from _pytest import config
from network import NetworkManager
from config import SettingReader
from globals.global_variable import GlobalVariable
from core import EventBus


# 添加项目根目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
configs = SettingReader().get_config()
modols = SettingReader().get_model()
logger = logging.getLogger(__name__)

async def main():
    
    # 获取网络管理器实例
    network_manager = NetworkManager()
    # 初始化全局变量
    GlobalVariable.eventBus = EventBus() #初始化事件总线


    # print(modols)
    # print(configs)
    
    try:
        # 启动所有服务器
        await network_manager.start_servers()
    except Exception as e:
        print(f"程序异常终止: {str(e)}")
        await network_manager.shutdown()
    finally:
        if hasattr(network_manager, '_flask_task') and not network_manager._flask_task.done():
            await network_manager.shutdown()
            

if __name__ == '__main__':    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序正在退出...")
    except Exception as e:
        print(f"\n程序异常退出: {str(e)}")
    finally:
        print("程序已退出")
        os._exit(0)
        
    
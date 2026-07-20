"""
KouriChat OneBot 协议适配器
支持 OneBot v11 和 v12 协议，通过正向 WebSocket 与外部 Bot 框架交互。
"""

from .server import OneBotServer
from .adapter import OneBotAdapter

__all__ = ['OneBotServer', 'OneBotAdapter']
__version__ = '1.0.0'

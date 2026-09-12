"""KouriChat 1.5：all-in-plugin 聊天机器人框架（cordis-python 内核 + elixir LLM）。"""

from .config import Config
from .core import assemble, load_plugin, shutdown
from .types import Channel, Message, OutMessage, Segment, User

__version__ = "1.5.0.2"

__all__ = [
    "Config", "assemble", "load_plugin", "shutdown",
    "Channel", "User", "Segment", "Message", "OutMessage",
    "__version__",
]

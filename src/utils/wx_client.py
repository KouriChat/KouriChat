"""
微信客户端封装，自动处理 wxautox（增强版）与 wxauto4（免费版）的兼容。
提供底层调用拦截与消息轮询增量缓冲，保证上层应用业务逻辑不变。
"""

import os
import sys
import json
import time
import logging
import subprocess
from dataclasses import dataclass
from collections import deque
from typing import Dict, List, Any, Optional

logger = logging.getLogger('wx_client')


@dataclass
class ChatMock:
    """模拟旧版 wxauto 聊天对象 (用于字典 Key)"""
    who: str

    def __hash__(self) -> int:
        return hash(self.who)

    def __eq__(self, other: Any) -> bool:
        return hasattr(other, 'who') and self.who == other.who


@dataclass
class MsgMock:
    """模拟旧版 wxauto 消息对象"""
    id: str
    type: str
    content: str
    sender: str


class _MyIconMock:
    """模拟微信头像及信息以防止上层报错"""
    Name: str = "KouriChat Bot"


def is_wxautox_activated() -> bool:
    """检查 wxautox 是否已经通过授权"""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'wxautox', '--debug-license'],
            capture_output=True,
            timeout=5
        )
        
        try:
            output = result.stdout.decode('utf-8') + result.stderr.decode('utf-8')
        except UnicodeDecodeError:
            output = result.stdout.decode('gbk', errors='ignore') + result.stderr.decode('gbk', errors='ignore')
        
        if '未授权' in output or 'Missing' in output or 'unauthorized' in output.lower() or 'WXAUTOX_DEBUG_LICENSE' in output:
            return False
            
        return result.returncode == 0
    except Exception as e:
        logger.error(f"检查 wxautox 授权状态失败: {e}")
        return False


def get_wxauto_type() -> bool:
    """读取用户配置，决定是否使用 wxautox"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'config', 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                
            # 优雅地读取嵌套字典配置
            categories = cfg.get('categories', {})
            user_settings = categories.get('user_settings', {})
            settings = user_settings.get('settings', {})
            
            if 'wxauto_type' in settings:
                wxauto_type = settings['wxauto_type'].get('value', '')
                return 'wxautox' in wxauto_type.lower()
    except Exception as e:
        logger.warning(f"读取 wxauto_type 配置失败，将自动推断: {e}")
        
    return is_wxautox_activated()


# 初始化底层类
use_wxautox = get_wxauto_type()
if use_wxautox:
    logger.info("配置为 wxautox (增强版)，尝试加载...")
    try:
        from wxautox import WeChat as OriginalWeChat
    except ImportError:
        logger.error("加载 wxautox 失败，强制回退免费版 wxauto4...")
        from wxauto4 import WeChat as OriginalWeChat
else:
    logger.info("配置为 wxauto4 (免费版)，尝试加载...")
    try:
        from wxauto4 import WeChat as OriginalWeChat
    except ImportError:
        logger.error("免费版 wxauto4 未安装。尝试加载 wxautox...")
        from wxautox import WeChat as OriginalWeChat


class WeChatAdapter:
    """
    代理类，接管并包装底层微信的所有调用。
    提供无缝的向上兼容和竞态条件保护。
    """
    
    def __init__(self, instance: Any, poll_interval: float = 2.0):
        self.instance = instance
        self._listened_chats: set = set()
        self._message_cache: Dict[str, deque] = {}
        self._poll_interval = poll_interval
        self._last_poll_time = 0.0
        self._savepic_config: Dict[str, bool] = {}
        self._savevoice_config: Dict[str, bool] = {}

    def __getattr__(self, name: str) -> Any:
        """动态代理所有属性访问至底层实例"""
        if name == 'A_MyIcon':
            return _MyIconMock()
            
        return getattr(self.instance, name)

    def GetSessionList(self) -> List[Any]:
        try:
            return self.instance.GetSession()
        except AttributeError:
            return []

    def AddListenChat(self, who: str, savepic: bool = False, savevoice: bool = False, *args, **kwargs):
        self._listened_chats.add(who)
        self._savepic_config[who] = savepic
        self._savevoice_config[who] = savevoice
        if who not in self._message_cache:
            self._message_cache[who] = deque(maxlen=100)

    def _get_msg_hash(self, msg: Any, sender: str, content: str) -> str:
        """获取消息的唯一标识符"""
        msg_id = getattr(msg, 'id', None)
        if msg_id:
            return str(msg_id)
        return str(hash(f"{sender}::{content}"))

    def _map_msg_type(self, r_msg: Any) -> str:
        """映射 wxauto4 的类名为内部支持的类型"""
        cls_name = type(r_msg).__name__
        type_mapping = {
            'FriendMessage': 'friend',
            'SystemMessage': 'sys',
            'SelfMessage': 'self',
            'TimeMessage': 'time'
        }
        
        msg_type = type_mapping.get(cls_name)
        if not msg_type:
            msg_type = getattr(r_msg, 'type', 'friend')
            if type(r_msg).__name__ == 'str' or isinstance(r_msg, (list, tuple)):
                msg_type = 'friend'
                
        # 强制其他普通聊天类型为 'friend'
        if msg_type not in ['sys', 'time', 'self']:
            msg_type = 'friend'
            
        return msg_type

    def GetListenMessage(self) -> Dict[ChatMock, List[MsgMock]]:
        """安全增量拉取监听的消息"""
        current_time = time.time()
        if current_time - self._last_poll_time < self._poll_interval:
            return {}
            
        self._last_poll_time = current_time
        result = {}
        
        for who in self._listened_chats:
            try:
                if not self.instance.ChatWith(who):
                    continue
                    
                # 修复 UI 竞态：等待界面渲染完毕
                time.sleep(0.2)
                
                raw_msgs = self.instance.GetAllMessage()
                if not raw_msgs:
                    continue
                
                cache = self._message_cache[who]
                is_first_poll = len(cache) == 0
                new_msgs = []
                
                for r_msg in raw_msgs:
                    msg_type = self._map_msg_type(r_msg)
                    
                    sender = getattr(r_msg, 'sender', '')
                    content = getattr(r_msg, 'content', getattr(r_msg, 'text', ''))
                    
                    # 兼容极早期 wxauto 元组格式
                    if isinstance(r_msg, (list, tuple)):
                        sender = r_msg[0] if len(r_msg) > 0 else ''
                        content = r_msg[1] if len(r_msg) > 1 else ''
                    elif type(r_msg).__name__ == 'str':
                        content = str(r_msg)
                        
                    # 修复私聊中无法获取发送者名称的问题
                    if not sender and msg_type == 'friend':
                        sender = who
                        
                    msg_hash = self._get_msg_hash(r_msg, sender, content)
                    
                    if msg_hash not in cache:
                        # 这是新消息，如果需要下载图片且是图片类型
                        cls_name = type(r_msg).__name__
                        if self._savepic_config.get(who, False) and ('Image' in cls_name or 'Pic' in cls_name):
                            if hasattr(r_msg, 'download'):
                                import os
                                try:
                                    save_dir = os.path.abspath(os.path.join("data", "images", "temp"))
                                    os.makedirs(save_dir, exist_ok=True)
                                    before_files = set(os.listdir(save_dir))
                                    
                                    # 尝试下载
                                    res = r_msg.download(dir_path=save_dir)
                                    
                                    if res and hasattr(res, '__str__') and os.path.exists(str(res)):
                                        content = str(res)
                                    else:
                                        # 对比文件变化找到新文件
                                        after_files = set(os.listdir(save_dir))
                                        new_files = after_files - before_files
                                        if new_files:
                                            # 按修改时间找最新的
                                            new_file_paths = [os.path.join(save_dir, f) for f in new_files]
                                            new_file_paths.sort(key=os.path.getmtime, reverse=True)
                                            content = new_file_paths[0]
                                except Exception as e:
                                    logger.warning(f"wx adapter failed to download image: {e}")
                                    
                        cache.append(msg_hash)
                        if not is_first_poll:
                            new_msgs.append(MsgMock(
                                id=msg_hash,
                                type=msg_type,
                                content=content,
                                sender=sender
                            ))
                
                if new_msgs:
                    logger.info(f"[WeChatAdapter] Found {len(new_msgs)} new messages for {who}")
                    result[ChatMock(who)] = new_msgs
                    
            except Exception:
                logger.exception(f"wx adapter error during polling for {who}")
            
        return result
        
    def SendMsg(self, msg: str, who: Optional[str] = None, clear: bool = True, **kwargs) -> Any:
        """带强制缓冲和重置的安全发送接口"""
        try:
            if who:
                logger.info(f"[WeChatAdapter] Switching to {who} to send message...")
                self.instance.ChatWith(who)
                time.sleep(0.5)
            
            logger.info("[WeChatAdapter] Sending message...")
            result = self.instance.SendMsg(msg, clear=clear, **kwargs)
            logger.info("[WeChatAdapter] Message sent successfully.")
            return result
        except Exception as e:
            logger.error(f"[WeChatAdapter] SendMsg error: {e}")
            return False

    def SendFiles(self, filepath: str, who: Optional[str] = None, **kwargs) -> Any:
        """带强制缓冲的安全发图接口"""
        try:
            if who:
                logger.info(f"[WeChatAdapter] Switching to {who} to send files...")
                self.instance.ChatWith(who)
                time.sleep(0.5)
                
            logger.info(f"[WeChatAdapter] Sending file: {filepath}")
            result = self.instance.SendFiles(filepath, **kwargs)
            logger.info("[WeChatAdapter] File sent successfully.")
            return result
        except Exception as e:
            logger.error(f"[WeChatAdapter] SendFiles error: {e}")
            return False


# 单例模式导出
_wechat_instance = None

def WeChat(*args, **kwargs) -> WeChatAdapter:
    global _wechat_instance
    if _wechat_instance is None:
        _wechat_instance = WeChatAdapter(OriginalWeChat(*args, **kwargs))
    return _wechat_instance


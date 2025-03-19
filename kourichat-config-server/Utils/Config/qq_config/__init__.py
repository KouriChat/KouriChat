import toml
import threading
from typing import Any, Dict, Optional
from pathlib import Path
from Utils.ScopeBase import ScopeBase

class QQConfigManager(ScopeBase):
    def __new__(cls, config_path: str = "./config/bot_config.toml", key: Optional[str] = None, is_single: bool = True, *args, **kwargs):
        return super().__new__(cls, is_single=is_single, obj_key=key)
        
    def __init__(
        self, 
        config_path: str = "./config/bot_config.toml", 
        key: Optional[str] = None,
        is_single: bool = True
        ):
        """初始化日志管理器

        Args:
            config_path (str): 配置文件地址
            key (Optional[str], optional): 作用域id
            is_single (bool, optional): 是否是单例模式
        """
        self._config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load_config()

    def _load_config(self) -> None:
        """加载配置文件"""
        with self._lock:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._config = toml.load(f) or {}
            else:
                self._config = {}

    def _save_config(self) -> None:
        """保存配置到文件"""
        with self._lock:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, 'w', encoding='utf-8') as f:
                toml.dump(self._config, f)

    def __getitem__(self, key: str) -> Any:
        """获取配置项"""
        with self._lock:
            return self._config[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """设置配置项并保存"""
        with self._lock:
            self._config[key] = value
            self._save_config()

    def __contains__(self, key: str) -> bool:
        """检查配置项是否存在"""
        with self._lock:
            return key in self._config

    def get(self, key: str, default: Any = None) -> Any:
        """安全获取配置项，如果不存在返回默认值"""
        with self._lock:
            return self._config.get(key, default)

    def update(self, config_dict: Dict[str, Any]) -> None:
        """批量更新配置并保存"""
        with self._lock:
            self._config.update(config_dict)
            self._save_config()

    def reload(self) -> None:
        """重新加载配置文件"""
        self._load_config()

    @property
    def config(self) -> Dict[str, Any]:
        """获取完整的配置字典（只读）"""
        with self._lock:
            return self._config.copy()

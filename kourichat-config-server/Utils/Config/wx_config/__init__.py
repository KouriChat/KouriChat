import yaml
import threading
from typing import Any, Dict, Optional
from pathlib import Path
from Utils.ScopeBase import ScopeBase

class WXConfigManager(ScopeBase):
    def __new__(cls, config_path: str = "./config/bot_config.yaml", key: Optional[str] = None, is_single: bool = True, *args, **kwargs):
        return super().__new__(cls, is_single=is_single, obj_key=key)
        
    def __init__(
        self, 
        config_path: str = "./config/bot_config.yaml", 
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
                    self._config = yaml.safe_load(f) or {}
            else:
                self._config = {}

    def _save_config(self) -> None:
        """保存配置文件"""
        with self._lock:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._config, f, allow_unicode=True)

    def __getitem__(self, key: str) -> Any:
        return self._config[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._config[key] = value
        self._save_config()

    def __contains__(self, key: str) -> bool:
        return key in self._config

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def update(self, config_dict: Dict[str, Any]) -> None:
        self._config.update(config_dict)
        self._save_config()

    def reload(self) -> None:
        self._load_config()

    @property
    def config(self) -> Dict[str, Any]:
        return self._config 
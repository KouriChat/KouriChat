"""
配置管理模块
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger("autoupdate.config")

@dataclass
class CloudAPIConfig:
    update_api_url: str = "https://git.kourichat.com/KouriChat-Main/cloud-delivery-repo/raw/branch/main/updater.json"
    timeout: int = 10
    retry_count: int = 3
    verify_ssl: bool = True

@dataclass
class NetworkAdapterConfig:
    enabled: bool = True
    auto_install: bool = True

@dataclass
class SecurityConfig:
    signature_verification: bool = True
    encryption_enabled: bool = True

@dataclass
class LoggingConfig:
    level: str = "INFO"
    enable_debug: bool = False
    log_file: Optional[str] = None
    max_log_size: int = 10485760

class ConfigManager:
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self._get_default_config_path()
        self.cloud_api = CloudAPIConfig()
        self.network_adapter = NetworkAdapterConfig()
        self.security = SecurityConfig()
        self.logging = LoggingConfig()
        
        self.load_config()
    
    def _get_default_config_path(self) -> str:
        # 使用模块内的配置文件
        default_config = Path(__file__).parent / "autoupdate_config.json"
        return str(default_config)
    
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # 更新各个配置对象
                if "cloud_api" in config_data:
                    self._update_dataclass(self.cloud_api, config_data["cloud_api"])
                
                if "network_adapter" in config_data:
                    self._update_dataclass(self.network_adapter, config_data["network_adapter"])
                # 向后兼容旧配置
                elif "interceptor" in config_data:
                    self._update_dataclass(self.network_adapter, config_data["interceptor"])
                
                if "security" in config_data:
                    self._update_dataclass(self.security, config_data["security"])
                
                if "logging" in config_data:
                    self._update_dataclass(self.logging, config_data["logging"])
                
                logger.info(f"Configuration loaded from {self.config_file}")
            else:
                logger.info("No configuration file found, using defaults")
                
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}")
            logger.info("Using default configuration")
    
    def _update_dataclass(self, obj, data: Dict[str, Any]):
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
    
    def get_config_summary(self) -> Dict[str, Any]:
        return {
            "cloud_api_url": self.cloud_api.update_api_url,
            "network_adapter_enabled": self.network_adapter.enabled,
            "security_enabled": self.security.signature_verification,
            "config_file": self.config_file
        }

# 全局配置管理器实例
_config_manager = None

def get_config() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

def init_config(config_file: Optional[str] = None) -> ConfigManager:
    global _config_manager
    _config_manager = ConfigManager(config_file)
    return _config_manager

def reload_config():
    if _config_manager:
        _config_manager.load_config()

# 便捷函数
def get_cloud_api_config() -> CloudAPIConfig:
    return get_config().cloud_api

def get_network_adapter_config() -> NetworkAdapterConfig:
    return get_config().network_adapter

def get_security_config() -> SecurityConfig:
    return get_config().security
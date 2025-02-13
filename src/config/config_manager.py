"""
配置管理模块
提供YAML配置文件的加载和管理功能，包括:
- 配置文件加载
- 配置值获取
- 配置值验证
- 配置热重载
"""

import os
import yaml
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self.load_config()

    def load_config(self) -> None:
        """加载YAML配置文件"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            logger.info("配置文件加载成功")
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            raise

    def reload_config(self) -> None:
        """重新加载配置文件"""
        self.load_config()

    def get_value(self, *keys: str, default: Any = None) -> Any:
        """
        获取配置值
        :param keys: 配置键路径
        :param default: 默认值
        :return: 配置值
        """
        try:
            value = self._config
            for key in keys:
                value = value[key]
            if isinstance(value, dict) and 'value' in value:
                return value['value']
            return value
        except (KeyError, TypeError):
            return default

    @property
    def listen_list(self) -> List[str]:
        """获取监听列表"""
        return self.get_value('base', 'listen_list', 'value', default=[])

    @property
    def llm_config(self) -> Dict:
        """获取当前活动的LLM配置"""
        active_llm = self.get_value('providers', 'llm', 'active')
        return {
            'api_key': self.get_value('providers', 'llm', 'services', active_llm, 'api_key', 'value'),
            'base_url': self.get_value('providers', 'llm', 'services', active_llm, 'base_url', 'value'),
            'chat_model': self.get_value('providers', 'llm', 'services', active_llm, 'models', 'chat', 'value'),
            'image_model': self.get_value('providers', 'llm', 'services', active_llm, 'models', 'image', 'value'),
            'max_token': self.get_value('providers', 'llm', 'services', active_llm, 'parameters', 'max_token', 'value'),
            'temperature': self.get_value('providers', 'llm', 'services', active_llm, 'parameters', 'temperature', 'value')
        }

    @property
    def vision_config(self) -> Dict:
        """获取当前活动的视觉服务配置"""
        active_vision = self.get_value('providers', 'vision', 'active')
        return {
            'api_key': self.get_value('providers', 'vision', 'services', active_vision, 'api_key', 'value'),
            'base_url': self.get_value('providers', 'vision', 'services', active_vision, 'base_url', 'value'),
            'temperature': self.get_value('providers', 'vision', 'services', active_vision, 'parameters', 'temperature', 'value')
        }

    @property
    def voice_config(self) -> Dict:
        """获取当前活动的语音服务配置"""
        active_voice = self.get_value('providers', 'voice', 'active')
        return {
            'api_url': self.get_value('providers', 'voice', 'services', active_voice, 'api_url', 'value')
        }

    @property
    def storage_paths(self) -> Dict:
        """获取存储路径配置"""
        return {
            'temp_image': self.get_value('storage', 'paths', 'images', 'temp', 'value'),
            'emoji': self.get_value('storage', 'paths', 'images', 'emoji', 'value'),
            'voice': self.get_value('storage', 'paths', 'voice', 'value'),
            'prompt': self.get_value('storage', 'paths', 'character', 'prompt', 'value')
        }

    @property
    def system_config(self) -> Dict:
        """获取系统配置"""
        return {
            'max_context_groups': self.get_value('system', 'character', 'max_context_groups', 'value'),
            'auto_message_template': self.get_value('system', 'auto_message', 'template', 'value'),
            'min_countdown_hours': self.get_value('system', 'auto_message', 'countdown', 'min_hours', 'value'),
            'max_countdown_hours': self.get_value('system', 'auto_message', 'countdown', 'max_hours', 'value'),
            'quiet_time_start': self.get_value('system', 'time_limits', 'quiet_period', 'start', 'value'),
            'quiet_time_end': self.get_value('system', 'time_limits', 'quiet_period', 'end', 'value')
        }

# 创建全局配置管理器实例
config = ConfigManager() 
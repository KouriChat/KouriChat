"""
代理配置模块
统一管理所有服务的代理设置
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger('main')

class ProxyConfig:
    """
    代理配置管理类
    提供统一的代理配置接口
    """

    def __init__(self):
        # 默认代理配置（仅作为备用）
        self._proxy_config = {}

        # 代理服务器列表
        self._proxy_servers = {
            'default': {
                'http': 'http://127.0.0.1:7890',
                'https': 'http://127.0.0.1:7890'
            },
            'clash': {
                'http': 'http://127.0.0.1:7890',
                'https': 'http://127.0.0.1:7890'
            },
            'v2ray': {
                'http': 'http://127.0.0.1:10809',
                'https': 'http://127.0.0.1:10809'
            },
            'shadowsocks': {
                'http': 'http://127.0.0.1:1080',
                'https': 'http://127.0.0.1:1080'
            }
        }

    def get_proxy_config(self, proxy_type: str = 'auto') -> Dict[str, str]:
        """
        获取代理配置（支持自动检测系统代理）

        Args:
            proxy_type: 代理类型
                       - 'auto': 自动检测系统代理（推荐）
                       - 'default', 'clash', 'v2ray', 'shadowsocks': 指定代理类型
                       - 'direct': 强制直连

        Returns:
            Dict[str, str]: 代理配置字典，空字典表示直连
        """
        # 自动检测系统代理
        if proxy_type == 'auto':
            system_proxy = self._detect_system_proxy()
            if system_proxy:
                logger.info(f"检测到系统代理: {system_proxy}")
                return system_proxy
            else:
                logger.info("未检测到系统代理，使用直连模式")
                return {}

        # 强制直连
        elif proxy_type == 'direct':
            logger.info("使用直连模式")
            return {}

        # 指定代理类型
        elif proxy_type in self._proxy_servers:
            config = self._proxy_servers[proxy_type].copy()
            logger.info(f"使用代理配置: {proxy_type} - {config}")
            return config

        else:
            logger.warning(f"未知的代理类型: {proxy_type}，使用默认配置")
            return self._proxy_config.copy()

    def set_custom_proxy(self, http_proxy: str, https_proxy: str) -> None:
        """
        设置自定义代理

        Args:
            http_proxy: HTTP代理地址
            https_proxy: HTTPS代理地址
        """
        self._proxy_config = {
            'http': self._normalize_proxy_url(http_proxy),
            'https': self._normalize_proxy_url(https_proxy)
        }
        logger.info(f"已设置自定义代理: {self._proxy_config}")

    def add_proxy_server(self, name: str, http_proxy: str, https_proxy: str) -> None:
        """
        添加新的代理服务器配置

        Args:
            name: 代理服务器名称
            http_proxy: HTTP代理地址
            https_proxy: HTTPS代理地址
        """
        self._proxy_servers[name] = {
            'http': self._normalize_proxy_url(http_proxy),
            'https': self._normalize_proxy_url(https_proxy)
        }
        logger.info(f"已添加代理服务器配置: {name}")

    def _normalize_proxy_url(self, proxy_url: str) -> str:
        """
        标准化代理URL格式

        Args:
            proxy_url: 代理URL

        Returns:
            str: 标准化的代理URL
        """
        if not proxy_url:
            return proxy_url

        # 确保URL格式正确
        if not proxy_url.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
            proxy_url = f"http://{proxy_url}"

        return proxy_url

    def _detect_system_proxy(self) -> Dict[str, str]:
        """
        自动检测系统代理配置

        Returns:
            Dict[str, str]: 系统代理配置，空字典表示未检测到有效代理
        """
        import os
        import requests

        logger.debug("开始检测系统代理...")

        # 常见的代理环境变量（按优先级排序）
        proxy_env_vars = [
            'ALL_PROXY', 'all_proxy',  # 通用代理
            'HTTPS_PROXY', 'https_proxy',  # HTTPS代理
            'HTTP_PROXY', 'http_proxy'  # HTTP代理
        ]

        detected_proxies = {}

        # 1. 检查环境变量
        for env_var in proxy_env_vars:
            proxy_url = os.environ.get(env_var)
            if proxy_url:
                logger.debug(f"发现环境变量 {env_var} = {proxy_url}")

                # 标准化URL
                normalized_url = self._normalize_proxy_url(proxy_url)

                # 根据变量类型设置对应的代理
                if env_var.lower() in ['http_proxy', 'all_proxy']:
                    detected_proxies['http'] = normalized_url
                if env_var.lower() in ['https_proxy', 'all_proxy']:
                    detected_proxies['https'] = normalized_url

                # 如果设置了ALL_PROXY，应用到所有协议
                if env_var.lower() == 'all_proxy':
                    detected_proxies['http'] = normalized_url
                    detected_proxies['https'] = normalized_url

        if not detected_proxies:
            logger.debug("未发现任何代理环境变量")
            return {}

        logger.debug(f"检测到的代理配置: {detected_proxies}")

        # 2. 验证代理连接
        if self._validate_proxy_connection(detected_proxies):
            logger.info(f"系统代理验证成功: {detected_proxies}")
            return detected_proxies
        else:
            logger.warning("系统代理验证失败，使用直连模式")
            return {}

    def _validate_proxy_connection(self, proxy_config: Dict[str, str], timeout: int = 5) -> bool:
        """
        验证代理连接是否可用

        Args:
            proxy_config: 代理配置字典
            timeout: 连接超时时间（秒）

        Returns:
            bool: 代理是否可用
        """
        import requests

        # 使用简单的HTTP测试URL
        test_urls = [
            "http://httpbin.org/ip",  # HTTP测试
            "https://httpbin.org/ip"  # HTTPS测试
        ]

        for test_url in test_urls:
            try:
                logger.debug(f"测试代理连接: {test_url}")
                response = requests.get(
                    test_url,
                    proxies=proxy_config,
                    timeout=timeout,
                    verify=False  # 跳过SSL验证，提高成功率
                )

                if response.status_code == 200:
                    logger.debug(f"代理连接测试成功: {test_url}")
                    return True
                else:
                    logger.debug(f"代理连接测试失败，状态码: {response.status_code}")

            except requests.exceptions.RequestException as e:
                logger.debug(f"代理连接测试异常: {test_url} - {str(e)}")
                continue

        return False

    def get_available_proxies(self) -> Dict[str, Dict[str, str]]:
        """
        获取所有可用的代理配置

        Returns:
            Dict[str, Dict[str, str]]: 所有代理配置
        """
        return self._proxy_servers.copy()

    def test_proxy_connection(self, proxy_config: Optional[Dict[str, str]] = None, test_url: str = "https://httpbin.org/ip") -> Dict:
        """
        测试代理连接

        Args:
            proxy_config: 要测试的代理配置，如果为None则使用当前配置
            test_url: 测试URL

        Returns:
            Dict: 测试结果
        """
        import requests

        if proxy_config is None:
            proxy_config = self._proxy_config

        try:
            logger.info(f"测试代理连接: {proxy_config}")
            response = requests.get(
                test_url,
                proxies=proxy_config,
                timeout=10
            )
            response.raise_for_status()

            return {
                "success": True,
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds(),
                "proxy_config": proxy_config,
                "test_url": test_url
            }
        except Exception as e:
            logger.error(f"代理连接测试失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "proxy_config": proxy_config,
                "test_url": test_url
            }

# 全局代理配置实例
proxy_manager = ProxyConfig()

def get_proxy_config(proxy_type: str = 'auto') -> Dict[str, str]:
    """
    获取代理配置的便捷函数（默认自动检测系统代理）

    Args:
        proxy_type: 代理类型
                   - 'auto': 自动检测系统代理（默认，推荐）
                   - 'default', 'clash', 'v2ray', 'shadowsocks': 指定代理类型
                   - 'direct': 强制直连

    Returns:
        Dict[str, str]: 代理配置字典，空字典表示直连
    """
    return proxy_manager.get_proxy_config(proxy_type)

def set_custom_proxy(http_proxy: str, https_proxy: str) -> None:
    """
    设置自定义代理的便捷函数

    Args:
        http_proxy: HTTP代理地址
        https_proxy: HTTPS代理地址
    """
    proxy_manager.set_custom_proxy(http_proxy, https_proxy)

def test_proxy_connection(proxy_type: str = 'auto', test_url: str = "https://httpbin.org/ip") -> Dict:
    """
    测试代理连接的便捷函数（默认自动检测）

    Args:
        proxy_type: 代理类型
        test_url: 测试URL

    Returns:
        Dict: 测试结果
    """
    proxy_config = proxy_manager.get_proxy_config(proxy_type)
    return proxy_manager.test_proxy_connection(proxy_config, test_url)

def get_system_proxy_status() -> Dict:
    """
    获取系统代理状态信息

    Returns:
        Dict: 系统代理状态信息
    """
    import os

    # 检测环境变量
    env_vars = {}
    for var in ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
        env_vars[var] = os.environ.get(var, '未设置')

    # 检测系统代理
    system_proxy = proxy_manager._detect_system_proxy()

    return {
        'environment_variables': env_vars,
        'system_proxy_detected': bool(system_proxy),
        'system_proxy_config': system_proxy,
        'connection_mode': '代理' if system_proxy else '直连'
    }

"""
Web 界面配置模块
"""

# WebSocket 配置
WS_CONFIG = {
    'retry_interval': 5,  # WebSocket 重连间隔（秒）
    'max_retries': 3,    # 最大重试次数
    'ping_interval': 30,  # 心跳包间隔（秒）
    'timeout': 10        # 连接超时时间（秒）
}

# 资源加载配置
RESOURCE_CONFIG = {
    'enable_analytics': False,      # 禁用 umami 分析
    'enable_external_images': False,  # 禁用外部图片加载
    'cache_timeout': 3600,         # 资源缓存时间（秒）
    'local_assets_path': './assets'  # 本地资源路径
}

# 页面性能配置
PERFORMANCE_CONFIG = {
    'enable_compression': True,     # 启用响应压缩
    'max_cache_size': 100,         # 最大缓存条目数
    'lazy_loading': True,          # 启用延迟加载
    'prefetch': False              # 禁用预加载
}

# 日志配置
LOG_CONFIG = {
    'log_to_file': False,           # 禁用文件日志
    'console_log_level': 'INFO',    # 控制台日志级别
    'ws_log_level': 'WARNING',      # WebSocket 日志级别
    'max_log_size': 1024 * 1024,    # 最大日志大小（字节）
    'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}

# UI 配置
UI_CONFIG = {
    'theme': 'light',
    'sidebar_state': 'expanded',
    'layout': 'wide',
    'enable_custom_fonts': False,  # 禁用自定义字体
    'enable_animations': False,    # 禁用动画效果
    'toast_duration': 3000        # 提示消息持续时间（毫秒）
}

def get_web_config():
    """获取 Web 配置"""
    return {
        'ws': WS_CONFIG,
        'resource': RESOURCE_CONFIG,
        'performance': PERFORMANCE_CONFIG,
        'log': LOG_CONFIG,
        'ui': UI_CONFIG
    } 
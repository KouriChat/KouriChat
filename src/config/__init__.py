"""
配置模块
提供配置管理功能，包括:
- 配置文件加载
- 配置访问接口
- 配置热重载
"""

from .config_manager import config

# 为了向后兼容，导出所有配置项
LISTEN_LIST = config.listen_list

# LLM配置
DEEPSEEK_API_KEY = config.llm_config['api_key']
DEEPSEEK_BASE_URL = config.llm_config['base_url']
MODEL = config.llm_config['chat_model']
IMAGE_MODEL = config.llm_config['image_model']
MAX_TOKEN = config.llm_config['max_token']
TEMPERATURE = config.llm_config['temperature']

# 视觉服务配置
MOONSHOT_API_KEY = config.vision_config['api_key']
MOONSHOT_BASE_URL = config.vision_config['base_url']
MOONSHOT_TEMPERATURE = config.vision_config['temperature']

# 语音服务配置
TTS_API_URL = config.voice_config['api_url']

# 存储路径配置
TEMP_IMAGE_DIR = config.storage_paths['temp_image']
EMOJI_DIR = config.storage_paths['emoji']
VOICE_DIR = config.storage_paths['voice']
PROMPT_NAME = config.storage_paths['prompt']

# 系统配置
MAX_GROUPS = config.system_config['max_context_groups']
AUTO_MESSAGE = config.system_config['auto_message_template']
MIN_COUNTDOWN_HOURS = config.system_config['min_countdown_hours']
MAX_COUNTDOWN_HOURS = config.system_config['max_countdown_hours']
QUIET_TIME_START = config.system_config['quiet_time_start']
QUIET_TIME_END = config.system_config['quiet_time_end'] 
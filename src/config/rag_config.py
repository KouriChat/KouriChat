"""
KouriChat RAG配置文件

此模块提供对RAG系统配置的简单访问。
它会从src/config/__init__.py加载配置设置，并提供嵌入服务和RAG系统所需的配置变量。
"""

import os
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

# 初始化日志记录器
logger = logging.getLogger(__name__)

# 确保可以导入SettingReader
try:
    from src.config import SettingReader
except ImportError:
    logger.error("无法导入SettingReader，请确保src目录在Python路径中")
    # 尝试添加src目录到Python路径
    root_dir = Path(__file__).parent.parent.parent
    if root_dir not in sys.path:
        sys.path.append(str(root_dir))
        logger.info(f"已添加{root_dir}到Python路径")
    try:
        from src.config import SettingReader
    except ImportError:
        logger.error("仍然无法导入SettingReader，使用默认配置")
        SettingReader = None

# 初始化配置读取器
try:
    config_reader = SettingReader() if SettingReader else None
    
    # 创建配置对象
    config = SimpleNamespace()
    
    # 创建子配置对象
    llm = SimpleNamespace()
    rag = SimpleNamespace()
    behavior = SimpleNamespace()
    user = SimpleNamespace()
    media = SimpleNamespace()
    
    # 设置默认值
    # LLM配置默认值
    llm.api_key = os.getenv("DEEPSEEK_API_KEY", "")
    llm.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.siliconflow.cn/v1/")
    llm.model = os.getenv("MODEL", "deepseek-ai/DeepSeek-V3")
    llm.max_tokens = int(os.getenv("MAX_TOKEN", "1000"))
    llm.temperature = float(os.getenv("TEMPERATURE", "1.2"))
    
    # RAG配置默认值
    rag.api_key = os.getenv("OPENAI_API_KEY", "")
    rag.base_url = os.getenv("OPENAI_API_BASE", "")
    rag.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    rag.reranker_model = os.getenv("RAG_RERANKER_MODEL", "")  # 默认为空，将使用LLM模型
    rag.top_k = int(os.getenv("RAG_TOP_K", "5"))
    rag.is_rerank = os.getenv("RAG_IS_RERANK", "True").lower() in ("true", "1", "yes", "y")
    
    # 添加本地模型设置
    rag.local_model_enabled = os.getenv("LOCAL_MODEL_ENABLED", "False").lower() in ("true", "1", "yes", "y")
    rag.local_embedding_model_path = os.getenv("LOCAL_EMBEDDING_MODEL_PATH", "paraphrase-multilingual-MiniLM-L12-v2")
        
    # 添加硅基流动自动适配配置
    rag.auto_adapt_siliconflow = os.getenv("AUTO_ADAPT_SILICONFLOW", "True").lower() in ("true", "1", "yes", "y")
    
    # 行为配置默认值
    behavior.context = SimpleNamespace()
    behavior.context.max_groups = 10
    behavior.context.avatar_dir = "MONO"
    
    # 添加auto_message配置
    behavior.auto_message = SimpleNamespace()
    behavior.auto_message.content = "请你模拟系统设置的角色，在微信上找对方聊天"
    behavior.auto_message.min_hours = 1
    behavior.auto_message.max_hours = 3
    
    # 添加quiet_time配置
    behavior.quiet_time = SimpleNamespace()
    behavior.quiet_time.start = "22:00"
    behavior.quiet_time.end = "08:00"
    
    # 用户配置默认值
    user.listen_list = []
    
    # 媒体配置默认值
    media.image_recognition = SimpleNamespace()
    media.image_recognition.api_key = ""
    media.image_recognition.base_url = "https://api.ciallo.ac.cn/v1"
    media.image_recognition.temperature = 0.35
    media.image_recognition.model = "kourichat-vision"
    
    media.image_generation = SimpleNamespace()
    media.image_generation.model = "deepseek-ai/Janus-Pro-7B"
    media.image_generation.temp_dir = "data/images/temp"
    
    media.text_to_speech = SimpleNamespace()
    media.text_to_speech.tts_api_url = "http://127.0.0.1:5000/tts"
    media.text_to_speech.voice_dir = "data/voices"
    
    # 从config_reader中读取配置
    if config_reader:
        # 读取LLM配置
        if hasattr(config_reader, 'llm'):
            llm.api_key = getattr(config_reader.llm, 'api_key', llm.api_key)
            llm.base_url = getattr(config_reader.llm, 'base_url', llm.base_url)
            llm.model = getattr(config_reader.llm, 'model', llm.model)
            llm.max_tokens = int(getattr(config_reader.llm, 'max_tokens', llm.max_tokens))
            llm.temperature = float(getattr(config_reader.llm, 'temperature', llm.temperature))
        
        # 读取RAG配置
        if hasattr(config_reader, 'rag'):
            rag.api_key = getattr(config_reader.rag, 'api_key', rag.api_key)
            rag.base_url = getattr(config_reader.rag, 'base_url', rag.base_url)
            
            # 处理embedding_model，支持字典或字符串类型
            embedding_model_config = getattr(config_reader.rag, 'embedding_model', rag.embedding_model)
            if isinstance(embedding_model_config, dict) and 'value' in embedding_model_config:
                rag.embedding_model = embedding_model_config['value']
            else:
                rag.embedding_model = embedding_model_config
                
            rag.top_k = getattr(config_reader.rag, 'top_k', rag.top_k)
            rag.is_rerank = getattr(config_reader.rag, 'is_rerank', rag.is_rerank)
            
            # 处理reranker_model，支持字典或字符串类型
            reranker_model_config = getattr(config_reader.rag, 'reranker_model', rag.reranker_model)
            if isinstance(reranker_model_config, dict) and 'value' in reranker_model_config:
                rag.reranker_model = reranker_model_config['value']
            else:
                rag.reranker_model = reranker_model_config
                
            # 读取本地模型设置
            local_model_enabled = getattr(config_reader.rag, 'local_model_enabled', rag.local_model_enabled)
            if isinstance(local_model_enabled, dict) and 'value' in local_model_enabled:
                rag.local_model_enabled = local_model_enabled['value']
            else:
                rag.local_model_enabled = local_model_enabled
                
            local_model_path = getattr(config_reader.rag, 'local_embedding_model_path', rag.local_embedding_model_path)
            if isinstance(local_model_path, dict) and 'value' in local_model_path:
                rag.local_embedding_model_path = local_model_path['value']
            else:
                rag.local_embedding_model_path = local_model_path
                
            # 读取硅基流动自动适配设置
            auto_adapt = getattr(config_reader.rag, 'auto_adapt_siliconflow', rag.auto_adapt_siliconflow)
            if isinstance(auto_adapt, dict) and 'value' in auto_adapt:
                rag.auto_adapt_siliconflow = auto_adapt['value']
            else:
                rag.auto_adapt_siliconflow = auto_adapt
        
        # 读取行为配置
        if hasattr(config_reader, 'behavior'):
            if hasattr(config_reader.behavior, 'context'):
                behavior.context.max_groups = getattr(config_reader.behavior.context, 'max_groups', behavior.context.max_groups)
                behavior.context.avatar_dir = getattr(config_reader.behavior.context, 'avatar_dir', behavior.context.avatar_dir)
            
            # 读取auto_message配置
            if hasattr(config_reader.behavior, 'auto_message'):
                behavior.auto_message.content = getattr(config_reader.behavior.auto_message, 'content', behavior.auto_message.content)
                behavior.auto_message.min_hours = getattr(config_reader.behavior.auto_message, 'min_hours', behavior.auto_message.min_hours)
                behavior.auto_message.max_hours = getattr(config_reader.behavior.auto_message, 'max_hours', behavior.auto_message.max_hours)
            
            # 读取quiet_time配置
            if hasattr(config_reader.behavior, 'quiet_time'):
                behavior.quiet_time.start = getattr(config_reader.behavior.quiet_time, 'start', behavior.quiet_time.start)
                behavior.quiet_time.end = getattr(config_reader.behavior.quiet_time, 'end', behavior.quiet_time.end)
        
        # 读取用户配置
        if hasattr(config_reader, 'user'):
            user.listen_list = getattr(config_reader.user, 'listen_list', user.listen_list)
        
        # 读取媒体配置
        if hasattr(config_reader, 'media'):
            # 图像识别配置
            if hasattr(config_reader.media, 'image_recognition'):
                media.image_recognition.api_key = getattr(config_reader.media.image_recognition, 'api_key', media.image_recognition.api_key)
                media.image_recognition.base_url = getattr(config_reader.media.image_recognition, 'base_url', media.image_recognition.base_url)
                media.image_recognition.temperature = getattr(config_reader.media.image_recognition, 'temperature', media.image_recognition.temperature)
                media.image_recognition.model = getattr(config_reader.media.image_recognition, 'model', media.image_recognition.model)
            
            # 图像生成配置
            if hasattr(config_reader.media, 'image_generation'):
                media.image_generation.model = getattr(config_reader.media.image_generation, 'model', media.image_generation.model)
                media.image_generation.temp_dir = getattr(config_reader.media.image_generation, 'temp_dir', media.image_generation.temp_dir)
            
            # 语音合成配置
            if hasattr(config_reader.media, 'text_to_speech'):
                media.text_to_speech.tts_api_url = getattr(config_reader.media.text_to_speech, 'tts_api_url', media.text_to_speech.tts_api_url)
                media.text_to_speech.voice_dir = getattr(config_reader.media.text_to_speech, 'voice_dir', media.text_to_speech.voice_dir)
    
    # 设置config对象的属性
    config.llm = llm
    config.rag = rag
    config.behavior = behavior
    config.user = user
    config.media = media
    
    # 为了兼容性，设置一些常量
    EMBEDDING_MODEL = rag.embedding_model
    EMBEDDING_FALLBACK_MODEL = "text-embedding-ada-002"
    OPENAI_API_KEY = rag.api_key
    OPENAI_API_BASE = rag.base_url
    RAG_TOP_K = rag.top_k
    RAG_IS_RERANK = rag.is_rerank
    RAG_RERANKER_MODEL = rag.reranker_model
    LOCAL_MODEL_ENABLED = rag.local_model_enabled
    LOCAL_EMBEDDING_MODEL_PATH = rag.local_embedding_model_path
    AUTO_ADAPT_SILICONFLOW = rag.auto_adapt_siliconflow
    DEEPSEEK_API_KEY = llm.api_key
    DEEPSEEK_BASE_URL = llm.base_url
    MODEL = llm.model
    MAX_TOKEN = llm.max_tokens
    TEMPERATURE = llm.temperature
    MAX_GROUPS = behavior.context.max_groups
    
    # 设置config对象的常量属性
    config.EMBEDDING_MODEL = EMBEDDING_MODEL
    config.EMBEDDING_FALLBACK_MODEL = EMBEDDING_FALLBACK_MODEL
    config.OPENAI_API_KEY = OPENAI_API_KEY
    config.OPENAI_API_BASE = OPENAI_API_BASE
    config.RAG_TOP_K = RAG_TOP_K
    config.RAG_IS_RERANK = RAG_IS_RERANK
    config.RAG_RERANKER_MODEL = RAG_RERANKER_MODEL
    config.LOCAL_MODEL_ENABLED = LOCAL_MODEL_ENABLED
    config.LOCAL_EMBEDDING_MODEL_PATH = LOCAL_EMBEDDING_MODEL_PATH
    config.AUTO_ADAPT_SILICONFLOW = AUTO_ADAPT_SILICONFLOW
    config.DEEPSEEK_API_KEY = DEEPSEEK_API_KEY
    config.DEEPSEEK_BASE_URL = DEEPSEEK_BASE_URL
    config.MODEL = MODEL
    config.MAX_TOKEN = MAX_TOKEN
    config.TEMPERATURE = TEMPERATURE
    config.MAX_GROUPS = MAX_GROUPS
    config.robot_wx_name = ""  # 添加机器人微信名称

except Exception as e:
    logger.error(f"加载配置时出错: {str(e)}")
    # 提供默认值
    config = SimpleNamespace()
    
    # 创建子配置对象
    llm = SimpleNamespace()
    rag = SimpleNamespace()
    behavior = SimpleNamespace()
    user = SimpleNamespace()
    media = SimpleNamespace()
    
    # 设置默认值
    # LLM配置默认值
    llm.api_key = os.getenv("DEEPSEEK_API_KEY", "")
    llm.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.ciallo.ac.cn/v1")
    llm.model = os.getenv("MODEL", "deepseek-chat")
    llm.max_tokens = int(os.getenv("MAX_TOKEN", "1000"))
    llm.temperature = float(os.getenv("TEMPERATURE", "1.0"))
    
    # RAG配置默认值
    rag.api_key = os.getenv("OPENAI_API_KEY", "")
    rag.base_url = os.getenv("OPENAI_API_BASE", "")
    rag.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    rag.reranker_model = os.getenv("RAG_RERANKER_MODEL", "")  # 默认为空，将使用LLM模型
    rag.top_k = int(os.getenv("RAG_TOP_K", "5"))
    rag.is_rerank = os.getenv("RAG_IS_RERANK", "True").lower() in ("true", "1", "yes", "y")
    
    # 添加本地模型设置
    rag.local_model_enabled = os.getenv("LOCAL_MODEL_ENABLED", "False").lower() in ("true", "1", "yes", "y")
    rag.local_embedding_model_path = os.getenv("LOCAL_EMBEDDING_MODEL_PATH", "paraphrase-multilingual-MiniLM-L12-v2")
        
    # 添加硅基流动自动适配配置
    rag.auto_adapt_siliconflow = os.getenv("AUTO_ADAPT_SILICONFLOW", "True").lower() in ("true", "1", "yes", "y")
    
    # 行为配置默认值
    behavior.context = SimpleNamespace()
    behavior.context.max_groups = 10
    behavior.context.avatar_dir = "MONO"
    
    # 添加auto_message配置
    behavior.auto_message = SimpleNamespace()
    behavior.auto_message.content = "请你模拟系统设置的角色，在微信上结合上下文找对方聊天"
    behavior.auto_message.min_hours = 1
    behavior.auto_message.max_hours = 3
    
    # 添加quiet_time配置
    behavior.quiet_time = SimpleNamespace()
    behavior.quiet_time.start = "22:00"
    behavior.quiet_time.end = "08:00"
    
    # 用户配置默认值
    user.listen_list = []
    
    # 媒体配置默认值
    media.image_recognition = SimpleNamespace()
    media.image_recognition.api_key = ""
    media.image_recognition.base_url = "https://api.ciallo.ac.cn/v1"
    media.image_recognition.temperature = 0.35
    media.image_recognition.model = "kourichat-vision"
    
    media.image_generation = SimpleNamespace()
    media.image_generation.model = "kourichat-imagegen"
    media.image_generation.temp_dir = "data/images/temp"
    
    media.text_to_speech = SimpleNamespace()
    media.text_to_speech.tts_api_url = "http://127.0.0.1:5000/tts"
    media.text_to_speech.voice_dir = "data/voices"
    
    # 设置config对象的属性
    config.llm = llm
    config.rag = rag
    config.behavior = behavior
    config.user = user
    config.media = media
    
    # 为了兼容性，设置一些常量
    EMBEDDING_MODEL = rag.embedding_model
    EMBEDDING_FALLBACK_MODEL = "text-embedding-ada-002"
    OPENAI_API_KEY = rag.api_key
    OPENAI_API_BASE = rag.base_url
    RAG_TOP_K = rag.top_k
    RAG_IS_RERANK = rag.is_rerank
    RAG_RERANKER_MODEL = rag.reranker_model
    LOCAL_MODEL_ENABLED = rag.local_model_enabled
    LOCAL_EMBEDDING_MODEL_PATH = rag.local_embedding_model_path
    AUTO_ADAPT_SILICONFLOW = rag.auto_adapt_siliconflow
    DEEPSEEK_API_KEY = llm.api_key
    DEEPSEEK_BASE_URL = llm.base_url
    MODEL = llm.model
    MAX_TOKEN = llm.max_tokens
    TEMPERATURE = llm.temperature
    MAX_GROUPS = behavior.context.max_groups
    
    # 设置config对象的常量属性
    config.EMBEDDING_MODEL = EMBEDDING_MODEL
    config.EMBEDDING_FALLBACK_MODEL = EMBEDDING_FALLBACK_MODEL
    config.OPENAI_API_KEY = OPENAI_API_KEY
    config.OPENAI_API_BASE = OPENAI_API_BASE
    config.RAG_TOP_K = RAG_TOP_K
    config.RAG_IS_RERANK = RAG_IS_RERANK
    config.RAG_RERANKER_MODEL = RAG_RERANKER_MODEL
    config.LOCAL_MODEL_ENABLED = LOCAL_MODEL_ENABLED
    config.LOCAL_EMBEDDING_MODEL_PATH = LOCAL_EMBEDDING_MODEL_PATH
    config.AUTO_ADAPT_SILICONFLOW = AUTO_ADAPT_SILICONFLOW
    config.DEEPSEEK_API_KEY = DEEPSEEK_API_KEY
    config.DEEPSEEK_BASE_URL = DEEPSEEK_BASE_URL
    config.MODEL = MODEL
    config.MAX_TOKEN = MAX_TOKEN
    config.TEMPERATURE = TEMPERATURE
    config.MAX_GROUPS = MAX_GROUPS
    config.robot_wx_name = ""  # 添加机器人微信名称

# 导出所有配置变量
__all__ = [
    "config",
    "llm",
    "rag",
    "behavior",
    "user",
    "media",
    "EMBEDDING_MODEL",
    "EMBEDDING_FALLBACK_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "RAG_TOP_K",
    "RAG_IS_RERANK",
    "RAG_RERANKER_MODEL",
    "LOCAL_MODEL_ENABLED",
    "LOCAL_EMBEDDING_MODEL_PATH",
    "AUTO_ADAPT_SILICONFLOW",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "MODEL",
    "MAX_TOKEN",
    "TEMPERATURE",
    "MAX_GROUPS"
]

# 记录当前使用的配置
logger.info(f"使用嵌入模型: {EMBEDDING_MODEL}，备用模型: {EMBEDDING_FALLBACK_MODEL}")
logger.info(f"RAG配置: TOP_K={RAG_TOP_K}, 重排序={RAG_IS_RERANK}, 本地模型启用={LOCAL_MODEL_ENABLED}") 

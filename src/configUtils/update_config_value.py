"""
配置更新模块
提供更新配置值到正确位置的功能
"""
import logging
from typing import Dict, Any

# 获取日志记录器
logger = logging.getLogger(__name__)

def update_config_value(config_data, key, value):
    """更新配置值到正确的位置"""
    try:
        # 配置项映射表
        mapping = {
            'LISTEN_LIST': ['categories', 'user_settings', 'settings', 'listen_list', 'value'],
            'DEEPSEEK_BASE_URL': ['categories', 'llm_settings', 'settings', 'base_url', 'value'],
            'MODEL': ['categories', 'llm_settings', 'settings', 'model', 'value'],
            'DEEPSEEK_API_KEY': ['categories', 'llm_settings', 'settings', 'api_key', 'value'],
            'MAX_TOKEN': ['categories', 'llm_settings', 'settings', 'max_tokens', 'value'],
            'TEMPERATURE': ['categories', 'llm_settings', 'settings', 'temperature', 'value'],
            'MOONSHOT_API_KEY': ['categories', 'media_settings', 'settings', 'image_recognition', 'api_key', 'value'],
            'MOONSHOT_BASE_URL': ['categories', 'media_settings', 'settings', 'image_recognition', 'base_url', 'value'],
            'MOONSHOT_TEMPERATURE': ['categories', 'media_settings', 'settings', 'image_recognition', 'temperature', 'value'],
            'MOONSHOT_MODEL': ['categories', 'media_settings', 'settings', 'image_recognition', 'model', 'value'],
            'AUTO_MESSAGE': ['categories', 'behavior_settings', 'settings', 'auto_message', 'content', 'value'],
            'MIN_COUNTDOWN_HOURS': ['categories', 'behavior_settings', 'settings', 'auto_message', 'countdown', 'min_hours', 'value'],
            'MAX_COUNTDOWN_HOURS': ['categories', 'behavior_settings', 'settings', 'auto_message', 'countdown', 'max_hours', 'value'],
            'QUIET_TIME_START': ['categories', 'behavior_settings', 'settings', 'quiet_time', 'start', 'value'],
            'QUIET_TIME_END': ['categories', 'behavior_settings', 'settings', 'quiet_time', 'end', 'value'],
            'MAX_GROUPS': ['categories', 'behavior_settings', 'settings', 'context', 'max_groups', 'value'],
            'AVATAR_DIR': ['categories', 'behavior_settings', 'settings', 'context', 'avatar_dir', 'value'],
            'RAG_API_KEY': ['categories', 'rag_settings', 'settings', 'api_key', 'value'],
            'RAG_BASE_URL': ['categories', 'rag_settings', 'settings', 'base_url', 'value'],
            'RAG_EMBEDDING_MODEL': ['categories', 'rag_settings', 'settings', 'embedding_model', 'value'],
            'RAG_IS_RERANK': ['categories', 'rag_settings', 'settings', 'is_rerank', 'value'],
            'RAG_RERANKER_MODEL': ['categories', 'rag_settings', 'settings', 'reranker_model', 'value'],
            'RAG_TOP_K': ['categories', 'rag_settings', 'settings', 'top_k', 'value'],
            'AUTO_DOWNLOAD_LOCAL_MODEL': ['categories', 'rag_settings', 'settings', 'auto_download_local_model', 'value'],
            'AUTO_ADAPT_SILICONFLOW': ['categories', 'rag_settings', 'settings', 'auto_adapt_siliconflow', 'value']
        }
        
        # 数值类型配置项
        numeric_keys = {
            'MAX_TOKEN': int,
            'TEMPERATURE': float,
            'MOONSHOT_TEMPERATURE': float,
            'MIN_COUNTDOWN_HOURS': float,
            'MAX_COUNTDOWN_HOURS': float,
            'MAX_GROUPS': int,
            'RAG_TOP_K': int
        }
        
        if key in mapping:
            path = mapping[key]
            target = config_data
            
            # 遍历路径到倒数第二个元素
            for part in path[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            
            # 处理数值类型
            if key in numeric_keys:
                try:
                    value = numeric_keys[key](value)
                except (ValueError, TypeError):
                    logger.error(f"无法将{key}的值'{value}'转换为{numeric_keys[key].__name__}类型")
                    return
            
            # 设置最终值
            target[path[-1]] = value
            
    except Exception as e:
        logger.error(f"更新配置值时出错: {str(e)}") 
"""
记忆管理器 - 顶层接口
负责与主程序交互，管理记忆的初始化、调用等
"""
import os
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Union, Callable

# 导入中层记忆处理器
from src.handlers.memories.memory_processor import MemoryProcessor
from src.api_client.wrapper import APIWrapper

# 设置日志
logger = logging.getLogger('main')

# 全局变量
_initialized = False
_memory_processor = None

def _run_async(coro):
    """
    运行异步函数并返回结果
    
    Args:
        coro: 异步协程对象
        
    Returns:
        协程运行结果
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # 如果没有事件循环，创建一个新的
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        # 使用future来异步运行协程
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    else:
        # 直接运行协程
        return loop.run_until_complete(coro)

def init_memory(root_dir, api_wrapper=None):
    """
    初始化记忆系统
    
    Args:
        root_dir: 根目录路径
        api_wrapper: API调用封装器，可选
        
    Returns:
        memory_processor: 记忆处理器
    """
    global _initialized, _memory_processor
    
    if _initialized and _memory_processor:
        logger.info("记忆系统已初始化，重用现有实例")
        return _memory_processor
    
    try:
        # 从配置获取RAG设置
        from src.config import config, SettingReader
        # 不再使用rag_config，直接使用SettingReader
        config_reader = SettingReader()
        
        # 初始化记忆系统
        logger.info(f"初始化记忆系统，根目录: {root_dir}")
        
        # 如果api_wrapper为None，创建一个
        if api_wrapper is None:
            from src.api_client.wrapper import APIWrapper
            api_wrapper = APIWrapper(
                api_key=config_reader.llm.api_key,
                base_url=config_reader.llm.base_url
            )
        
        # 设置配置文件路径
        rag_config_path = os.path.join(root_dir, "src", "config", "config.yaml")
        
        # 检查配置文件是否存在
        if not os.path.exists(rag_config_path):
            logger.warning(f"RAG配置文件不存在: {rag_config_path}")
            
            # 尝试创建配置文件
            try:
                from src.handlers.memories.core.rag import create_default_config
                # 确保目录存在
                os.makedirs(os.path.dirname(rag_config_path), exist_ok=True)
                create_default_config(rag_config_path)
                logger.info(f"已创建默认RAG配置文件: {rag_config_path}")
                
                # 自定义配置
                import yaml
                with open(rag_config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                
                # 不再同步LLM的API配置到RAG配置
                # 使用默认的RAG配置
                
                # 保存修改后的配置
                with open(rag_config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
                
                logger.info(f"已保存RAG配置文件")
            except Exception as e:
                logger.error(f"创建RAG配置文件失败: {str(e)}")
        else:
            logger.info(f"找到RAG配置文件: {rag_config_path}")
        
        # 初始化内存处理器
        _memory_processor = MemoryProcessor(root_dir, api_wrapper, rag_config_path)
        _initialized = True
        
        return _memory_processor
    except Exception as e:
        logger.error(f"初始化记忆系统失败: {str(e)}", exc_info=True)
        # 创建一个默认的MemoryProcessor作为回退方案
        _memory_processor = MemoryProcessor(root_dir)
        return _memory_processor

# 记忆API - 同步版本
def remember(user_message, assistant_response, user_id=None):
    """
    记住对话内容 - 同步版本
    
    Args:
        user_message: 用户消息
        assistant_response: 助手回复
        user_id: 用户ID（可选）
        
    Returns:
        bool: 是否成功记住
    """
    global _memory_processor
    
    if not _memory_processor:
        logger.error("记忆处理器未初始化")
        return False
        
    try:
        # 移除"[当前用户问题]"标记
        if isinstance(user_message, str) and "[当前用户问题]" in user_message:
            user_message = user_message.replace("[当前用户问题]", "").strip()
            
        # 直接调用 MemoryProcessor.remember，修正参数顺序
        # 原错误调用: _memory_processor.remember(user_message, assistant_response, user_id)
        return _memory_processor.remember(user_id, user_message, assistant_response) # 修正后的调用
    except Exception as e:
        logger.error(f"调用remember方法时出错: {str(e)}")
        return False

# 检索API - 同步版本
def retrieve(query, top_k=5):
    """
    检索相关记忆 - 同步版本
    
    Args:
        query: 查询文本
        top_k: 返回结果数量
        
    Returns:
        str: 格式化的记忆文本
    """
    global _memory_processor
    
    if not _memory_processor:
        logger.error("记忆处理器未初始化")
        return ""
        
    try:
        return _memory_processor.retrieve(query, top_k)
    except Exception as e:
        logger.error(f"检索记忆失败: {str(e)}")
        return ""

# 重要性判断API - 同步版本
def is_important(text):
    """
    判断文本是否包含重要信息 - 同步版本
    
    Args:
        text: 需要判断的文本
        
    Returns:
        bool: 是否包含重要信息
    """
    global _memory_processor
    
    if not _memory_processor:
        logger.error("记忆处理器未初始化")
        return False
        
    try:
        # 直接调用，MemoryProcessor.is_important已改为同步方法
        return _memory_processor.is_important(text)
    except Exception as e:
        logger.error(f"判断文本重要性失败: {str(e)}")
        return False

# 获取记忆处理器实例
def get_memory_processor():
    """
    获取记忆处理器实例
    
    Returns:
        MemoryProcessor: 记忆处理器实例
    """
    global _memory_processor
    return _memory_processor

# 获取记忆统计信息
def get_memory_stats():
    """
    获取记忆统计信息
    
    Returns:
        dict: 包含记忆统计信息的字典
    """
    global _memory_processor
    
    if not _memory_processor:
        return {
            "memory_count": 0,
            "embedding_count": 0,
            "initialized": False
        }
    
    try:
        stats = _memory_processor.get_stats()
        stats["initialized"] = True
        return stats
    except Exception as e:
        logger.error(f"获取记忆统计失败: {str(e)}")
        return {
            "memory_count": getattr(_memory_processor, "memory_count", 0),
            "embedding_count": getattr(_memory_processor, "embedding_count", 0),
            "initialized": True
        }

# 清空记忆
def clear_memories():
    """
    清空所有记忆
    
    Returns:
        bool: 是否成功清空
    """
    global _memory_processor
    
    if not _memory_processor:
        logger.error("记忆处理器未初始化")
        return False
        
    return _memory_processor.clear_memories()

# 保存记忆
def save_memories():
    """
    保存所有记忆
    
    Returns:
        bool: 是否成功保存
    """
    global _memory_processor
    
    if not _memory_processor:
        logger.error("记忆处理器未初始化")
        return False
        
    return _memory_processor.save()

# 初始化RAG
def init_rag_from_config(config_path):
    """
    从配置文件初始化RAG系统
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        object: RAG实例
    """
    global _memory_processor
    
    if not _memory_processor:
        logger.error("记忆处理器未初始化")
        return None
        
    return _memory_processor.init_rag(config_path)

# 获取RAG实例
def get_rag():
    """
    获取RAG实例
    
    Returns:
        object: RAG实例
    """
    global _memory_processor
    
    if not _memory_processor:
        logger.error("记忆处理器未初始化")
        return None
        
    return _memory_processor.get_rag()

# 获取相关记忆
def get_relevant_memories(query, username=None, top_k=5):
    """
    获取相关记忆
    将检索结果转换为结构化格式
    
    Args:
        query: 查询文本
        username: 用户名（可选）
        top_k: 返回的记忆条数
        
    Returns:
        list: 相关记忆内容列表，每项包含message和reply
    """
    global _memory_processor
    
    if not _memory_processor:
        logger.error("记忆处理器未初始化")
        return []
    
    try:
        return _memory_processor.get_relevant_memories(query, username, top_k)
    except Exception as e:
        logger.error(f"获取相关记忆失败: {str(e)}")
        return [] 
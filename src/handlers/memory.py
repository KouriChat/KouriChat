"""
兼容层 - 旧接口的适配器
提供与原始内存系统兼容的API，适配新的模块化内存系统
"""
import os
import logging
import asyncio
import functools
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
from datetime import datetime

# 导入新的记忆模块
from src.handlers.handler_init import (
    setup_memory, remember, retrieve, is_important, 
    get_memory_handler, get_memory_stats, 
    clear_memories, save_memories, init_rag_from_config,
    setup_rag, get_rag
)
from src.api_client.wrapper import APIWrapper

# 设置日志
logger = logging.getLogger('main')

# 全局变量
_initialized = False
_memory_handler = None

# 在文件开头添加这三个类的定义，以确保它们在被引用前已定义
# SimpleEmbeddingModel类定义
class SimpleEmbeddingModel:
    """简单的嵌入模型模拟类，提供get_cache_stats方法"""
    def __init__(self):
        self._cache_hits = 0
        self._cache_misses = 0
        logging.getLogger('main').info("创建简单嵌入模型模拟类")
    
    def get_cache_stats(self):
        """获取缓存统计信息"""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total) * 100 if total > 0 else 0
        return {
            'cache_size': 0,
            'hit_rate_percent': hit_rate
        }

# SimpleRag类定义
class SimpleRag:
    """简单的RAG模拟类，提供基本的embedding_model属性"""
    def __init__(self):
        # 创建一个简单的模拟嵌入模型
        self.embedding_model = SimpleEmbeddingModel()
        logging.getLogger('main').info("创建简单RAG模拟类")

# FakeShortTermMemory类定义
class FakeShortTermMemory:
    """
    提供与short_term_memory兼容的接口的假类
    """
    def __init__(self, memory_handler):
        self.memory_handler = memory_handler
        self.rag = SimpleRag()  # 一个简单的RAG模拟
        logging.getLogger('main').info("创建假短期记忆类以兼容旧接口")
    
    def add_memory(self, user_id=None, memory_key=None, memory_value=None):
        """
        添加记忆
        
        Args:
            user_id: 用户ID
            memory_key: 记忆键
            memory_value: 记忆值
            
        Returns:
            bool: 是否成功添加
        """
        try:
            # 使用memory_handler的remember方法添加记忆
            logging.getLogger('main').info(f"通过假短期记忆类添加记忆 - 用户: {user_id}, 记忆键长度: {len(memory_key) if memory_key else 0}")
            return self.memory_handler.remember(memory_key, memory_value)
        except Exception as e:
            logging.getLogger('main').error(f"通过假短期记忆类添加记忆失败: {str(e)}")
            return False

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
        memory_handler: 记忆处理器
    """
    global _initialized, _memory_handler
    
    if _initialized and _memory_handler:
        logger.info("记忆系统已初始化，重用现有实例")
        return _memory_handler
    
    try:
        # 确保导入所需模块
        from src.handlers.memory import MemoryHandler
        from src.handlers.handler_init import setup_memory, init_rag_from_config
        
        # 从配置获取RAG设置
        from src.config import config, SettingReader
        # 不再使用rag_config，直接从config读取
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
        
        # 先初始化RAG系统（如果配置了）
        try:
            logger.info("尝试初始化RAG系统...")
            # 从配置初始化RAG
            rag_instance = init_rag_from_config(rag_config_path)
            if rag_instance:
                logger.info("成功初始化RAG系统")
                # 输出详细RAG配置，使用从config_reader读取的值
                embedding_model = config_reader.rag.embedding_model
                top_k = config_reader.rag.top_k
                is_rerank = config_reader.rag.is_rerank
                reranker_model = config_reader.rag.reranker_model
                local_model_enabled = config_reader.rag.local_model_enabled
                local_embedding_model_path = config_reader.rag.local_embedding_model_path
                
                logger.info(f"使用嵌入模型: {embedding_model}")
                logger.info(f"TopK: {top_k}, 是否重排序: {is_rerank}")
                if is_rerank and reranker_model:
                    logger.info(f"重排序模型: {reranker_model}")
                if local_model_enabled:
                    logger.info(f"使用本地嵌入模型: {local_embedding_model_path}")
            else:
                logger.info("将在记忆系统初始化过程中自动配置RAG")
        except Exception as e:
            logger.warning(f"初始化RAG系统时出错: {str(e)}，将使用基本记忆系统")
        
        # 初始化记忆系统
        _memory_handler = setup_memory(root_dir, api_wrapper)
        _initialized = True
        
        # 返回记忆处理器
        return _memory_handler
    except Exception as e:
        logger.error(f"初始化记忆系统失败: {str(e)}", exc_info=True)
        # 创建一个空的MemoryHandler作为回退方案
        _memory_handler = MemoryHandler(root_dir)
        return _memory_handler

# 兼容旧版MemoryHandler类
class MemoryHandler:
    """
    兼容层 - 原始MemoryHandler类
    适配新的记忆系统，保持接口兼容性
    """
    
    def __init__(self, root_dir=None, api_key=None, base_url=None, model=None, **kwargs):
        """
        初始化记忆处理器
        
        Args:
            root_dir: 根目录路径
            api_key: API密钥（可选）
            base_url: API基础URL（可选）
            model: 模型名称（可选，兼容旧代码）
            **kwargs: 其他参数（兼容性考虑）
        """
        self.root_dir = root_dir
        
        # 创建API包装器（如果提供了凭据）
        if api_key and base_url:
            self.api_wrapper = APIWrapper(
                api_key=api_key,
                base_url=base_url
            )
        else:
            self.api_wrapper = None
            
        # 内部状态
        self._initialized = False
        
        # 初始化其他属性
        self.memory_count = 0
        self.embedding_count = 0
        self.model = model  # 保存模型名称（兼容性考虑）
        
        # 尝试延迟初始化
        self._initialize()
        
    def _initialize(self):
        """
        延迟初始化功能
        """
        global _memory_handler
        
        try:
            if not self._initialized:
                # 如果全局实例已存在，使用它
                if _memory_handler:
                    logger.info("使用现有记忆处理器实例")
                    self._initialized = True
                    return
                
                # 否则初始化新实例
                if self.root_dir:
                    _memory_handler = init_memory(self.root_dir, self.api_wrapper)
                    
                    # 更新状态信息
                    stats = get_memory_stats()
                    self.memory_count = stats["memory_count"]
                    self.embedding_count = stats["embedding_count"]
                    
                    self._initialized = True
                    logger.info(f"记忆处理器初始化完成，记忆条数: {self.memory_count}")
                else:
                    logger.warning("无法初始化记忆处理器，未提供根目录")
        except Exception as e:
            logger.error(f"记忆处理器初始化失败: {str(e)}")
            
    # 同步版本
    def remember(self, user_message, assistant_response, user_id=None):
        """
        记住对话内容 - 同步版本
        
        Args:
            user_message: 用户消息
            assistant_response: 助手回复
            user_id: 用户ID（可选）
            
        Returns:
            bool: 是否成功记住
        """
        try:
            # 确保初始化
            if not self._initialized:
                self._initialize()
            
            # 移除"[当前用户问题]"标记
            if isinstance(user_message, str) and "[当前用户问题]" in user_message:
                user_message = user_message.replace("[当前用户问题]", "").strip()
            
            # 检查RAG系统并直接添加到RAG（避免重复添加）
            from src.handlers.handler_init import get_rag
            rag_instance = get_rag()
            
            # 移除对已不存在的ShortTermMemory的引用
            # 不再使用旧的ShortTermMemory
            
            # 运行异步函数
            # 从全局函数导入remember，确保正确处理user_id参数
            from src.handlers.handler_init import remember as global_remember
            return _run_async(global_remember(user_message, assistant_response, user_id))
        except Exception as e:
            logger.error(f"记住对话失败: {str(e)}")
            return False
    
    # 同步版本
    def retrieve(self, query, top_k=5):
        """
        检索记忆 - 同步版本
        
        Args:
            query: 查询文本
            top_k: 返回的记忆条数
            
        Returns:
            str: 格式化的记忆内容
        """
        try:
            # 确保初始化
            if not self._initialized:
                self._initialize()
                
            # 运行异步函数
            return _run_async(retrieve(query, top_k))
        except Exception as e:
            logger.error(f"检索记忆失败: {str(e)}")
            return ""
    
    # 同步版本
    def is_important(self, text):
        """
        检查文本是否包含重要关键词 - 同步版本
        
        Args:
            text: 要检查的文本
            
        Returns:
            bool: 是否需要长期记忆
        """
        try:
            # 确保初始化
            if not self._initialized:
                self._initialize()
                
            # 运行异步函数
            return _run_async(is_important(text))
        except Exception as e:
            logger.error(f"检查重要记忆失败: {str(e)}")
            return False
            
    def update_embeddings(self):
        """
        更新所有记忆的嵌入向量 - 同步版本
        """
        # 获取处理器
        handler = get_memory_handler()
        if handler:
            # 运行异步函数
            _run_async(handler.update_embedding_for_all())
            logger.info("记忆嵌入向量更新完成")
    
    # 兼容函数 - 添加短期记忆
    def add_short_memory(self, question, answer, user_id="default"):
        """
        添加短期记忆（兼容旧接口）
        
        Args:
            question: 用户问题
            answer: AI回复
            user_id: 用户ID
            
        Returns:
            bool: 是否成功添加
        """
        return self.remember(question, answer, user_id)
    
    # 兼容函数 - 获取相关记忆
    def get_relevant_memories(self, query, username=None, top_k=5):
        """
        获取相关记忆（兼容旧接口）
        
        Args:
            query: 查询文本
            username: 用户名（可选）
            top_k: 返回的记忆条数
            
        Returns:
            list: 相关记忆内容列表，包含message和reply
        """
        try:
            # 打印调试信息
            logger.info(f"获取相关记忆 - 查询: {query[:30]}..., 用户: {username}, TopK: {top_k}")
            
            # 确保初始化
            if not self._initialized:
                logger.info("记忆处理器未初始化，尝试初始化")
                self._initialize()
            
            # 检查当前实例是否可用
            if not hasattr(self, 'retrieve') or not callable(getattr(self, 'retrieve', None)):
                logger.warning("当前记忆处理器没有可用的retrieve方法，尝试使用全局记忆系统")
                
                # 尝试使用全局记忆系统
                global _memory_handler
                if _memory_handler and hasattr(_memory_handler, 'retrieve') and callable(_memory_handler.retrieve):
                    logger.info("使用全局记忆处理器的retrieve方法")
                    memories_text = _memory_handler.retrieve(query, top_k)
                else:
                    logger.error("全局记忆处理器也没有可用的retrieve方法")
                    return []
            else:
                # 使用当前实例的retrieve方法
                logger.info("使用当前记忆处理器的retrieve方法")
                memories_text = self.retrieve(query, top_k)
            
            # 检查结果
            if not memories_text or memories_text == "没有找到相关记忆":
                logger.info("没有找到相关记忆")
                return []
            
            # 记录原始返回内容
            logger.info(f"原始记忆文本: {memories_text[:100]}...")
                
            # 尝试解析格式为列表字典
            memories = []
            
            # 解析记忆文本并转换格式
            lines = memories_text.split('\n\n')
            for line in lines:
                if not line.strip():
                    continue
                    
                if line.startswith('相关记忆:'):
                    continue
                    
                parts = line.split('\n')
                if len(parts) >= 2:
                    user_part = parts[0].strip()
                    ai_part = parts[1].strip()
                    
                    # 提取用户消息和AI回复
                    user_msg = user_part[user_part.find(': ')+2:] if ': ' in user_part else user_part
                    ai_msg = ai_part[ai_part.find(': ')+2:] if ': ' in ai_part else ai_part
                    
                    # 添加到记忆列表
                    memories.append({
                        'message': user_msg,
                        'reply': ai_msg
                    })
            
            logger.info(f"解析出 {len(memories)} 条相关记忆")
            return memories
        except Exception as e:
            logger.error(f"获取记忆失败: {str(e)}", exc_info=True)
            # 返回空列表作为回退方案
            return []
    
    # 兼容函数 - 检查重要记忆
    def check_important_memory(self, text):
        """检查记忆是否重要 - 兼容方法"""
        try:
            from src.handlers.handler_init import is_important
            return is_important(text)
        except Exception as e:
            logger.error(f"检查记忆重要性失败: {str(e)}")
            return False
    
    # 兼容函数 - 生成记忆摘要
    def summarize_memories(self, limit=20):
        """总结记忆 - 模拟方法"""
        logger.warning("summarize_memories方法已弃用，返回空结果")
        return []
    
    # 兼容函数 - 清理记忆内容
    def clean_memory_content(self, memory_key, memory_value):
        """清理记忆内容 - 兼容方法"""
        try:
            # 导入原始函数
            from src.handlers.memories.core.memory_utils import clean_memory_content
            
            # 调用函数
            return clean_memory_content(memory_key, memory_value)
        except Exception as e:
            logger.error(f"清理记忆内容失败: {str(e)}")
            
            # 如果导入失败，提供一个简单的实现
            def simple_clean(text):
                if not text:
                    return ""
                return text.strip()
                
            return simple_clean(memory_key), simple_clean(memory_value)
            
    # 修改short_term_memory属性
    @property
    def short_term_memory(self):
        """获取短期记忆处理器"""
        try:
            # 获取记忆处理器
            handler = get_memory_handler()
            if handler and hasattr(handler, 'short_term_memory'):
                return handler.short_term_memory
                
            # 如果handler不存在或没有short_term_memory属性
            logger.warning("短期记忆处理器不可用，使用假短期记忆类作为回退")
            if not hasattr(self, '_fake_short_term_memory'):
                # 从全局类中创建
                self._fake_short_term_memory = FakeShortTermMemory(self)
            return self._fake_short_term_memory
        except Exception as e:
            logger.error(f"获取短期记忆处理器失败: {str(e)}")
            if not hasattr(self, '_fake_short_term_memory'):
                # 从全局类中创建
                self._fake_short_term_memory = FakeShortTermMemory(self)
            return self._fake_short_term_memory
            
    # 为兼容添加add_memory方法
    def add_memory(self, key, value, user_id=None):
        """
        添加记忆（兼容short_term_memory.add_memory）
        
        Args:
            key: 用户消息
            value: 助手回复
            user_id: 用户ID（必需）
            
        Returns:
            bool: 是否成功添加
        """
        try:
            if not user_id:
                logger.error("添加记忆失败：未提供用户ID")
                return False
            
            logger.info(f"添加记忆 - 用户消息长度: {len(key)}, 回复长度: {len(value)}, 用户ID: {user_id}")
            
            # 使用记忆处理器添加记忆
            success = self._memory_processor.add_memory(user_id, key, value)
            
            if success:
                logger.info(f"已成功添加记忆到用户 {user_id} 的存储")
            
            return success
        except Exception as e:
            logger.error(f"添加记忆失败: {str(e)}", exc_info=True)
            return False
    
    def save(self):
        """
        保存记忆数据
        """
        save_memories()
        
    def clear(self):
        """
        清空所有记忆
        """
        clear_memories()

# 为了向后兼容性导出这些函数和类
__all__ = [
    'init_memory', 'MemoryHandler',
    'remember', 'retrieve', 'is_important',
    'save_memories', 'clear_memories'
] 
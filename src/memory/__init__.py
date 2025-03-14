from .core.memory import Memory
from .core.rag import RAG, EmbeddingModel, ReRanker
import logging

_memory_instance = None
_rag_instance = None
_rag_settings = None
_memory_setting = None

logger = logging.getLogger('main')


def setup_rag(embedding_model: EmbeddingModel, reranker: ReRanker = None):
    """
    设置 RAG 所需的配置
    :param embedding_model: 嵌入模型
    :param reranker: 重排模型
    """
    global _rag_settings
    _rag_settings = {
        "embedding": embedding_model,
        "reranker": reranker
    }


def setup_memory(memory_path: str):
    """
    设置 Memory 需要的配置
    :param memory_path: 记忆文件路径
    """
    global _memory_setting
    _memory_setting = {
        "path": memory_path
    }


def get_memory():
    """
    获取 Memory 单例实例
    """
    global _memory_instance, _memory_setting
    if _memory_instance is None:
        if _memory_setting is None:
            raise RuntimeError("Please call setup() first to initialize settings")
        _memory_instance = Memory(config_path=_memory_setting['path'])
    return _memory_instance


def get_rag() -> RAG:
    """
    获取 RAG 单例实例
    """
    global _rag_instance, _rag_settings
    if _rag_instance is None:
        if _rag_settings is None:
            raise RuntimeError("Please call setup() first to initialize settings")
        _rag_instance = RAG(
            embedding_model=_rag_settings['embedding'],
            reranker=_rag_settings['reranker']
        )
    return _rag_instance


def start_memory():
    try:
        # 重置RAG实例，确保使用最新配置
        global _rag_instance
        _rag_instance = None
        
        logger.info("正在初始化记忆系统...")
        rag = get_rag()
        memory = get_memory()

        memory_pairs = memory.get_key_value_pairs()
        if memory_pairs is not None and len(memory_pairs) > 0:
            try:
                logger.info(f"正在加载 {len(memory_pairs)} 条记忆到RAG索引...")
                rag.add_documents(memory_pairs)
                logger.info("记忆加载完成")
            except Exception as e:
                logger.error(f"加载记忆文档到RAG索引失败: {str(e)}")
        else:
            logger.info("没有找到现有记忆，将从空记忆开始")

        @memory.add_memory_hook
        def hook(key, value):
            # 这里是在记忆文档增加时，对rag内部文档进行增量维护（添加新的文档）
            try:
                # 使用简洁的日志，避免每次添加记忆都产生大量输出
                logger.debug(f"正在添加新记忆到RAG索引: {key[:30]}...")
                rag.add_documents([f"{key}:{value}"])
            except Exception as e:
                logger.error(f"添加新记忆到RAG索引失败: {str(e)}")
                
        logger.info("记忆系统初始化完成")
    except Exception as e:
        logger.error(f"启动记忆系统失败: {str(e)}")
        logger.warning("程序将继续运行，但记忆检索功能可能不可用")

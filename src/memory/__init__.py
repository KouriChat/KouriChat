from .core.memory import Memory
from .core.rag import RAG, EmbeddingModel, ReRanker

_memory_instance = None
_rag_instance = None
_rag_settings = None
_memory_setting = None


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
    rag = get_rag()
    memory = get_memory()

    if memory.get_key_value_pairs() is not None:
        rag.add_documents(memory.get_key_value_pairs())

    @memory.add_memory_hook
    def hook(key, value):
        # 这里是在记忆文档增加时，对rag内部文档进行增量维护（添加新的文档）
        rag.add_documents([f"{key}:{value}"])

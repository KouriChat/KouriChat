from src.memories.memory import *
from src.memories.memory.core.rag import ReRanker, EmbeddingModel

class ShortTermMemory:
    _instance = None
    
    @classmethod
    def get_instance(cls, memory_path=None, embedding_model=None, reranker=None, force_new=False):
        """
        获取单例实例
        :param memory_path: 记忆路径
        :param embedding_model: 嵌入模型
        :param reranker: 重排序器
        :param force_new: 是否强制创建新实例
        :return: ShortTermMemory实例
        """
        if force_new or cls._instance is None:
            if memory_path is not None and embedding_model is not None:
                instance = cls(memory_path, embedding_model, reranker)
                if not force_new:
                    cls._instance = instance
                return instance
            elif cls._instance is None:
                raise ValueError("首次创建实例需要提供所有必要参数")
        return cls._instance
    
    def __init__(self, memory_path: str, embedding_model: EmbeddingModel, reranker: ReRanker = None):
        setup_memory(memory_path)
        # 修复参数顺序：先传递embedding_model，再传reranker
        setup_rag(embedding_model, reranker)  # 修改此处
        self.memory = get_memory()
        self.rag = get_rag()

        if self.memory.settings is not None:
            self.rag.add_documents(self.memory.settings)

        self._handle_save_memory = None
        self._handle_start_hook = None
    
    def handle_save_memory(self, func):
        """
        这个方法用于绑定保存记忆的函数
        """
        self._handle_save_memory = func

    def save_memory(self):
        """
        这个方法用于保存记忆
        """
        if self._handle_save_memory:
            self._handle_save_memory(lambda: (self.memory.save(), self.rag.save()))
        else:
            self.memory.save()
            self.rag.save()
    
    def add_start_hook(self, func):
        """
        这个方法用于绑定开始记忆的钩子
        """
        self._handle_start_hook = func
    
    def start_memory(self):
        """
        这个方法用于开始记忆文档维护
        """
        if self._handle_start_hook:
            self._handle_start_hook()
        start_memory()

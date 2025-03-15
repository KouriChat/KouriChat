from typing import List

from src.memories.memory_saver import MemorySaver

class KeyMemory:
    _instance = None
    
    @classmethod
    def get_instance(cls, saver=None, force_new=False):
        """
        获取单例实例
        :param saver: 记忆保存器接口
        :param force_new: 是否强制创建新实例
        :return: KeyMemory实例
        """
        if force_new or cls._instance is None:
            if saver is not None:
                instance = cls(saver)
                if not force_new:
                    cls._instance = instance
                return instance
            elif cls._instance is None:
                raise ValueError("首次创建实例需要提供所有必要参数")
        return cls._instance
    
    def __init__(self, saver: MemorySaver):
        self.saver = saver
        self.memories = self.saver.load()

    def add_memory(self, memory: str):
        self.saver.add(memory)
        self.memories.append(memory)
    
    def get_memory(self) -> List[str]:
        return self.memories

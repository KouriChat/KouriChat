from typing import List
from src.memories.memory_saver import MemorySaver
from src.services.ai.llms.base_llm import BaseLLM
"""
此文件依赖于eliver的lib中 BaseLLM 类
"""

class LongTermMemory:
    _instance = None
    
    @classmethod
    def get_instance(cls, saver=None, llm=None, memory_handle_prompt=None, is_increment=True, force_new=False):
        """
        获取单例实例
        :param saver: 记忆保存器接口
        :param llm: 大模型（用于处理记忆）
        :param memory_handle_prompt: 记忆处理提示词
        :param is_increment: 是否增量保存记忆
        :param force_new: 是否强制创建新实例
        :return: LongTermMemory实例
        """
        if force_new or cls._instance is None:
            if saver is not None and llm is not None and memory_handle_prompt is not None:
                instance = cls(saver, llm, memory_handle_prompt, is_increment)
                if not force_new:
                    cls._instance = instance
                return instance
            elif cls._instance is None:
                raise ValueError("首次创建实例需要提供所有必要参数")
        return cls._instance
    
    def __init__(
            self, 
            saver: MemorySaver, 
            llm: BaseLLM, 
            memory_handle_prompt: str, 
            is_increment: bool = True
            ):
        """
        初始化长期记忆
        :param saver: 记忆保存器接口
        :param llm: 大模型（用于处理记忆）
        :param memory_handle_prompt: 记忆处理提示词
        :param is_increment: 是否增量保存记忆
        """
        self.saver = saver
        self.is_increment = is_increment
        self.memories = []
        self.memories = self.saver.load()
        self.llm = llm
        self.memory_handle_prompt = memory_handle_prompt
    
    def get_memories(self) -> List[str]:
        return self.memories
    
    def add_memory(self, memories: List[str]):
        """
        用于增量增加记忆
        :param memories: 需要添加的记忆列表
        """
        add_memory = self.llm.generate_response(
            {
                "system": self.memory_handle_prompt,
                "user": ";".join(memories)
            }
        )
        self.memories.append(add_memory)
        self.saver.add(add_memory)

    def save_memory(self, memories: List[str]):
        """
        用于保存记忆
        :param memories: 需要保存的记忆列表
        """
        add_memory = self.llm.generate_response(
            {
                "system": self.memory_handle_prompt,
                "user": ";".join(memories + self.memories)
                # 这里需要将需要保存的记忆和已经保存的记忆拼接起来，然后再次总结处理
            }
        )
        self.memories = add_memory
        self.saver.add(add_memory)

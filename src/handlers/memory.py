import os
import logging
from typing import List
from services.ai.deepseek import DeepSeekAI
from datetime import datetime
logger = logging.getLogger(__name__)


class MemoryHandler:
    def __init__(self, root_dir: str, api_key: str, base_url: str, model:str,max_token: int, temperature: float, max_groups: int):

        self.root_dir = root_dir
        self.memory_dir = os.path.join(root_dir, "data", "memory")
        self.short_memory_path = os.path.join(self.memory_dir, "short_memory.txt.txt")
        self.long_memory_buffer_path = os.path.join(self.memory_dir, "long_memory_buffer.txt")
        self.api_key = api_key
        self.base_url = base_url
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        self.model = model
        os.makedirs(self.memory_dir, exist_ok=True)

    def _get_deepseek_client(self):
        """使用DeepSeekAI替代OpenAI客户端"""
        return DeepSeekAI(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
            max_token=self.max_token,
            temperature=self.temperature,
            max_groups=self.max_groups
        )

    def add_short_memory(self, message: str, reply: str):
        """添加短期记忆"""
        with open(self.short_memory_path, "a", encoding="utf-8") as f:
            f.write(f"用户: {message}\n")
            f.write(f"bot: {reply}\n\n")

    def summarize_memories(self):
        """总结短期记忆到长期记忆"""
        if not os.path.exists(self.short_memory_path):
            return

        with open(self.short_memory_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if len(lines) >= 2:  # 15组对话
            try:
                deepseek = self._get_deepseek_client()
                summary = deepseek.get_response(
                    message="".join(lines[-30:]),
                    user_id="system",
                    system_prompt="请将以下对话记录总结为最重要的3条长期记忆，用中文简要表述："
                )
                logger.debug(f"总结结果:\n{summary}")

                with open(self.long_memory_buffer_path, "a", encoding="utf-8") as f:
                    f.write(f"总结时间: {datetime.now()}\n")
                    f.write(summary + "\n\n")

                # 清空短期记忆
                open(self.short_memory_path, "w").close()

            except Exception as e:
                logger.error(f"记忆总结失败: {str(e)}")

    def get_relevant_memories(self, query: str) -> List[str]:
        """获取相关记忆（增加空值检查和日志）"""
        if not os.path.exists(self.long_memory_buffer_path):
            logger.warning("长期记忆缓冲区不存在")
            return []

        try:
            with open(self.long_memory_buffer_path, "r", encoding="utf-8") as f:
                memories = [line.strip() for line in f if line.strip()]

            if not memories:
                logger.debug("长期记忆缓冲区为空")
                return []

            # 调用API时增加超时和重试机制
            deepseek = self._get_deepseek_client()
            response = deepseek.get_response(
                message="\n".join(memories[-20:]),
                user_id="retrieval",
                system_prompt=f"请从以下记忆中找到与'{query}'最相关的条目，按相关性排序返回最多3条:"
            )
            return [line.strip() for line in response.split("\n") if line.strip()]

        except Exception as e:
            logger.error(f"记忆检索失败: {str(e)}")
            return []
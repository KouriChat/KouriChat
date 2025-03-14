import os
import logging
import random
from typing import List, Optional, Dict  # 添加 Dict 导入
from datetime import datetime
from src.services.ai.llm_service import LLMService
import jieba
import re
from src.handlers.emotion import SentimentResourceLoader, SentimentAnalyzer
import json
from src.memory import *
from src.memory.core.rag import OnlineEmbeddingModel, OnlineCrossEncoderReRanker

logger = logging.getLogger('main')

# 定义需要重点关注的关键词列表
KEYWORDS = [
    "记住了没？", "记好了", "记住", "别忘了", "牢记", "记忆深刻", "不要忘记", "铭记",
    "别忘掉", "记在心里", "时刻记得", "莫失莫忘", "印象深刻", "难以忘怀", "念念不忘", "回忆起来",
    "永远不忘", "留意", "关注", "提醒", "提示", "警示", "注意", "特别注意",
    "记得检查", "请记得", "务必留意", "时刻提醒自己", "定期回顾", "随时注意", "不要忽略", "确认一下",
    "核对", "检查", "温馨提示", "小心"
]


class MemoryHandler:
    def __init__(self, root_dir: str, api_key: str, base_url: str, model: str,
                 max_token: int, temperature: float, max_groups: int,
                 bot_name: str = None, sentiment_analyzer: SentimentAnalyzer = None):
        # 基础参数
        self.root_dir = root_dir
        self.api_key = api_key
        self.base_url = base_url
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        self.model = model

        # 从config模块获取配置
        from src.config import config
        self.bot_name = bot_name or config.robot_wx_name
        self.listen_list = config.user.listen_list

        # 记忆目录结构
        self.memory_base_dir = os.path.join(root_dir, "data", "memory")
        os.makedirs(self.memory_base_dir, exist_ok=True)

        # 初始化每个用户的记忆文件
        for user_id in self.listen_list:
            if user_id:  # 确保用户ID不为空
                self._init_user_files(user_id)

        # 初始化Rag记忆的方法
        setup_memory(os.path.join(self.memory_base_dir, "rag-memory.json"))
        setup_rag(
            embedding_model=OnlineEmbeddingModel(
                api_key=config.rag.api_key,
                base_url=config.rag.base_url,
                model_name=config.rag.embedding_model
            ),
            reranker=OnlineCrossEncoderReRanker(
                api_key=config.rag.api_key,
                base_url=config.rag.base_url,
                model_name=config.rag.reranker_model
            ) if config.rag.is_rerank is True else None
        )
        self.is_rerank = config.rag.is_rerank
        self.top_k = config.rag.top_k
        start_memory()

    # 删除不需要的方法
    def _load_config(self):
        """此方法不再需要"""
        pass

    def _get_robot_name_from_config(self):
        """此方法不再需要"""
        pass

    def _get_listen_list_from_config(self):
        """此方法不再需要"""
        pass

    def _get_memory_paths(self, user_id: str) -> tuple:
        """获取用户的所有记忆文件路径"""
        user_dir = self._get_user_memory_dir(user_id)
        return (
            os.path.join(user_dir, "short_memory.txt"),
            os.path.join(user_dir, "long_memory_buffer.txt"),
            os.path.join(user_dir, "important_memory.txt")  # 修改文件名
        )

    def add_short_memory(self, message: str, reply: str, user_id: str):
        """添加短期记忆"""
        # 移除或修改这个检查，因为可能有些用户ID不在listen_list中
        # if not user_id or user_id not in self.listen_list:
        if not user_id:
            logger.error(f"无效的用户ID: {user_id}")
            return

        try:
            self._ensure_memory_files(user_id)
            short_memory_path, _, _ = self._get_memory_paths(user_id)

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 写入记忆 - 修改格式：将"用户"改为"对方"，"bot"改为"你"
            memory_content = (
                f"[{timestamp}] 对方: {message}\n"
                f"[{timestamp}] 你: {reply}\n\n"
            )

            # 将记忆写入Rag记忆
            get_memory()[f"[{timestamp}] 对方: {message}"] = f"[{timestamp}] 你: {reply}"
            get_memory().save_config()

            try:
                with open(short_memory_path, "a", encoding="utf-8") as f:
                    f.write(memory_content)
                logger.info(f"成功写入短期记忆: {user_id}")
                print(f"控制台日志: 成功写入短期记忆 - 用户ID: {user_id}")
            except Exception as e:
                logger.error(f"写入短期记忆失败: {str(e)}")
                print(f"控制台日志: 写入短期记忆失败 - 用户ID: {user_id}, 错误: {str(e)}")
                return

            # 检查关键词并添加重要记忆
            if any(keyword in message for keyword in KEYWORDS):
                self._add_important_memory(message, user_id)

        except Exception as e:
            logger.error(f"添加短期记忆失败: {str(e)}")
            print(f"控制台日志: 添加短期记忆失败 - 用户ID: {user_id}, 错误: {str(e)}")

    def _add_important_memory(self, message: str, user_id: str):
        """添加重要记忆"""
        if not user_id:
            raise ValueError("用户ID不能为空")

        try:
            _, _, important_memory_path = self._get_memory_paths(user_id)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            memory_content = f"[{timestamp}] 重要记忆: {message}\n"

            # 写入Rag记忆
            get_memory()[f"{timestamp} 重要记忆"] = f"[{timestamp}] 重要记忆: {message}"
            get_memory().save_config()

            with open(important_memory_path, "a", encoding="utf-8") as f:
                f.write(memory_content)
            logger.info(f"成功写入重要记忆: {user_id}")
            print(f"控制台日志: 成功写入重要记忆 - 用户ID: {user_id}")
        except Exception as e:
            logger.error(f"写入重要记忆失败: {str(e)}")
            print(f"控制台日志: 写入重要记忆失败 - 用户ID: {user_id}, 错误: {str(e)}")

    def _ensure_memory_files(self, user_id: str):
        """确保用户的记忆文件存在"""
        try:
            # 获取所有记忆文件路径
            short_memory_path, long_memory_buffer_path, important_memory_path = self._get_memory_paths(user_id)

            # 确保用户目录存在
            user_dir = os.path.dirname(short_memory_path)
            os.makedirs(user_dir, exist_ok=True)

            # 检查并创建所有必要的文件
            for file_path in [short_memory_path, long_memory_buffer_path, important_memory_path]:
                if not os.path.exists(file_path):
                    with open(file_path, 'w', encoding='utf-8') as f:
                        pass  # 创建空文件
                    logger.info(f"创建记忆文件: {file_path}")

            return True
        except Exception as e:
            logger.error(f"确保记忆文件存在时出错: {str(e)}")
            return False

    def get_relevant_memories(self, query: str, user_id: Optional[str] = None) -> List[str]:
        """获取相关记忆，只在用户主动询问时检索重要记忆和长期记忆"""
        if user_id is None and self.listen_list:
            user_id = self.listen_list[0]

        if not user_id:
            logger.error("无效的用户ID")
            return []

        _, long_memory_buffer_path, important_memory_path = self._get_memory_paths(user_id)

        memories = []

        # 检查查询是否与重要记忆相关
        if any(keyword in query for keyword in KEYWORDS):
            try:
                with open(important_memory_path, "r", encoding="utf-8") as f:
                    important_memories = [line.strip() for line in f if line.strip()]
                    memories.extend(important_memories)
                logger.debug(f"检索到用户 {user_id} 的重要记忆: {len(important_memories)} 条")
            except Exception as e:
                logger.error(f"读取重要记忆失败: {str(e)}")

        # 检查查询是否明确要求查看长期记忆
        if "长期记忆" in query or "日记" in query:
            try:
                with open(long_memory_buffer_path, "r", encoding="utf-8") as f:
                    long_memories = [line.strip() for line in f if line.strip()]
                    memories.extend(long_memories)
                logger.debug(f"检索到用户 {user_id} 的长期记忆: {len(long_memories)} 条")
            except Exception as e:
                logger.error(f"读取长期记忆失败: {str(e)}")

        # Rag向量查询
        memories += get_rag().query(query, self.top_k, self.is_rerank)

        return memories

    def summarize_daily_memory(self, user_id: str):
        """将短期记忆总结为日记式的长期记忆"""
        try:
            short_memory_path, long_memory_buffer_path, _ = self._get_memory_paths(user_id)

            # 读取当天的短期记忆
            today = datetime.now().strftime('%Y-%m-%d')
            today_memories = []

            with open(short_memory_path, "r", encoding="utf-8") as f:
                for line in f:
                    if today in line:
                        today_memories.append(line.strip())

            if not today_memories:
                return

            # 生成日记式总结
            summary = f"\n[{today}] 今天的对话回顾：\n"
            summary += "我们聊了很多话题。" if len(today_memories) > 10 else "我们简单交谈了几句。"

            # 记录重要的对话内容
            important_topics = []
            for memory in today_memories:
                if any(keyword in memory for keyword in KEYWORDS):
                    content = memory.split("]:", 1)[1].strip() if "]" in memory else memory
                    important_topics.append(content)

            if important_topics:
                summary += "\n特别记住了以下内容：\n"
                summary += "\n".join(f"- {topic}" for topic in important_topics)

            # 写入长期记忆
            with open(long_memory_buffer_path, "a", encoding="utf-8") as f:
                f.write(f"{summary}\n\n")

            # 写入Rag记忆
            get_memory()[f"用户{user_id}的{today} 日常总结"] = summary
            get_memory().save_config()

            logger.info(f"成功生成用户 {user_id} 的每日记忆总结")

        except Exception as e:
            logger.error(f"生成记忆总结失败: {str(e)}")

    def _get_user_memory_dir(self, user_id: str) -> str:
        """获取特定用户的记忆目录路径"""
        # 创建层级目录结构: data/memory/{bot_name}/{user_id}/
        bot_memory_dir = os.path.join(self.memory_base_dir, self.bot_name)
        user_memory_dir = os.path.join(bot_memory_dir, user_id)

        # 确保目录存在
        try:
            os.makedirs(bot_memory_dir, exist_ok=True)
            os.makedirs(user_memory_dir, exist_ok=True)
            logger.debug(f"确保用户记忆目录存在: {user_memory_dir}")
        except Exception as e:
            logger.error(f"创建用户记忆目录失败 {user_memory_dir}: {str(e)}")

        return user_memory_dir

    def _init_user_files(self, user_id: str):
        """初始化用户的记忆文件"""
        try:
            short_memory_path, long_memory_buffer_path, important_memory_path = self._get_memory_paths(user_id)

            files_to_check = [short_memory_path, long_memory_buffer_path, important_memory_path]
            for f in files_to_check:
                if not os.path.exists(f):
                    try:
                        with open(f, "w", encoding="utf-8") as _:
                            logger.info(f"为用户 {user_id} 创建文件: {os.path.basename(f)}")
                    except Exception as file_e:
                        logger.error(f"创建记忆文件失败 {f}: {str(file_e)}")
        except Exception as e:
            logger.error(f"初始化用户文件失败 {user_id}: {str(e)}")

    def get_recent_memory(self, user_id: str, max_count: int = 5) -> List[Dict[str, str]]:
        """获取最近的对话记录"""
        try:
            # 使用正确的路径获取方法
            short_memory_path, _, _ = self._get_memory_paths(user_id)
            if not os.path.exists(short_memory_path):
                return []

            with open(short_memory_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            history = []
            current_pair = {}

            # 从后往前读取，获取最近的对话
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("[") and "] 对方:" in line:
                    current_pair["message"] = line.split("] 对方:", 1)[1].strip()
                    if "reply" in current_pair:
                        history.append(current_pair)
                        current_pair = {}
                        if len(history) >= max_count:
                            break
                elif line.startswith("[") and "] 你:" in line:
                    current_pair["reply"] = line.split("] 你:", 1)[1].strip()
                # 兼容旧格式
                elif line.startswith("[") and "] 用户:" in line:
                    current_pair["message"] = line.split("] 用户:", 1)[1].strip()
                    if "reply" in current_pair:
                        history.append(current_pair)
                        current_pair = {}
                        if len(history) >= max_count:
                            break
                elif line.startswith("[") and "] bot:" in line:
                    current_pair["reply"] = line.split("] bot:", 1)[1].strip()

            # 确保顺序是从早到晚
            return list(reversed(history))

        except Exception as e:
            logger.error(f"获取记忆失败: {str(e)}")
            return []

    def get_rag_memories(self, content):
        """获取Rag记忆"""
        rag = get_rag()
        logger.info(f"rag文档总数：{len(rag.documents)}")
        res = rag.query(content, self.top_k, self.is_rerank)
        return res

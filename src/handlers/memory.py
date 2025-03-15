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
from src.memory import get_rag, setup_memory, setup_rag, start_memory, get_memory
from src.memory.core.rag_memory import RAGMemory
from src.memory.core.rag import OnlineEmbeddingModel, OnlineCrossEncoderReRanker
import openai

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
        
        # 检查嵌入模型名称是否为空
        embedding_model_name = config.rag.embedding_model
        if not embedding_model_name:
            # 如果嵌入模型名称为空，使用默认值
            embedding_model_name = "text-embedding-3-large"
            logger.info(f"嵌入模型名称为空，使用默认值: {embedding_model_name}")
        else:
            logger.info(f"使用配置的嵌入模型: {embedding_model_name}")
            
        # 检查重排序模型名称是否为空
        reranker_model_name = config.rag.reranker_model
        if config.rag.is_rerank and not reranker_model_name:
            # 如果重排序模型名称为空，使用默认值
            reranker_model_name = "gpt-3.5-turbo"
            logger.info(f"重排序模型名称为空，使用默认值: {reranker_model_name}")
        elif config.rag.is_rerank:
            logger.info(f"使用配置的重排序模型: {reranker_model_name}")
            
        setup_rag(
            embedding_model=OnlineEmbeddingModel(
                api_key=config.rag.api_key,
                base_url=config.rag.base_url,
                model_name=embedding_model_name
            ),
            reranker=OnlineCrossEncoderReRanker(
                api_key=config.rag.api_key,
                base_url=config.rag.base_url,
                model_name=reranker_model_name
            ) if config.rag.is_rerank is True else None
        )
        self.is_rerank = config.rag.is_rerank
        self.top_k = config.rag.top_k
        start_memory()
        
        # 新增：用户名映射字典，用于群聊中识别用户
        self.user_name_mapping = {}
        # 新增：群聊用户记忆缓存
        self.group_user_memory_cache = {}

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

    def _get_memory_paths(self, user_id: str, group_id: str = None, sender_name: str = None) -> tuple:
        """获取用户的所有记忆文件路径
        
        Args:
            user_id: 用户ID，可以是个人ID或群ID
            group_id: 群ID，如果是群聊则提供
            sender_name: 发送者名称，如果是群聊中的用户则提供
            
        Returns:
            包含短期记忆、长期记忆和重要记忆文件路径的元组
        """
        # 如果是群聊中的个人消息
        if group_id and sender_name:
            # 创建群聊用户的唯一标识
            group_user_id = f"{group_id}_{sender_name}"
            
            # 记录用户名映射
            if group_id not in self.user_name_mapping:
                self.user_name_mapping[group_id] = {}
            self.user_name_mapping[group_id][sender_name] = group_user_id
            
            # 获取群聊用户的记忆目录
            user_dir = self._get_group_user_memory_dir(group_id, sender_name)
        else:
            # 个人聊天
            user_dir = self._get_user_memory_dir(user_id)
            
        return (
            os.path.join(user_dir, "short_memory.txt"),
            os.path.join(user_dir, "long_memory_buffer.txt"),
            os.path.join(user_dir, "important_memory.txt")
        )

    def add_short_memory(self, message: str, reply: str, user_id: str, group_id: str = None, sender_name: str = None):
        """添加短期记忆
        
        Args:
            message: 用户消息
            reply: 机器人回复
            user_id: 用户ID或群ID
            group_id: 群ID，如果是群聊则提供
            sender_name: 发送者名称，如果是群聊中的用户则提供
        """
        # 检查用户ID是否有效
        if not user_id:
            logger.error(f"无效的用户ID: {user_id}")
            return

        try:
            # 确保记忆文件存在
            self._ensure_memory_files(user_id, group_id, sender_name)
            
            # 获取记忆文件路径
            short_memory_path, _, _ = self._get_memory_paths(user_id, group_id, sender_name)

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 写入记忆 - 简化格式，只保留时间戳和对话双方身份
            memory_content = (
                f"[{timestamp}] 对方: {message}\n"
                f"[{timestamp}] 你: {reply}\n\n"
            )

            # 构建记忆键，只保留时间戳和对方标识，剔除所有提示词
            memory_key = f"[{timestamp}] 对方: {message}"
            
            # 将记忆写入Rag记忆
            get_memory()[memory_key] = f"[{timestamp}] 你: {reply}"
            get_memory().save_config()

            try:
                with open(short_memory_path, "a", encoding="utf-8") as f:
                    f.write(memory_content)
                logger.debug(f"成功写入短期记忆: {user_id}{' (群聊用户: '+sender_name+')' if group_id and sender_name else ''}")
            except Exception as e:
                logger.error(f"写入短期记忆失败: {str(e)}")
                return

        except Exception as e:
            logger.error(f"添加短期记忆失败: {str(e)}")

    def _ensure_memory_files(self, user_id: str, group_id: str = None, sender_name: str = None):
        """确保用户的记忆文件存在"""
        try:
            # 获取所有记忆文件路径
            short_memory_path, long_memory_buffer_path, important_memory_path = self._get_memory_paths(user_id, group_id, sender_name)

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

    def get_relevant_memories(self, query: str, user_id: Optional[str] = None, group_id: str = None, sender_name: str = None) -> List[str]:
        """获取相关记忆
        
        Args:
            query: 查询内容
            user_id: 用户ID或群ID
            group_id: 群ID，如果是群聊则提供
            sender_name: 发送者名称，如果是群聊中的用户则提供
            
        Returns:
            相关记忆列表
        """
        if user_id is None and self.listen_list:
            user_id = self.listen_list[0]

        if not user_id:
            logger.error("无效的用户ID")
            return []

        # 检查是否是时间相关查询
        if self._is_time_related_query(query):
            logger.info("检测到时间相关查询，优先返回时间记忆")
            time_memories = self._get_time_related_memories(user_id, group_id, sender_name)
            if time_memories:
                return time_memories

        _, long_memory_buffer_path, important_memory_path = self._get_memory_paths(user_id, group_id, sender_name)

        memories = []

        # 检查查询是否明确要求查看长期记忆
        if "长期记忆" in query or "日记" in query:
            try:
                with open(long_memory_buffer_path, "r", encoding="utf-8") as f:
                    long_memories = [line.strip() for line in f if line.strip()]
                    memories.extend(long_memories)
                logger.debug(f"检索到用户 {user_id}{' (群聊用户: '+sender_name+')' if group_id and sender_name else ''} 的长期记忆: {len(long_memories)} 条")
            except Exception as e:
                logger.error(f"读取长期记忆失败: {str(e)}")

        # Rag向量查询
        try:
            rag_memories = self.get_rag_memories(query, user_id, group_id, sender_name)
            memories.extend(rag_memories)
        except Exception as e:
            logger.error(f"RAG查询失败: {str(e)}")
            logger.info("将继续使用传统记忆检索方法")

        return memories
        
    def _get_time_related_memories(self, user_id: str, group_id: str = None, sender_name: str = None) -> List[str]:
        """获取时间相关的记忆"""
        short_memory_path, _, _ = self._get_memory_paths(user_id, group_id, sender_name)
        time_memories = []
        
        try:
            with open(short_memory_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
                # 查找最近的时间相关对话
                for i in range(len(lines) - 1, 0, -1):
                    line = lines[i].strip()
                    if not line:
                        continue
                        
                    # 检查是否是时间相关回复
                    if "现在是" in line and "你:" in line:
                        # 找到对应的用户问题
                        if i > 0 and "对方:" in lines[i-1]:
                            user_question = lines[i-1].strip()
                            time_memories.append(user_question)
                            time_memories.append(line)
                            break
                            
                # 如果没有找到明确的时间回复，返回最近的几条对话
                if not time_memories and len(lines) >= 4:
                    for i in range(len(lines) - 1, max(0, len(lines) - 5), -1):
                        if lines[i].strip():
                            time_memories.append(lines[i].strip())
        except Exception as e:
            logger.error(f"读取时间相关记忆失败: {str(e)}")
            
        return time_memories

    def summarize_daily_memory(self, user_id: str, group_id: str = None, sender_name: str = None):
        """将短期记忆总结为日记式的长期记忆"""
        try:
            short_memory_path, long_memory_buffer_path, _ = self._get_memory_paths(user_id, group_id, sender_name)

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

            # 写入长期记忆
            with open(long_memory_buffer_path, "a", encoding="utf-8") as f:
                f.write(f"{summary}\n\n")

            # 写入Rag记忆
            memory_key = f"用户{user_id}"
            if group_id and sender_name:
                memory_key += f"({sender_name}@{group_id})"
            memory_key += f"的{today} 日常总结"
            
            get_memory()[memory_key] = summary
            get_memory().save_config()

            logger.info(f"成功生成用户 {user_id}{' (群聊用户: '+sender_name+')' if group_id and sender_name else ''} 的每日记忆总结")

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

            # 过滤掉 None 值
            files_to_check = [f for f in [short_memory_path, long_memory_buffer_path, important_memory_path] if f is not None]
            
            for f in files_to_check:
                if not os.path.exists(f):
                    try:
                        with open(f, "w", encoding="utf-8") as _:
                            logger.info(f"为用户 {user_id} 创建文件: {os.path.basename(f)}")
                    except Exception as file_e:
                        logger.error(f"创建记忆文件失败 {f}: {str(file_e)}")
        except Exception as e:
            logger.error(f"初始化用户文件失败 {user_id}: {str(e)}")

    def get_recent_memory(self, user_id: str, max_count: int = 5, group_id: str = None, sender_name: str = None) -> List[Dict[str, str]]:
        """获取最近的对话记录"""
        try:
            # 使用正确的路径获取方法
            short_memory_path, _, _ = self._get_memory_paths(user_id, group_id, sender_name)
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

    def get_rag_memories(self, content, user_id: str = None, group_id: str = None, sender_name: str = None):
        """获取Rag记忆"""
        try:
            # 检查是否是时间相关查询
            if self._is_time_related_query(content):
                logger.info("检测到时间相关查询，RAG检索将特别关注时间信息")
                # 对于时间相关查询，我们需要特别处理
                # 1. 首先尝试从RAG中获取相关记忆
                rag = get_rag()
                logger.debug(f"rag文档总数：{len(rag.documents)}")
                
                # 增强查询，使其更关注时间信息
                enhanced_query = content
                if "几点" in content or "时间" in content:
                    enhanced_query = f"{content} 时间 几点 当前时间"
                elif "刚才" in content or "之前" in content or "记得" in content:
                    enhanced_query = f"{content} 最近对话 记忆"
                
                # 如果是群聊中的特定用户，增强查询以包含用户信息
                if group_id and sender_name:
                    enhanced_query = f"{enhanced_query} {sender_name}@{group_id}"
                
                logger.info(f"执行增强查询: '{enhanced_query}'")
                res = rag.query(enhanced_query, self.top_k, self.is_rerank)
                
                # 2. 过滤结果，优先保留包含时间信息的记忆
                filtered_res = []
                time_pattern = r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]'
                
                for memory in res:
                    # 如果记忆中包含时间戳，优先保留
                    if re.search(time_pattern, memory):
                        # 如果是群聊中的特定用户，只保留该用户的记忆
                        if group_id and sender_name:
                            user_pattern = f"\\({sender_name}@{group_id}\\)"
                            if re.search(user_pattern, memory) or not "(" in memory:
                                filtered_res.append(memory)
                        else:
                            filtered_res.append(memory)
                
                # 如果过滤后没有结果，则使用原始结果
                if filtered_res:
                    logger.info(f"时间相关查询过滤后的记忆数量: {len(filtered_res)}")
                    return filtered_res
                else:
                    logger.info("时间相关查询没有找到包含时间戳的记忆，使用原始结果")
                    # 如果是群聊中的特定用户，过滤结果只保留该用户的记忆
                    if group_id and sender_name:
                        user_filtered_res = []
                        user_pattern = f"\\({sender_name}@{group_id}\\)"
                        for memory in res:
                            if re.search(user_pattern, memory) or not "(" in memory:
                                user_filtered_res.append(memory)
                        return user_filtered_res if user_filtered_res else res
                    return res
            else:
                # 非时间相关查询，使用标准RAG检索
                rag = get_rag()
                logger.debug(f"rag文档总数：{len(rag.documents)}")
                
                # 如果是群聊中的特定用户，增强查询以包含用户信息
                enhanced_query = content
                if group_id and sender_name:
                    enhanced_query = f"{content} {sender_name}@{group_id}"
                    logger.info(f"群聊用户查询增强: '{enhanced_query}'")
                
                res = rag.query(enhanced_query, self.top_k, self.is_rerank)
                
                # 如果是群聊中的特定用户，过滤结果只保留该用户的记忆
                if group_id and sender_name:
                    user_filtered_res = []
                    user_pattern = f"\\({sender_name}@{group_id}\\)"
                    for memory in res:
                        if re.search(user_pattern, memory) or not "(" in memory:
                            user_filtered_res.append(memory)
                    
                    if user_filtered_res:
                        logger.info(f"群聊用户 {sender_name} 的记忆过滤后数量: {len(user_filtered_res)}")
                        return user_filtered_res
                    else:
                        logger.info(f"群聊用户 {sender_name} 没有特定记忆，使用通用结果")
                        return res
                return res
        except Exception as e:
            logger.error(f"获取RAG记忆失败: {str(e)}")
            return []  # 返回空列表，不影响程序运行
            
    def _get_group_user_memory_dir(self, group_id: str, sender_name: str) -> str:
        """获取群聊中特定用户的记忆目录路径"""
        # 创建层级目录结构: data/memory/{bot_name}/groups/{group_id}/{sender_name}/
        bot_memory_dir = os.path.join(self.memory_base_dir, self.bot_name)
        groups_dir = os.path.join(bot_memory_dir, "groups")
        group_dir = os.path.join(groups_dir, group_id)
        user_memory_dir = os.path.join(group_dir, sender_name)

        # 确保目录存在
        try:
            os.makedirs(groups_dir, exist_ok=True)
            os.makedirs(group_dir, exist_ok=True)
            os.makedirs(user_memory_dir, exist_ok=True)
            logger.debug(f"确保群聊用户记忆目录存在: {user_memory_dir}")
        except Exception as e:
            logger.error(f"创建群聊用户记忆目录失败 {user_memory_dir}: {str(e)}")

        return user_memory_dir
        
    def identify_group_user(self, group_id: str, message: str) -> Optional[str]:
        """通过记忆识别群聊中的用户
        
        通过检索之前的记忆，尝试确定当前消息最可能来自哪个用户
        
        Args:
            group_id: 群ID
            message: 用户消息
            
        Returns:
            识别出的用户名，如果无法识别则返回None
        """
        if group_id not in self.user_name_mapping or not self.user_name_mapping[group_id]:
            logger.info(f"群 {group_id} 中没有已知用户")
            return None
            
        # 获取该群中所有已知用户
        known_users = list(self.user_name_mapping[group_id].keys())
        logger.info(f"群 {group_id} 中的已知用户: {known_users}")
        
        # 如果只有一个用户，直接返回
        if len(known_users) == 1:
            return known_users[0]
            
        # 对每个用户计算相似度分数
        user_scores = {}
        
        for user_name in known_users:
            # 获取用户的最近记忆
            recent_memories = self.get_recent_memory(group_id, max_count=10, group_id=group_id, sender_name=user_name)
            
            # 如果没有记忆，跳过
            if not recent_memories:
                continue
                
            # 计算消息与用户历史记忆的相似度
            score = 0
            for memory in recent_memories:
                if "message" in memory:
                    # 简单的词汇重叠计算
                    user_msg = memory["message"]
                    common_words = set(jieba.cut(user_msg)) & set(jieba.cut(message))
                    score += len(common_words)
                    
            user_scores[user_name] = score
            
        # 如果没有得分，无法识别
        if not user_scores:
            return None
            
        # 返回得分最高的用户
        max_score_user = max(user_scores.items(), key=lambda x: x[1])
        
        # 如果最高分数为0，无法可靠识别
        if max_score_user[1] == 0:
            return None
            
        logger.info(f"识别群聊用户: {max_score_user[0]}，得分: {max_score_user[1]}")
        return max_score_user[0]

    def _is_time_related_query(self, query: str) -> bool:
        """检查是否是时间相关的查询"""
        time_keywords = [
            '几点', '时间', '现在是', '当前时间', 'time now', 'what time',
            '刚才', '之前', '记得', '说过什么', '聊了什么'
        ]
        return any(keyword in query for keyword in time_keywords)

    def get_embedding_with_fallback(self, text, model=EMBEDDING_MODEL):
        """获取嵌入向量，失败时快速跳过"""
        try:
            # 添加超时控制
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("嵌入请求超时")
            
            # 设置5秒超时
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(5)
            
            response = openai.Embedding.create(
                input=text,
                model=model
            )
            
            # 取消超时
            signal.alarm(0)
            
            return response['data'][0]['embedding']
        except Exception as e:
            logger.warning(f"嵌入失败，跳过: {str(e)}")
            # 返回空向量或默认向量
            return [0.0] * 1024  # 使用标准维度

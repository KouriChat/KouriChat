import os
import logging
from typing import List, Optional, Dict  # 添加 Dict 导入
from datetime import datetime
from src.memories.key_memory import KeyMemory
from src.memories.long_term_memory import LongTermMemory
from src.memories.memory.core.rag import RAG, OnlineCrossEncoderReRanker, OnlineEmbeddingModel
from src.memories.memory_saver import MySQLMemorySaver, SQLiteMemorySaver
from src.memories.short_term_memory import ShortTermMemory
from src.services.ai.llm_service import LLMService

import jieba
import re
from src.handlers.emotion import SentimentResourceLoader, SentimentAnalyzer
import json
from src.memory import get_rag, setup_memory, setup_rag, start_memory, get_memory
from src.memory.core.rag_memory import RAGMemory
from src.memory.core.rag import OnlineEmbeddingModel, OnlineCrossEncoderReRanker
import openai
import time  # 添加time模块导入，用于超时控制

# 定义嵌入模型
EMBEDDING_MODEL = "text-embedding-3-large"  # 默认嵌入模型
EMBEDDING_FALLBACK_MODEL = "text-embedding-ada-002"  # 备用嵌入模型

# 从config模块获取配置
from src.config import config
from src.services.ai.llms.openai_llm import OpenAILLM


logger = logging.getLogger('main')

# 定义需要重点关注的关键词列表
KEYWORDS = [
    "记住了没？", "记好了", "记住", "别忘了", "牢记", "记忆深刻", "不要忘记", "铭记",
    "别忘掉", "记在心里", "时刻记得", "莫失莫忘", "印象深刻", "难以忘怀", "念念不忘", "回忆起来",
    "永远不忘", "留意", "关注", "提醒", "提示", "警示", "注意", "特别注意",
    "记得检查", "请记得", "务必留意", "时刻提醒自己", "定期回顾", "随时注意", "不要忽略", "确认一下",
    "核对", "检查", "温馨提示", "小心"
]

def get_saver(is_long_term: bool = False):
    if config["categories"]["memory_settings"]["db_settings"]["type"] == "sqlite":
        return SQLiteMemorySaver(
            table_name=config["categories"]["memory_settings"]["long_term_memory"]["table_name"] if is_long_term else config["categories"]["memory_settings"]["key_memory"]["table_name"],
            db_path=config["categories"]["memory_settings"]["db_settings"]["sqlite_path"]
        )
    elif config["categories"]["memory_settings"]["db_settings"]["type"] == "mysql":
        return MySQLMemorySaver(
            table_name=config["categories"]["memory_settings"]["long_term_memory"]["table_name"] if is_long_term else config["categories"]["memory_settings"]["key_memory"]["table_name"],
            db_settings={
                "host": config["categories"]["memory_settings"]["db_settings"]["host"],
                "port": config["categories"]["memory_settings"]["db_settings"]["port"],
                "user": config["categories"]["memory_settings"]["db_settings"]["user"],
                "password": config["categories"]["memory_settings"]["db_settings"]["password"],
                "database": config["categories"]["memory_settings"]["db_settings"]["database"],
            }
        )
    else:
        raise ValueError("不支持的数据库类型")

class MemoryHandler:
    def __init__(self, root_dir: str, api_key: str, base_url: str, model: str,
                 max_token: int, temperature: float, max_groups: int,
                 llm: LLMService,bot_name: str = None, sentiment_analyzer: SentimentAnalyzer = None):
        # 基础参数
        self.root_dir = root_dir
        self.api_key = api_key
        self.base_url = base_url
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        self.model = model


        # 从config模块获取配置
        from src.config.rag_config import config
        self.config = config  # 保存config对象的引用

        self.llm = llm

        self.bot_name = bot_name or config.robot_wx_name
        self.listen_list = config.user.listen_list

        # 记忆目录结构
        self.memory_base_dir = os.path.join(root_dir, "data", "memory")
        os.makedirs(self.memory_base_dir, exist_ok=True)

        # 初始化Rag记忆的方法
        # 2025-03-15修改，使用ShortTermMemory单例模式
        self.short_term_memory = ShortTermMemory.get_instance(
            memory_path=os.path.join(self.memory_base_dir, "rag-memory.json"),
            embedding_model=OnlineEmbeddingModel(
                api_key=config.rag.api_key,
                base_url=config.rag.base_url,
                model_name=config.rag.embedding_model
            ),
            reranker=OnlineCrossEncoderReRanker(
                api_key=config.rag.api_key,
                base_url=config.rag.base_url,
                model_name=config.rag.reranker_model
            ) 
        )
        self.key_memory = KeyMemory.get_instance(
            get_saver(is_long_term=False)
        )
        self.long_term_memory = LongTermMemory.get_instance(
            get_saver(is_long_term=True),
            OpenAILLM(
                api_key=config.llm.api_key,
                url=config.llm.base_url,
                model_name=config.llm.model,
                max_tokens=config.llm.max_tokens,
                temperature=config.llm.temperature,
                max_context_messages=config.behavior.context.max_groups,
                logger=logger,
    
            ),
            config["categories"]["memory_settings"]["long_term_memory"]["process_prompt"]
        )
        self.is_rerank = config.rag.is_rerank
        self.top_k = config.rag.top_k
        self.short_term_memory.start_memory()
        self.add_short_term_memory_hook()

        # 初始化一个长期记忆和关键记忆的组合rag
        self.lg_tm_m_and_k_m = RAG(
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
        self.init_lg_tm_m_and_k_m()
    
    def init_lg_tm_m_and_k_m(self):
        """
        初始化长期记忆和关键记忆的组合rag库
        """
        self.lg_tm_m_and_k_m.add_documents(self.long_term_memory.get_memories())
        self.lg_tm_m_and_k_m.add_documents(self.key_memory.get_memory())

    def add_short_term_memory_hook(self):
        """添加短期记忆监听器方法"""
        @self.llm.llm.context_handler
        def short_term_memory_add(ai_response: str, user_response: str):
            try:

                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                # 将记忆写入Rag记忆
                # 2025-03-15修改，把写入Rag的代码修改到llm的钩子方法中
                self.short_term_memory.memory[f"[{timestamp}] 对方: {ai_response}"] = f"[{timestamp}] 你: {user_response}"
                self.short_term_memory.save_memory()

                # 2025-03-15修改，记忆文件弃用
                # try:
                #     with open(short_memory_path, "a", encoding="utf-8") as f:
                #         f.write(memory_content)
                #     logger.info(f"成功写入短期记忆: {user_id}")
                #     print(f"控制台日志: 成功写入短期记忆 - 用户ID: {user_id}")
                # except Exception as e:
                #     logger.error(f"写入短期记忆失败: {str(e)}")
                #     print(f"控制台日志: 写入短期记忆失败 - 用户ID: {user_id}, 错误: {str(e)}")
                #     return

                # 检查关键词并添加重要记忆
                # 2025-03-15修改，重要记忆暂时弃用
            except Exception as e:
                logger.error(f"添加短期记忆失败: {str(e)}")
                print(f"控制台日志: 添加短期记忆失败 - 用户:, 错误: {str(e)}")

    def _add_important_memory(self, message: str, user_id: str):
        """添加重要记忆"""
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        memory_content = f'["{timestamp} 用户{user_id}的重要记忆"] = "[{timestamp}] 重要记忆内容: {message}"'

        # 写入Rag记忆
        self.key_memory.add_memory(memory_content)

        logger.info(f"成功写入重要记忆: {user_id}")

    def get_relevant_memories(self, query: str, user_id: Optional[str] = None) -> List[str]:
        """获取相关记忆，只在用户主动询问时检索重要记忆和长期记忆"""
        content = f"[{user_id}]:{query}"
        memories = self.lg_tm_m_and_k_m.query(content, self.top_k, self.is_rerank)
        memories += self.short_term_memory.rag.query(content, self.top_k, self.is_rerank)
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
        # 从avatar_dir中提取角色名
        avatar_dir = self.config.behavior.context.avatar_dir
        avatar_name = os.path.basename(avatar_dir)  # 获取路径的最后一部分作为角色名
        
        # 创建层级目录结构: data/memory/{avatar_name}/{user_id}/
        bot_memory_dir = os.path.join(self.memory_base_dir, avatar_name)
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
        添加长期记忆处理任务
        这个方法会启动一个线程，定期处理长期记忆
        """
        try:
            # 从配置获取保存间隔时间(分钟)
            from src.config import config
            save_interval = config.memory.long_term_memory.save_interval
            
            # 创建并启动定时器线程
            def process_memory():
                try:
                    # 调用长期记忆处理方法
                    self.long_term_memory.add_memory(self.short_term_memory.memory.get_key_value_pairs())
                    
                    # 清空短期记忆文档和索引
                    self.short_term_memory.memory.settings.clear()
                    self.short_term_memory.rag.documents.clear()
                    self.short_term_memory.rag.index.clear()

                    logger.info(f"成功处理用户 {user_id} 的长期记忆")
                except Exception as e:
                    logger.error(f"处理长期记忆失败: {str(e)}")


    def get_embedding_with_fallback(self, text, model=EMBEDDING_MODEL):
        """获取嵌入向量，失败时快速跳过"""
        try:
            # 使用time模块进行超时控制
            start_time = time.time()
            timeout = 5  # 5秒超时
            
            # 创建OpenAI客户端
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            # 设置超时
            response = client.embeddings.create(
                input=text,
                model=model,
                timeout=timeout
            )
            
            # 获取嵌入向量
            embedding = response.data[0].embedding
            return embedding
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {str(e)}")
            if model != EMBEDDING_FALLBACK_MODEL:
                logger.info(f"尝试使用备用模型 {EMBEDDING_FALLBACK_MODEL}")
                return self.get_embedding_with_fallback(text, EMBEDDING_FALLBACK_MODEL)
            else:
                # 如果备用模型也失败，返回空向量
                logger.error("备用模型也失败，返回空向量")
                return [0.0] * 1536  # 返回1536维的零向量

    def get_recent_chat_time(self, user_id: str) -> Optional[datetime]:
        """
        获取与特定用户的最近聊天时间
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[datetime]: 最近聊天的时间，如果没有聊天记录则返回None
        """
        try:
            # 获取用户短期记忆文件路径
            short_memory_path = os.path.join(self._get_user_memory_dir(user_id), "short_memory.json")
            
            # 检查文件是否存在
            if not os.path.exists(short_memory_path):
                logger.info(f"用户 {user_id} 没有短期记忆文件")
                return None
                
            # 读取短期记忆文件
            with open(short_memory_path, 'r', encoding='utf-8') as f:
                memories = json.load(f)
                
            # 如果没有记忆，返回None
            if not memories:
                logger.info(f"用户 {user_id} 的短期记忆为空")
                return None
                
            # 获取最近的记忆
            latest_memory = memories[-1]
            
            # 提取时间戳
            timestamp_str = latest_memory.get('timestamp')
            if not timestamp_str:
                logger.warning(f"用户 {user_id} 的最近记忆没有时间戳")
                return None
                
            # 解析时间戳
            try:
                # 尝试解析ISO格式的时间戳
                latest_time = datetime.fromisoformat(timestamp_str)
            except ValueError:
                try:
                    # 尝试解析常规格式的时间戳
                    latest_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    logger.error(f"无法解析时间戳: {timestamp_str}")
                    return None
                    
            logger.info(f"用户 {user_id} 的最近聊天时间: {latest_time}")
            return latest_time
            
        except Exception as e:
            logger.error(f"获取最近聊天时间失败: {str(e)}")
            return None


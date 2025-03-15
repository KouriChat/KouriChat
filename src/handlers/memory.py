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
from src.handlers.emotion import SentimentAnalyzer
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

    def add_long_term_memory_process_task(self, user_id: str):
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

            import threading
            import time
            
            def timer_thread():
                while True:
                    process_memory()
                    # 休眠指定时间间隔(转换为秒)
                    time.sleep(save_interval * 60)
            
            thread = threading.Thread(target=timer_thread, daemon=True)
            thread.start()
            
            logger.info(f"已启动长期记忆处理线程,间隔时间:{save_interval}分钟")
            
        except Exception as e:
            logger.error(f"启动长期记忆处理线程失败: {str(e)}")

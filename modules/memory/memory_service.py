import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
from src.services.ai.llm_service import LLMService

# 获取日志记录器
logger = logging.getLogger('memory')

class MemoryService:
    """
    新版记忆服务模块，包含两种记忆类型:
    1. 短期记忆：用于保存最近对话，在程序重启后加载到上下文
    2. 核心记忆：精简的用户核心信息摘要(50-100字)
    每个用户拥有独立的记忆存储空间
    """
    def __init__(self, root_dir: str, api_key: str, base_url: str, model: str, max_token: int, temperature: float, max_groups: int = 10):
        self.root_dir = root_dir
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups  # 保存上下文组数设置
        self.llm_client = None
        self.conversation_count = {}  # 记录每个角色与用户组合的对话计数: {avatar_name_user_id: count}

    def initialize_memory_files(self, avatar_name: str, user_id: str):
        """初始化角色的记忆文件，确保文件存在"""
        try:
            # 确保记忆目录存在
            memory_dir = self._get_avatar_memory_dir(avatar_name, user_id)
            short_memory_path = self._get_short_memory_path(avatar_name, user_id)
            core_memory_path = self._get_core_memory_path(avatar_name, user_id)
            
            # 初始化短期记忆文件（如果不存在）
            if not os.path.exists(short_memory_path):
                with open(short_memory_path, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                logger.info(f"创建短期记忆文件: {short_memory_path}")
            
            # 初始化核心记忆文件（如果不存在）
            if not os.path.exists(core_memory_path):
                initial_core_data = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "content": ""  # 初始为空字符串
                }
                with open(core_memory_path, "w", encoding="utf-8") as f:
                    json.dump(initial_core_data, f, ensure_ascii=False, indent=2)
                logger.info(f"创建核心记忆文件: {core_memory_path}")
        
        except Exception as e:
            logger.error(f"初始化记忆文件失败: {str(e)}")

    def _get_llm_client(self):
        """获取或创建LLM客户端"""
        if not self.llm_client:
            from src.config.proxy_config import get_proxy_config
            proxy_config = get_proxy_config()  # 使用自动检测系统代理

            self.llm_client = LLMService(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                max_token=self.max_token,
                temperature=self.temperature,
                max_groups=self.max_groups,
                proxy_config=proxy_config
            )
            logger.info(f"创建LLM客户端，上下文大小设置为: {self.max_groups}轮对话")
        return self.llm_client
        
    def _get_avatar_memory_dir(self, avatar_name: str, user_id: str) -> str:
        """获取角色记忆目录，如果不存在则创建"""
        avatar_memory_dir = os.path.join(self.root_dir, "data", "avatars", avatar_name, "memory", user_id)
        os.makedirs(avatar_memory_dir, exist_ok=True)
        return avatar_memory_dir
    
    def _get_short_memory_path(self, avatar_name: str, user_id: str) -> str:
        """获取短期记忆文件路径"""
        memory_dir = self._get_avatar_memory_dir(avatar_name, user_id)
        return os.path.join(memory_dir, "short_memory.json")
    
    def _get_core_memory_path(self, avatar_name: str, user_id: str) -> str:
        """获取核心记忆文件路径"""
        memory_dir = self._get_avatar_memory_dir(avatar_name, user_id)
        return os.path.join(memory_dir, "core_memory.json")
    
    def add_conversation(self, avatar_name: str, user_message: str, bot_reply: str, user_id: str, is_system_message: bool = False):
        """
        添加对话到短期记忆，并更新对话计数。
        每达到10轮对话，自动更新核心记忆。
        
        Args:
            avatar_name: 角色名称
            user_message: 用户消息
            bot_reply: 机器人回复
            user_id: 用户ID，用于隔离不同用户的记忆
            is_system_message: 是否为系统消息，如果是则不记录
        """
        # 确保对话计数器已初始化
        conversation_key = f"{avatar_name}_{user_id}"
        if conversation_key not in self.conversation_count:
            self.conversation_count[conversation_key] = 0
            
        # 如果是系统消息或错误消息则跳过记录
        if is_system_message or bot_reply.startswith("Error:"):
            logger.debug(f"跳过记录消息: {user_message[:30]}...")
            return
            
        try:
            # 确保记忆目录存在
            memory_dir = self._get_avatar_memory_dir(avatar_name, user_id)
            short_memory_path = self._get_short_memory_path(avatar_name, user_id)
            
            logger.info(f"保存对话到用户记忆: 角色={avatar_name}, 用户ID={user_id}")
            logger.debug(f"记忆存储路径: {short_memory_path}")
            
            # 读取现有短期记忆
            short_memory = []
            if os.path.exists(short_memory_path):
                try:
                    with open(short_memory_path, "r", encoding="utf-8") as f:
                        short_memory = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"短期记忆文件损坏，重置为空列表: {short_memory_path}")
            
            # 添加新对话
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_conversation = {
                "timestamp": timestamp,
                "user": user_message,
                "bot": bot_reply
            }
            short_memory.append(new_conversation)
            
            # 保留最近50轮对话
            if len(short_memory) > 50:
                short_memory = short_memory[-50:]
            
            # 保存更新后的短期记忆
            with open(short_memory_path, "w", encoding="utf-8") as f:
                json.dump(short_memory, f, ensure_ascii=False, indent=2)
            
            # 更新对话计数
            self.conversation_count[conversation_key] += 1
            current_count = self.conversation_count[conversation_key]
            logger.debug(f"当前对话计数: {current_count}/10 (角色={avatar_name}, 用户ID={user_id})")
            
            # 每10轮对话更新一次核心记忆
            if self.conversation_count[conversation_key] >= 10:
                logger.info(f"角色 {avatar_name} 为用户 {user_id} 达到10轮对话，开始更新核心记忆")
                self.update_core_memory(avatar_name, user_id)
                self.conversation_count[conversation_key] = 0
                
        except Exception as e:
            logger.error(f"添加对话到短期记忆失败: {str(e)}")
    
    def update_core_memory(self, avatar_name: str, user_id: str):
        """
        更新核心记忆，将短期记忆和现有核心记忆整合，生成新的核心记忆摘要
        """
        try:
            short_memory_path = self._get_short_memory_path(avatar_name, user_id)
            core_memory_path = self._get_core_memory_path(avatar_name, user_id)
            
            # 读取短期记忆
            short_memory = []
            if os.path.exists(short_memory_path):
                with open(short_memory_path, "r", encoding="utf-8") as f:
                    short_memory = json.load(f)
            
            if not short_memory:
                logger.info(f"短期记忆为空，跳过核心记忆更新: {avatar_name} 用户: {user_id}")
                return
            
            # 读取现有核心记忆
            core_memory = ""
            if os.path.exists(core_memory_path):
                try:
                    with open(core_memory_path, "r", encoding="utf-8") as f:
                        core_data = json.load(f)
                        core_memory = core_data.get("content", "")
                except (json.JSONDecodeError, KeyError):
                    logger.warning(f"核心记忆文件损坏或格式错误，将重新生成: {core_memory_path}")
            
            # 构建最近对话内容（适配新的记忆格式）
            recent_conversations = "\n".join([
                f"用户: {conv.get('user', {}).get('content', '') if isinstance(conv.get('user'), dict) else conv.get('user', '')}\n"
                f"回复: {conv.get('bot', {}).get('content', '') if isinstance(conv.get('bot'), dict) else conv.get('bot', '')}" 
                for conv in short_memory[-10:]  # 仅使用最近10轮对话
            ])
            
            # 读取外部提示词文件
            try:
                # 从当前文件位置获取项目根目录
                current_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(os.path.dirname(current_dir))
                prompt_path = os.path.join(project_root, "data", "base", "memory.md")
                
                if not os.path.exists(prompt_path):
                    logger.error(f"核心记忆提示词文件不存在: {prompt_path}")
                    logger.info(f"跳过核心记忆更新: {avatar_name} 用户: {user_id}")
                    return
                    
                with open(prompt_path, "r", encoding="utf-8") as f:
                    memory_prompt_template = f.read().strip()
                    logger.debug(f"已加载记忆提示词模板，长度: {len(memory_prompt_template)} 字节")
            except Exception as e:
                logger.error(f"读取记忆提示词模板失败: {str(e)}")
                logger.info(f"跳过核心记忆更新: {avatar_name} 用户: {user_id}")
                return
            
            # 构建完整提示词
            prompt = f"""{memory_prompt_template}

现有核心记忆：
{core_memory}

最近对话内容：
{recent_conversations}"""
            
            # 调用LLM生成新的核心记忆
            llm = self._get_llm_client()
            client_id = f"core_memory_{avatar_name}_{user_id}"
            new_core_memory = llm.get_response(
                message=prompt,
                user_id=client_id,
                system_prompt="你是一个专注于信息提炼的AI助手。你的任务是从对话中提取最关键的信息，并创建一个极其精简的摘要。"
            )
            
            # 检查是否为错误响应，如果是则保留原有核心记忆
            if new_core_memory.startswith("Error:"):
                logger.warning(f"生成核心记忆时出现错误，保留原有核心记忆: {new_core_memory}")
                new_core_memory = core_memory
            
            # 保存新的核心记忆
            core_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "content": new_core_memory
            }
            
            with open(core_memory_path, "w", encoding="utf-8") as f:
                json.dump(core_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已更新角色 {avatar_name} 为用户 {user_id} 的核心记忆")
            
        except Exception as e:
            logger.error(f"更新核心记忆失败: {str(e)}")
    
    def get_core_memory(self, avatar_name: str, user_id: str) -> str:
        """获取角色的核心记忆内容"""
        try:
            core_memory_path = self._get_core_memory_path(avatar_name, user_id)
            
            if not os.path.exists(core_memory_path):
                logger.info(f"核心记忆不存在: {avatar_name} 用户: {user_id}")
                return ""
            
            logger.debug(f"获取用户核心记忆: 角色={avatar_name}, 用户ID={user_id}")
            logger.debug(f"核心记忆路径: {core_memory_path}")
            
            with open(core_memory_path, "r", encoding="utf-8") as f:
                core_data = json.load(f)
                core_memory = core_data.get("content", "")
                logger.debug(f"核心记忆长度: {len(core_memory)} 字节")
                return core_memory
                
        except Exception as e:
            logger.info(f"获取核心记忆失败: {str(e)}")
            return ""
    
    def get_recent_context(self, avatar_name: str, user_id: str, context_size: int = None) -> List[Dict]:
        """
        获取最近的对话上下文，用于重启后恢复对话连续性
        直接使用LLM服务配置的max_groups作为上下文大小
        
        Args:
            avatar_name: 角色名称
            user_id: 用户ID，用于获取特定用户的记忆
            context_size: 已废弃参数，保留仅为兼容性，实际使用LLM配置
        """
        try:
            # 获取LLM客户端的配置值
            llm_client = self._get_llm_client()
            max_groups = llm_client.config["max_groups"]
            logger.info(f"使用LLM配置的对话轮数: {max_groups}")
            
            short_memory_path = self._get_short_memory_path(avatar_name, user_id)
            
            if not os.path.exists(short_memory_path):
                logger.info(f"短期记忆不存在: {avatar_name} 用户: {user_id}")
                return []
            
            with open(short_memory_path, "r", encoding="utf-8") as f:
                short_memory = json.load(f)
            
            # 转换为LLM接口要求的消息格式
            context = []
            for conv in short_memory[-max_groups:]:  # 使用max_groups轮对话
                context.append({"role": "user", "content": conv["user"]})
                context.append({"role": "assistant", "content": conv["bot"]})
            
            logger.info(f"已加载 {len(context)//2} 轮对话作为上下文")
            return context
            
        except Exception as e:
            logger.error(f"获取最近上下文失败: {str(e)}")
            return []

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

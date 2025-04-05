import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime
from src.services.ai.llm_service import LLMService

logger = logging.getLogger('main')

class MemoryService:
    """
    新版记忆服务模块，包含两种记忆类型:
    1. 短期记忆：用于保存最近对话，在程序重启后加载到上下文
    2. 核心记忆：精简的用户核心信息摘要(50-100字)
    """
    def __init__(self, root_dir: str, api_key: str, base_url: str, model: str, max_token: int, temperature: float):
        self.root_dir = root_dir
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_token = max_token
        self.temperature = temperature
        self.llm_client = None
        self.conversation_count = {}  # 记录每个角色的对话计数: {avatar_name: count}

    def initialize_memory_files(self, avatar_name: str):
        """初始化角色的记忆文件，确保文件存在"""
        try:
            # 确保记忆目录存在
            memory_dir = self._get_avatar_memory_dir(avatar_name)
            short_memory_path = self._get_short_memory_path(avatar_name)
            core_memory_path = self._get_core_memory_path(avatar_name)
            
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
            self.llm_client = LLMService(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                max_token=self.max_token,
                temperature=self.temperature,
                max_groups=5  # 这里只需要较小的上下文
            )
        return self.llm_client

    def _get_avatar_memory_dir(self, avatar_name: str) -> str:
        """获取角色记忆目录，如果不存在则创建"""
        avatar_memory_dir = os.path.join(self.root_dir, "data", "avatars", avatar_name, "memory")
        os.makedirs(avatar_memory_dir, exist_ok=True)
        return avatar_memory_dir
    
    def _get_short_memory_path(self, avatar_name: str) -> str:
        """获取短期记忆文件路径"""
        memory_dir = self._get_avatar_memory_dir(avatar_name)
        return os.path.join(memory_dir, "short_memory.json")
    
    def _get_core_memory_path(self, avatar_name: str) -> str:
        """获取核心记忆文件路径"""
        memory_dir = self._get_avatar_memory_dir(avatar_name)
        return os.path.join(memory_dir, "core_memory.json")
    
    def add_conversation(self, avatar_name: str, user_message: str, bot_reply: str, is_system_message: bool = False):
        """
        添加对话到短期记忆，并更新对话计数。
        每达到10轮对话，自动更新核心记忆。
        
        Args:
            avatar_name: 角色名称
            user_message: 用户消息
            bot_reply: 机器人回复
            is_system_message: 是否为系统消息，如果是则不记录
        """
        # 确保对话计数器已初始化
        if avatar_name not in self.conversation_count:
            self.conversation_count[avatar_name] = 0
            
        # 如果是系统消息或错误消息则跳过记录
        if is_system_message or bot_reply.startswith("Error:"):
            logger.debug(f"跳过记录消息: {user_message[:30]}...")
            return
            
        try:
            # 确保记忆目录存在
            memory_dir = self._get_avatar_memory_dir(avatar_name)
            short_memory_path = self._get_short_memory_path(avatar_name)
            
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
            self.conversation_count[avatar_name] += 1
            
            # 每10轮对话更新一次核心记忆
            if self.conversation_count[avatar_name] >= 10:
                logger.info(f"角色 {avatar_name} 达到10轮对话，开始更新核心记忆")
                self.update_core_memory(avatar_name)
                self.conversation_count[avatar_name] = 0
                
        except Exception as e:
            logger.error(f"添加对话到短期记忆失败: {str(e)}")
    
    def update_core_memory(self, avatar_name: str):
        """
        更新核心记忆，将短期记忆和现有核心记忆整合，生成新的核心记忆摘要
        """
        try:
            short_memory_path = self._get_short_memory_path(avatar_name)
            core_memory_path = self._get_core_memory_path(avatar_name)
            
            # 读取短期记忆
            short_memory = []
            if os.path.exists(short_memory_path):
                with open(short_memory_path, "r", encoding="utf-8") as f:
                    short_memory = json.load(f)
            
            if not short_memory:
                logger.info(f"短期记忆为空，跳过核心记忆更新: {avatar_name}")
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
            
            # 构建优化后的提示词
            prompt = f"""分析以下对话和现有核心记忆，提炼极简核心记忆摘要。

要求：
1. 严格控制字数在50-100字内
2. 仅保留对未来对话至关重要的信息
3. 按优先级提取：用户个人信息 > 用户偏好/喜好 > 重要约定 > 特殊事件 > 常去地点
4. 使用第一人称视角撰写，仿佛是你自己在记录对话记忆
5. 使用极简句式，省略不必要的修饰词,禁止使用颜文字和括号描述动作
6. 不保留日期、时间等临时性信息，除非是周期性的重要约定
7. 如果没有关键新信息，则保持现有核心记忆不变
8. 信息应当是从你的角度了解到的用户信息
9. 格式为简洁的要点，可用分号分隔不同信息
10. 如果约定的时间已经过去，或者用户改变了约定，则更改相关的约定记忆

现有核心记忆：
{core_memory}

最近对话内容：
{recent_conversations}

仅返回最终核心记忆内容，不要包含任何解释："""
            
            # 调用LLM生成新的核心记忆
            llm = self._get_llm_client()
            new_core_memory = llm.get_response(
                message=prompt,
                user_id=f"core_memory_{avatar_name}",
                system_prompt="你是一个专注于信息提炼的AI助手。你的任务是从对话中提取最关键的信息，并创建一个极其精简的摘要。"
            )
            
            # 保存新的核心记忆
            core_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "content": new_core_memory
            }
            
            with open(core_memory_path, "w", encoding="utf-8") as f:
                json.dump(core_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已更新角色 {avatar_name} 的核心记忆")
            
        except Exception as e:
            logger.error(f"更新核心记忆失败: {str(e)}")
    
    def get_core_memory(self, avatar_name: str) -> str:
        """获取角色的核心记忆内容"""
        try:
            core_memory_path = self._get_core_memory_path(avatar_name)
            
            if not os.path.exists(core_memory_path):
                logger.info(f"核心记忆不存在: {avatar_name}")
                return ""
            
            with open(core_memory_path, "r", encoding="utf-8") as f:
                core_data = json.load(f)
                return core_data.get("content", "")
                
        except Exception as e:
            logger.info(f"获取核心记忆失败: {str(e)}")
            return ""
    
    def get_recent_context(self, avatar_name: str, context_size: int = 5) -> List[Dict]:
        """
        获取最近的对话上下文，用于重启后恢复对话连续性
        默认使用最近5轮对话作为上下文
        返回格式为LLM使用的消息列表格式
        """
        try:
            short_memory_path = self._get_short_memory_path(avatar_name)
            
            if not os.path.exists(short_memory_path):
                logger.info(f"短期记忆不存在: {avatar_name}")
                return []
            
            with open(short_memory_path, "r", encoding="utf-8") as f:
                short_memory = json.load(f)
            
            # 转换为LLM接口要求的消息格式
            context = []
            for conv in short_memory[-context_size:]:  # 仅获取最近N轮对话
                context.append({"role": "user", "content": conv["user"]})
                context.append({"role": "assistant", "content": conv["bot"]})
            
            return context
            
        except Exception as e:
            logger.info(f"获取最近上下文失败: {str(e)}")
            return []

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
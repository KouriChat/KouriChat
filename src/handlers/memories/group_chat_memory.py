"""
群聊记忆处理模块
负责管理群聊消息的存储、检索和处理，使用 RAG 系统进行存储
"""

import os
import json
import logging
import time
from datetime import datetime
import re
from typing import Dict, List, Optional, Any

from src.handlers.memories.core.rag import RagManager
from src.utils.logger import get_logger

logger = logging.getLogger('main')

class GroupChatMemory:
    def __init__(self, root_dir: str, avatar_name: str, group_chats: List[str], api_wrapper = None):
        """
        初始化群聊记忆处理器
        
        Args:
            root_dir: 项目根目录
            avatar_name: 角色名称
            group_chats: 群聊ID列表
            api_wrapper: API调用包装器，用于嵌入向量生成
        """
        self.root_dir = root_dir
        self.avatar_name = avatar_name
        self.group_chats = group_chats
        self.api_wrapper = api_wrapper
        
        # 为每个群聊创建独立的 RAG 管理器
        self.rag_managers: Dict[str, RagManager] = {}
        self._init_group_memories()
        
    def _init_group_memories(self):
        """初始化所有群聊的记忆存储"""
        try:
            # 获取 RAG 配置文件路径
            rag_config_path = os.path.join(self.root_dir, "src", "config", "config.yaml")
            
            # 初始化每个群聊的 RAG 系统
            for group_id in self.group_chats:
                # 清理群聊ID，移除非法字符
                safe_group_id = self._get_safe_group_id(group_id)
                
                # 构建群聊专属的存储路径
                group_storage_dir = os.path.join(
                    self.root_dir,
                    "data",
                    "avatars",
                    self.avatar_name,
                    "groups",
                    safe_group_id
                )
                
                # 确保目录存在
                os.makedirs(group_storage_dir, exist_ok=True)

                # 创建标准的memory.json文件，与私聊保持一致
                memory_json_path = os.path.join(group_storage_dir, "memory.json")
                if not os.path.exists(memory_json_path):
                    # 初始化空的memory.json，使用新的格式
                    with open(memory_json_path, "w", encoding="utf-8") as f:
                        json.dump({
                            group_id: []
                        }, f, ensure_ascii=False, indent=2)
                    logger.info(f"为群聊 {group_id} 创建了memory.json文件")
                
                try:
                    # 为每个群聊创建独立的 RAG 管理器
                    rag_manager = RagManager(
                        config_path=rag_config_path,
                        api_wrapper=self.api_wrapper,
                        storage_dir=group_storage_dir  # 使用群聊专属的存储目录
                    )
                    self.rag_managers[group_id] = rag_manager
                    logger.info(f"初始化群聊 {group_id} 的 RAG 系统成功")
                except Exception as e:
                    logger.error(f"初始化群聊 {group_id} 的 RAG 系统失败: {str(e)}")
                    
        except Exception as e:
            logger.error(f"初始化群聊记忆失败: {str(e)}")
            
    def _get_safe_group_id(self, group_id: str) -> str:
        """
        生成安全的群聊ID作为目录名
        
        Args:
            group_id: 原始群聊ID
            
        Returns:
            str: 安全的目录名
        """
        # 移除非法字符，只保留字母、数字、下划线和连字符
        safe_id = "".join(c for c in group_id if c.isalnum() or c in ('-', '_'))
        if not safe_id:
            safe_id = "default_group"
        return safe_id
            
    def add_message(self, group_id: str, sender_name: str, message: str, is_at: bool = False) -> str:
        """
        添加群聊消息到记忆
        
        Args:
            group_id: 群聊ID
            sender_name: 发送者名称
            message: 消息内容
            is_at: 是否@机器人
            
        Returns:
            str: 消息时间戳
        """
        try:
            # 如果群聊未初始化，尝试动态初始化
            if group_id not in self.rag_managers:
                logger.info(f"群聊 {group_id} 首次出现，正在初始化 RAG 系统")
                
                # 添加到群聊列表
                if group_id not in self.group_chats:
                    self.group_chats.append(group_id)
                
                # 清理群聊ID，移除非法字符
                safe_group_id = self._get_safe_group_id(group_id)
                
                # 构建群聊专属的存储路径
                group_storage_dir = os.path.join(
                    self.root_dir,
                    "data",
                    "avatars",
                    self.avatar_name,
                    "groups",
                    safe_group_id
                )
                
                # 确保目录存在
                os.makedirs(group_storage_dir, exist_ok=True)

                # 检查memory.json是否存在，如果不存在则创建
                memory_json_path = os.path.join(group_storage_dir, "memory.json")
                if not os.path.exists(memory_json_path):
                    # 初始化空的memory.json，使用新的格式
                    with open(memory_json_path, "w", encoding="utf-8") as f:
                        json.dump({
                            group_id: []
                        }, f, ensure_ascii=False, indent=2)
                    logger.info(f"为群聊 {group_id} 创建了memory.json文件")
                
                try:
                    # 获取 RAG 配置文件路径
                    rag_config_path = os.path.join(self.root_dir, "src", "config", "config.yaml")
                    
                    # 为群聊创建独立的 RAG 管理器
                    rag_manager = RagManager(
                        config_path=rag_config_path,
                        api_wrapper=self.api_wrapper,
                        storage_dir=group_storage_dir  # 使用群聊专属的存储目录
                    )
                    self.rag_managers[group_id] = rag_manager
                    logger.info(f"动态初始化群聊 {group_id} 的 RAG 系统成功")
                except Exception as e:
                    logger.error(f"动态初始化群聊 {group_id} 的 RAG 系统失败: {str(e)}")
                    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            # 创建记忆条目
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 构建消息对象
            message_data = {
                "timestamp": timestamp,
                "sender_name": sender_name,
                "human_message": message,
                "assistant_message": None,  # 初始为None，等待回复时更新
                "ai_name": self.avatar_name,
                "is_at": is_at
            }
            
            # 同时更新memory.json文件和RAG系统
            safe_group_id = self._get_safe_group_id(group_id)
            memory_json_path = os.path.join(
                self.root_dir,
                "data",
                "avatars",
                self.avatar_name,
                "groups",
                safe_group_id,
                "memory.json"
            )
            
            # 更新memory.json文件
            if os.path.exists(memory_json_path):
                try:
                    # 读取现有内容
                    with open(memory_json_path, "r", encoding="utf-8") as f:
                        memory_data = json.load(f)
                    
                    # 确保群聊ID存在
                    if group_id not in memory_data:
                        memory_data[group_id] = []
                    
                    # 添加新消息
                    memory_data[group_id].append(message_data)
                    
                    # 保存更新后的数据
                    with open(memory_json_path, "w", encoding="utf-8") as f:
                        json.dump(memory_data, f, ensure_ascii=False, indent=2)
                    
                    logger.info(f"已保存新消息到群聊 {group_id} 的memory.json文件")
                except Exception as e:
                    logger.error(f"更新群聊 {group_id} 的memory.json文件失败: {str(e)}")
            
            # 异步添加到RAG系统
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self.rag_managers[group_id].add_group_chat_message(group_id, message_data),
                    loop
                )
                future.result()
            else:
                loop.run_until_complete(self.rag_managers[group_id].add_group_chat_message(group_id, message_data))
                
            return timestamp
            
        except Exception as e:
            logger.error(f"添加群聊消息失败: {str(e)}")
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
    def update_assistant_response(self, group_id: str, timestamp: str, response: str) -> bool:
        """
        更新助手回复
        
        Args:
            group_id: 群聊ID
            timestamp: 消息时间戳
            response: 助手回复
            
        Returns:
            bool: 是否成功更新
        """
        try:
            if group_id not in self.rag_managers:
                logger.warning(f"群聊 {group_id} 未初始化 RAG 系统")
                return False
            
            # 更新memory.json文件
            safe_group_id = self._get_safe_group_id(group_id)
            memory_json_path = os.path.join(
                self.root_dir,
                "data",
                "avatars",
                self.avatar_name,
                "groups",
                safe_group_id,
                "memory.json"
            )
            
            # 更新内存中的memory.json
            if os.path.exists(memory_json_path):
                try:
                    # 读取现有内容
                    with open(memory_json_path, "r", encoding="utf-8") as f:
                        memory_data = json.load(f)
                    
                    # 确保群聊ID存在
                    if group_id not in memory_data:
                        memory_data[group_id] = []
                    
                    # 查找是否有相同时间戳的消息
                    found = False
                    for i, memory in enumerate(memory_data[group_id]):
                        if isinstance(memory, dict) and memory.get("timestamp") == timestamp:
                            # 更新现有消息
                            memory["assistant_message"] = response
                            found = True
                            break
                    
                    # 如果没有找到，添加新消息
                    if not found:
                        # 创建新消息条目
                        memory_data[group_id].append({
                            "timestamp": timestamp,
                            "sender_name": "未知用户",  # 这里可能缺少发送者信息
                            "human_message": "",  # 这里可能缺少原始消息
                            "assistant_message": response,
                            "ai_name": self.avatar_name,
                            "is_at": False
                        })
                    
                    # 保存更新后的数据
                    with open(memory_json_path, "w", encoding="utf-8") as f:
                        json.dump(memory_data, f, ensure_ascii=False, indent=2)
                    
                    logger.info(f"已更新群聊 {group_id} 的memory.json文件")
                except Exception as e:
                    logger.error(f"更新群聊 {group_id} 的memory.json文件失败: {str(e)}")
            
            # 异步更新RAG系统
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self.rag_managers[group_id].update_group_chat_response(group_id, timestamp, response),
                    loop
                )
                future.result()
            else:
                loop.run_until_complete(self.rag_managers[group_id].update_group_chat_response(group_id, timestamp, response))
            
            return True
            
        except Exception as e:
            logger.error(f"更新助手回复失败: {str(e)}")
            return False
            
    def get_memory_from_file(self, group_id: str, limit: int = 10) -> List[Dict]:
        """
        从memory.json文件中直接获取群聊记忆
        
        Args:
            group_id: 群聊ID
            limit: 获取的消息数量
            
        Returns:
            List[Dict]: 消息列表
        """
        try:
            # 获取memory.json文件路径
            safe_group_id = self._get_safe_group_id(group_id)
            memory_json_path = os.path.join(
                self.root_dir,
                "data",
                "avatars",
                self.avatar_name,
                "groups",
                safe_group_id,
                "memory.json"
            )
            
            if not os.path.exists(memory_json_path):
                logger.warning(f"群聊 {group_id} 的memory.json文件不存在")
                return []
            
            # 读取文件内容
            with open(memory_json_path, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
            
            # 检查群聊ID是否存在
            if group_id not in memory_data:
                logger.warning(f"群聊 {group_id} 在memory.json中不存在")
                return []
            
            # 获取消息列表
            messages = memory_data[group_id]
            
            # 按时间戳排序（最新的在前）
            messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # 返回指定数量的消息
            return messages[:limit]
            
        except Exception as e:
            logger.error(f"从文件获取群聊记忆失败: {str(e)}")
            return []

    def get_context_messages(self, group_id: str, current_timestamp: str, context_size: int = 7) -> List[Dict]:
        """
        获取上下文消息，返回最近7轮对话的上下文
        
        Args:
            group_id: 群聊ID
            current_timestamp: 当前消息时间戳
            context_size: 获取的上下文消息数量，默认为7轮
            
        Returns:
            List[Dict]: 上下文消息列表
        """
        try:
            # 检查是否初始化了RAG系统
            if group_id not in self.rag_managers:
                logger.warning(f"群聊 {group_id} 未初始化 RAG 系统")
                return []
            
            # 使用RAG钩子获取最近的消息
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self.rag_managers[group_id].group_chat_query(group_id, current_timestamp, context_size),
                    loop
                )
                context_messages = future.result()
            else:
                context_messages = loop.run_until_complete(
                    self.rag_managers[group_id].group_chat_query(group_id, current_timestamp, context_size)
                )
            
            # 如果找到上下文，直接返回
            if context_messages:
                logger.info(f"获取到最近 {len(context_messages)} 轮群聊上下文消息")
                return context_messages
            
            # 如果RAG钩子没有返回结果，尝试从memory.json文件读取
            file_memories = self.get_memory_from_file(group_id, context_size + 1)
            
            if file_memories:
                # 排除当前消息
                context_messages = [
                    msg for msg in file_memories 
                    if msg.get("timestamp") != current_timestamp
                ]
                
                # 限制返回数量
                logger.info(f"从memory.json获取到最近 {len(context_messages)} 轮群聊上下文消息")
                return context_messages[:context_size]
            
            logger.info("未找到任何群聊上下文消息")
            return []
            
        except Exception as e:
            logger.error(f"获取上下文消息失败: {str(e)}")
            return []
            
    def clear_group_memory(self, group_id: str) -> bool:
        """
        清空群聊记忆
        
        Args:
            group_id: 群聊ID
            
        Returns:
            bool: 是否成功清空
        """
        try:
            if group_id not in self.rag_managers:
                logger.warning(f"群聊 {group_id} 未初始化 RAG 系统")
                return False
                
            # 清空 RAG 存储
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self.rag_managers[group_id].clear_storage(),
                    loop
                )
                future.result()
            else:
                loop.run_until_complete(self.rag_managers[group_id].clear_storage())
            
            return True
            
        except Exception as e:
            logger.error(f"清空群聊记忆失败: {str(e)}")
            return False

    def get_message_by_content(self, group_id: str, content: str) -> Optional[Dict]:
        """
        根据消息内容查找消息
        
        Args:
            group_id: 群聊ID
            content: 消息内容
            
        Returns:
            Optional[Dict]: 找到的消息，如果未找到则返回None
        """
        try:
            # 检查输入
            if not content or not content.strip():
                logger.warning("查找的消息内容为空")
                return None
                
            # 获取memory.json文件路径
            safe_group_id = self._get_safe_group_id(group_id)
            memory_json_path = os.path.join(
                self.root_dir,
                "data",
                "avatars",
                self.avatar_name,
                "groups",
                safe_group_id,
                "memory.json"
            )
            
            if not os.path.exists(memory_json_path):
                logger.warning(f"群聊 {group_id} 的memory.json文件不存在")
                return None
            
            # 读取文件内容
            with open(memory_json_path, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
            
            # 检查群聊ID是否存在
            if group_id not in memory_data:
                logger.warning(f"群聊 {group_id} 在memory.json中不存在")
                return None
            
            # 获取消息列表
            messages = memory_data[group_id]
            
            # 按时间戳倒序排序（最新的优先）
            messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            content_clean = content.strip()
            
            # 首先尝试精确匹配
            for msg in messages:
                msg_content = msg.get("human_message", "").strip()
                if msg_content == content_clean:
                    logger.info(f"找到精确匹配的消息: {msg_content[:30]}...")
                    return msg
            
            # 如果引用的是图片内容，尝试匹配[图片内容]标记的消息
            if "[图片]" in content_clean or "图片内容" in content_clean:
                for msg in messages:
                    msg_content = msg.get("human_message", "").strip()
                    if "[图片内容]" in msg_content or "[图片]" in msg_content:
                        logger.info(f"找到匹配的图片消息: {msg_content[:30]}...")
                        return msg
            
            # 尝试部分匹配（检查引用内容是否是原始消息的子串）
            # 限制在最近20条消息中搜索，避免匹配过旧的消息
            recent_messages = messages[:20]
            for msg in recent_messages:
                msg_content = msg.get("human_message", "").strip()
                # 如果消息内容很短(少于5个字符)，则要求完全匹配
                if len(msg_content) < 5:
                    if msg_content == content_clean:
                        logger.info(f"找到短消息的精确匹配: {msg_content}")
                        return msg
                # 对于长消息，如果引用内容是原始消息的一部分，也视为匹配
                elif (content_clean in msg_content or 
                     any(word in msg_content for word in content_clean.split() if len(word) > 1)):
                    logger.info(f"找到部分匹配的消息: 引用[{content_clean[:15]}...] 在 [{msg_content[:30]}...]")
                    return msg
            
            logger.info(f"未找到匹配的消息，内容: {content_clean[:30]}...")
            return None
            
        except Exception as e:
            logger.error(f"根据内容查找消息失败: {str(e)}")
            return None 
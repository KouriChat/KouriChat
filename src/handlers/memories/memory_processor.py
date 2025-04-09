"""
记忆处理器 - 中层代码
负责管控记忆的过滤格式化、写入、读取等功能
"""
import os
import logging
import json
import time
import asyncio
import re
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
from datetime import datetime

# 导入底层核心
from src.handlers.memories.core.memory_utils import clean_memory_content, get_memory_path
from src.handlers.memories.core.rag import RagManager
from src.api_client.wrapper import APIWrapper
from src.utils.logger import get_logger

# 设置日志
logger = logging.getLogger('main')

class MemoryProcessor:
    """
    记忆处理器，中层模块，管理所有记忆操作
    """
    
    _instance = None  # 单例实例
    _initialized = False  # 初始化标志
    
    def __new__(cls, *args, **kwargs):
        """
        实现单例模式
        """
        if cls._instance is None:
            logger.info("创建记忆处理器单例实例")
            cls._instance = super(MemoryProcessor, cls).__new__(cls)
        return cls._instance
        
    def __init__(self, root_dir: str = None, api_wrapper: APIWrapper = None, rag_config_path: str = None):
        """
        初始化记忆处理器
        
        Args:
            root_dir: 项目根目录
            api_wrapper: API调用包装器
            rag_config_path: RAG配置文件路径
        """
        # 避免重复初始化
        if MemoryProcessor._initialized:
            # 如果切换了角色，需要重新加载记忆
            if self.root_dir != root_dir:
                logger.info("检测到角色切换，重新加载记忆")
                self.root_dir = root_dir
                self.reload_memory()
            return
            
        # 设置根目录
        self.root_dir = root_dir or os.getcwd()
        self.api_wrapper = api_wrapper
        
        # 初始化基本属性
        self.memory_data = {}  # 记忆数据
        self.embedding_data = {}  # 嵌入向量数据
        self.memory_hooks = []  # 记忆钩子
        self.memory_count = 0  # 记忆数量
        self.embedding_count = 0  # 嵌入向量数量
        
        # 记忆文件路径
        self.memory_path = get_memory_path(self.root_dir)
        logger.info(f"记忆文件路径: {self.memory_path}")
        
        # 初始化组件
        logger.info("初始化记忆处理器")
        self._load_memory()
        
        # 初始化RAG
        self.rag_manager = None
        if rag_config_path:
            self.init_rag(rag_config_path)
        
        # 标记为已初始化
        MemoryProcessor._initialized = True
        logger.info("记忆处理器初始化完成")
        
    def _load_memory(self):
        """加载记忆数据"""
        try:
            if os.path.exists(self.memory_path):
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.memory_data = data.get("memories", {})
                    self.embedding_data = data.get("embeddings", {})
                
                # 判断是否为最新的JSON格式（私聊或群聊）
                is_new_format = True
                for user_id, memories in self.memory_data.items():
                    # 检查是否为列表格式
                    if not isinstance(memories, list):
                        is_new_format = False
                        break
                    # 检查记忆条目的格式
                    if memories and isinstance(memories[0], dict):
                        if "human_message" not in memories[0] or "assistant_message" not in memories[0]:
                            is_new_format = False
                            break
                
                if is_new_format:
                    # 新格式直接使用，无需转换
                    logger.info("检测到新的JSON格式记忆，直接加载")
                    self.memory_count = sum(len(memories) for memories in self.memory_data.values() if isinstance(memories, list))
                    self.embedding_count = len(self.embedding_data)
                    logger.info(f"从 {self.memory_path} 加载了 {self.memory_count} 条记忆和 {self.embedding_count} 条嵌入向量")
                    return
                
                # 以下是兼容旧格式的转换逻辑
                # 确保每个用户的记忆是列表格式，并且记忆条目格式正确
                memory_format_corrected = False
                
                # 合并错误格式的用户ID (以"["开头的时间戳格式)
                # 创建一个映射，将错误的用户ID映射到正确的用户ID
                user_id_mapping = {}
                for user_id in list(self.memory_data.keys()):
                    # 检查是否是带时间戳的错误格式
                    if user_id.startswith("["):
                        memory_format_corrected = True
                        # 提取真实用户ID，通常格式为"[时间戳]ta 私聊对你说：xxx"
                        real_user_id = None
                        # 尝试多种模式匹配
                        match_patterns = [
                            r"\[.*?\]ta\s+私聊对你说：\s*(.*?)$",  # 标准私聊格式
                            r"\[.*?\]ta\s+私聊对你说：\s*(.*?)\s*\$.*$",  # 带分隔符的格式
                            r"\[.*?\]ta.*?私聊.*?：\s*(.*?)$",  # 宽松私聊格式
                            r"\[.*?\].*?在群聊里.*?：\s*(.*?)$",  # 群聊格式
                            r"\[.*?\]\s*(.*?)\s*[在私聊].*$",  # 另一种私聊格式
                        ]
                        
                        for pattern in match_patterns:
                            match = re.search(pattern, user_id)
                            if match:
                                extracted_id = match.group(1).strip()
                                # 避免空ID或过长ID（可能是消息内容而非用户ID）
                                if extracted_id and len(extracted_id) < 30:
                                    real_user_id = extracted_id
                                    break
                        
                        if real_user_id:
                            user_id_mapping[user_id] = real_user_id
                            logger.info(f"映射错误的用户ID: '{user_id}' -> '{real_user_id}'")
                        else:
                            # 无法提取有效ID，使用默认ID
                            user_id_mapping[user_id] = "未知用户"
                            logger.warning(f"无法从 '{user_id}' 提取有效用户ID，使用默认ID")
                
                # 根据映射合并记忆数据
                for old_id, new_id in user_id_mapping.items():
                    if old_id in self.memory_data:
                        # 确保目标用户ID存在记忆列表
                        if new_id not in self.memory_data:
                            self.memory_data[new_id] = []
                        elif not isinstance(self.memory_data[new_id], list):
                            # 如果不是列表，转换为列表
                            old_data = self.memory_data[new_id]
                            self.memory_data[new_id] = []
                            # 尝试保存旧数据
                            if isinstance(old_data, dict) and old_data:
                                try:
                                    for k, v in old_data.items():
                                        self.memory_data[new_id].append({
                                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                            "human_message": k,
                                            "assistant_message": v
                                        })
                                except Exception as e:
                                    logger.error(f"转换旧数据格式失败: {str(e)}")
                        
                        # 将旧ID的记忆添加到新ID下
                        old_memories = self.memory_data[old_id]
                        if isinstance(old_memories, list):
                            # 修复记忆条目中的human_message和assistant_message颠倒问题
                            for memory in old_memories:
                                if isinstance(memory, dict):
                                    # 检查assistant_message是否是用户ID，如果是则交换
                                    if memory.get("assistant_message") == new_id:
                                        temp = memory.get("human_message", "")
                                        memory["human_message"] = memory.get("assistant_message", "")
                                        memory["assistant_message"] = temp
                            
                            # 添加到新ID的记忆列表
                            self.memory_data[new_id].extend(old_memories)
                            logger.info(f"已合并 {len(old_memories)} 条记忆从 '{old_id}' 到 '{new_id}'")
                        
                        # 删除旧ID的记忆
                        del self.memory_data[old_id]
                        memory_format_corrected = True
                
                # 确保所有用户的记忆都是列表格式（标准化为新格式）
                for user_id in list(self.memory_data.keys()):
                    if not isinstance(self.memory_data[user_id], list):
                        memory_format_corrected = True
                        old_data = self.memory_data[user_id]
                        self.memory_data[user_id] = []
                        
                        # 尝试转换非列表格式的记忆
                        if isinstance(old_data, dict):
                            for key, value in old_data.items():
                                entry = {
                                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "human_message": key,
                                    "assistant_message": value
                                }
                                self.memory_data[user_id].append(entry)
                        
                        logger.info(f"已将用户 '{user_id}' 的记忆转换为列表格式")
                
                # 验证每个记忆条目的格式
                for user_id, memories in self.memory_data.items():
                    if isinstance(memories, list):
                        for i, memory in enumerate(memories):
                            if not isinstance(memory, dict) or "human_message" not in memory or "assistant_message" not in memory:
                                memory_format_corrected = True
                                # 尝试修复格式
                                if isinstance(memory, dict):
                                    # 确保所需的键存在
                                    if "timestamp" not in memory:
                                        memory["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                                    if "human_message" not in memory:
                                        memory["human_message"] = "未知消息"
                                    if "assistant_message" not in memory:
                                        memory["assistant_message"] = "未知回复"
                                    memories[i] = memory
                                else:
                                    # 无法修复，用默认条目替换
                                    memories[i] = {
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                        "human_message": "格式错误的记忆",
                                        "assistant_message": str(memory)
                                    }
                
                # 如果有修正，保存更新后的数据
                if memory_format_corrected:
                    logger.info("检测到并修复了记忆格式问题，将保存修复后的格式")
                    self.save()
                
                self.memory_count = sum(len(memories) for memories in self.memory_data.values() if isinstance(memories, list))
                self.embedding_count = len(self.embedding_data)
                logger.info(f"从 {self.memory_path} 加载了 {self.memory_count} 条记忆和 {self.embedding_count} 条嵌入向量")
            else:
                logger.info(f"记忆文件 {self.memory_path} 不存在，将创建新文件")
                self.memory_data = {}
                self.embedding_data = {}
                self.save()
        except Exception as e:
            logger.error(f"加载记忆数据失败: {str(e)}")
            # 重置数据
            self.memory_data = {}
            self.embedding_data = {}
    
    def init_rag(self, config_path):
        """
        初始化RAG系统
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            RagManager: RAG管理器实例
        """
        try:
            logger.info(f"初始化RAG系统，配置文件: {config_path}")
            self.rag_manager = RagManager(config_path, self.api_wrapper)
            logger.info("RAG系统初始化成功")
            return self.rag_manager
        except Exception as e:
            logger.error(f"初始化RAG系统失败: {str(e)}")
            return None
            
    def get_rag(self):
        """
        获取RAG管理器
        
        Returns:
            RagManager: RAG管理器实例
        """
        return self.rag_manager
    
    def save(self):
        """
        保存记忆数据
        
        Returns:
            bool: 是否成功保存
        """
        logger.info(f"开始保存记忆数据到 {self.memory_path}")
        try:
            # 确保目录存在
            memory_dir = os.path.dirname(self.memory_path)
            os.makedirs(memory_dir, exist_ok=True)
            
            # 使用临时文件进行安全写入
            import tempfile
            import shutil
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', 
                                            encoding='utf-8', 
                                            suffix='.json', 
                                            prefix='memory_', 
                                            dir=memory_dir, 
                                            delete=False) as temp_file:
                # 将数据写入临时文件
                json.dump({
                    "memories": self.memory_data,
                    "embeddings": self.embedding_data,
                }, temp_file, ensure_ascii=False, indent=2)
                
                # 确保数据刷新到磁盘
                temp_file.flush()
                os.fsync(temp_file.fileno())
                
                # 保存临时文件路径用于后续操作
                temp_path = temp_file.name
            
            # 创建一个备份文件
            if os.path.exists(self.memory_path):
                backup_path = f"{self.memory_path}.bak"
                try:
                    shutil.copy2(self.memory_path, backup_path)
                    logger.debug(f"已创建记忆文件备份: {backup_path}")
                except Exception as backup_err:
                    # 备份失败不阻止继续操作，但会记录日志
                    logger.warning(f"创建记忆文件备份失败: {str(backup_err)}")
            
            # 使用原子操作替换旧文件
            try:
                # 在Windows上，可能需要先删除目标文件
                if os.name == 'nt' and os.path.exists(self.memory_path):
                    os.unlink(self.memory_path)
                
                # 原子重命名操作
                shutil.move(temp_path, self.memory_path)
                logger.info(f"记忆数据已安全保存到 {self.memory_path}")
                
                # 清理可能的旧备份文件
                old_backups = [f for f in os.listdir(memory_dir) 
                              if f.startswith(os.path.basename(self.memory_path) + ".bak")
                              and os.path.isfile(os.path.join(memory_dir, f))]
                
                # 保留最近的5个备份
                if len(old_backups) > 5:
                    # 按修改时间排序
                    old_backups.sort(key=lambda f: os.path.getmtime(os.path.join(memory_dir, f)))
                    # 删除最旧的备份
                    for old_bak in old_backups[:-5]:
                        try:
                            os.remove(os.path.join(memory_dir, old_bak))
                            logger.debug(f"已删除旧备份文件: {old_bak}")
                        except Exception as del_err:
                            logger.warning(f"删除旧备份文件失败: {str(del_err)}")
                
                return True
            except Exception as move_err:
                logger.error(f"替换记忆文件失败: {str(move_err)}")
                
                # 尝试从备份恢复
                backup_path = f"{self.memory_path}.bak"
                if os.path.exists(backup_path):
                    try:
                        shutil.copy2(backup_path, self.memory_path)
                        logger.info(f"已从备份恢复记忆文件")
                    except Exception as restore_err:
                        logger.error(f"从备份恢复失败: {str(restore_err)}")
                
                return False
        except Exception as e:
            logger.error(f"保存记忆数据失败: {str(e)}")
            return False
            
    def clear_memories(self):
        """
        清空所有记忆
        
        Returns:
            bool: 是否成功清空
        """
        try:
            self.memory_data = {}
            self.embedding_data = {}
            self.memory_count = 0
            self.embedding_count = 0
            
            # 清空RAG存储
            if self.rag_manager:
                self.rag_manager.clear_storage()
                
            self.save()
            logger.info("已清空所有记忆")
            return True
        except Exception as e:
            logger.error(f"清空记忆失败: {str(e)}")
            return False
        
    def add_memory_hook(self, hook: Callable):
        """
        添加记忆钩子
        
        Args:
            hook: 钩子函数，接收记忆键和值作为参数
        """
        self.memory_hooks.append(hook)
        logger.debug(f"已添加记忆钩子: {hook.__name__}")
        
    def remember(self, user_id: str, user_message: str, assistant_response: str) -> bool:
        """
        记住对话
        
        Args:
            user_id: 用户ID
            user_message: 用户消息
            assistant_response: 助手回复
            
        Returns:
            bool: 是否成功记住
        """
        try:
            # 检查是否为API错误消息，如果是则不存储
            api_error_patterns = [
                "无法连接到API服务器", 
                "API请求失败", 
                "连接超时", 
                "无法访问API", 
                "API返回错误",
                "抱歉，我暂时无法连接",
                "无法连接到服务器",
                "网络连接问题",
                "服务暂时不可用"
            ]
            
            # 检查助手回复是否包含API错误信息
            if any(pattern in assistant_response for pattern in api_error_patterns):
                logger.info("检测到API错误消息，跳过存储记忆")
                return False
            
            # 获取当前角色名
            try:
                from src.config import config
                avatar_name = config.behavior.context.avatar_dir
                if not avatar_name:
                    logger.error("未设置当前角色")
                    avatar_name = "default"
            except Exception as e:
                logger.error(f"获取角色名失败: {str(e)}")
                avatar_name = "default"
            
            # 清理用户ID - 确保使用真实用户ID而不是格式化的消息内容
            clean_user_id = user_id
            
            # 检查用户ID是否包含时间戳和消息内容格式
            if isinstance(user_id, str) and user_id.startswith("[") and "]" in user_id:
                # 尝试提取真实用户ID
                match_patterns = [
                    r"\[.*?\]ta\s+私聊对你说：\s*(.*?)$",  # 标准私聊格式
                    r"\[.*?\]ta\s+私聊对你说：\s*(.*?)\s*\$.*$",  # 带分隔符的格式
                    r"\[.*?\]ta.*?私聊.*?：\s*(.*?)$",  # 宽松私聊格式
                    r"\[.*?\].*?在群聊里.*?：\s*(.*?)$",  # 群聊格式
                    r"\[.*?\]\s*(.*?)\s*[在私聊].*$",  # 另一种私聊格式
                ]
                
                for pattern in match_patterns:
                    match = re.search(pattern, user_id)
                    if match:
                        extracted_id = match.group(1).strip()
                        # 避免空ID或过长ID（可能是消息内容而非用户ID）
                        if extracted_id and len(extracted_id) < 30:
                            clean_user_id = extracted_id
                            logger.info(f"从消息格式中提取用户ID: '{user_id}' -> '{clean_user_id}'")
                            break
            
            # 判断是否为主动消息
            is_auto_message = False
            if user_message is None:
                is_auto_message = True
                user_message = ""  # 确保用户消息不是None
            elif (("系统指令" in user_message and assistant_response) or 
                  (isinstance(user_message, str) and user_message.strip().startswith("(此时时间为") and "[系统指令]" in user_message)):
                # 如果用户消息包含"系统指令"，则认为是主动消息
                logger.info("检测到主动消息")
                is_auto_message = True
            
            # 清理消息内容
            clean_user_msg, clean_assistant_msg = clean_memory_content(user_message, assistant_response)
            
            # 额外清理：确保移除memory_number及其后续内容
            if isinstance(clean_assistant_msg, str):
                clean_assistant_msg = re.sub(r'\s*memory_number:.*?($|\n)', '', clean_assistant_msg)
                
                # 确保移除memory_number和$分隔符混合情况
                clean_assistant_msg = re.sub(r'\s*memory_number:.*?\$', '', clean_assistant_msg)
                
                # 最后一道防线：直接移除包含memory_number的整行
                if "memory_number:" in clean_assistant_msg:
                    lines = clean_assistant_msg.split('\n')
                    clean_lines = [line for line in lines if "memory_number:" not in line]
                    clean_assistant_msg = '\n'.join(clean_lines)
            
            # 清理场景转换标记和其他新增标记
            def clean_rag_content(text):
                """清理要存入RAG的内容"""
                if not isinstance(text, str):
                    return "" if text is None else str(text)
                    
                # 移除场景转换标记
                text = re.sub(r'\n\[场景切换：[^\]]+\]\n', ' ', text)
                # 移除时间戳
                text = re.sub(r'\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?\]', '', text)
                # 移除对话标记
                text = re.sub(r'ta(?:私聊|在群聊里)对你说[：:]\s*', '', text)
                # 移除其他系统标记
                text = re.sub(r'\[系统[^\]]*\].*?\[/系统[^\]]*\]', '', text)
                # 将$符号替换为空格
                text = re.sub(r'\s*\$\s*', ' ', text)
                # 移除多余的空白字符
                text = re.sub(r'\s+', ' ', text)
                return text.strip()
            
            # 创建记忆条目
            memory_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "human_message": "" if is_auto_message else clean_user_msg.replace('$', ' '),  # 自动消息人类部分为空字符串
                "assistant_message": clean_assistant_msg.replace('$', ' ') if isinstance(clean_assistant_msg, str) else str(clean_assistant_msg)
            }
            
            # 使用用户ID作为键，而不是从消息中提取
            memory_key = clean_user_id
            
            # 确保用户ID存在于记忆数据中，并且是列表形式
            if memory_key not in self.memory_data:
                self.memory_data[memory_key] = []
            elif not isinstance(self.memory_data[memory_key], list):
                # 如果当前不是列表形式，转换为列表形式
                old_data = self.memory_data[memory_key]
                self.memory_data[memory_key] = []
                if old_data and isinstance(old_data, dict):  # 如果有旧数据，添加为第一个元素
                    for key, value in old_data.items():
                        if isinstance(key, str) and isinstance(value, str):
                            self.memory_data[memory_key].append({
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "human_message": key.replace('$', ' '),  # 替换$为空格
                                "assistant_message": value.replace('$', ' ')  # 替换$为空格
                            })
            
            # 添加到记忆数据 - 以数组形式存储
            logger.info(f"准备将记忆条目添加到 memory_data (用于 memory.json) - User: {memory_key}")
            self.memory_data[memory_key].append(memory_entry)
            self.memory_count = sum(len(memories) if isinstance(memories, list) else 1 for memories in self.memory_data.values())
            logger.info(f"已添加记忆条目到 memory_data，当前 memory_count: {self.memory_count}")
            
            # 添加到RAG系统
            if self.rag_manager and not is_auto_message:  # 主动消息不添加到RAG
                # 清理用户消息和助手回复
                clean_user_msg = clean_rag_content(clean_user_msg)
                clean_assistant_msg = clean_rag_content(clean_assistant_msg)
                
                # 构建记忆文档
                memory_doc = {
                    "id": f"memory_{int(time.time())}",
                    "content": f"{clean_user_id}: {clean_user_msg}\n{avatar_name}: {clean_assistant_msg}",
                    "metadata": {
                        "sender": clean_user_id,
                        "receiver": avatar_name,
                        "sender_text": clean_user_msg,
                        "receiver_text": clean_assistant_msg,
                        "timestamp": memory_entry["timestamp"],
                        "type": "chat",
                        "user_id": avatar_name
                    }
                }
                
                # 预处理过滤 - 检查内容质量
                if self._is_valid_for_rag(clean_user_msg, clean_assistant_msg):
                    # 使用线程池异步处理RAG添加操作
                    try:
                        # 直接调用方法，不再使用线程
                        logger.info(f"开始添加记忆到RAG: {clean_user_msg[:30]}...，角色: {avatar_name}")
                        success = self._add_to_rag(memory_doc)
                        if success:
                            logger.info("成功添加记忆到RAG系统")
                        else:
                            logger.warning("添加记忆到RAG系统失败")
                    except Exception as e:
                        logger.error(f"添加记忆到RAG系统出错: {str(e)}")
            
            # 调用钩子
            for hook in self.memory_hooks:
                hook(memory_key, memory_entry)
            
            # 保存到文件
            logger.info("准备调用 self.save() 将 memory_data 保存到 memory.json")
            save_success = self.save()
            if save_success:
                logger.info(f"成功调用 self.save() 并保存 memory.json，当前记忆数量: {self.memory_count}")
            else:
                logger.error(f"调用 self.save() 失败，memory.json 可能未更新")
            return True
        except Exception as e:
            logger.error(f"记住对话失败: {str(e)}")
            return False
    
    def _extract_key_from_message(self, message: str) -> str:
        """
        从消息中提取关键词作为记忆键
        
        Args:
            message: 用户消息
            
        Returns:
            str: 提取的关键词，用于作为简化的记忆键
        """
        try:
            if not isinstance(message, str) or not message.strip():
                return "默认记忆"
                
            # 清理消息，去除特殊字符和标点
            clean_msg = message.strip()
            
            # 检测是否包含"发送了一个动画表情"或"发送了表情包"
            has_animation = False
            if "发送了一个动画表情" in clean_msg:
                has_animation = True
                clean_msg = "发送了一个动画表情"
            elif "发送了表情包" in clean_msg:
                has_animation = True
                match = re.search(r"发送了表情包[：:]\s*(.*?)(?:。|$)", clean_msg)
                if match:
                    emoji_desc = match.group(1).strip()
                    clean_msg = f"发送了表情包 $ {emoji_desc}"
                else:
                    clean_msg = "发送了表情包"
            
            # 如果不是表情包，提取前几个词作为键
            if not has_animation:
                # 首先尝试提取最多5个词或30个字符，以较短者为准
                words = re.findall(r'[\w\u4e00-\u9fff]+', clean_msg)
                if words:
                    # 提取前5个词
                    key_words = words[:5]
                    key = " ".join(key_words)
                    
                    # 如果太长，截断到30个字符
                    if len(key) > 30:
                        key = key[:30]
                else:
                    # 如果没有提取到词，使用原始消息的前30个字符
                    key = clean_msg[:30]
            else:
                key = clean_msg
                
            # 检测是否有额外关键词，如果有，使用$分隔添加
            extra_keywords = []
            
            # 检测常见的表情关键词
            emoji_keywords = ["嘿嘿", "嘤嘤嘤", "哈喽", "你好", "笑死"]
            for keyword in emoji_keywords:
                if keyword in message and keyword not in key:
                    extra_keywords.append(keyword)
            
            # 组合最终键
            if extra_keywords:
                # 最多添加两个额外关键词
                extra_str = " $ ".join(extra_keywords[:2])
                key = f"{key} $ {extra_str}"
            
            return key
        except Exception as e:
            logger.error(f"提取记忆键失败: {str(e)}")
            return "默认记忆"
    
    def _add_to_rag(self, memory_doc):
        """
        添加记忆到RAG系统（直接方法而非线程）
        
        Args:
            memory_doc: 记忆文档
            
        Returns:
            bool: 是否成功添加
        """
        try:
            if not self.rag_manager:
                logger.warning("RAG管理器未初始化，无法添加记忆到RAG系统")
                return False
                
            # 创建事件循环
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 在事件循环中运行异步方法
                result = loop.run_until_complete(self.rag_manager.add_document(memory_doc))
                loop.close()
                
                if result:
                    logger.info(f"成功添加记忆到RAG系统: {memory_doc['id']}")
                else:
                    logger.warning(f"添加记忆到RAG系统失败: {memory_doc['id']}")
                
                return result
            except Exception as e:
                logger.error(f"在调用RAG添加文档时出错: {str(e)}", exc_info=True)
                return False
        except Exception as e:
            logger.error(f"添加记忆到RAG系统失败: {str(e)}", exc_info=True)
            return False
    
    def _is_valid_for_rag(self, sender_text: str, receiver_text: str) -> bool:
        """
        检查内容是否适合添加到RAG系统
        
        Args:
            sender_text: 发送者文本
            receiver_text: 接收者文本
            
        Returns:
            bool: 是否适合添加到RAG
        """
        # 用户要求所有消息都要添加到RAG，移除长度限制
        # 原有的长度检查（已废弃）:
        # if len(sender_text) < 5 or len(receiver_text) < 5:
        #     logger.info(f"RAG filter: Text too short. Sender: {len(sender_text)}, Receiver: {len(receiver_text)}")
        #     return False
        
        # 允许短消息，只记录长度信息但不过滤
        if len(sender_text) < 5 or len(receiver_text) < 5:
            logger.info(f"短文本消息添加到RAG: Sender长度: {len(sender_text)}, Receiver长度: {len(receiver_text)}")
            
        # 检查是否包含特定的无意义内容
        noise_patterns = [
            "你好", "在吗", "谢谢", "没事了", "好的", "嗯嗯", "好", "是的", "不是",
            "你是谁", "你叫什么", "再见", "拜拜", "晚安", "早安", "午安"
        ]
        
        # 修改：不再过滤噪音模式，只记录日志
        if sender_text.strip() in noise_patterns or receiver_text.strip() in noise_patterns:
            logger.info(f"包含噪音模式但仍添加到RAG: Sender: '{sender_text[:20]}...', Receiver: '{receiver_text[:20]}...'")
            # 不再返回 False
            
        # 检查是否为API错误消息
        api_error_patterns = [
            "无法连接到API服务器", 
            "API请求失败", 
            "连接超时", 
            "无法访问API", 
            "API返回错误",
            "抱歉，我暂时无法连接",
            "无法连接到服务器",
            "网络连接问题",
            "服务暂时不可用"
        ]
        
        if any(pattern in receiver_text for pattern in api_error_patterns):
            logger.info("检测到API错误消息，不适合添加到RAG")
            return False
            
        return True
        
    def retrieve(self, query: str, top_k: int = 5) -> str:
        """
        检索相关记忆（同步方法）
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            str: 格式化的记忆文本
        """
        try:
            if not self.rag_manager:
                logger.warning("RAG系统未初始化，无法检索记忆")
                return ""
            
            # 创建事件循环来运行异步查询
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # 如果没有事件循环，创建一个新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            # 在事件循环中运行异步查询
            if loop.is_running():
                # 使用future来异步运行协程
                future = asyncio.run_coroutine_threadsafe(self.rag_manager.query(query, top_k), loop)
                results = future.result()
            else:
                # 直接运行协程
                results = loop.run_until_complete(self.rag_manager.query(query, top_k))
            
            if not results or len(results) == 0:
                logger.info(f"未找到与查询 '{query}' 相关的记忆")
                return ""
                
            # 格式化结果
            formatted_results = []
            for i, result in enumerate(results):
                content = result.get('content', '')
                metadata = result.get('metadata', {})
                score = result.get('score', 0)
                
                timestamp = metadata.get('timestamp', '未知时间')
                formatted_results.append(f"记忆 {i+1} [{timestamp}] (相关度: {score:.2f}):\n{content}\n")
                
            return "\n".join(formatted_results)
        except Exception as e:
            logger.error(f"检索记忆失败: {str(e)}")
            return ""
    
    def is_important(self, text: str) -> bool:
        """
        判断文本是否包含重要信息（同步方法）
        
        Args:
            text: 需要判断的文本
            
        Returns:
            bool: 是否包含重要信息
        """
        try:
            # 如果有RAG管理器，使用它的方法判断
            if self.rag_manager:
                # 创建事件循环来运行异步查询
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # 如果没有事件循环，创建一个新的
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                # 在事件循环中运行异步查询
                if loop.is_running():
                    # 使用future来异步运行协程
                    future = asyncio.run_coroutine_threadsafe(self.rag_manager.is_important(text), loop)
                    return future.result()
                else:
                    # 直接运行协程
                    return loop.run_until_complete(self.rag_manager.is_important(text))
                
            # 否则使用简单的规则判断
            # 1. 长度判断
            if len(text) > 100:  # 长文本更可能包含重要信息
                return True
                
            # 2. 关键词判断
            important_keywords = [
                "记住", "牢记", "不要忘记", "重要", "必须", "一定要",
                "地址", "电话", "密码", "账号", "名字", "生日",
                "喜欢", "讨厌", "爱好", "兴趣"
            ]
            
            for keyword in important_keywords:
                if keyword in text:
                    return True
                    
            return False
        except Exception as e:
            logger.error(f"判断文本重要性失败: {str(e)}")
            return False
            
    async def generate_summary(self, limit: int = 20) -> str:
        """
        生成记忆摘要
        
        Args:
            limit: 摘要包含的记忆条数
            
        Returns:
            str: 记忆摘要
        """
        try:
            if not self.api_wrapper:
                logger.error("未提供API包装器，无法生成摘要")
                return ""
                
            # 如果有RAG管理器，使用它的方法生成摘要
            if self.rag_manager:
                return await self.rag_manager.generate_summary(limit)
                
            # 否则从基本记忆中生成
            if not self.memory_data:
                return "没有可用的记忆。"
                
            # 选择最新的几条记忆
            recent_memories = list(self.memory_data.items())[-limit:]
            
            # 格式化记忆
            memory_text = ""
            for i, (key, value) in enumerate(recent_memories):
                memory_text += f"记忆 {i+1}:\n用户: {key}\nAI: {value}\n\n"
                
            # 构造摘要请求
            prompt = f"""请根据以下对话记忆，总结出重要的信息点：

{memory_text}

请提供一个简洁的摘要，包含关键信息点和重要的细节。"""

            # 调用API生成摘要
            response = await self.api_wrapper.async_completion(
                prompt=prompt,
                temperature=0.3,
                max_tokens=500
            )
            
            return response.get("content", "无法生成摘要")
        except Exception as e:
            logger.error(f"生成记忆摘要失败: {str(e)}")
            return "生成摘要时出错"

    def get_stats(self):
        """
        获取记忆统计信息
        
        Returns:
            Dict: 包含记忆统计信息的字典
        """
        stats = {
            "memory_count": self.memory_count,
            "embedding_count": self.embedding_count,
        }
        
        # 如果有RAG管理器，添加嵌入模型缓存统计
        if self.rag_manager:
            try:
                embedding_model = self.rag_manager.embedding_model
                if embedding_model and hasattr(embedding_model, 'get_cache_stats'):
                    cache_stats = embedding_model.get_cache_stats()
                    
                    # 合并缓存统计到结果中
                    if isinstance(cache_stats, dict):
                        stats["cache_hits"] = cache_stats.get("hits", 0)
                        stats["cache_misses"] = cache_stats.get("misses", 0)
                        stats["cache_size"] = cache_stats.get("size", 0)
                        stats["cache_hit_rate_percent"] = 0
                        
                        # 计算命中率
                        total = stats["cache_hits"] + stats["cache_misses"]
                        if total > 0:
                            stats["cache_hit_rate_percent"] = (stats["cache_hits"] / total) * 100
            except Exception as e:
                logger.error(f"获取嵌入模型缓存统计失败: {str(e)}")
                
        return stats
    
    # 为与顶层接口兼容，添加别名
    get_memory_stats = get_stats 
    
    def get_relevant_memories(self, query, username=None, top_k=5):
        """
        获取与查询相关的记忆
        
        Args:
            query: 查询字符串
            username: 用户名（可选）
            top_k: 返回结果数量
            
        Returns:
            List[Dict]: 相关记忆列表
        """
        try:
            if not query:
                logger.info("查询为空，不执行记忆检索")
                return []
                
            logger.info(f"开始检索记忆: '{query[:30]}...' (用户: {username})")
            
            # 如果提供了username，优先直接获取该用户的记忆
            direct_matches = []
            if username and username in self.memory_data:
                logger.info(f"找到用户 '{username}' 的记忆")
                memories = self.memory_data[username]
                if isinstance(memories, list) and memories:
                    # 获取最新的几条记忆
                    recent_memories = memories[-min(top_k, len(memories)):]
                    
                    # 逆序处理，最新的记忆放在前面
                    for memory in reversed(recent_memories):
                        if isinstance(memory, dict):
                            direct_matches.append({
                                "memory": f"{memory.get('human_message', '')}",
                                "response": memory.get('assistant_message', ''),
                                "timestamp": memory.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M")),
                                "score": 1.0,  # 直接匹配给予最高分
                                "source": "direct_match"
                            })
                    
                    logger.info(f"直接获取到用户 '{username}' 的 {len(direct_matches)} 条记忆")
                    return direct_matches
            
            # 如果没有提供username或找不到该用户的记忆，使用语义搜索
            if self.rag_manager:
                results_text = self.retrieve(query, top_k)
                if results_text and results_text != "没有找到相关记忆":
                    # 解析RAG结果
                    rag_results = []
                    try:
                        # 按照记忆块分割
                        memory_blocks = results_text.split("\n\n")
                        for block in memory_blocks:
                            if not block.strip():
                                continue
                                
                            # 提取信息
                            timestamp_match = re.search(r'\[(.*?)\]', block)
                            timestamp = timestamp_match.group(1) if timestamp_match else "未知时间"
                            
                            # 提取相关度
                            score_match = re.search(r'\(相关度: ([\d.]+)\)', block)
                            score = float(score_match.group(1)) if score_match else 0.5
                            
                            # 提取内容
                            content = re.sub(r'记忆 \d+ \[.*?\] \(相关度: [\d.]+\):', '', block).strip()
                            
                            # 尝试分离对话
                            parts = content.split("\n")
                            if len(parts) >= 2:
                                # 假设第一行是用户消息，第二行是助手回复
                                user_msg = parts[0]
                                assistant_msg = parts[1]
                                
                                # 提取发送者和消息内容
                                user_match = re.search(r'(.*?):\s*(.*)', user_msg)
                                if user_match:
                                    memory_content = user_match.group(2)
                                else:
                                    memory_content = user_msg
                                    
                                assistant_match = re.search(r'(.*?):\s*(.*)', assistant_msg)
                                if assistant_match:
                                    response_content = assistant_match.group(2)
                                else:
                                    response_content = assistant_msg
                                    
                                rag_results.append({
                                    "memory": memory_content,
                                    "response": response_content,
                                    "timestamp": timestamp,
                                    "score": score,
                                    "source": "rag"
                                })
                        
                        # 排序并返回结果
                        if rag_results:
                            rag_results.sort(key=lambda x: x["score"], reverse=True)
                            logger.info(f"从RAG获取到 {len(rag_results)} 条记忆")
                            return rag_results[:top_k]
                    except Exception as e:
                        logger.error(f"解析RAG结果失败: {str(e)}")
            
            logger.info("未找到相关记忆")
            return []
            
        except Exception as e:
            logger.error(f"获取相关记忆失败: {str(e)}")
            return []

    def add_memory(self, user_id: str, human_message: str, assistant_message: str):
        """
        添加新的记忆
        
        Args:
            user_id: 用户ID
            human_message: 用户消息
            assistant_message: 助手回复
            
        Returns:
            bool: 是否成功添加
        """
        try:
            if user_id not in self.memory_data:
                self.memory_data[user_id] = []
            
            memory_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "human_message": human_message,
                "assistant_message": assistant_message
            }
            
            self.memory_data[user_id].append(memory_entry)
            self.memory_count += 1
            
            # 调用记忆钩子
            for hook in self.memory_hooks:
                hook(user_id, memory_entry)
            
            # 保存到文件
            self.save()
            return True
        except Exception as e:
            logger.error(f"添加记忆失败: {str(e)}")
            return False

    def clear_memory(self):
        """
        清理当前内存中的记忆数据
        """
        logger.info("清理内存中的记忆数据")
        self.memory_data = {}
        self.embedding_data = {}
        self.memory_count = 0
        self.embedding_count = 0
        
    def reload_memory(self):
        """
        重新加载记忆数据
        """
        logger.info("重新加载记忆数据")
        self.clear_memory()
        self._load_memory() 
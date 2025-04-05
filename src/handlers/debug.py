"""
调试命令处理模块
提供调试命令的解析和执行功能
"""

import os
import logging
import json
from typing import List, Dict, Tuple, Any, Optional
from modules.memory.diary import DiaryService  # 导入日记服务

logger = logging.getLogger('main')

class DebugCommandHandler:
    """调试命令处理器类，处理各种调试命令"""
    
    def __init__(self, root_dir: str, memory_service=None, llm_service=None, diary_service=None):
        """
        初始化调试命令处理器
        
        Args:
            root_dir: 项目根目录
            memory_service: 记忆服务实例
            llm_service: LLM服务实例
            diary_service: 日记服务实例
        """
        self.root_dir = root_dir
        self.memory_service = memory_service
        self.llm_service = llm_service
        self.diary_service = diary_service
        self.avatars_dir = os.path.join(root_dir, "data", "avatars")
        self.DEBUG_PREFIX = "/"
        
        # 如果没有提供日记服务，则尝试初始化
        if self.diary_service is None and llm_service:
            from config import config
            try:
                self.diary_service = DiaryService(
                    root_dir=root_dir,
                    api_key=config.llm.api_key,
                    base_url=config.llm.base_url,
                    model=config.llm.model,
                    max_token=config.llm.max_tokens,
                    temperature=config.llm.temperature
                )
                logger.info("日记服务已初始化")
            except Exception as e:
                logger.error(f"初始化日记服务失败: {str(e)}")
                self.diary_service = None
        
    def is_debug_command(self, message: str) -> bool:
        """
        判断消息是否为调试命令
        
        Args:
            message: 用户消息
            
        Returns:
            bool: 是否为调试命令
        """
        return message.strip().startswith(self.DEBUG_PREFIX)
    
    def process_command(self, command: str, current_avatar: str, user_id: str) -> Tuple[bool, str]:
        """
        处理调试命令
        
        Args:
            command: 调试命令（包含/前缀）
            current_avatar: 当前角色名
            user_id: 用户ID
            
        Returns:
            Tuple[bool, str]: (是否需要拦截普通消息处理, 响应消息)
        """
        # 去除前缀并转为小写
        cmd = command.strip()[1:].lower()
        
        # 帮助命令
        if cmd == "help":
            return True, self._get_help_message()
            
        # 显示当前角色记忆
        elif cmd == "mem":
            return True, self._show_memory(current_avatar)
            
        # 重置当前角色的最近记忆
        elif cmd == "reset":
            return True, self._reset_short_memory(current_avatar)
            
        # 清空当前角色的核心记忆
        elif cmd == "clear":
            return True, self._clear_core_memory(current_avatar)
            
        # 清空当前角色的对话上下文
        elif cmd == "context":
            return True, self._clear_context(user_id)
        
        # 生成日记
        elif cmd == "diary":
            return True, self._generate_diary(current_avatar)
            
        # 退出调试模式
        elif cmd == "exit":
            return True, "已退出调试模式"
            
        # 无效命令
        else:
            return True, f"未知命令: {cmd}\n使用 /help 查看可用命令"
    
    def _get_help_message(self) -> str:
        """获取帮助信息"""
        return """调试模式命令:
- /help: 显示此帮助信息
- /mem: 显示当前角色的记忆
- /reset: 重置当前角色的最近记忆
- /clear: 清空当前角色的核心记忆
- /context: 清空当前角色的对话上下文
- /diary: 生成角色小日记
- /exit: 退出调试模式"""
    
    def _show_memory(self, avatar_name: str) -> str:
        """
        显示当前角色的记忆
        
        Args:
            avatar_name: 角色名
            
        Returns:
            str: 记忆信息
        """
        if not self.memory_service:
            return "错误: 记忆服务未初始化"
            
        try:
            # 获取核心记忆
            core_memory = self.memory_service.get_core_memory(avatar_name)
            
            # 获取短期记忆路径
            short_memory_path = os.path.join(
                self.avatars_dir, avatar_name, "memory", "short_memory.json"
            )
            
            # 读取最近5轮对话
            recent_dialogues = []
            if os.path.exists(short_memory_path):
                with open(short_memory_path, "r", encoding="utf-8") as f:
                    short_memory = json.load(f)
                    # 只取最近5轮对话
                    recent_dialogues = short_memory[-5:]
                    logger.info(f"读取到 {len(recent_dialogues)} 条对话记录")
            
            # 组装信息
            result = f"【当前角色: {avatar_name}】\n\n"
            
            # 显示核心记忆
            result += "【核心记忆】\n"
            if core_memory:
                try:
                    core_data = json.loads(core_memory)
                    result += f"{core_data.get('content', '')}\n"
                except:
                    result += f"{core_memory}\n"
            else:
                result += "(无)\n"
            
            # 显示最近对话
            result += "\n【最近对话】\n"
            if recent_dialogues:
                for i, dialogue in enumerate(reversed(recent_dialogues), 1):
                    try:
                        # 获取用户消息，去掉时间戳
                        user_msg = dialogue.get('user', '')
                        if '\n' in user_msg:
                            user_msg = user_msg.split('\n')[-1]
                        if ']' in user_msg:
                            user_msg = user_msg.split(']')[-1]
                        
                        # 获取机器人消息，只取第一段
                        bot_msg = dialogue.get('bot', '')
                        if '$' in bot_msg:
                            bot_msg = bot_msg.split('$')[0]
                        
                        result += f"{i}. User: {user_msg}\n   AI: {bot_msg}\n"
                    except Exception as e:
                        logger.error(f"处理对话记录时出错: {str(e)}")
                        continue
            else:
                result += "(无)\n"
            
            return result
            
        except Exception as e:
            logger.error(f"显示记忆失败: {str(e)}")
            return f"显示记忆时出错: {str(e)}"
    
    def _reset_short_memory(self, avatar_name: str) -> str:
        """
        重置当前角色的最近记忆
        
        Args:
            avatar_name: 角色名
            
        Returns:
            str: 操作结果
        """
        try:
            short_memory_path = os.path.join(
                self.avatars_dir, avatar_name, "memory", "short_memory.json"
            )
            
            if not os.path.exists(short_memory_path):
                return f"角色 {avatar_name} 没有短期记忆文件"
            
            # 重置为空列表
            with open(short_memory_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
                
            logger.info(f"已重置角色 {avatar_name} 的短期记忆")
            return f"已重置角色 {avatar_name} 的短期记忆"
            
        except Exception as e:
            logger.error(f"重置短期记忆失败: {str(e)}")
            return f"重置短期记忆时出错: {str(e)}"
    
    def _clear_core_memory(self, avatar_name: str) -> str:
        """
        清空当前角色的核心记忆
        
        Args:
            avatar_name: 角色名
            
        Returns:
            str: 操作结果
        """
        try:
            if not self.memory_service:
                return "错误: 记忆服务未初始化"
                
            core_memory_path = os.path.join(
                self.avatars_dir, avatar_name, "memory", "core_memory.json"
            )
            
            if not os.path.exists(core_memory_path):
                return f"角色 {avatar_name} 没有核心记忆文件"
            
            # 清空核心记忆内容，保留文件结构
            core_data = {
                "timestamp": self.memory_service._get_timestamp(),
                "content": ""
            }
            
            with open(core_memory_path, "w", encoding="utf-8") as f:
                json.dump(core_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"已清空角色 {avatar_name} 的核心记忆")
            return f"已清空角色 {avatar_name} 的核心记忆"
            
        except Exception as e:
            logger.error(f"清空核心记忆失败: {str(e)}")
            return f"清空核心记忆时出错: {str(e)}"
    
    def _clear_context(self, user_id: str) -> str:
        """
        清空当前用户的对话上下文
        
        Args:
            user_id: 用户ID
            
        Returns:
            str: 操作结果
        """
        try:
            if not self.llm_service:
                return "错误: LLM服务未初始化"
                
            # 清空用户上下文
            if user_id in self.llm_service.chat_contexts:
                self.llm_service.chat_contexts[user_id] = []
                logger.info(f"已清空用户 {user_id} 的对话上下文")
                return f"已清空当前对话上下文"
            else:
                return "当前没有活跃的对话上下文"
                
        except Exception as e:
            logger.error(f"清空对话上下文失败: {str(e)}")
            return f"清空对话上下文时出错: {str(e)}"
    
    def _generate_diary(self, avatar_name: str) -> str:
        """
        生成当前角色的日记
        
        Args:
            avatar_name: 角色名
            
        Returns:
            str: 生成的日记内容
        """
        if not self.diary_service:
            return "错误: 日记服务未初始化"
            
        try:
            # 生成日记
            diary_content = self.diary_service.generate_diary(avatar_name)
            
            if not diary_content or diary_content.startswith("无法"):
                return diary_content
                
            logger.info(f"已生成{avatar_name}小日记")
            return diary_content
            
        except Exception as e:
            logger.error(f"生成日记失败: {str(e)}")
            return f"日记生成失败: {str(e)}" 
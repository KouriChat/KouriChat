"""
调试命令处理模块
提供调试命令的解析和执行功能
"""

import os
import logging
import json
import threading
from datetime import datetime
from typing import List, Dict, Tuple, Any, Optional, Callable
from modules.memory.content_generator import ContentGenerator  # 导入内容生成服务

logger = logging.getLogger('main')

class DebugCommandHandler:
    """调试命令处理器类，处理各种调试命令"""

    def __init__(self, root_dir: str, memory_service=None, llm_service=None, content_generator=None):
        """
        初始化调试命令处理器

        Args:
            root_dir: 项目根目录
            memory_service: 记忆服务实例
            llm_service: LLM服务实例
            content_generator: 内容生成服务实例
        """
        self.root_dir = root_dir
        self.memory_service = memory_service
        self.llm_service = llm_service
        self.content_generator = content_generator
        self.DEBUG_PREFIX = "/"

        # 如果没有提供内容生成服务，尝试初始化
        if not self.content_generator:
            try:
                from data.config import config
                self.content_generator = ContentGenerator(
                    root_dir=self.root_dir,
                    api_key=config.OPENAI_API_KEY,
                    base_url=config.OPENAI_API_BASE,
                    model=config.OPENAI_API_MODEL,
                    max_token=config.OPENAI_MAX_TOKENS,
                    temperature=config.OPENAI_TEMPERATURE
                )
                logger.info("内容生成服务初始化成功")
            except Exception as e:
                logger.error(f"初始化内容生成服务失败: {str(e)}")
                self.content_generator = None

    def is_debug_command(self, message: str) -> bool:
        """
        判断消息是否为调试命令

        Args:
            message: 用户消息

        Returns:
            bool: 是否为调试命令
        """
        return message.strip().startswith(self.DEBUG_PREFIX)

    def process_command(self, command: str, current_avatar: str, user_id: str, chat_id: str = None, callback: Callable = None) -> Tuple[bool, str]:
        """
        处理调试命令

        Args:
            command: 调试命令（包含/前缀）
            current_avatar: 当前角色名
            user_id: 用户ID
            chat_id: 聊天ID，用于异步回调
            callback: 回调函数，用于异步处理生成的内容

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
            return True, self._show_memory(current_avatar, user_id)

        # 重置当前角色的最近记忆
        elif cmd == "reset":
            return True, self._reset_short_memory(current_avatar, user_id)

        # 清空当前角色的核心记忆
        elif cmd == "clear":
            return True, self._clear_core_memory(current_avatar, user_id)

        # 清空当前角色的对话上下文
        elif cmd == "context":
            return True, self._clear_context(user_id)
        
        # 手动生成核心记忆
        elif cmd == "gen_core_mem":
            return True, self._gen_core_mem(current_avatar, user_id)

        # 内容生成命令，如果提供了回调函数，则使用异步方式
        elif cmd in ["diary", "state", "letter", "list", "pyq", "gift", "shopping"]:
            if callback and chat_id:
                # 使用异步方式生成内容
                return True, self._generate_content_async(cmd, current_avatar, user_id, chat_id, callback)
            else:
                # 使用同步方式生成内容
                return True, self._generate_content(cmd, current_avatar, user_id)

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
- /state: 查看角色状态
- /letter: 角色给你写的信
- /list: 角色的备忘录
- /pyq: 角色的朋友圈
- /gift: 角色想送的礼物
- /shopping: 角色的购物清单
- /exit: 退出调试模式"""

    def _gen_core_mem(self, avatar_name: str, user_id: str) -> str:
        if not self.memory_service:
            return f"错误: 记忆服务未初始化"

        context = self.memory_service.get_recent_context(avatar_name, user_id)
        if self.memory_service.update_core_memory(avatar_name, user_id, context):
            return f"成功更新核心记忆"
        else:
            return f"未能成功更新核心记忆"

    def _show_memory(self, avatar_name: str, user_id: str) -> str:
        """
        显示当前角色的记忆

        Args:
            avatar_name: 角色名
            user_id: 用户ID

        Returns:
            str: 记忆内容
        """
        if not self.memory_service:
            return "错误: 记忆服务未初始化"

        try:
            # 获取短期记忆
            # 直接读取短期记忆文件
            short_memory_path = self.memory_service._get_short_memory_path(avatar_name, user_id)
            if not os.path.exists(short_memory_path):
                return "当前角色没有短期记忆"

            try:
                with open(short_memory_path, "r", encoding="utf-8") as f:
                    short_memory = json.load(f)
                if not short_memory:
                    return "当前角色没有短期记忆"
            except Exception as e:
                logger.error(f"读取短期记忆失败: {str(e)}")
                return f"读取短期记忆失败: {str(e)}"

            # 获取核心记忆
            core_memory = self.memory_service.get_core_memory(avatar_name, user_id)
            if not core_memory:
                core_memory_str = "当前角色没有核心记忆"
            else:
                core_memory_str = core_memory

            # 格式化短期记忆
            short_memory_str = "\n\n".join([
                f"用户: {item.get('user', '')}\n回复: {item.get('bot', '')}"
                for item in short_memory[-5:]  # 只显示最近5轮对话
            ])

            return f"核心记忆:\n{core_memory_str}\n\n短期记忆:\n{short_memory_str}"

        except Exception as e:
            logger.error(f"获取记忆失败: {str(e)}")
            return f"获取记忆失败: {str(e)}"

    def _reset_short_memory(self, avatar_name: str, user_id: str) -> str:
        """
        重置当前角色的最近记忆

        Args:
            avatar_name: 角色名
            user_id: 用户ID

        Returns:
            str: 操作结果
        """
        if not self.memory_service:
            return "错误: 记忆服务未初始化"

        try:
            # 直接重置短期记忆文件
            short_memory_path = self.memory_service._get_short_memory_path(avatar_name, user_id)
            if os.path.exists(short_memory_path):
                with open(short_memory_path, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
            return f"已重置 {avatar_name} 的最近记忆"
        except Exception as e:
            logger.error(f"重置最近记忆失败: {str(e)}")
            return f"重置最近记忆失败: {str(e)}"

    def _clear_core_memory(self, avatar_name: str, user_id: str) -> str:
        """
        清空当前角色的核心记忆

        Args:
            avatar_name: 角色名
            user_id: 用户ID

        Returns:
            str: 操作结果
        """
        if not self.memory_service:
            return "错误: 记忆服务未初始化"

        try:
            # 直接清空核心记忆文件
            core_memory_path = self.memory_service._get_core_memory_path(avatar_name, user_id)
            if os.path.exists(core_memory_path):
                initial_core_data = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "content": ""  # 初始为空字符串
                }
                with open(core_memory_path, "w", encoding="utf-8") as f:
                    json.dump(initial_core_data, f, ensure_ascii=False, indent=2)
            return f"已清空 {avatar_name} 的核心记忆"
        except Exception as e:
            logger.error(f"清空核心记忆失败: {str(e)}")
            return f"清空核心记忆失败: {str(e)}"

    def _clear_context(self, user_id: str) -> str:
        """
        清空当前角色的对话上下文

        Args:
            user_id: 用户ID

        Returns:
            str: 操作结果
        """
        if not self.llm_service:
            return "错误: LLM服务未初始化"

        try:
            self.llm_service.clear_history(user_id)
            return "已清空对话上下文"
        except Exception as e:
            logger.error(f"清空对话上下文失败: {str(e)}")
            return f"清空对话上下文失败: {str(e)}"

    def _generate_content(self, content_type: str, avatar_name: str, user_id: str) -> str:
        """
        通用内容生成方法

        Args:
            content_type: 内容类型，如 'diary', 'state', 'letter'
            avatar_name: 角色名
            user_id: 用户ID

        Returns:
            str: 生成的内容
        """
        if not self.content_generator:
            return "错误: 内容生成服务未初始化"

        try:
            # 根据内容类型调用相应的方法
            content_type_methods = {
                'diary': self.content_generator.generate_diary,
                'state': self.content_generator.generate_state,
                'letter': self.content_generator.generate_letter,
                'list': self.content_generator.generate_list,
                'pyq': self.content_generator.generate_pyq,
                'gift': self.content_generator.generate_gift,
                'shopping': self.content_generator.generate_shopping
            }

            # 获取并使用相应的生成方法，或使用默认方法
            generate_method = content_type_methods.get(content_type)
            if not generate_method:
                return f"不支持的内容类型: {content_type}"

            content = generate_method(avatar_name, user_id)

            if not content or content.startswith("无法"):
                return content

            logger.info(f"已生成{avatar_name}的{content_type} 用户: {user_id}")
            return content

        except Exception as e:
            logger.error(f"生成{content_type}失败: {str(e)}")
            return f"{content_type}生成失败: {str(e)}"

    def _generate_content_async(self, content_type: str, avatar_name: str, user_id: str, chat_id: str, callback: Callable[[str, str, str], None]) -> str:
        """
        异步生成内容

        Args:
            content_type: 内容类型，如 'diary', 'state', 'letter'
            avatar_name: 角色名
            user_id: 用户ID
            chat_id: 聊天ID，用于回调发送消息
            callback: 回调函数，用于处理生成的内容

        Returns:
            str: 初始响应消息
        """
        if not self.content_generator:
            return "错误: 内容生成服务未初始化"

        # 创建异步线程执行内容生成
        def generate_thread():
            try:
                # 根据内容类型调用相应的方法
                content_type_methods = {
                    'diary': self.content_generator.generate_diary,
                    'state': self.content_generator.generate_state,
                    'letter': self.content_generator.generate_letter,
                    'list': self.content_generator.generate_list,
                    'pyq': self.content_generator.generate_pyq,
                    'gift': self.content_generator.generate_gift,
                    'shopping': self.content_generator.generate_shopping
                }

                # 获取并使用相应的生成方法，或使用默认方法
                generate_method = content_type_methods.get(content_type)
                if not generate_method:
                    result = f"不支持的内容类型: {content_type}"
                    callback(command=f"/{content_type}", reply=result, chat_id=chat_id)
                    return

                # 生成内容
                content = generate_method(avatar_name, user_id)

                if not content or content.startswith("无法"):
                    callback(command=f"/{content_type}", reply=content, chat_id=chat_id)
                    return

                logger.info(f"已生成{avatar_name}的{content_type} 用户: {user_id}")
                # 调用回调函数处理生成的内容
                callback(command=f"/{content_type}", reply=content, chat_id=chat_id)

            except Exception as e:
                error_msg = f"{content_type}生成失败: {str(e)}"
                logger.error(error_msg)
                callback(command=f"/{content_type}", reply=error_msg, chat_id=chat_id)

        # 启动异步线程
        thread = threading.Thread(target=generate_thread)
        thread.daemon = True  # 设置为守护线程，不会阻止程序退出
        thread.start()

        # 静默生成，不返回任何初始响应
        return ""

    def _generate_diary(self, avatar_name: str, user_id: str) -> str:
        """生成当前角色的日记"""
        return self._generate_content('diary', avatar_name, user_id)

    def _generate_state(self, avatar_name: str, user_id: str) -> str:
        """生成当前角色的状态信息"""
        return self._generate_content('state', avatar_name, user_id)

    def _generate_letter(self, avatar_name: str, user_id: str) -> str:
        """生成当前角色给用户写的信"""
        return self._generate_content('letter', avatar_name, user_id)

    def _generate_list(self, avatar_name: str, user_id: str) -> str:
        """生成当前角色的备忘录"""
        return self._generate_content('list', avatar_name, user_id)

    def _generate_pyq(self, avatar_name: str, user_id: str) -> str:
        """生成当前角色的朋友圈"""
        return self._generate_content('pyq', avatar_name, user_id)

    def _generate_gift(self, avatar_name: str, user_id: str) -> str:
        """生成当前角色想送的礼物"""
        return self._generate_content('gift', avatar_name, user_id)

    def _generate_shopping(self, avatar_name: str, user_id: str) -> str:
        """生成当前角色的购物清单"""
        return self._generate_content('shopping', avatar_name, user_id)

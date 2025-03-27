"""
消息处理模块
负责处理聊天消息，包括:
- 消息队列管理
- 消息分发处理
- API响应处理
- 多媒体消息处理
- 对话结束处理
"""

from datetime import datetime
import logging
import threading
import time
from wxauto import WeChat
import random
import os
from src.services.ai.llm_service import LLMService
from src.config import config
import re
import jieba
import asyncio
import math
import difflib
from src.handlers.file import FileHandler
from typing import List, Dict

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger("main")


class MessageHandler:
    def __init__(
        self,
        root_dir,
        llm: LLMService,
        robot_name,
        prompt_content,
        image_handler,
        emoji_handler,
        voice_handler,
        memory_handler,
        wx=None,
        is_debug=False,
        is_qq=False,
    ):
        self.root_dir = root_dir
        self.robot_name = robot_name
        self.prompt_content = prompt_content
        self.debug = is_debug
        # 添加消息缓存相关属性
        self.message_cache = {}  # 用户消息缓存
        self.last_message_time = {}  # 用户最后发送消息的时间
        self.message_timer = {}  # 用户消息处理定时器
        # 使用 DeepSeekAI 替换直接的 OpenAI 客户端
        self.deepseek = llm
        # 消息队列相关
        self.user_queues = {}
        self.queue_lock = threading.Lock()
        self.chat_contexts = {}
        self.auto_task_message_queue: List[Dict[str, str]] = []

        # 微信实例
        self.wx = wx
        self.is_debug = is_debug
        self.is_qq = is_qq

        # 添加 handlers
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler
        self.memory_handler = memory_handler

        # 检查是否有RAG管理器
        self.rag_manager = None
        if memory_handler and hasattr(memory_handler, "rag_manager"):
            self.rag_manager = memory_handler.rag_manager
            self.use_semantic_search = True
        else:
            self.use_semantic_search = False

        # 设置各权重比例
        self.time_weight = 0.4  # 时间权重比例
        self.semantic_weight = 0.4  # 语义相关性权重比例
        self.user_weight = 0.2  # 用户相关性权重比例

        # 定义上下文轮数
        self.private_context_turns = 5
        self.group_context_turns = 3

        # 保持独立处理的内容
        self.emotions = {}  # 情绪状态存储
        self.last_active_time = {}  # 最后活跃时间
        self.is_replying = False  # 回复状态

        # 定义数据管理参数
        self.max_memory_age = 7 * 24 * 60 * 60  # 记忆保留最大时间（7天）

        # 添加未回复计数器，用于自动重置
        self.unanswered_counters = {}
        self.unanswered_timers = {}
        self.quiet_time_config = {"start_hour": 22, "end_hour": 8}  # 默认安静时间配置

        # 添加群聊@消息处理相关属性
        self.group_at_cache = (
            {}
        )  # 群聊@消息缓存，格式: {group_id: [{'sender_name': name, 'content': content, 'timestamp': time}, ...]}
        self.group_at_timer = {}  # 群聊@消息定时器

        # 添加消息发送锁，确保消息发送的顺序性
        self.send_message_lock = threading.Lock()

        # 添加全局消息处理队列和队列锁
        self.global_message_queue = []  # 全局消息队列，包含所有群组的待处理消息
        self.global_message_queue_lock = threading.Lock()  # 全局消息队列锁
        self.is_processing_queue = False  # 标记是否正在处理队列
        self.queue_process_timer = None  # 全局队列处理定时器
        self.send_message_lock_time = time.time()  # 记录发送锁的创建时间

        # 添加群聊记忆处理器
        try:
            # 导入 GroupChatMemory 类
            from src.handlers.memories.group_chat_memory import GroupChatMemory

            # 安全处理头像名称
            if isinstance(robot_name, str):
                safe_avatar_name = re.sub(r"[^\w\-_\. ]", "_", robot_name)
            else:
                safe_avatar_name = "default_avatar"

            # 获取配置文件中的群聊列表
            group_chats = config.get("group_chats", [])

            # 初始化群聊记忆
            self.group_chat_memory = GroupChatMemory(
                root_dir=root_dir,
                avatar_name=safe_avatar_name,
                group_chats=group_chats,  # 传入已识别的群聊列表
                api_wrapper=(
                    memory_handler.api_wrapper
                    if hasattr(memory_handler, "api_wrapper")
                    and memory_handler is not None
                    else None
                ),
            )

        except Exception as e:
            logger.error(f"初始化群聊记忆失败: {str(e)}")
            # 导入 GroupChatMemory 类（确保在这里也能访问到）
            from src.handlers.memories.group_chat_memory import GroupChatMemory

            # 使用默认值初始化
            self.group_chat_memory = GroupChatMemory(
                root_dir=root_dir,
                avatar_name="default",
                group_chats=[],
                api_wrapper=(
                    memory_handler.api_wrapper
                    if hasattr(memory_handler, "api_wrapper")
                    else None
                ),
            )

        # 添加群聊消息处理队列
        self.group_message_queues = {}
        self.group_queue_lock = threading.Lock()
        self.at_message_timestamps = {}  # 存储@消息的时间戳

        self.unanswered_counters = {}
        self.unanswered_timers = {}
        self.last_reply_time = {}  # 添加last_reply_time属性跟踪最后回复时间
        self.MAX_MESSAGE_LENGTH = 500

        # 启动定时清理定时器，30秒后首次执行，然后每10分钟执行一次
        cleanup_timer = threading.Timer(30.0, self.cleanup_message_queues)
        cleanup_timer.daemon = True
        cleanup_timer.start()

        logger.info(f"消息处理器初始化完成，机器人名称：{self.robot_name}")

        # 添加权重阈值
        self.weight_threshold = 0.3  # 可以根据需要调整阈值

        # 添加衰减相关参数
        self.decay_method = "exponential"  # 或 'linear'
        self.decay_rate = 0.1  # 可以根据需要调整衰减率

        self._init_auto_task_message()

    def _get_config_value(self, key, default_value):
        """从配置文件获取特定值，如果不存在则返回默认值"""
        try:
            # 尝试从config.behavior.context中获取
            if hasattr(config, "behavior") and hasattr(config.behavior, "context"):
                if hasattr(config.behavior.context, key):
                    return getattr(config.behavior.context, key)

            # 尝试从config.categories.advanced_settings.settings中获取
            try:
                advanced_settings = config.categories.advanced_settings.settings
                if hasattr(advanced_settings, key):
                    return getattr(advanced_settings, key).value
            except AttributeError:
                pass

            # 尝试从config.categories.user_settings.settings中获取
            try:
                user_settings = config.categories.user_settings.settings
                if hasattr(user_settings, key):
                    return getattr(user_settings, key).value
            except AttributeError:
                pass

            # 如果都不存在，返回默认值
            return default_value
        except Exception as e:
            logger.error(f"获取配置值{key}失败: {str(e)}")
            return default_value

    def get_api_response(
        self, message: str, user_id: str, group_id: str = None, sender_name: str = None
    ) -> str:
        """获取API回复"""
        try:
            # 使用正确的属性名和方法名
            if not hasattr(self, "deepseek") or self.deepseek is None:
                logger.error("LLM服务未初始化，无法生成回复")
                return "系统错误：LLM服务未初始化"

            # 使用正确的属性名称调用方法
            try:
                # 修改：检查URL末尾是否有斜杠，并记录日志
                if hasattr(self.deepseek.llm, "url") and self.deepseek.llm.url.endswith(
                    "/"
                ):
                    # 尝试在本地临时修复URL
                    fixed_url = self.deepseek.llm.url.rstrip("/")
                    self.deepseek.llm.url = fixed_url

                # 调用API获取响应
                response = self.deepseek.llm.handel_prompt(message, user_id)

                # 简化API响应日志，只记录响应长度
                if response:
                    response_length = len(response)
                    # 只记录一次响应长度，避免重复日志
                    logger.info(f"API响应: {response_length}字符")
                else:
                    logger.error("收到空响应")

                # 增加异常检测，避免将错误信息存入记忆
                if response and (
                    "API调用失败" in response
                    or "Connection error" in response
                    or "服务暂时不可用" in response
                    or "Error:" in response
                    or "错误:" in response
                    or "认证错误" in response
                ):
                    logger.error(f"API调用返回错误: {response}")

                    # 增加错误类型的分类
                    if "Connection error" in response or "连接错误" in response:
                        logger.error("网络连接错误 - 请检查网络连接和API地址配置")
                        return f"抱歉，我暂时无法连接到API服务器。请检查网络连接和API地址配置。"

                    elif "认证错误" in response or "API密钥" in response:
                        logger.error("API认证错误 - 请检查API密钥是否正确")
                        return f"抱歉，API认证失败。请检查API密钥配置。"

                    elif "模型" in response and (
                        "错误" in response or "不存在" in response
                    ):
                        logger.error("模型错误 - 模型名称可能不正确或不可用")
                        return f"抱歉，无法使用指定的AI模型。请检查模型名称配置。"

                    else:
                        return f"抱歉，我暂时无法回应。错误信息：{response}"

                return response

            except Exception as api_error:
                error_msg = str(api_error)
                logger.error(f"API调用异常: {error_msg}")

                # 增加异常处理的详细分类
                if "Connection" in error_msg or "connect" in error_msg.lower():
                    logger.error(f"网络连接错误 - 请检查网络连接和API地址")
                    return (
                        f"API调用失败: 无法连接到服务器。请检查网络连接和API地址配置。"
                    )

                elif (
                    "authenticate" in error_msg.lower()
                    or "authorization" in error_msg.lower()
                    or "auth" in error_msg.lower()
                ):
                    logger.error(f"API认证错误 - 请检查API密钥是否正确")
                    return f"API调用失败: 认证错误。请检查API密钥配置。"

                elif "not found" in error_msg.lower() or "404" in error_msg:
                    logger.error(f"API资源不存在 - 请检查API地址和路径是否正确")
                    return f"API调用失败: 请求的资源不存在。请检查API地址和路径。"

                else:
                    return f"API调用出错：{error_msg}"

        except Exception as e:
            logger.error(f"获取API回复失败: {str(e)}")
            # 降级处理：使用简化的提示
            try:
                return f"抱歉，我暂时无法回应，请稍后再试。(错误: {str(e)[:50]}...)"
            except Exception as fallback_error:
                logger.error(f"降级处理也失败: {str(fallback_error)}")
                return f"服务暂时不可用，请稍后重试。"

    def _safe_send_msg(self, msg, who, max_retries=None, char_by_char=False):
        """安全发送消息，带重试机制"""
        if not msg or not who:
            logger.warning("消息或接收人为空，跳过发送")
            return False

        # 检查调试模式
        if self.is_debug:
            # 调试模式下直接打印消息而不是发送
            logger.debug(f"[调试模式] 发送消息: {msg[:20]}...")
            return True

        # 检查wx对象是否可用
        if self.wx is None:
            logger.warning("WeChat对象为None，无法发送消息")
            return False

        # 不再特殊处理消息末尾的反斜杠，因为所有反斜杠都已在分割阶段处理
        processed_msg = msg

        # 设置重试次数
        if max_retries is None:
            max_retries = 3

        # 尝试发送消息
        for attempt in range(max_retries):
            try:
                if self.is_qq:
                    # QQ消息直接返回，不实际发送
                    return True
                else:
                    # 微信消息发送
                    if char_by_char:
                        # 逐字发送
                        for char in processed_msg:
                            self.wx.SendMsg(char, who)
                            time.sleep(random.uniform(0.1, 0.3))
                    else:
                        # 整条发送
                        self.wx.SendMsg(processed_msg, who)
                return True
            except Exception as e:
                # 只在最后一次重试失败时记录错误
                if attempt == max_retries - 1:
                    logger.error(f"发送消息失败: {str(e)}")

                if attempt < max_retries - 1:
                    time.sleep(1)  # 等待一秒后重试

        return False

    def auto_send_message(
        self,
        listen_list,
        robot_wx_name,
        get_personality_summary,
        is_quiet_time,
        start_countdown,
    ):
        """自动发送消息"""
        try:
            # 检查是否在安静时间
            if is_quiet_time():
                logger.info("当前是安静时间，不发送自动消息")
                start_countdown()  # 重新开始倒计时
                return

            # 获取人设摘要
            prompt_content = get_personality_summary(self.prompt_content)

            # 获取自动消息内容
            from src.config import config

            # 检查配置是否存在
            if (
                not hasattr(config, "behavior")
                or not hasattr(config.behavior, "auto_message")
                or not hasattr(config.behavior.auto_message, "content")
            ):
                logger.error("配置文件中缺少behavior.auto_message.content设置")
                auto_message = "你好，我是AI助手，有什么可以帮助你的吗？"
                logger.info(f"使用默认自动消息: {auto_message}")
            else:
                auto_message = config.behavior.auto_message.content
                logger.info(f"从配置读取的自动消息: {auto_message}")

            # 随机选择一个用户
            if not listen_list:
                logger.warning("监听列表为空，无法发送自动消息")
                start_countdown()  # 重新开始倒计时
                return

            target_user = random.choice(listen_list)
            logger.info(f"选择的目标用户: {target_user}")

            # 检查最近是否有聊天记录（30分钟内）
            if recent_chat := self.deepseek.llm.user_recent_chat_time.get(target_user):
                current_time = datetime.now()
                time_diff = current_time - recent_chat
                # 如果30分钟内有聊天，跳过本次主动消息
                if time_diff.total_seconds() < 1800:  # 30分钟 = 1800秒
                    logger.info(
                        f"距离上次与 {target_user} 的聊天不到30分钟，跳过本次主动消息"
                    )
                    start_countdown()  # 重新开始倒计时
                    return

            # 发送消息
            if self.wx:
                # 确保微信窗口处于活动状态
                try:
                    self.wx.ChatWith(target_user)
                    time.sleep(1)  # 等待窗口激活

                    # 获取最近的对话记忆作为上下文
                    context = ""
                    if self.memory_handler:
                        try:
                            # 获取相关记忆
                            current_time = datetime.now()
                            query_text = f"与用户 {target_user} 相关的重要对话"

                            # 按照配置，决定是否使用语义搜索
                            if self.use_semantic_search and self.rag_manager:
                                logger.info(f"使用语义搜索和时间衰减权重获取相关记忆")
                                # 获取原始记忆
                                raw_memories = (
                                    self.memory_handler.get_relevant_memories(
                                        query_text,
                                        target_user,
                                        top_k=20,  # 获取更多记忆，后续会筛选
                                    )
                                )

                                # 应用权重并筛选记忆
                                memories = self._apply_weights_and_filter_context(
                                    raw_memories,
                                    current_time=current_time,
                                    max_turns=10,
                                    current_user=target_user,
                                )

                                logger.info(f"应用权重后保留 {len(memories)} 条记忆")
                            else:
                                # 使用普通方式获取相关记忆
                                memories = self.memory_handler.get_relevant_memories(
                                    query_text, target_user, top_k=10
                                )

                            if memories:
                                memory_parts = []
                                for i, mem in enumerate(memories):
                                    if mem.get("message") and mem.get("reply"):
                                        # 计算时间衰减权重（用于日志）
                                        time_weight = (
                                            self._calculate_time_decay_weight(
                                                mem.get("timestamp", ""), current_time
                                            )
                                            if self.use_time_decay
                                            else 1.0
                                        )

                                        # 添加权重信息到日志
                                        logger.debug(
                                            f"记忆 #{i+1}: 权重={time_weight:.2f}, 内容={mem['message'][:30]}..."
                                        )

                                        memory_parts.append(
                                            f"对话{i+1}:\n用户: {mem['message']}\nAI: {mem['reply']}"
                                        )

                                if memory_parts:
                                    context = (
                                        "以下是之前的对话记录：\n\n"
                                        + "\n\n".join(memory_parts)
                                        + "\n\n(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容)\n\n"
                                    )
                                    logger.info(
                                        f"找到 {len(memory_parts)} 轮历史对话记录"
                                    )
                        except Exception as e:
                            logger.error(f"获取历史对话记录失败: {str(e)}")

                    # 构建系统指令和上下文
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    system_instruction = (
                        f"{context}(此时时间为{current_time}) [系统指令] {auto_message}"
                    )

                    # 添加长度限制提示词 - 自动消息保持在50-100字符之间，2-3个句子
                    length_prompt = "\n\n请注意：你的回复应当简洁明了，控制在50-100个字符和2-3个句子左右。"
                    system_instruction += length_prompt

                    # 获取AI回复
                    ai_response = self.get_api_response(
                        message=system_instruction,
                        user_id=target_user,
                        sender_name=robot_wx_name,
                    )

                    if ai_response:
                        # 将长消息分段发送
                        message_parts = self._split_message_for_sending(ai_response)
                        for part in message_parts["parts"]:
                            self._safe_send_msg(part, target_user)
                            time.sleep(1.5)  # 添加短暂延迟避免发送过快

                        logger.info(
                            f"已发送主动消息到 {target_user}: {ai_response[:50]}..."
                        )

                        # 记录主动消息到记忆
                        if self.memory_handler:
                            try:
                                # 检查是否是群聊ID
                                is_group_chat = False
                                if hasattr(self, "group_chat_memory"):
                                    is_group_chat = (
                                        target_user
                                        in self.group_chat_memory.group_chats
                                    )

                                if is_group_chat:
                                    # 标记为系统发送的消息，确保机器人名称正确
                                    timestamp = datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    )
                                    # 将消息存入群聊记忆
                                    self.group_chat_memory.add_message(
                                        target_user,  # 群聊ID
                                        self.robot_name,  # 发送者为机器人
                                        system_instruction,  # 保存系统指令作为输入
                                        message_parts.get(
                                            "memory_content", ai_response
                                        ),  # 使用处理后的内容
                                        timestamp,
                                        is_system=True,  # 标记为系统消息
                                    )
                                    logger.info(
                                        f"成功记录主动消息到群聊记忆: {target_user}"
                                    )
                                else:
                                    # 普通私聊消息记忆
                                    self.memory_handler.remember(
                                        target_user, system_instruction, ai_response
                                    )
                                    logger.info(f"成功记录主动消息到个人记忆")
                            except Exception as e:
                                logger.error(f"记录主动消息到记忆失败: {str(e)}")
                    else:
                        logger.warning(f"AI未生成有效回复，跳过发送")
                    # 重新开始倒计时
                    start_countdown()
                except Exception as e:
                    logger.error(f"发送自动消息失败: {str(e)}")
                    start_countdown()  # 出错也重新开始倒计时
            else:
                logger.error("WeChat对象为None，无法发送自动消息")
                start_countdown()  # 重新开始倒计时
        except Exception as e:
            logger.error(f"自动发送消息失败: {str(e)}")
            start_countdown()  # 出错也重新开始倒计时

    def handle_user_message(
        self,
        content: str,
        chat_id: str,
        sender_name: str,
        username: str,
        is_group: bool = False,
        is_image_recognition: bool = False,
        is_self_message: bool = False,
        is_at: bool = False,
    ):
        """统一的消息处理入口"""
        try:
            # 验证并修正用户ID
            if not username or username == "System":
                username = chat_id.split("@")[0] if "@" in chat_id else chat_id
                if username == "filehelper":
                    username = "FileHelper"
                sender_name = sender_name or username

            # 如果是自己发送的消息并且是图片或表情包，直接跳过处理
            if is_self_message and (
                content.endswith(".jpg")
                or content.endswith(".png")
                or content.endswith(".gif")
            ):
                logger.info(f"检测到自己发送的图片或表情包，跳过保存和识别: {content}")
                return None

            # 检查是否是群聊消息
            if is_group:
                logger.info(
                    f"处理群聊消息: 群ID={chat_id}, 发送者={sender_name}, 内容={content[:30]}..."
                )
                # 传递is_at参数
                return self._handle_group_message(
                    content, chat_id, sender_name, username, is_at
                )

            # 处理私聊消息的逻辑保持不变
            actual_content = self._clean_message_content(content)
            logger.info(f"收到私聊消息: {actual_content}")

            if not hasattr(self, "_last_message_times"):
                self._last_message_times = {}
            self._last_message_times[username] = datetime.now()

            if is_self_message:
                self._send_self_message(content, chat_id)
                return None

            content_length = len(actual_content)

            should_cache = True
            if should_cache:
                return self._cache_message(
                    content,
                    chat_id,
                    sender_name,
                    username,
                    is_group,
                    is_image_recognition,
                )

            return self._handle_uncached_message(
                content, chat_id, sender_name, username, is_group, is_image_recognition
            )

        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return None

    def _handle_group_message(
        self,
        content: str,
        group_id: str,
        sender_name: str,
        username: str,
        is_at: bool = False,
    ):
        """处理群聊消息"""
        try:
            # 优先使用传入的is_at参数，如果main.py已经正确检测并传入
            is_at_from_param = is_at

            # 检查是否包含引用消息
            quoted_content = None
            quoted_sender = None
            # 微信引用消息格式通常是: "引用 xxx 的消息"或"回复 xxx 的消息"
            quote_match = re.search(
                r"(?:引用|回复)\s+([^\s]+)\s+的(?:消息)?[:：]?\s*(.+?)(?=\n|$)", content
            )
            if quote_match and is_at_from_param:
                quoted_sender = quote_match.group(1)
                quoted_content = quote_match.group(2).strip()
                logger.info(
                    f"检测到引用消息 - 引用者: {quoted_sender}, 内容: {quoted_content}"
                )
                # 从原始消息中移除引用部分
                content = re.sub(
                    r"(?:引用|回复)\s+[^\s]+\s+的(?:消息)?[:：]?\s*.+?(?=\n|$)",
                    "",
                    content,
                ).strip()

            # 备用检测：如果传入参数为False，再尝试本地检测
            if not is_at_from_param:
                # 改进@机器人检测逻辑 - 使用更全面的模式匹配
                # 常见的空格字符：普通空格、不间断空格、零宽空格、特殊的微信空格等

                # 检查完整的正则模式
                # 允许@后面的名称部分有一些小的变化（比如有些空格字符可能会被替换）
                robot_name_pattern = re.escape(self.robot_name).replace(
                    "\\ ", "[ \u2005\u00a0\u200b\u3000]*"
                )
                at_pattern = re.compile(
                    f"@{robot_name_pattern}[\\s\u2005\u00a0\u200b\u3000]?"
                )
                is_at_local = bool(at_pattern.search(content))

                # 检查完整的模式列表
                if not is_at_local:
                    robot_at_patterns = [
                        f"@{self.robot_name}",  # 基本@模式
                        f"@{self.robot_name} ",  # 普通空格
                        f"@{self.robot_name}\u2005",  # 特殊的微信空格
                        f"@{self.robot_name}\u00a0",  # 不间断空格
                        f"@{self.robot_name}\u200b",  # 零宽空格
                        f"@{self.robot_name}\u3000",  # 全角空格
                    ]
                    is_at_local = any(
                        pattern in content for pattern in robot_at_patterns
                    )

                # 额外检查@开头的消息
                if not is_at_local and content.startswith("@"):
                    # 提取@后面的第一个词，检查是否接近机器人名称
                    at_name_match = re.match(
                        r"@([^ \u2005\u00A0\u200B\u3000]+)", content
                    )
                    if at_name_match:
                        at_name = at_name_match.group(1)
                        # 检查名称相似度（允许一些小的变化）
                        similarity_ratio = difflib.SequenceMatcher(
                            None, at_name, self.robot_name
                        ).ratio()
                        if similarity_ratio > 0.8:  # 80%相似度作为阈值
                            is_at_local = True
                            logger.info(
                                f"基于名称相似度检测到@机器人: {at_name} vs {self.robot_name}, 相似度: {similarity_ratio:.2f}"
                            )

                # 提取原始@部分以供后续处理
                at_match = re.search(
                    f"(@{re.escape(self.robot_name)}[\\s\u2005\u00a0\u200b\u3000]?)",
                    content,
                )
                at_content = at_match.group(1) if at_match else ""

                # 记录检测结果
                logger.debug(f"本地@检测结果: {is_at_local}, 提取的@内容: {at_content}")
            else:
                # 直接使用传入的参数
                is_at_local = True
                at_content = ""  # 不需要再提取，因为main.py已经处理过

            # 使用传入参数和本地检测的综合结果
            is_at_final = is_at_from_param or is_at_local

            # 清理消息内容
            actual_content = self._clean_message_content(content)

            # 使用最终的@状态进行日志记录和后续处理
            logger.info(
                f"收到群聊消息 - 群: {group_id}, 发送者: {sender_name}, 内容: {actual_content}, 是否@: {is_at_final}"
            )

            # 保存所有群聊消息到群聊记忆，不论是否@
            timestamp = self.group_chat_memory.add_message(
                group_id, sender_name, actual_content, is_at_final
            )
            logger.debug(f"消息已保存到群聊记忆: {group_id}, 时间戳: {timestamp}")

            # 如果是@消息，加入处理队列并进行回复
            if is_at_final:
                logger.info(f"检测到@消息: {actual_content}, 发送者: {sender_name}")
                self.at_message_timestamps[f"{group_id}_{timestamp}"] = timestamp

                # 明确记录实际@人的用户信息
                actual_sender_name = sender_name  # 确保使用实际发送消息的人的名称
                actual_username = username  # 确保使用实际发送消息的人的ID

                # 决定是否缓存@消息或立即处理
                return self._cache_group_at_message(
                    actual_content,
                    group_id,
                    actual_sender_name,
                    actual_username,
                    timestamp,
                )
            else:
                logger.debug(f"非@消息，仅保存到记忆: {actual_content[:30]}...")

            return None

        except Exception as e:
            logger.error(f"处理群聊消息失败: {str(e)}", exc_info=True)
            return None

    def _handle_uncached_message(
        self,
        content: str,
        chat_id: str,
        sender_name: str,
        username: str,
        is_group: bool,
        is_image_recognition: bool,
    ):
        """处理未缓存的消息，直接调用API获取回复"""
        try:
            # 获取API回复
            response = self.get_api_response(content, username)

            if response and not self.is_debug:
                # 分割消息并发送
                split_messages = self._split_message_for_sending(response)
                self._send_split_messages(split_messages, chat_id)

            return response

        except Exception as e:
            logger.error(f"处理未缓存消息失败: {str(e)}", exc_info=True)
            return None

    def _cache_group_at_message(
        self,
        content: str,
        group_id: str,
        sender_name: str,
        username: str,
        timestamp: str,
    ):
        """缓存群聊@消息，并将其添加到全局消息处理队列"""
        current_time = time.time()

        # 创建消息对象
        message_obj = {
            "content": content,
            "sender_name": sender_name,
            "username": username,
            "timestamp": timestamp,
            "added_time": current_time,
            "group_id": group_id,
        }

        # 将消息添加到全局处理队列
        with self.global_message_queue_lock:
            self.global_message_queue.append(message_obj)

            # 如果没有正在处理的队列，启动处理
            if not self.is_processing_queue:
                # 设置处理状态
                self.is_processing_queue = True
                # 设置延迟处理定时器，等待一小段时间收集更多可能的消息
                if self.queue_process_timer:
                    self.queue_process_timer.cancel()

                self.queue_process_timer = threading.Timer(
                    2.0, self._process_global_message_queue
                )
                self.queue_process_timer.daemon = True
                self.queue_process_timer.start()

        # 同时保持原有的群聊缓存机制作为备份
        if group_id not in self.group_at_cache:
            self.group_at_cache[group_id] = []

        # 添加到群聊@消息缓存
        self.group_at_cache[group_id].append(message_obj)

        logger.info(
            f"缓存群聊@消息: 群: {group_id}, 发送者: {sender_name}, 已添加到全局队列"
        )
        return None

    def _process_global_message_queue(self):
        """处理全局消息队列，按顺序处理所有群聊的消息"""
        try:
            # 获取队列中的所有消息
            with self.global_message_queue_lock:
                if not self.global_message_queue:
                    self.is_processing_queue = False
                    return

                current_message = self.global_message_queue.pop(0)

            # 处理当前消息
            group_id = current_message["group_id"]
            logger.info(
                f"从全局队列处理消息: 群ID: {group_id}, 发送者: {current_message['sender_name']}"
            )

            # 调用消息处理方法
            result = self._handle_at_message(
                current_message["content"],
                group_id,
                current_message["sender_name"],
                current_message["username"],
                current_message["timestamp"],
            )

            # 处理完成后，检查队列中是否还有消息
            with self.global_message_queue_lock:
                if self.global_message_queue:
                    # 如果还有消息，设置定时器处理下一条
                    # 使用较短的延迟，但仍然保持一定间隔，避免消息发送过快
                    self.queue_process_timer = threading.Timer(
                        1.0, self._process_global_message_queue
                    )
                    self.queue_process_timer.daemon = True
                    self.queue_process_timer.start()
                else:
                    # 如果没有更多消息，重置处理状态
                    self.is_processing_queue = False

        except Exception as e:
            logger.error(f"处理全局消息队列失败: {str(e)}")
            # 重置处理状态，防止队列处理卡死
            with self.global_message_queue_lock:
                self.is_processing_queue = False

    def _process_cached_group_at_messages(self, group_id: str):
        """处理缓存的群聊@消息 - 现在为兼容保留，实际处理由全局队列处理器完成"""
        try:
            # 检查全局队列处理是否正在进行
            with self.global_message_queue_lock:
                if self.is_processing_queue:
                    logger.info(
                        f"全局队列处理已在进行中，跳过单独处理群 {group_id} 的消息"
                    )
                    return None

                # 如果全局队列未在处理，但该群组有缓存消息，则添加到全局队列
                if group_id in self.group_at_cache and self.group_at_cache[group_id]:
                    for msg in self.group_at_cache[group_id]:
                        self.global_message_queue.append(msg)

                    # 清空该群组的缓存
                    self.group_at_cache[group_id] = []

                    # 启动全局队列处理
                    if not self.is_processing_queue:
                        self.is_processing_queue = True
                        self.queue_process_timer = threading.Timer(
                            0.5, self._process_global_message_queue
                        )
                        self.queue_process_timer.daemon = True
                        self.queue_process_timer.start()

                    logger.info(f"已将群 {group_id} 的缓存消息添加到全局队列")
                    return None

            # 如果该群组没有缓存消息，直接返回
            if group_id not in self.group_at_cache or not self.group_at_cache[group_id]:
                return None

            logger.warning(f"使用旧方法处理群 {group_id} 的缓存消息 - 这是兼容模式")

            # 简化的处理逻辑，只处理第一条消息
            if len(self.group_at_cache[group_id]) > 0:
                msg = self.group_at_cache[group_id][0]
                result = self._handle_at_message(
                    msg["content"],
                    group_id,
                    msg["sender_name"],
                    msg["username"],
                    msg["timestamp"],
                )

                # 清除缓存
                self.group_at_cache[group_id] = []
                return result

            return None

        except Exception as e:
            logger.error(f"处理缓存的群聊@消息失败: {str(e)}")
            # 清除缓存，防止错误消息卡在缓存中
            if group_id in self.group_at_cache:
                self.group_at_cache[group_id] = []
            return None

    def _handle_at_message(
        self,
        content: str,
        group_id: str,
        sender_name: str,
        username: str,
        timestamp: str,
    ):
        """处理@消息"""
        try:
            # 记录实际的@消息发送者信息
            logger.info(
                f"处理@消息 - 群ID: {group_id}, 发送者: {sender_name}, 用户ID: {username}"
            )

            # 检查是否包含引用消息
            quoted_content = None
            quoted_sender = None
            quote_match = re.search(
                r"(?:引用|回复)\s+([^\s]+)\s+的(?:消息)?[:：]?\s*(.+?)(?=\n|$)", content
            )
            if quote_match:
                quoted_sender = quote_match.group(1)
                quoted_content = quote_match.group(2).strip()
                logger.info(
                    f"检测到引用消息 - 引用者: {quoted_sender}, 内容: {quoted_content}"
                )
                # 从原始消息中移除引用部分
                content = re.sub(
                    r"(?:引用|回复)\s+[^\s]+\s+的(?:消息)?[:：]?\s*.+?(?=\n|$)",
                    "",
                    content,
                ).strip()

                # 如果引用内容为空，尝试从群聊记忆中获取
                if quoted_content and hasattr(self, "group_chat_memory"):
                    # 获取引用消息的上下文
                    quoted_context = self.group_chat_memory.get_message_by_content(
                        group_id, quoted_content
                    )
                    if quoted_context:
                        logger.info(f"找到引用消息的上下文: {quoted_context}")
                        # 将引用内容添加到当前消息的上下文中
                        content = f"(引用消息: {quoted_sender} 说: {quoted_content})\n{content}"

            # 获取当前时间
            current_time = datetime.now()

            # 使用两种方式获取上下文消息，然后合并
            context_messages = []
            semantic_messages = []
            time_based_messages = []

            # 定义at_messages变量，避免未定义错误
            at_messages = []
            if hasattr(self, "group_at_cache") and group_id in self.group_at_cache:
                at_messages = self.group_at_cache[group_id]

            # 1. 获取基于时间顺序的上下文消息
            if hasattr(self, "group_chat_memory"):
                # 获取群聊消息上下文
                time_based_messages = self.group_chat_memory.get_context_messages(
                    group_id, timestamp
                )

                # 过滤掉当前at消息
                time_based_messages = [
                    msg
                    for msg in time_based_messages
                    if not any(
                        cached_msg["timestamp"] == msg["timestamp"]
                        for cached_msg in at_messages
                    )
                ]

                # 预过滤消息（移除过旧的消息）
                time_based_messages = [
                    msg
                    for msg in time_based_messages
                    if (
                        current_time
                        - datetime.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                    ).total_seconds()
                    <= 21600  # 6小时
                ]

            # 2. 如果有RAG管理器，获取语义相似的消息
            if self.use_semantic_search and self.rag_manager:
                # 调用异步方法获取语义相似消息
                try:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        # 如果当前线程没有事件循环，创建一个新的
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    semantic_messages = loop.run_until_complete(
                        self._get_semantic_similar_messages(
                            content,
                            group_id=group_id,
                            top_k=self.group_context_turns * 2,
                        )
                    )
                    # 过滤掉当前消息
                    semantic_messages = [
                        msg
                        for msg in semantic_messages
                        if msg.get("timestamp") != timestamp
                    ]
                except Exception as e:
                    logger.error(f"获取语义相似消息失败: {str(e)}")
                    semantic_messages = []

            # 3. 合并两种消息源并移除重复项
            seen_timestamps = set()
            for msg in time_based_messages:
                msg_timestamp = msg.get("timestamp")
                if msg_timestamp and msg_timestamp not in seen_timestamps:
                    seen_timestamps.add(msg_timestamp)
                    context_messages.append(msg)

            # 添加语义相似的消息，避免重复
            for msg in semantic_messages:
                msg_timestamp = msg.get("timestamp")
                if msg_timestamp and msg_timestamp not in seen_timestamps:
                    seen_timestamps.add(msg_timestamp)
                    # 添加语义分数
                    msg["semantic_score"] = msg.get("score", 0.5)
                    context_messages.append(msg)

            # 应用权重并筛选上下文，传入当前用户名
            filtered_msgs = self._apply_weights_and_filter_context(
                context_messages,
                current_time,
                current_user=sender_name,  # 传递当前@消息的发送者
            )

            # 创建过滤后的上下文
            filtered_context = []
            for msg in filtered_msgs:
                # 清理消息内容
                human_message = self._clean_memory_content(msg["human_message"])
                assistant_message = (
                    self._clean_memory_content(msg["assistant_message"])
                    if msg["assistant_message"]
                    else None
                )

                if human_message:
                    filtered_context.append(
                        {
                            "sender_name": msg["sender_name"],
                            "human_message": human_message,
                            "assistant_message": assistant_message,
                        }
                    )

            # 构建上下文字符串，确保包含用户名
            context = ""
            if filtered_context:
                context_parts = []
                for msg in filtered_context:
                    # 添加发送者消息，确保用户名清晰可见
                    sender_display = msg["sender_name"]
                    context_parts.append(f"{sender_display}: {msg['human_message']}")
                    # 如果有机器人回复，也添加进去
                    if msg["assistant_message"]:
                        context_parts.append(
                            f"{self.robot_name}: {msg['assistant_message']}"
                        )

                if context_parts:
                    context = "<context>" + "\n".join(context_parts) + "</context>\n\n"

            # 构建API请求内容，明确标识当前@发送者
            current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
            api_content = f"<time>{current_time_str}</time>\n<group>{group_id}</group>\n<sender>{sender_name}</sender>\n{context}<input>{content}</input>"

            # 在日志中明确记录谁@了机器人
            logger.info(
                f"@消息请求AI响应 - 发送者: {sender_name}, 用户ID: {username}, 内容: {content[:30]}..."
            )

            # 获取AI回复，确保传递正确的用户标识
            reply = self.get_api_response(api_content, username)

            # 如果成功获取回复
            if reply:
                # 清理回复内容
                reply = self._clean_ai_response(reply)

                # 在回复中显式提及发送者，确保回复的是正确的人
                if not reply.startswith(f"@{sender_name}"):
                    reply = f"@{sender_name} {reply}"

                # 分割消息并获取过滤后的内容
                split_messages = self._split_message_for_sending(reply)

                # 使用memory_content更新群聊记忆
                if isinstance(split_messages, dict) and split_messages.get(
                    "memory_content"
                ):
                    memory_content = split_messages["memory_content"]
                    self.group_chat_memory.update_assistant_response(
                        group_id, timestamp, memory_content
                    )
                else:
                    # 如果没有memory_content字段，则使用过滤动作和表情后的回复
                    filtered_reply = self._filter_action_emotion(reply)
                    self.group_chat_memory.update_assistant_response(
                        group_id, timestamp, filtered_reply
                    )

                # 发送消息
                if not self.is_debug:
                    self._send_split_messages(split_messages, group_id)

                if isinstance(split_messages, dict):
                    return split_messages.get("parts", reply)
                return reply

            return None

        except Exception as e:
            logger.error(f"处理@消息失败: {str(e)}")
            return None

    def _clean_message_content(self, content: str) -> str:
        """清理消息内容，去除时间戳和前缀"""
        # 匹配并去除时间戳和前缀
        patterns = [
            r"^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)?\s+ta私聊对你说\s*",
            r"^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s+ta私聊对你说\s*",
            r"^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)\s+ta(私聊|在群聊里)对你说\s*",
            r"^.*?ta私聊对你说\s*",
            r"^.*?ta在群聊里对你说\s*",  # 添加群聊消息模式
        ]

        actual_content = content

        # 保存@信息
        at_match = re.search(r"(@[^\s]+)", actual_content)
        at_content = at_match.group(1) if at_match else ""

        # 清理时间戳和前缀
        for pattern in patterns:
            if re.search(pattern, actual_content):
                actual_content = re.sub(pattern, "", actual_content)
                break

        # 如果有@信息且在清理过程中被移除，重新添加到开头
        if at_content and at_content not in actual_content:
            actual_content = f"{at_content} {actual_content}"

        return actual_content.strip()

    def _cache_message(
        self,
        content: str,
        chat_id: str,
        sender_name: str,
        username: str,
        is_group: bool,
        is_image_recognition: bool,
    ) -> None:
        """缓存消息并设置定时器"""
        current_time = time.time()

        # 取消现有定时器
        if username in self.message_timer and self.message_timer[username]:
            self.message_timer[username].cancel()

        # 添加到消息缓存
        if username not in self.message_cache:
            self.message_cache[username] = []

        # 提取实际内容
        actual_content = self._clean_message_content(content)

        self.message_cache[username].append(
            {
                "content": content,
                "chat_id": chat_id,
                "sender_name": sender_name,
                "is_group": is_group,
                "is_image_recognition": is_image_recognition,
                "timestamp": current_time,
            }
        )

        # 设置新的定时器
        wait_time = self._calculate_wait_time(
            username, len(self.message_cache[username])
        )
        timer = threading.Timer(
            wait_time, self._process_cached_messages, args=[username]
        )
        timer.daemon = True
        timer.start()
        self.message_timer[username] = timer

        # 简化日志，只显示缓存内容和等待时间
        logger.info(f"缓存消息: {actual_content} | 等待时间: {wait_time:.1f}秒")

        return None

    def _calculate_wait_time(self, username: str, msg_count: int) -> float:
        """计算消息等待时间"""
        base_wait_time = 3.0
        typing_speed = self._estimate_typing_speed(username)

        if msg_count == 1:
            wait_time = base_wait_time + 5.0
        else:
            estimated_typing_time = min(4.0, typing_speed * 20)  # 假设用户输入20个字符
            wait_time = base_wait_time + estimated_typing_time

        # 简化日志，只在debug级别显示详细计算过程
        logger.debug(
            f"消息等待时间计算: 基础={base_wait_time}秒, 打字速度={typing_speed:.2f}秒/字, 结果={wait_time:.1f}秒"
        )

        return wait_time

    def _process_cached_messages(self, username: str):
        """处理缓存的消息"""
        try:
            if not self.message_cache.get(username):
                return None

            messages = self.message_cache[username]
            messages.sort(key=lambda x: x.get("timestamp", 0))

            # 获取最近的对话记录作为上下文
            context = self._get_conversation_context(username)

            # 合并消息内容
            raw_contents = []
            first_timestamp = None

            for msg in messages:
                content = msg["content"]
                if not first_timestamp:
                    # 提取第一条消息的时间戳
                    timestamp_match = re.search(
                        r"\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?", content
                    )
                    if timestamp_match:
                        first_timestamp = timestamp_match.group()

                # 清理消息内容
                cleaned_content = self._clean_message_content(content)
                if cleaned_content:
                    raw_contents.append(cleaned_content)

            # 使用 \ 作为句子分隔符合并消息
            content_text = " $ ".join(raw_contents)

            # 格式化最终消息
            first_timestamp = first_timestamp or datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            )
            merged_content = f"[{first_timestamp}]ta 私聊对你说：{content_text}"

            if context:
                merged_content = f"{context}\n\n(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容)\n\n{merged_content}"

            # 处理合并后的消息
            last_message = messages[-1]
            result = self._handle_uncached_message(
                merged_content,
                last_message["chat_id"],
                last_message["sender_name"],
                username,
                last_message["is_group"],
                any(msg.get("is_image_recognition", False) for msg in messages),
            )

            # 清理缓存和定时器
            self.message_cache[username] = []
            if username in self.message_timer and self.message_timer[username]:
                self.message_timer[username].cancel()
                self.message_timer[username] = None

            return result

        except Exception as e:
            logger.error(f"处理缓存消息失败: {str(e)}", exc_info=True)
            return None

    def _get_conversation_context(self, username: str) -> str:
        """获取对话上下文"""
        try:
            # 构建更精确的查询，包含用户ID和当前时间信息，以获取更相关的记忆
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            query = f"与用户 {username} 相关的最近重要对话 {current_time}"

            # 结合语义检索和传统检索
            memories = []
            semantic_memories = []

            # 1. 使用基于向量的语义检索
            if self.use_semantic_search and self.rag_manager:
                try:
                    # 异步调用需要在协程中或通过事件循环执行
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        # 如果当前线程没有事件循环，创建一个新的
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    semantic_results = loop.run_until_complete(
                        self._get_semantic_similar_messages(
                            query,
                            user_id=username,
                            top_k=self.private_context_turns * 2,
                        )
                    )

                    # 转换格式
                    for result in semantic_results:
                        if "human_message" in result and "assistant_message" in result:
                            semantic_memories.append(
                                {
                                    "message": result.get("human_message", ""),
                                    "reply": result.get("assistant_message", ""),
                                    "timestamp": result.get("timestamp", ""),
                                    "score": result.get("score", 0.5),
                                    "source": "semantic",
                                }
                            )
                except Exception as e:
                    logger.error(f"获取语义相似消息失败: {str(e)}")
                    semantic_memories = []

            # 2. 使用传统的记忆检索
            # 获取相关记忆，使用从配置获取的私聊轮数值
            recent_history = self.memory_handler.get_relevant_memories(
                query,
                username,
                top_k=self.private_context_turns
                * 2,  # 检索更多记忆，后续会基于权重筛选
            )

            # 3. 合并两种来源的记忆，避免重复
            seen_messages = set()

            # 先添加传统检索结果
            for memory in recent_history:
                msg_key = (memory.get("message", "")[:50], memory.get("reply", "")[:50])
                if msg_key not in seen_messages:
                    seen_messages.add(msg_key)
                    memory["source"] = "traditional"
                    memories.append(memory)

            # 再添加语义检索结果，避免重复
            for memory in semantic_memories:
                msg_key = (memory.get("message", "")[:50], memory.get("reply", "")[:50])
                if msg_key not in seen_messages:
                    seen_messages.add(msg_key)
                    memories.append(memory)

            if memories:
                # 为记忆计算权重
                weighted_memories = []
                for memory in memories:
                    # 尝试从记忆中提取时间戳
                    timestamp = memory.get("timestamp", "")
                    if not timestamp:
                        # 尝试从消息内容中提取时间戳
                        timestamp_match = re.search(
                            r"\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?",
                            memory.get("message", ""),
                        )
                        if timestamp_match:
                            timestamp = timestamp_match.group()

                    # 计算时间权重
                    if not timestamp:
                        time_weight = 0.5  # 默认中等权重
                    else:
                        # 计算时间衰减权重
                        time_weight = self._calculate_time_decay_weight(timestamp)

                    # 计算质量权重
                    quality_score = self._memory_quality_score(memory, username)

                    # 计算语义权重
                    semantic_score = memory.get("score", 0.5)

                    # 组合权重 - 使用配置的权重分配
                    if self.use_semantic_search and memory.get("source") == "semantic":
                        # 语义检索结果给予更高的语义权重比例
                        final_weight = (
                            self.time_weight * time_weight
                            + (1.0 - self.time_weight) * semantic_score
                        ) * (quality_score / 100)
                    else:
                        # 传统检索结果
                        final_weight = time_weight * (quality_score / 100)

                    weighted_memories.append(
                        {
                            "memory": memory,
                            "weight": final_weight,
                            "time_weight": time_weight,
                            "quality_score": quality_score,
                            "semantic_score": semantic_score,
                        }
                    )

                # 按权重从高到低排序
                weighted_memories.sort(key=lambda x: x["weight"], reverse=True)

                # 过滤掉权重低于阈值的记忆
                filtered_memories = [
                    item["memory"]
                    for item in weighted_memories
                    if item["weight"] >= self.weight_threshold
                ]

                # 如果过滤后记忆数量少于私聊轮数，增加更多记忆
                if len(filtered_memories) < self.private_context_turns:
                    remaining_memories = [
                        item["memory"]
                        for item in weighted_memories
                        if item["memory"] not in filtered_memories
                    ]
                    filtered_memories.extend(
                        remaining_memories[
                            : self.private_context_turns - len(filtered_memories)
                        ]
                    )

                # 限制最大记忆数量
                quality_memories = filtered_memories[: self.private_context_turns]

                logger.info(
                    f"基于权重筛选：从 {len(memories)} 条记忆中筛选出 {len(quality_memories)} 条高质量记忆"
                )

                # 构建上下文
                context_parts = []
                for idx, hist in enumerate(quality_memories):
                    if hist.get("message") and hist.get("reply"):
                        context_parts.append(
                            f"对话{idx+1}:\n用户: {hist['message']}\nAI: {hist['reply']}"
                        )

                if context_parts:
                    return "以下是之前的对话记录：\n\n" + "\n\n".join(context_parts)

            return ""

        except Exception as e:
            logger.error(f"获取记忆历史记录失败: {str(e)}")
            return ""

    def _estimate_typing_speed(self, username: str) -> float:
        """估计用户的打字速度（秒/字符）"""
        # 如果没有足够的历史消息，使用默认值
        if username not in self.message_cache or len(self.message_cache[username]) < 2:
            # 根据用户ID是否存在于last_message_time中返回不同的默认值
            # 如果是新用户，给予更长的等待时间
            if username not in self.last_message_time:
                typing_speed = 0.2  # 新用户默认速度：每字0.2秒
            else:
                typing_speed = 0.15  # 已知用户默认速度：每字0.15秒

            logger.info(f"用户打字速度: {typing_speed:.2f}秒/字符")
            return typing_speed

        # 获取最近的两条消息
        messages = self.message_cache[username]
        if len(messages) < 2:
            typing_speed = 0.15
            logger.info(f"用户打字速度: {typing_speed:.2f}秒/字符")
            return typing_speed

        # 按时间戳排序，确保我们比较的是连续的消息
        recent_msgs = sorted(messages, key=lambda x: x.get("timestamp", 0))[-2:]

        # 计算时间差和字符数
        time_diff = recent_msgs[1].get("timestamp", 0) - recent_msgs[0].get(
            "timestamp", 0
        )

        # 获取实际内容（去除时间戳和前缀）
        content = recent_msgs[0].get("content", "")

        # 定义系统提示词模式
        time_prefix_pattern = (
            r"^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)?\s+ta私聊对你说\s+"
        )
        time_prefix_pattern2 = (
            r"^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s+ta私聊对你说\s+"
        )
        time_prefix_pattern3 = r"^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)\s+ta(私聊|在群聊里)对你说\s*"
        reminder_pattern = r"\((?:上次的对话内容|以上是历史对话内容)[^)]*\)"
        context_pattern = r"对话\d+:\n用户:.+\nAI:.+"
        system_patterns = [
            # 旧的精确字数限制提示
            r"\n\n请注意：你的回复应当与用户消息的长度相当，控制在约\d+个字符和\d+个句子左右。",
            # 新的提示词变体
            r"\n\n请简短回复，控制在一两句话内。",
            r"\n\n请注意保持自然的回复长度，与用户消息风格协调。",
            r"\n\n请保持简洁明了的回复。",
            # 其他系统提示词
            r"\(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容\)",
            r"请你回应用户的结束语",
        ]

        # 先去除基本的时间戳和前缀
        if re.search(time_prefix_pattern, content):
            content = re.sub(time_prefix_pattern, "", content)
        elif re.search(time_prefix_pattern2, content):
            content = re.sub(time_prefix_pattern2, "", content)
        elif re.search(time_prefix_pattern3, content):
            content = re.sub(time_prefix_pattern3, "", content)

        # 去除其他系统提示词
        content = re.sub(reminder_pattern, "", content)
        content = re.sub(context_pattern, "", content, flags=re.DOTALL)

        for pattern in system_patterns:
            content = re.sub(pattern, "", content)

        # 计算过滤后的实际用户内容长度
        filtered_content = content.strip()
        char_count = len(filtered_content)

        # 如果时间差或字符数无效，使用默认值
        if time_diff <= 0 or char_count <= 0:
            typing_speed = 0.15
            logger.info(f"用户打字速度: {typing_speed:.2f}秒/字符")
            return typing_speed

        # 计算打字速度（秒/字）
        typing_speed = time_diff / char_count

        # 应用平滑因子，避免极端值
        # 如果我们有历史记录的打字速度，将其纳入考虑
        if hasattr(self, "_typing_speeds") and username in self._typing_speeds:
            prev_speed = self._typing_speeds[username]
            # 使用加权平均，新速度权重0.4，历史速度权重0.6
            typing_speed = 0.4 * typing_speed + 0.6 * prev_speed

        # 存储计算出的打字速度
        if not hasattr(self, "_typing_speeds"):
            self._typing_speeds = {}
        self._typing_speeds[username] = typing_speed

        # 限制在合理范围内：0.2秒/字 到 1.2秒/字
        typing_speed = max(0.2, min(1.2, typing_speed))

        # 只输出最终的打字速度
        logger.info(f"用户打字速度: {typing_speed:.2f}秒/字符")

        return typing_speed

    def _calculate_response_length_ratio(self, input_length: int) -> float:
        """
        根据输入长度计算回复长度的比例

        Args:
            input_length: 用户输入的字符长度

        Returns:
            float: 回复长度的比例因子
        """
        if input_length <= 10:
            return 2.0  # 短消息给予较长回复
        elif input_length <= 50:
            return 1.5
        elif input_length <= 100:
            return 1.2
        else:
            return 1.0  # 长消息保持相同长度

    def _filter_action_emotion(self, text: str) -> str:
        """
        过滤掉文本中的动作和情感描述（通常在括号内）

        Args:
            text: 原始文本

        Returns:
            str: 过滤后的文本
        """
        # 过滤方括号内的内容
        text = re.sub(r"\[([^\]]*)\]", "", text)
        # 过滤圆括号内的内容
        text = re.sub(r"\(([^\)]*)\)", "", text)
        # 过滤【】内的内容
        text = re.sub(r"【([^】]*)】", "", text)
        # 清理可能留下的多余空格
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _clean_memory_content(self, content: str) -> str:
        """清理记忆内容中的特殊标记"""
        if not content:
            return ""
        # 清理XML标记
        content = re.sub(r"<[^>]+>", "", content)
        # 清理其他系统标记
        content = re.sub(r"\[系统.*?\]", "", content)
        return content.strip()

    def _clean_ai_response(self, response: str) -> str:
        """清理AI回复中的所有系统标记和提示词"""
        if not response:
            return ""

        # 移除所有XML样式的标记
        response = re.sub(r"<[^>]+>", "", response)

        # 清理其他系统标记和提示词
        patterns_to_remove = [
            r"\[系统提示\].*?\[/系统提示\]",
            r"\[系统指令\].*?\[/系统指令\]",
            r"记忆\d+:\s*\n用户:.*?\nAI:.*?(?=\n\n|$)",
            r"以下是之前的对话记录：.*?(?=\n\n)",
            r"\(以上是历史对话内容[^)]*\)",
            r"memory_number:.*?(?=\n|$)",
            r"\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?\]",
            r"请注意：.*?(?=\n|$)",
            r"请(?:简短|简洁)回复.*?(?=\n|$)",
            r"请.*?控制在.*?(?=\n|$)",
            r"请你回应用户的结束语",
            r"^你：|^对方：|^AI：",
            r"ta(?:私聊|在群聊里)对你说[：:]\s*",
        ]

        for pattern in patterns_to_remove:
            response = re.sub(pattern, "", response, flags=re.DOTALL | re.IGNORECASE)

        # 移除多余的空白字符
        response = re.sub(r"\s+", " ", response)
        return response.strip()

    def _filter_punctuation(self, text: str, is_last_sentence: bool = False) -> str:
        """
        过滤标点符号，保留问号、感叹号、省略号、书名号、括号、引号
        如果是最后一句，并过滤掉句尾的句号
        """
        if not text:
            return ""

        # 定义需要保留的标点符号集合
        keep_punctuation = set(
            [
                "?",
                "!",
                "？",
                "！",
                "…",
                "《",
                "》",
                "(",
                ")",
                "（",
                "）",
                '"',
                '"',
                """, """,
                "「",
                "」",
            ]
        )

        # 需要过滤的标点符号（除了保留的那些）
        filter_punctuation = set(
            ["。", "，", "、", "：", "；", "·", "~", ",", ".", ":", ";"]
        )

        # 如果是最后一句，且以句号结尾，移除句尾的句号
        if is_last_sentence and text[-1] in ["。", "."]:
            text = text[:-1]

        # 处理文本中的标点
        result = ""
        for char in text:
            if char in filter_punctuation:
                # 过滤掉需要过滤的标点
                continue
            result += char

        return result

    def _process_for_sending_and_memory(self, content: str) -> dict:
        """
        处理AI回复，添加$和￥分隔符，过滤标点符号
        返回处理后的分段消息和存储到记忆的内容
        """
        if not content:
            return {
                "parts": [],
                "memory_content": "",
                "total_length": 0,
                "sentence_count": 0,
            }

        # 首先按照$符号分割消息，但保留连续的多个$只当作一个分隔符
        # 替换连续的多个$为一个特殊标记
        content_with_markers = re.sub(r"\${2,}", "###MULTI_DOLLAR###", content)

        # 过滤掉$和￥符号周围的标点符号
        # 定义需要过滤的标点符号集合（包括中英文标点）
        filter_punctuation = (
            r"。，、；：·~\.,;:，、"
            '"!！?？…()（）""\'\'""'
            "【】[]{}《》<>『』「」—_-+=*&#@"
        )

        # 过滤$符号前面的标点符号
        content_with_markers = re.sub(
            r"[" + filter_punctuation + r"]+\s*\$", "$", content_with_markers
        )
        # 过滤$符号后面的标点符号
        content_with_markers = re.sub(
            r"\$\s*[" + filter_punctuation + r"]+", "$", content_with_markers
        )

        # 过滤￥符号前面的标点符号
        content_with_markers = re.sub(
            r"[" + filter_punctuation + r"]+\s*￥", "￥", content_with_markers
        )
        # 过滤￥符号后面的标点符号
        content_with_markers = re.sub(
            r"￥\s*[" + filter_punctuation + r"]+", "￥", content_with_markers
        )

        # 处理$符号周围可能存在的空格问题
        # 将" $ "、"$ "和" $"标准化为单个$符号进行分割
        content_with_markers = re.sub(r"\s*\$\s*", "$", content_with_markers)

        # 移除可能存在的￥符号周围的空格
        content_with_markers = re.sub(r"\s*￥\s*", "￥", content_with_markers)

        # 然后按照单个$分割
        dollar_parts = re.split(r"\$", content_with_markers)

        # 如果没有找到$分隔符，或者只有一部分，则使用原始分段逻辑
        if len(dollar_parts) <= 1:
            # 检查是否包含表情符号或特殊字符
            has_emoji = bool(
                re.search(r"[\U00010000-\U0010ffff\u2600-\u26FF\u2700-\u27BF]", content)
            )

            # 对于包含表情符号的内容，使用不同的处理策略
            if has_emoji:
                # 直接使用句子作为分割单位，不再使用标点符号分割
                # 可能包含表情符号的句子，按照换行符或者句号分割
                sentences = re.split(r"([。！？\.\!\?\n])", content)

                # 重组句子
                complete_sentences = []
                for i in range(0, len(sentences) - 1, 2):
                    if i + 1 < len(sentences):
                        # 将句子和标点符号重新组合
                        sentence = sentences[i] + sentences[i + 1]
                        complete_sentences.append(sentence)

                # 处理最后一个可能没有标点的片段
                if len(sentences) % 2 == 1 and sentences[-1].strip():
                    complete_sentences.append(sentences[-1])

                # 如果没有成功分割，则将整个内容作为一句话处理
                if not complete_sentences:
                    complete_sentences = [content]

                # 直接将每个句子作为一部分，不进行标点过滤
                processed_parts = []
                memory_parts = []

                for i, sentence in enumerate(complete_sentences):
                    clean_sentence = sentence.strip()
                    if clean_sentence:
                        # 恢复特殊标记为连续的$
                        clean_sentence = clean_sentence.replace(
                            "###MULTI_DOLLAR###", "$$"
                        )

                        # 添加到处理结果
                        processed_parts.append(clean_sentence)

                        # 为记忆内容准备，最后一句添加￥
                        if i == len(complete_sentences) - 1:
                            memory_parts.append(clean_sentence + "￥")
                        else:
                            memory_parts.append(clean_sentence)

                # 为记忆内容添加$分隔符 - 不使用空格
                memory_content = "$".join(memory_parts)

                return {
                    "parts": processed_parts,
                    "memory_content": memory_content,
                    "total_length": sum(len(part) for part in processed_parts),
                    "sentence_count": len(processed_parts),
                }

            # 没有表情符号的情况，使用原来的处理逻辑
            # 使用正则表达式识别句子
            sentences = re.split(r"([。！？\.\!\?])", content)

            # 重组句子
            complete_sentences = []
            for i in range(0, len(sentences) - 1, 2):
                if i + 1 < len(sentences):
                    # 将句子和标点符号重新组合
                    sentence = sentences[i] + sentences[i + 1]
                    complete_sentences.append(sentence)

            # 处理最后一个可能没有标点的片段
            if len(sentences) % 2 == 1 and sentences[-1].strip():
                complete_sentences.append(sentences[-1])

            # 如果没有分离出句子，则视为一个完整句子
            if not complete_sentences and content.strip():
                complete_sentences = [content]

            # 处理每个句子，添加分隔符，过滤标点
            processed_parts = []
            memory_parts = []

            # 将每个句子作为单独的部分处理
            for i, sentence in enumerate(complete_sentences):
                is_last = i == len(complete_sentences) - 1
                # 过滤标点符号
                filtered_sentence = self._filter_punctuation(sentence, is_last)

                # 如果句子不为空，添加到处理结果中
                if filtered_sentence.strip():
                    # 恢复特殊标记为连续的$
                    filtered_sentence = filtered_sentence.replace(
                        "###MULTI_DOLLAR###", "$$"
                    )

                    # 处理记忆内容，给最后一句添加￥
                    memory_sentence = filtered_sentence
                    if is_last:
                        memory_sentence = memory_sentence + "￥"

                    processed_parts.append(filtered_sentence)
                    memory_parts.append(memory_sentence)

            # 为记忆内容添加$分隔符 - 不使用空格
            memory_content = "$".join(memory_parts)

            return {
                "parts": processed_parts,
                "memory_content": memory_content,
                "total_length": sum(len(part) for part in processed_parts),
                "sentence_count": len(processed_parts),
            }

        # 现在处理$分隔的部分
        processed_parts = []
        memory_parts = []

        for i, part in enumerate(dollar_parts):
            # 恢复特殊标记为连续的$
            part = part.replace("###MULTI_DOLLAR###", "$$")

            # 清理和准备部分，进行标点过滤
            clean_part = part.strip()
            if clean_part:
                # 对非空部分应用标点过滤
                is_last = i == len(dollar_parts) - 1
                filtered_part = self._filter_punctuation(clean_part, is_last)

                # 再次检查分隔符前后的标点符号（保证彻底清理）
                if i > 0:  # 不是第一部分，检查开头的标点
                    filtered_part = re.sub(
                        r"^[" + filter_punctuation + r"]+", "", filtered_part
                    )

                if i < len(dollar_parts) - 1:  # 不是最后部分，检查结尾的标点
                    filtered_part = re.sub(
                        r"[" + filter_punctuation + r"]+$", "", filtered_part
                    )

                if filtered_part.strip():
                    processed_parts.append(filtered_part)

                    # 为记忆内容准备，最后一部分添加￥
                    if i == len(dollar_parts) - 1:
                        memory_parts.append(filtered_part + "￥")
                    else:
                        memory_parts.append(filtered_part)

        # 为记忆内容添加$分隔符 - 直接连接，不添加空格
        memory_content = "$".join(memory_parts)

        return {
            "parts": processed_parts,
            "memory_content": memory_content,
            "total_length": sum(len(part) for part in processed_parts),
            "sentence_count": len(processed_parts),
        }

    def _split_message_for_sending(self, text):
        """将消息分割成适合发送的多个部分"""
        if not text:
            return {"parts": [], "total_length": 0, "sentence_count": 0}

        # 使用新的处理函数
        processed = self._process_for_sending_and_memory(text)

        # 添加更详细的日志，用于调试
        logger.info(f'消息分割: 原文 "{text[:100]}..."')
        logger.info(f"消息分割: 分成了 {len(processed['parts'])} 个部分")

        for i, part in enumerate(processed["parts"]):
            # 增加日志详细度，显示每个部分的实际内容和长度
            logger.info(f'消息分割部分 {i+1}: "{part}" (长度: {len(part)}字符)')

        if "memory_content" in processed:
            # 显示处理后的记忆内容和长度
            mem_content = processed["memory_content"]
            logger.info(
                f'记忆内容: "{mem_content[:100]}..." (总长度: {len(mem_content)}字符)'
            )

            # 添加分隔符调试信息
            dollar_count = mem_content.count("$")
            yen_count = mem_content.count("￥")
            logger.debug(
                f"记忆内容中的分隔符: $符号数量={dollar_count}, ￥符号数量={yen_count}"
            )

        return {
            "parts": processed["parts"],
            "total_length": processed["total_length"],
            "sentence_count": processed["sentence_count"],
            "memory_content": processed["memory_content"],
        }

    def _send_split_messages(self, messages, chat_id):
        """发送分割后的消息，不进行重试和失败检查"""
        if not messages or not isinstance(messages, dict):
            return False

        # 添加发送锁，确保一个消息的所有部分发送完毕后才能发送下一个消息
        if not hasattr(self, "send_message_lock"):
            self.send_message_lock = threading.Lock()

        # 使用锁确保消息发送的原子性
        with self.send_message_lock:
            # 记录已发送的消息，防止重复发送
            sent_messages = set()

            # 计算自然的发送间隔
            base_interval = 0.5  # 基础间隔时间（秒）

            # 检查消息内容是否已经包含@标记，避免重复@
            first_part = messages["parts"][0] if messages["parts"] else ""
            already_has_at = bool(re.search(r"^@[^\s]+", first_part))

            # 检查是否是群聊消息（通过chat_id是否包含群聊标识）
            is_group_chat = False
            sender_name = None

            # 只有当消息不包含@标记时才尝试添加
            if not already_has_at:
                # 从chat_id中提取群聊信息
                if hasattr(self, "group_chat_memory"):
                    is_group_chat = chat_id in self.group_chat_memory.group_chats
                    if is_group_chat:
                        # 从最近的群聊消息中获取发送者名称
                        recent_messages = self.group_chat_memory.get_memory_from_file(
                            chat_id, limit=1
                        )
                        if recent_messages:
                            sender_name = recent_messages[0].get("sender_name")

            for i, part in enumerate(messages["parts"]):
                if part not in sent_messages and part.strip():
                    # 处理消息中的$分隔符
                    processed_part = part

                    # 移除消息开头的$符号
                    if processed_part.startswith("$"):
                        processed_part = processed_part[1:].strip()

                    # 不再移除消息中的$符号，因为它们已经被用作分隔符
                    # processed_part = processed_part.replace(' $ ', ' ').replace('$ ', ' ').replace(' $', ' ')

                    # 模拟真实用户输入行为
                    time.sleep(base_interval)  # 基础间隔

                    # 只有在第一条消息、是群聊、有发送者名称且消息不已经包含@时才添加@
                    if i == 0 and is_group_chat and sender_name and not already_has_at:
                        send_content = f"@{sender_name}\u2005{processed_part}"
                    else:
                        send_content = processed_part

                    # 发送消息，不检查结果
                    logger.info(
                        f"发送消息片段 {i+1}/{len(messages['parts'])}: {send_content[:20]}..."
                    )

                    # 不捕获异常，不检查结果，假设所有消息都已成功发送
                    self.wx.SendMsg(send_content, chat_id)
                    sent_messages.add(part)

                    # 根据消息长度动态调整下一条消息的等待时间
                    wait_time = base_interval + random.uniform(0.3, 0.7) * (
                        len(processed_part) / 50
                    )
                    time.sleep(wait_time)

        # 所有消息都假设已成功发送
        return True

    def get_private_api_response(
        self, message, user_id, memory_id=None, current_time=None
    ):
        """获取私聊API响应"""
        try:
            deepseek_response = self.get_api_response(message, user_id)

            # 如果API响应为空或出错，直接返回
            if not deepseek_response or not isinstance(deepseek_response, str):
                logger.error(f"API响应为空或格式错误: {deepseek_response}")
                return "抱歉，我暂时无法回应，请稍后再试。"

            # 清理API回复，移除系统标记和提示词
            cleaned_response = self._clean_ai_response(deepseek_response)

            # 处理回复，添加$和￥分隔符，过滤标点符号
            processed = self._process_for_sending_and_memory(cleaned_response)

            # 如果设置了memory_id，更新记忆
            if hasattr(self, "memory_handler") and memory_id:
                try:
                    # 使用memory_content作为存储内容
                    memory_content = processed.get("memory_content", cleaned_response)
                    # 使用修改后的API响应更新记忆
                    self.memory_handler.update_memory(memory_id, memory_content)
                    logger.info(f"记忆已更新: {memory_id}")
                except Exception as memory_e:
                    logger.error(f"更新记忆失败: {str(memory_e)}")

            # 返回分割后的消息对象，以便主函数处理发送
            return {
                "parts": processed.get("parts", [cleaned_response]),
                "total_length": processed.get("total_length", len(cleaned_response)),
                "sentence_count": processed.get("sentence_count", 1),
            }

        except Exception as e:
            logger.error(f"获取私聊API响应失败: {str(e)}")
            return "抱歉，处理您的消息时出现了错误，请稍后再试。"

    def set_replying_status(self, is_replying):
        """设置所有处理器的回复状态"""
        try:
            # 设置图像识别服务的状态
            if (
                hasattr(self, "image_recognition_service")
                and self.image_recognition_service
            ):
                self.image_recognition_service.set_replying_status(is_replying)

            # 设置图片处理器的状态
            if hasattr(self, "image_handler") and self.image_handler:
                self.image_handler.set_replying_status(is_replying)

            # 设置表情包处理器的状态
            if hasattr(self, "emoji_handler") and self.emoji_handler:
                self.emoji_handler.set_replying_status(is_replying)

        except Exception as e:
            logger.error(f"设置回复状态时出错: {str(e)}")

    def process_message(self, message, who, source="wechat"):
        """处理接收到的微信消息"""
        try:
            # 设置所有处理器为"正在回复"状态
            self.set_replying_status(True)

            # 检查消息类型
            if isinstance(message, dict) and "Type" in message:
                # 检查是否是自己发送的消息
                is_self_message = message.get("IsSelf", False)

                if message["Type"] == 1:  # 文本消息
                    return self.process_text_message(
                        message["Content"], who, source, is_self_message
                    )
                elif message["Type"] == 3:  # 图片消息
                    return self.process_image_message(
                        message.get("Content", ""), who, is_self_message
                    )
                else:
                    logger.warning(f"未支持的消息类型: {message['Type']}")
                    return "抱歉，暂不支持此类型的消息。"
            else:
                # 直接处理文本内容
                return self.process_text_message(message, who, source, False)
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}", exc_info=True)
            return "抱歉，处理您的消息时出现了错误，请稍后再试。"
        finally:
            # 确保处理完成后重置回复状态
            self.set_replying_status(False)

    def process_image_message(
        self, image_path: str, who: str, is_self_message: bool = False
    ):
        """处理图片消息，识别图片内容"""
        try:
            # 如果是自己发送的图片，直接跳过处理
            if is_self_message:
                logger.info(f"检测到自己发送的图片，跳过识别: {image_path}")
                return None

            # 获取当前时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 设置所有处理器为"正在回复"状态
            self.set_replying_status(True)

            try:
                # # 将图片内容添加到服务中进行识别
                # def callback(recognition_result):
                #     try:
                #         # 将识别结果作为普通消息处理
                #         if recognition_result:
                #             logger.info(f"图片识别结果: {recognition_result[:100]}...")
                #             # 构建消息格式
                #             formatted_content = f"[{current_time}] ta私聊对你说：{recognition_result}"
                #             # 调用API处理识别后的文本
                #             response = self.get_api_response(formatted_content, who)

                #             # 发送回复
                #             if response and not self.is_debug:
                #                 # 分割并发送消息
                #                 split_messages = self._split_message_for_sending(response)
                #                 self._send_split_messages(split_messages, who)
                #     except Exception as e:
                #         logger.error(f"处理图片识别回调时出错: {str(e)}")
                # 2025-03-27 el弃用，这里队列回调不正确，改成直接调用

                if (
                    hasattr(self, "image_recognition_service")
                    and self.image_recognition_service
                ):
                    result = self.image_recognition_service._recognize_image_impl(
                        image_path, False
                    )
                    logger.info(f"图片识别请求已添加到队列: {result}")
                    return result
                else:
                    logger.error("图像识别服务未初始化")
                    return "抱歉，图片识别服务未准备好"
            finally:
                # 重置回复状态
                self.set_replying_status(False)

        except Exception as e:
            logger.error(f"处理图片消息失败: {str(e)}", exc_info=True)
            return "抱歉，处理图片时出现错误"

    def _handle_emoji_message(
        self, content: str, chat_id: str, user_id: str, is_self_emoji: bool = False
    ):
        """处理表情包请求消息"""
        try:
            # 如果是自己发送的表情包，直接跳过处理
            if is_self_emoji:
                logger.info(f"检测到自己发送的表情包，跳过处理")
                return None

            # 获取当前时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 设置所有处理器为"正在回复"状态
            self.set_replying_status(True)

            try:
                # # 将表情包请求添加到队列中进行处理
                # def callback(emoji_path):
                #     try:
                #         if emoji_path and os.path.exists(emoji_path):
                #             logger.info(f"找到表情包: {emoji_path}")
                #             # 发送表情包
                #             if not self.is_debug:
                #                 self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                #     except Exception as e:
                #         logger.error(f"处理表情包回调时出错: {str(e)}")
                # 2025-03-27 el弃用，这里队列回调不正确，改成直接调用

                if hasattr(self, "emoji_handler") and self.emoji_handler:
                    result = self.emoji_handler._get_emotion_emoji_impl(
                        content, user_id
                    )
                    logger.info(f"表情包请求已添加到队列: {result}")
                    return result
                else:
                    logger.error("表情包处理器未初始化")
                    return "抱歉，表情包功能未准备好"
            finally:
                # 重置回复状态
                self.set_replying_status(False)

        except Exception as e:
            logger.error(f"处理表情包请求失败: {str(e)}", exc_info=True)
            return "抱歉，处理表情包时出现错误"

    def process_text_message(
        self,
        content: str,
        who: str,
        source: str = "wechat",
        is_self_message: bool = False,
    ):
        """处理文本消息"""
        try:
            # 如果内容为空，直接返回
            if not content or not content.strip():
                return None

            # 检查是否是表情包请求
            if (
                hasattr(self, "emoji_handler")
                and self.emoji_handler
                and self.emoji_handler.is_emoji_request(content)
            ):
                logger.info(f"检测到表情包请求: {content}")
                return self._handle_emoji_message(content, who, who, is_self_message)

            # 检查是否是随机图片请求
            if (
                hasattr(self, "image_handler")
                and self.image_handler
                and self.image_handler.is_random_image_request(content)
            ):
                logger.info(f"检测到随机图片请求: {content}")
                return self._handle_random_image_request(content, who, None, who, False)

            # 检查是否是图像生成请求
            if (
                hasattr(self, "image_handler")
                and self.image_handler
                and self.image_handler.is_image_generation_request(content)
            ):
                logger.info(f"检测到图像生成请求: {content}")
                return self._handle_image_generation_request(
                    content, who, None, who, False
                )

            # 其他处理逻辑...

            # 获取API回复
            # 添加历史记忆等

            # 调用API获取响应
            response = self.get_api_response(content, who)

            # 发送回复消息
            if response and not self.is_debug:
                # 分割并发送消息
                split_messages = self._split_message_for_sending(response)
                self._send_split_messages(split_messages, who)

            return response

        except Exception as e:
            logger.error(f"处理文本消息失败: {str(e)}", exc_info=True)
            return "抱歉，处理您的消息时出现错误"

    def _init_auto_task_message(self):
        """初始化处理自动任务消息的线程"""

        def _process_auto_task_message():
            """
            处理发送自动任务消息
            """
            while True:
                if self.auto_task_message_queue:
                    if len(self.auto_task_message_queue) == 0:
                        return
                    logger.info(
                        f"开始处理自动任务消息队列，当前队列长度: {
                            len(self.auto_task_message_queue)
                            }"
                            )
                    for message_dict in self.auto_task_message_queue:
                        if "chat_id" in message_dict and "content" in message_dict:
                            logger.info(f"处理自动任务消息: {message_dict}")
                            chat_id = message_dict["chat_id"]
                            content = message_dict["content"]
                            messages = self._split_message_for_sending(content)
                            self._send_split_messages(messages, chat_id)
                            self.auto_task_message_queue.remove(message_dict)
                time.sleep(0.1)

        threading.Timer(1, _process_auto_task_message).start()

    # 添加新的获取最大上下文轮数的方法
    def _get_max_context_turns(self):
        """从配置文件获取最大上下文轮数"""
        try:
            # 优先尝试从config.categories.user_settings.settings.max_groups获取
            try:
                if hasattr(config, "categories") and hasattr(
                    config.categories, "user_settings"
                ):
                    user_settings = config.categories.user_settings.settings
                    if hasattr(user_settings, "max_groups"):
                        max_turns = user_settings.max_groups.value
                        if isinstance(max_turns, (int, float)) and max_turns > 0:
                            return int(max_turns)
                        logger.warning(
                            f"配置中的max_groups值无效: {max_turns}，使用默认值"
                        )
            except AttributeError as e:
                logger.warning(f"通过user_settings获取max_groups失败: {str(e)}")

            # 尝试从config.behavior.context中获取
            if hasattr(config, "behavior") and hasattr(config.behavior, "context"):
                if hasattr(config.behavior.context, "max_groups"):
                    max_turns = config.behavior.context.max_groups
                    if isinstance(max_turns, (int, float)) and max_turns > 0:
                        return int(max_turns)
                    logger.warning(
                        f"behavior.context中的max_groups值无效: {max_turns}，使用默认值"
                    )

            # 尝试现有的配置项名称
            group_turns = self._get_config_value("group_context_turns", None)
            if (
                group_turns is not None
                and isinstance(group_turns, (int, float))
                and group_turns > 0
            ):
                return int(group_turns)

            # 使用默认值
            return 30
        except Exception as e:
            logger.error(f"获取最大上下文轮数失败: {str(e)}")
            return 30

    def _calculate_time_decay_weight(
        self, timestamp, current_time=None, time_format="%Y-%m-%d %H:%M:%S"
    ):
        """
        计算基于时间衰减的权重

        Args:
            timestamp: 消息时间戳字符串
            current_time: 当前时间，如果为None则使用当前系统时间
            time_format: 时间格式

        Returns:
            float: 时间衰减权重，范围[0, 1]
        """
        try:
            if not timestamp:
                return 0.0

            # 如果未提供当前时间，使用当前系统时间
            if current_time is None:
                current_time = datetime.now()
            elif isinstance(current_time, str):
                current_time = datetime.strptime(current_time, time_format)

            # 将时间戳转换为datetime对象
            msg_time = datetime.strptime(timestamp, time_format)

            # 计算时间差（秒）
            time_diff_seconds = (current_time - msg_time).total_seconds()

            # 确保时间差非负
            time_diff_seconds = max(0, time_diff_seconds)

            # 将时间差转换为小时
            time_diff_hours = time_diff_seconds / 3600.0

            # 根据配置的衰减方法计算权重
            if self.decay_method == "exponential":
                # 指数衰减: weight = exp(-λ * t)
                weight = math.exp(-self.decay_rate * time_diff_hours)
            else:
                # 线性衰减: weight = max(0, 1 - λ * t)
                weight = max(0.0, 1.0 - self.decay_rate * time_diff_hours)

            # 确保权重在[0, 1]范围内
            weight = max(0.0, min(1.0, weight))

            return weight

        except Exception as e:
            logger.error(f"计算时间衰减权重失败: {str(e)}")
            return 0.5  # 出错时返回中等权重作为默认值

    def _apply_weights_and_filter_context(
        self, context_messages, current_time=None, max_turns=None, current_user=None
    ):
        """
        应用权重并筛选上下文消息

        Args:
            context_messages: 上下文消息列表
            current_time: 当前时间，如果为None则使用当前系统时间
            max_turns: 最大保留的上下文轮数，如果为None则使用配置值
            current_user: 当前交互的用户名，用于增强相关消息的权重

        Returns:
            list: 经过权重排序和筛选后的上下文消息
        """
        if not context_messages:
            return []

        # 如果未指定max_turns，使用配置的值
        if max_turns is None:
            max_turns = self.group_context_turns

        # 如果未启用时间衰减和语义搜索，按时间排序并截取最近的max_turns条
        if not self.use_time_decay and not self.use_semantic_search:
            # 按时间戳排序（从旧到新）
            sorted_msgs = sorted(context_messages, key=lambda x: x.get("timestamp", ""))
            # 返回最新的max_turns条消息
            return sorted_msgs[-max_turns:]

        # 当前时间
        if current_time is None:
            current_time = datetime.now()

        # 为每条消息计算权重
        weighted_msgs = []
        for msg in context_messages:
            # 1. 基础权重 - 时间衰减
            time_weight = self._calculate_time_decay_weight(
                msg.get("timestamp", ""), current_time
            )

            # 2. 用户相关性权重
            user_weight = 1.0  # 默认权重
            if current_user:
                # 如果消息的发送者与当前用户匹配，增加权重
                msg_sender = msg.get("sender_name", "").lower()
                current_user_lower = current_user.lower()

                # 完全匹配给予最高权重
                if msg_sender == current_user_lower:
                    user_weight = 2.0
                # 部分匹配（如昵称包含用户名）也提高权重
                elif (
                    current_user_lower in msg_sender or msg_sender in current_user_lower
                ):
                    user_weight = 1.5
                # 如果是机器人回复当前用户的消息，也提高权重
                elif (
                    msg.get("human_message", "")
                    and msg.get("assistant_message", "")
                    and current_user_lower in msg.get("human_message", "").lower()
                ):
                    user_weight = 1.3

            # 3. 语义相关性权重
            semantic_weight = 0.5  # 默认中等语义相关性
            if self.use_semantic_search and "semantic_score" in msg:
                semantic_weight = msg["semantic_score"]

            # 组合权重 - 使用配置的权重比例
            if self.use_semantic_search:
                # 组合三种权重
                final_weight = (
                    self.time_weight * time_weight
                    + self.user_weight * user_weight
                    + self.semantic_weight * semantic_weight
                )
            else:
                # 只使用时间和用户权重
                final_weight = time_weight * user_weight

            weighted_msgs.append(
                {
                    "message": msg,
                    "weight": final_weight,
                    "is_relevant_user": user_weight > 1.0,
                    "time_weight": time_weight,
                    "user_weight": user_weight,
                    "semantic_weight": semantic_weight,
                }
            )

        # 按权重从高到低排序
        weighted_msgs.sort(key=lambda x: x["weight"], reverse=True)

        # 记录权重计算情况（仅记录top 3用于调试）
        for i, item in enumerate(weighted_msgs[:3]):
            msg = item["message"]
            logger.debug(
                f"消息权重 #{i+1}: 权重={item['weight']:.2f}, 时间={item['time_weight']:.2f}, 用户={item['user_weight']:.2f}, 语义={item['semantic_weight']:.2f}, 内容={msg.get('human_message', '')[:30]}..."
            )

        # 过滤掉权重低于阈值的消息
        filtered_msgs = [
            item["message"]
            for item in weighted_msgs
            if item["weight"] >= self.weight_threshold
        ]

        # 确保消息的多样性：保留一定数量的相关用户消息和其他用户消息
        if current_user and len(filtered_msgs) < max_turns:
            # 分离相关用户和其他用户的消息
            relevant_msgs = [
                m
                for m in weighted_msgs
                if m["is_relevant_user"] and m["message"] not in filtered_msgs
            ]
            other_msgs = [
                m
                for m in weighted_msgs
                if not m["is_relevant_user"] and m["message"] not in filtered_msgs
            ]

            # 计算需要补充的消息数量
            remaining_slots = max_turns - len(filtered_msgs)

            # 预留至少30%的槽位给其他用户的消息，确保对话的多样性
            min_other_slots = max(1, int(remaining_slots * 0.3))
            max_relevant_slots = remaining_slots - min_other_slots

            # 添加相关用户消息
            filtered_msgs.extend(
                [m["message"] for m in relevant_msgs[:max_relevant_slots]]
            )

            # 再添加其他用户消息
            filtered_msgs.extend([m["message"] for m in other_msgs[:min_other_slots]])

        # 如果仍然不足max_turns，继续添加剩余消息
        if len(filtered_msgs) < max_turns:
            remaining_msgs = [
                item["message"]
                for item in weighted_msgs
                if item["message"] not in filtered_msgs
            ]
            filtered_msgs.extend(remaining_msgs[: max_turns - len(filtered_msgs)])

        # 最后再按时间排序，确保上下文时间顺序正确
        filtered_msgs.sort(key=lambda x: x.get("timestamp", ""))

        # 限制最大消息数量
        return filtered_msgs[-max_turns:]

    def QQ_handle_text_message(self, content: str, qqid: str, sender_name: str) -> dict:
        """
        处理普通文本消息

        Args:
            content: 消息内容
            qqid: QQ号
            sender_name: 发送者名称

        Returns:
            dict: 处理后的回复消息
        """
        try:
            # 添加正则表达式过滤时间戳
            time_pattern = r"\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]"
            content = re.sub(time_pattern, "", content)

            # 更通用的模式
            general_pattern = r"\[\d[^\]]*\]|\[\d+\]"
            content = re.sub(general_pattern, "", content)

            logger.info("处理普通文本回复")

            # 定义结束关键词
            end_keywords = [
                "结束",
                "再见",
                "拜拜",
                "下次聊",
                "先这样",
                "告辞",
                "bye",
                "晚点聊",
                "回头见",
                "稍后",
                "改天",
                "有空聊",
                "去忙了",
                "暂停",
                "待一会儿",
                "过一会儿",
                "晚安",
                "休息",
                "走了",
                "撤了",
                "闪了",
                "不聊了",
                "断了",
                "下线",
                "离开",
                "停",
                "歇",
                "退",
            ]

            # 检查消息中是否包含结束关键词
            is_end_of_conversation = any(keyword in content for keyword in end_keywords)

            # 计算用户输入的字符长度，用于动态调整回复长度
            user_input_length = len(content)
            target_length = int(
                user_input_length
                * self._calculate_response_length_ratio(user_input_length)
            )
            target_sentences = max(
                1, min(4, int(target_length / 25))
            )  # 大约每25个字符一个句子

            # 添加长度限制提示词
            length_prompt = f"\n\n请注意：你的回复应当与用户消息的长度相当，控制在约{target_length}个字符和{target_sentences}个句子左右。"

            if is_end_of_conversation:
                # 如果检测到结束关键词，在消息末尾添加提示
                content += "\n请以你的身份回应用户的结束语。" + length_prompt
                logger.info(f"检测到对话结束关键词，尝试生成更自然的结束语")
            else:
                # 添加长度限制提示词
                content += length_prompt

            # 获取 API 回复
            reply = self.get_api_response(content, qqid)
            if "</think>" in reply:
                think_content, reply = reply.split("</think>", 1)
                logger.info("\n思考过程:")
                logger.info(think_content.strip())
                logger.info(reply.strip())
            else:
                logger.info("\nAI回复:")
                logger.info(reply)

            # 过滤括号内的动作和情感描述
            reply = self._filter_action_emotion(reply)

            # 使用统一的消息分割方法
            delayed_reply = self._split_message_for_sending(reply)
            return delayed_reply
        except Exception as e:
            logger.error(f"处理QQ文本消息失败: {str(e)}")
            return {
                "parts": ["抱歉，处理消息时出现错误，请稍后重试。"],
                "total_length": 0,
            }

    def QQ_handle_voice_request(self, content, qqid, sender_name):
        """处理普通文本回复（语音功能已移除）"""
        return self.QQ_handle_text_message(content, qqid, sender_name)

    def QQ_handle_random_image_request(self, content, qqid, sender_name):
        """处理普通文本回复（随机图片功能已移除）"""
        return self.QQ_handle_text_message(content, qqid, sender_name)

    def QQ_handle_image_generation_request(self, content, qqid, sender_name):
        """处理普通文本回复（图像生成功能已移除）"""
        return self.QQ_handle_text_message(content, qqid, sender_name)

    def _memory_quality_score(self, mem, username):
        """评估记忆质量分数，返回0-100之间的值"""
        if not mem.get("message") or not mem.get("reply"):
            return 0

        msg_len = len(mem["message"])
        reply_len = len(mem["reply"])

        # 太短的对话质量低
        if msg_len < 5 or reply_len < 10:
            return 0

        # 太长的对话也不理想
        if msg_len > 500 or reply_len > 1000:
            return 10

        # 基础分数
        score = min(100, (msg_len + reply_len) / 10)

        # 包含特定用户名或对话元素的加分
        if (
            username.lower() in mem["message"].lower()
            or username.lower() in mem["reply"].lower()
        ):
            score += 15

        # 包含问答格式的加分
        if "?" in mem["message"] or "？" in mem["message"]:
            score += 10

        return min(100, score)  # 确保分数不超过100

    # 添加RAG语义查询方法
    async def _get_semantic_similar_messages(
        self, query: str, group_id: str = None, user_id: str = None, top_k: int = 5
    ) -> List[Dict]:
        """获取语义相似的上下文消息，使用RAG系统进行检索"""
        try:
            if not self.rag_manager:
                logger.warning("未配置RAG管理器，无法获取语义相似消息")
                return []

            # 获取RAG查询结果
            results = await self.rag_manager.query(query, top_k * 2)

            # 过滤结果
            filtered_results = []
            for result in results:
                metadata = result.get("metadata", {})
                msg_type = metadata.get("type", "")
                msg_group_id = metadata.get("group_id", "")
                msg_sender = metadata.get("sender_name", "")

                # 检查发送者是否是机器人自己，如果是则跳过
                if msg_sender == self.robot_name:
                    continue

                # 根据消息类型进行过滤
                if msg_type == "group_chat_message" and (
                    not group_id or msg_group_id == group_id
                ):
                    # 群聊消息处理
                    filtered_results.append(
                        {
                            "timestamp": metadata.get("timestamp", ""),
                            "sender_name": msg_sender,
                            "human_message": metadata.get("human_message", ""),
                            "assistant_message": metadata.get("assistant_message", ""),
                            "score": result.get("score", 0.0),
                        }
                    )
                elif (
                    msg_type == "private_message"
                    and user_id
                    and metadata.get("user_id") == user_id
                ):
                    # 私聊消息处理
                    filtered_results.append(
                        {
                            "timestamp": metadata.get("timestamp", ""),
                            "sender_name": msg_sender,
                            "human_message": metadata.get("human_message", ""),
                            "assistant_message": metadata.get("assistant_message", ""),
                            "score": result.get("score", 0.0),
                        }
                    )

            # 按得分排序
            filtered_results.sort(key=lambda x: x.get("score", 0), reverse=True)

            # 返回前top_k个结果
            return filtered_results[:top_k]
        except Exception as e:
            logger.error(f"获取语义相似消息失败: {str(e)}")
            return []

    def cleanup_message_queues(self):
        """清理过期的消息队列和缓存，避免消息堆积和处理卡死"""
        try:
            current_time = time.time()
            message_timeout = 3600  # 1小时超时时间

            # 1. 清理全局消息队列中的过期消息
            with self.global_message_queue_lock:
                if self.global_message_queue:
                    # 过滤掉添加时间超过1小时的消息
                    fresh_messages = [
                        msg
                        for msg in self.global_message_queue
                        if current_time - msg.get("added_time", 0) < message_timeout
                    ]

                    expired_count = len(self.global_message_queue) - len(fresh_messages)
                    if expired_count > 0:
                        logger.info(f"清理全局消息队列中的 {expired_count} 条过期消息")
                        self.global_message_queue = fresh_messages

                    # 如果队列处理标志卡住，但队列中有消息，重置处理状态
                    if self.global_message_queue and not self.is_processing_queue:
                        logger.warning("检测到队列处理状态异常，重启处理流程")
                        self.is_processing_queue = True

                        # 取消现有定时器（如果有）
                        if self.queue_process_timer:
                            self.queue_process_timer.cancel()

                        # 启动新的处理定时器
                        self.queue_process_timer = threading.Timer(
                            1.0, self._process_global_message_queue
                        )
                        self.queue_process_timer.daemon = True
                        self.queue_process_timer.start()

            # 2. 清理群聊缓存中的过期消息
            for group_id in list(self.group_at_cache.keys()):
                if self.group_at_cache[group_id]:
                    # 过滤掉添加时间超过1小时的消息
                    fresh_messages = [
                        msg
                        for msg in self.group_at_cache[group_id]
                        if current_time - msg.get("added_time", 0) < message_timeout
                    ]

                    expired_count = len(self.group_at_cache[group_id]) - len(
                        fresh_messages
                    )
                    if expired_count > 0:
                        logger.info(
                            f"清理群 {group_id} 中的 {expired_count} 条过期消息"
                        )
                        self.group_at_cache[group_id] = fresh_messages

            # 3. 清理分发锁，如果锁定时间过长
            # 这里简单处理，如果发送锁长时间未释放（超过5分钟），强制重置
            # 实际应用中可能需要更复杂的机制确保线程安全
            if (
                hasattr(self, "send_message_lock_time")
                and current_time - self.send_message_lock_time > 300
            ):
                logger.warning("检测到消息发送锁可能已死锁，强制重置")
                self.send_message_lock = threading.Lock()

            # 记录当前时间作为下次检查的参考
            self.send_message_lock_time = current_time

            # 设置下一次清理的定时器（每10分钟清理一次）
            cleanup_timer = threading.Timer(600, self.cleanup_message_queues)
            cleanup_timer.daemon = True
            cleanup_timer.start()

            logger.debug("消息队列清理完成")

        except Exception as e:
            logger.error(f"清理消息队列失败: {str(e)}")
            # 即使失败，也设置下一次的清理定时器
            cleanup_timer = threading.Timer(600, self.cleanup_message_queues)
            cleanup_timer.daemon = True
            cleanup_timer.start()

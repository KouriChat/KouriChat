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
from typing import List, Dict, Optional

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger("main")


class MessageHandler:
    def __init__(
        self,
        root_dir,
        llm: LLMService,
        robot_name: str = None,
        prompt_content: str = None,
        image_handler = None,
        emoji_handler = None,
        voice_handler = None,
        memory_handler = None,
        group_chat_memory = None,  # 新增参数，外部传入的群聊记忆实例
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
        self.wx = None
        self.is_debug = is_debug
        self.is_qq = is_qq

        # 添加详细日志，帮助诊断微信实例是否正确传递
        if self.wx:
            logger.info(f"消息处理器初始化 - 微信实例可用: {self.wx}")
        else:
            logger.warning("消息处理器初始化 - 微信实例为空")

        # 添加 handlers
        self.image_handler = image_handler
        self.emoji_handler = emoji_handler
        self.voice_handler = voice_handler
        self.memory_handler = memory_handler
        
        # 添加表情包发送跟踪器，以避免重复发送表情包
        self.emoji_sent_tracker = {}  # {message_id: True} 用于跟踪已经发送过表情包的消息
        self.emoji_lock = threading.Lock()  # 用于保护表情包发送跟踪器
        
        # 确保处理器能访问到微信实例
        if self.wx is not None:
            if self.emoji_handler and hasattr(self.emoji_handler, "update_wx_instance"):
                self.emoji_handler.update_wx_instance(self.wx)
                logger.info("已更新表情包处理器的微信实例")
                # 添加额外验证，确保wx实例确实被传递
                if hasattr(self.emoji_handler, "wx") and self.emoji_handler.wx:
                    logger.info("确认表情处理器的微信实例已正确设置")
                else:
                    logger.error("表情处理器的微信实例没有正确设置，可能导致表情无法发送")
            if self.image_handler and hasattr(self.image_handler, "update_wx_instance"):
                self.image_handler.update_wx_instance(self.wx)
            if self.voice_handler and hasattr(self.voice_handler, "update_wx_instance"):
                self.voice_handler.update_wx_instance(self.wx)
        else:
            logger.warning("无法更新处理器的微信实例，因为微信实例为空")

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
        
        # 添加表情包周期发送标记
        self.emoji_sent_this_cycle = False

        # 添加群聊@消息处理相关属性
        self.group_at_cache = (
            {}
        )  # 群聊@消息缓存，格式: {group_id: [{'sender_name': name, 'content': content, 'timestamp': time}, ...]}
        self.group_at_timer = {}  # 群聊@消息定时器

        # 添加消息发送锁，确保消息发送的顺序性
        self.send_message_lock = threading.Lock()
        
        # 添加最后收到消息时间戳记录
        self.last_received_message_timestamp: Dict[str, float] = {}
        
        # 添加自动任务队列专用锁
        self.auto_task_queue_lock = threading.Lock()
        
        # 添加全局消息处理队列和队列锁
        self.global_message_queue = []  # 全局消息队列，包含所有群组的待处理消息
        self.global_message_queue_lock = threading.Lock()  # 全局消息队列锁
        self.is_processing_queue = False  # 标记是否正在处理队列
        self.queue_process_timer = None  # 全局队列处理定时器
        self.send_message_lock_time = time.time()  # 记录发送锁的创建时间

        # 添加群聊记忆处理器
        if group_chat_memory is not None:
            # 优先使用外部传入的群聊记忆实例
            self.group_chat_memory = group_chat_memory
            logger.info("使用外部传入的群聊记忆实例")
        else:
            # 如果没有传入，则进行自行初始化
            try:
                # 导入 GroupChatMemory 类
                from src.handlers.memories.group_chat_memory import GroupChatMemory

                # 安全处理头像名称
                if isinstance(robot_name, str):
                    safe_avatar_name = re.sub(r"[^\w\-_\. ]", "_", robot_name)
                else:
                    safe_avatar_name = "default_avatar"

                # 获取群聊列表
                try:
                    from src.config import rag_config
                    group_chats = []
                    # 尝试从不同的配置路径获取群聊列表
                    if hasattr(rag_config.config, 'group_chats'):
                        group_chats = rag_config.config.group_chats
                    elif hasattr(rag_config.config, 'behavior') and hasattr(rag_config.config.behavior, 'context') and hasattr(rag_config.config.behavior.context, 'group_ids'):
                        group_chats = rag_config.config.behavior.context.group_ids
                except Exception as e:
                    logger.warning(f"无法从rag_config获取群聊列表: {str(e)}")
                    group_chats = []

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

        # 添加时间衰减控制
        self.use_time_decay = True  # 默认启用时间衰减

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

            # 添加：重置表情发送标记
            self.emoji_sent_this_cycle = False

            # 获取自动消息内容
            from src.config import config

            # 检查配置是否存在
            if (
                not hasattr(config, "behavior")
                or not hasattr(config.behavior, "auto_message")
                or not hasattr(config.behavior.auto_message, "content")
            ):
                logger.error("配置文件中缺少behavior.auto_message.content设置")
                auto_message = "你好，有什么可以帮助你的吗？"
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
                                        + "\n\n(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容，并且回复不要重复！！！)\n\n"
                                    )
                                    logger.info(
                                        f"找到 {len(memory_parts)} 轮历史对话记录"
                                    )
                        except Exception as e:
                            logger.error(f"获取历史对话记录失败: {str(e)}")

                    # 构建系统指令和上下文
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
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
                        # 修改：同步获取表情路径并检查周期标记
                        emoji_path = None
                        if not self.emoji_sent_this_cycle and hasattr(self, 'emoji_handler') and self.emoji_handler.enabled:
                            try:
                                # 同步获取表情路径
                                emoji_path = self.emoji_handler.get_emotion_emoji(
                                    ai_response, 
                                    target_user
                                )
                                
                                # 如果获取到路径，先发送表情
                                if emoji_path and os.path.exists(emoji_path):
                                    logger.info(f"发送AI回复情感表情包: {emoji_path}")
                                    if hasattr(self, 'wx') and self.wx:
                                        try:
                                            self.wx.SendFiles(filepath=emoji_path, who=target_user)
                                            logger.info(f"成功通过wxauto发送表情包文件: {emoji_path}")
                                            time.sleep(0.5) # 短暂等待，确保表情先显示
                                            self.emoji_sent_this_cycle = True # 标记已发送
                                        except Exception as e:
                                            logger.error(f"通过wxauto发送表情包失败: {str(e)}")
                                    else:
                                        logger.error("wx实例不可用，无法发送表情包")
                                
                            except Exception as e:
                                logger.error(f"处理AI回复表情包失败: {str(e)}")
                        
                        # 在发送表情后，再处理和发送文本
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
                                        "%Y-%m-%d %H:%M"
                                    )
                                    # 将消息存入群聊记忆
                                    self.group_chat_memory.add_message(
                                        target_user,  # 群聊ID
                                        self.robot_name,  # 发送者为机器人
                                        system_instruction,  # 保存系统指令作为输入
                                        is_at=True  # 标记为系统消息，使用is_at参数
                                    )
                                    
                                    # 更新助手回复
                                    self.group_chat_memory.update_assistant_response(
                                        target_user,
                                        timestamp,
                                        message_parts.get("memory_content", ai_response)
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
            # 添加：记录收到消息的时间戳
            current_ts = time.time()
            self.last_received_message_timestamp[chat_id] = current_ts
            
            # 添加：在处理消息开始时重置表情发送标记
            self.emoji_sent_this_cycle = False
            
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
            
        # 移除：之前错误放置的重置标记
        # # 添加：在处理消息开始时重置表情发送标记
        # self.emoji_sent_this_cycle = False

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
        # 添加：记录收到消息的时间戳
        current_ts = time.time()
        self.last_received_message_timestamp[group_id] = current_ts
        
        # 开始处理之前，更新当前群聊发送者信息
        self._update_current_group_sender(group_id, sender_name, username)
        
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
                
                # 无论是否引用消息，都需要根据is_at_from_param判断是否处理
                # 引用消息不再自动触发回复，必须同时有@才行

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
            # 设置当前正在回复
            self.set_replying_status(True)

            # 调用API获取回复
            response = self.get_api_response(content, username, chat_id if is_group else None, sender_name)
            
            # 诊断日志
            logger.info(f"获取到API回复，内容长度: {len(response) if response else 0}")

            if response and not self.is_debug:
                # 诊断日志
                if hasattr(self, 'emoji_handler'):
                    if self.emoji_handler:
                        logger.info(f"表情处理器可用，启用状态: {self.emoji_handler.enabled}")
                        if not self.emoji_handler.enabled:
                            logger.warning("表情处理器已禁用，不会触发表情分析")
                    else:
                        logger.warning("表情处理器为None，不会触发表情分析")
                else:
                    logger.warning("消息处理器没有emoji_handler属性，不会触发表情分析")
                
                # 生成消息唯一标识符，用于跟踪表情包发送状态
                message_id = f"{chat_id}_{int(time.time())}_{hash(response[:20])}"
                
                # 处理表情包 - 只有当该消息没有发送过表情包时才处理
                should_process_emoji = True
                with self.emoji_lock:
                    if message_id in self.emoji_sent_tracker:
                        # 已经为该消息发送过表情包，不再处理
                        should_process_emoji = False
                        logger.info(f"消息已经发送过表情包，跳过表情处理: {message_id}")
                    else:
                        # 标记该消息已处理表情包
                        self.emoji_sent_tracker[message_id] = True
                        # 清理旧跟踪记录，避免内存泄漏
                        current_time = time.time()
                        for old_id in list(self.emoji_sent_tracker.keys()):
                            if current_time - int(old_id.split('_')[1]) > 60:  # 60秒后清除
                                self.emoji_sent_tracker.pop(old_id, None)
                
                if should_process_emoji and hasattr(self, 'emoji_handler') and self.emoji_handler and self.emoji_handler.enabled:
                    try:
                        # 修改：同步获取表情路径
                        emoji_path = self.emoji_handler.get_emotion_emoji(
                            response, 
                            chat_id
                        )
                        
                        # 如果获取到路径，先发送表情
                        if emoji_path and os.path.exists(emoji_path):
                            logger.info(f"发送未缓存消息表情包: {emoji_path}")
                            if hasattr(self, 'wx') and self.wx:
                                try:
                                    self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                                    logger.info(f"成功通过wxauto发送未缓存消息表情包文件: {emoji_path}")
                                    time.sleep(0.5) # 短暂等待
                                    self.emoji_sent_this_cycle = True # 标记已发送
                                except Exception as e:
                                    logger.error(f"通过wxauto发送未缓存消息表情包失败: {str(e)}")
                            else:
                                logger.error("wx实例不可用，无法发送表情包")
                        else:
                            if emoji_path:
                                logger.error(f"表情包文件不存在: {emoji_path}")
                            else:
                                logger.info("没有生成表情包路径")

                    except Exception as e:
                        logger.error(f"处理AI回复表情包失败: {str(e)}", exc_info=True)
                
                # 不再等待表情处理，直接处理文本消息
                
                # 分割消息并发送
                split_messages = self._split_message_for_sending(response)
                # 如果是群聊消息，传递发送者名称
                if is_group:
                    self._send_split_messages(split_messages, chat_id, sender_name)
                else:
                    self._send_split_messages(split_messages, chat_id)
                
                # 修复：将对话存入记忆
                try:
                    if hasattr(self, "memory_handler") and self.memory_handler:
                        # 如果是群聊消息
                        if is_group:
                            # 将消息存入群聊记忆
                            if hasattr(self, "group_chat_memory") and self.group_chat_memory:
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                                # 将消息存入群聊记忆
                                self.group_chat_memory.add_message(
                                    chat_id,  # 群聊ID
                                    sender_name or "未知用户",  # 发送者
                                    content,  # 用户原始消息
                                    is_at=False
                                )
                                
                                # 更新助手回复
                                self.group_chat_memory.update_assistant_response(
                                    chat_id,
                                    timestamp,
                                    split_messages.get("memory_content", response)
                                )
                                logger.info(f"成功记录群聊对话到记忆: {chat_id}")
                        else:
                            # 普通私聊消息记忆
                            self.memory_handler.remember(
                                username,  # 第一个参数是用户ID
                                content,   # 第二个参数是用户消息
                                response   # 第三个参数是AI回复
                            )
                            logger.info(f"成功记录对话到个人记忆: {username}")
                except Exception as e:
                    logger.error(f"记录对话到记忆失败: {str(e)}")

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
            "processed": False,  # 添加处理标记，避免重复处理
        }

        # 将消息添加到全局处理队列
        with self.global_message_queue_lock:
            # 检查是否已存在相同消息，避免重复添加
            is_duplicate = False
            for existing_msg in self.global_message_queue:
                if (existing_msg.get("group_id") == group_id and 
                    existing_msg.get("timestamp") == timestamp and
                    existing_msg.get("username") == username):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                self.global_message_queue.append(message_obj)
                logger.info(f"消息已添加到全局队列: 群: {group_id}, 发送者: {sender_name}")
            else:
                logger.warning(f"检测到重复消息，跳过添加到队列: 群: {group_id}, 发送者: {sender_name}")

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

        # 同时保持原有的群聊缓存机制作为备份，但仅在使用旧处理方式的兼容模式时使用
        # 新版本完全依赖全局队列处理，不再使用群组缓存
        if not hasattr(self, "use_global_queue_only"):
            self.use_global_queue_only = True  # 默认使用全局队列模式
            
        if not self.use_global_queue_only:
            if group_id not in self.group_at_cache:
                self.group_at_cache[group_id] = []
            # 添加到群聊@消息缓存
            self.group_at_cache[group_id].append(message_obj)
            logger.info(f"消息已添加到群组缓存(兼容模式): 群: {group_id}, 发送者: {sender_name}")

        logger.info(f"缓存群聊@消息完成: 群: {group_id}, 发送者: {sender_name}")
        return None

    def _process_global_message_queue(self):
        """处理全局消息队列，按顺序处理所有群聊的消息"""
        try:
            # 获取队列中的所有消息
            with self.global_message_queue_lock:
                if not self.global_message_queue:
                    self.is_processing_queue = False
                    return

                # 获取队列中第一条未处理的消息
                current_message = None
                for idx, msg in enumerate(self.global_message_queue):
                    if not msg.get("processed", False):
                        current_message = msg
                        # 标记为已处理
                        self.global_message_queue[idx]["processed"] = True
                        break
                
                # 如果所有消息都已处理，清空队列并返回
                if not current_message:
                    self.global_message_queue.clear()
                    self.is_processing_queue = False
                    return
                
                # 如果剩余的都是已处理的消息，清空队列
                if all(msg.get("processed", False) for msg in self.global_message_queue):
                    self.global_message_queue.clear()

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
                # 移除已处理的消息
                self.global_message_queue = [
                    msg for msg in self.global_message_queue 
                    if not (msg.get("group_id") == current_message["group_id"] and 
                           msg.get("timestamp") == current_message["timestamp"] and
                           msg.get("username") == current_message["username"])
                ]
                
                # 如果还有未处理的消息，检查并继续处理
                has_unprocessed = any(not msg.get("processed", False) for msg in self.global_message_queue)
                
                if has_unprocessed:
                    # 如果还有消息，设置定时器处理下一条
                    # 使用较短的延迟，但仍然保持一定间隔，避免消息发送过快
                    self.queue_process_timer = threading.Timer(
                        1.0, self._process_global_message_queue
                    )
                    self.queue_process_timer.daemon = True
                    self.queue_process_timer.start()
                else:
                    # 如果没有更多消息，重置处理状态并清空队列
                    self.is_processing_queue = False
                    self.global_message_queue.clear()

        except Exception as e:
            logger.error(f"处理全局消息队列失败: {str(e)}")
            # 重置处理状态，防止队列处理卡死
            with self.global_message_queue_lock:
                self.is_processing_queue = False

    def _process_cached_group_at_messages(self, group_id: str):
        """处理缓存的群聊@消息 - 现在为兼容保留，实际处理由全局队列处理器完成"""
        try:
            # 如果使用全局队列模式，则不再使用此方法处理消息
            if hasattr(self, "use_global_queue_only") and self.use_global_queue_only:
                logger.info(f"使用全局队列模式，跳过单独处理群 {group_id} 的缓存消息")
                return None
                
            # 检查全局队列处理是否正在进行
            with self.global_message_queue_lock:
                if self.is_processing_queue:
                    logger.info(
                        f"全局队列处理已在进行中，跳过单独处理群 {group_id} 的消息"
                    )
                    return None

                # 如果全局队列未在处理，但该群组有缓存消息，则添加到全局队列
                if group_id in self.group_at_cache and self.group_at_cache[group_id]:
                    # 检查每条消息，避免重复添加
                    added_count = 0
                    for msg in self.group_at_cache[group_id]:
                        # 检查是否已经在全局队列中
                        is_duplicate = False
                        for existing_msg in self.global_message_queue:
                            if (existing_msg.get("group_id") == msg.get("group_id") and 
                                existing_msg.get("timestamp") == msg.get("timestamp") and
                                existing_msg.get("username") == msg.get("username")):
                                is_duplicate = True
                                break
                        
                        # 只添加不在全局队列中的消息
                        if not is_duplicate:
                            # 添加处理标记
                            msg["processed"] = False
                            self.global_message_queue.append(msg)
                            added_count += 1

                    # 清空该群组的缓存
                    self.group_at_cache[group_id] = []

                    if added_count > 0:
                        logger.info(f"已将群 {group_id} 的 {added_count} 条缓存消息添加到全局队列")
                        
                        # 启动全局队列处理
                        if not self.is_processing_queue:
                            self.is_processing_queue = True
                            self.queue_process_timer = threading.Timer(
                                0.5, self._process_global_message_queue
                            )
                            self.queue_process_timer.daemon = True
                            self.queue_process_timer.start()
                    else:
                        logger.info(f"群 {group_id} 的所有缓存消息都已在全局队列中，无需添加")
                    
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
            current_time = datetime.now()

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

                # 检查引用内容是否包含[图片]标记，如果有，尝试查找并识别图片
                if quoted_content and ("[图片]" in quoted_content or "[图片内容]" in quoted_content):
                    # 尝试从图片缓存中查找相关图片
                    image_info = self._find_recent_image_in_group(group_id)
                    if image_info and hasattr(self, "image_recognition_service") and self.image_recognition_service:
                        logger.info(f"找到引用的图片: {image_info['image_path']}")
                        
                        # 识别图片内容
                        image_recognition_result = self.image_recognition_service._recognize_image_impl(
                            image_info['image_path'], False
                        )
                        
                        # 将图片识别结果添加到消息内容中
                        if image_recognition_result:
                            content = f"(图片内容: {image_recognition_result})\n{content}"
                            logger.info(f"已添加图片识别结果到消息中")

                # 如果引用内容为空，尝试从群聊记忆中获取
                if quoted_content and hasattr(self, "group_chat_memory"):
                    # 获取引用消息的上下文
                    quoted_context = self.group_chat_memory.get_message_by_content(
                        group_id, quoted_content
                    )
                    if quoted_context:
                        logger.info(f"找到引用消息的上下文: {quoted_context}")
                        # 将引用内容添加到当前消息的上下文中，但确保回复的是当前发送消息的人
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
                        - datetime.strptime(msg["timestamp"], "%Y-%m-%d %H:%M")
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
                    context = "[上下文]\n" + "\n".join(context_parts) + "\n[/上下文]\n\n"

            # 构建API请求内容，明确标识当前@发送者
            current_time_str = current_time.strftime("%Y-%m-%d %H:%M")
            api_content = f"[时间]{current_time_str}[/时间]\n[群组]{group_id}[/群组]\n[发送者]{sender_name}[/发送者]\n{context}[消息内容]{content}[/消息内容]"

            # 在日志中明确记录谁@了机器人
            logger.info(
                f"@消息请求AI响应 - 发送者: {sender_name}, 用户ID: {username}, 内容: {content[:30]}..."
            )

            # 获取AI回复，确保传递正确的用户标识
            reply = self.get_api_response(api_content, username)

            if reply:
                # 清理回复内容
                reply = self._clean_ai_response(reply)

                # 生成消息唯一标识符，用于跟踪表情包发送状态
                message_id = f"{group_id}_{int(time.time())}_{hash(reply[:20])}"
                
                # 进行AI回复内容的情感分析并发送表情包 - 完全异步模式
                should_process_emoji = True
                with self.emoji_lock:
                    if message_id in self.emoji_sent_tracker:
                        # 已经为该消息发送过表情包，不再处理
                        should_process_emoji = False
                        logger.info(f"@消息已经发送过表情包，跳过表情处理: {message_id}")
                    else:
                        # 标记该消息已处理表情包
                        self.emoji_sent_tracker[message_id] = True
                        # 清理旧跟踪记录
                        current_time = time.time()
                        for old_id in list(self.emoji_sent_tracker.keys()):
                            if current_time - int(old_id.split('_')[1]) > 60:  # 60秒后清除
                                self.emoji_sent_tracker.pop(old_id, None)
                
                if should_process_emoji and hasattr(self, 'emoji_handler') and self.emoji_handler.enabled:
                    try:
                        # 同步获取表情路径
                        emoji_path = self.emoji_handler.get_emotion_emoji(
                            reply, 
                            group_id # 使用 group_id 作为 user_id
                        )
                        
                        # 如果获取到路径，先发送表情
                        if emoji_path and os.path.exists(emoji_path):
                            logger.info(f"发送@群聊消息AI回复情感表情包: {emoji_path}")
                            if hasattr(self, 'wx') and self.wx:
                                try:
                                    self.wx.SendFiles(filepath=emoji_path, who=group_id)
                                    logger.info(f"成功通过wxauto发送@群聊消息表情包文件: {emoji_path}")
                                    time.sleep(0.5) # 短暂等待
                                    self.emoji_sent_this_cycle = True # 标记已发送
                                except Exception as e:
                                    logger.error(f"通过wxauto发送@群聊消息表情包失败: {str(e)}")
                                else:
                                    logger.error("wx实例不可用，无法发送表情包")
                    except Exception as e:
                        logger.error(f"处理AI回复表情包失败: {str(e)}", exc_info=True)
                    
                    # 在表情发送后处理文本
                    # 在回复中显式提及发送者，确保回复的是正确的人（当前发消息的人）
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

                    # 发送消息，将艾特消息的发送者名称传递给_send_split_messages函数
                    if not self.is_debug:
                        self._send_split_messages(split_messages, group_id, sender_name)

                    # 返回发送的部分或原始回复
                    if isinstance(split_messages, dict):
                        return split_messages.get("parts", reply)
                    return reply

            # 如果没有回复，返回 None
            return None

        except Exception as e:
            logger.error(f"处理@消息失败: {str(e)}")
            return None

    def _clean_message_content(self, content: str) -> str:
        """清理消息内容，去除时间戳和前缀"""
        # 匹配并去除时间戳和前缀
        patterns = [
            r'^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)?\s+ta私聊对你说\s*',
            r'^\[\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\]\s+ta私聊对你说\s*',
            r'^\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\)\s+ta(私聊|在群聊里)对你说\s*',
            r'^.*?ta私聊对你说\s*',
            r'^.*?ta在群聊里对你说\s*',  # 添加群聊消息模式
            r'^\[?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(:\d{2})?\]?\s+', # 匹配纯时间戳格式
            r'^\(?\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(:\d{2})?\)?\s+'  # 匹配带小括号的时间戳格式
        ]

        actual_content = content

        # 保存@信息
        at_match = re.search(r'(@[^\s]+)', actual_content)
        at_content = at_match.group(1) if at_match else ''

        # 清理时间戳和前缀
        for pattern in patterns:
            if re.search(pattern, actual_content):
                actual_content = re.sub(pattern, '', actual_content)
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
            self.message_timer[username] = None

        # 添加到消息缓存
        if username not in self.message_cache:
            self.message_cache[username] = []
            
        # 检查最近是否已经处理过相同内容的消息，避免重复处理
        cleaned_content = self._clean_message_content(content)
        for msg in self.message_cache[username]:
            msg_content = self._clean_message_content(msg["content"])
            # 如果内容一致且时间非常接近（3秒内）
            if (msg_content == cleaned_content and 
                current_time - msg["timestamp"] < 3.0):
                logger.warning(f"检测到3秒内重复消息，跳过缓存: {cleaned_content[:30]}...")
                # 仍然设置一个短时间的定时器，确保处理最终会被触发
                timer = threading.Timer(
                    1.0, self._process_cached_messages, args=[username]
                )
                timer.daemon = True
                timer.start()
                self.message_timer[username] = timer
                return None

        # 添加新消息到缓存
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
        logger.info(f"缓存消息: {cleaned_content} | 等待时间: {wait_time:.1f}秒")

        return None

    def _calculate_wait_time(self, username: str, msg_count: int) -> float:
        """计算消息等待时间"""
        base_wait_time = 3.0
        typing_speed = self._estimate_typing_speed(username)

        if msg_count == 1:
            wait_time = base_wait_time + 5.0
        else:
            estimated_typing_time = min(4.0, typing_speed * 10)  # 假设用户输入10个字符
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
                logger.info(f"用户 {username} 的消息缓存为空，无需处理。")
                return None

            # 增加日志：打印将要处理的缓存内容
            cached_msgs = self.message_cache[username]
            logger.info(f"开始处理用户 {username} 的缓存消息，共 {len(cached_msgs)} 条:")
            for i, msg_data in enumerate(cached_msgs):
                logger.info(f"  缓存消息 {i+1}: {self._clean_message_content(msg_data.get('content', ''))[:50]}... (时间戳: {msg_data.get('timestamp')})")

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
            logger.info(f"合并后的消息内容: {merged_content[:100]}...") # 记录合并后的内容

            if context:
                merged_content = f"{context}\n\n(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容，并且回复不要重复！！！)\n\n{merged_content}"

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
                
            # 增加日志：确认缓存已清空
            logger.info(f"处理完成，已清空用户 {username} 的消息缓存。")

            return result

        except Exception as e:
            logger.error(f"处理缓存消息失败: {str(e)}", exc_info=True)
            return None

    def _get_conversation_context(self, username: str) -> str:
        """获取对话上下文"""
        try:
            # 构建更精确的查询，包含用户ID和当前时间信息，以获取更相关的记忆
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
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
            r"\(以上是历史对话内容，仅供参考，无需进行互动。请专注处理接下来的新内容，并且回复不要重复！！！\)",
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
        """处理动作描写和表情符号，确保格式一致"""
        if not text:
            return ""
            
        # 1. 先移除文本中的引号，避免引号包裹非动作文本
        text = text.replace('"', '').replace('"', '').replace('"', '')
        
        # 2. 处理分隔符 - 确保分隔符在括号外面
        parts = text.split('$')
        
        # 3. 保护已经存在的括号内容
        protected_parts = {}
        processed_parts = []
        
        for part_index, part in enumerate(parts):
            part = part.strip()
            if not part:  # 跳过空部分
                continue
                
            # 匹配所有类型的括号及其内容
            bracket_pattern = r'[\(\[（【][^\(\[（【\)\]）】]*[\)\]）】]'
            brackets = list(re.finditer(bracket_pattern, part))
            
            # 保护已有的括号内容
            current_protected_parts = {}
            for i, match in enumerate(brackets):
                placeholder = f"__PROTECTED_{part_index}_{i}__"
                current_protected_parts[placeholder] = match.group()
                part = part.replace(match.group(), placeholder)
            
            # 3.1 保护颜文字 - 使用更宽松的匹配规则
            # 定义常用颜文字字符集
            emoticon_chars_set = set(
                '（()）~～‿⁀∀︿⌒▽△□◇○●ˇ＾∇＿゜◕ω・ノ丿╯╰つ⊂＼／┌┐┘└°△▲▽▼◇◆○●◎■□▢▣▤▥▦▧▨▩♡♥ღ☆★✡⁂✧✦❈❇✴✺✹✸✷✶✵✳✳✲✱✰✯✮✭✬✫✪✩✨✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁✀✿✾✽✼✻✺✹✸✷✶✵✴✳✲✱✰✯✮✭✬✫✪✩✧✦✥✤✣✢✡✠✟✞✝✜✛✚✙✘✗✖✕✔✓✒✑✐✏✎✍✌✋✊✉✈✇✆✅✄✃✂✁❤♪♫♬♩♭♮♯°○◎●◯◐◑◒◓◔◕◖◗¤☼☀☁☂☃☄★☆☎☏⊙◎☺☻☯☭♠♣♧♡♥❤❥❣♂♀☿❀❁❃❈❉❊❋❖☠☢☣☤☥☦☧☨☩☪☫☬☭☮☯☸☹☺☻☼☽☾☿♀♁♂♃♄♆♇♈♉♊♋♌♍♎♏♐♑♒♓♔♕♖♗♘♙♚♛♜♝♞♟♠♡♢♣♤♥♦♧♨♩♪♫♬♭♮♯♰♱♲♳♴♵♶♷♸♹♺♻♼♽♾♿⚀⚁⚂⚃⚄⚆⚇⚈⚉⚊⚋⚌⚍⚎⚏⚐⚑⚒⚓⚔⚕⚖⚗⚘⚙⚚⚛⚜⚝⚞⚟*^_^')
            
            emoji_patterns = [
                # 括号类型的颜文字
                r'\([\w\W]{1,10}?\)',  # 匹配较短的括号内容
                r'（[\w\W]{1,10}?）',  # 中文括号
                
                # 符号组合类型
                r'[＼\\\/\*\-\+\<\>\^\$\%\!\?\@\#\&\|\{\}\=\;\:\,\.]{2,}',  # 常见符号组合
                
                # 常见表情符号
                r'[◕◑◓◒◐•‿\^▽\◡\⌒\◠\︶\ω\´\`\﹏\＾\∀\°\◆\□\▽\﹃\△\≧\≦\⊙\→\←\↑\↓\○\◇\♡\❤\♥\♪\✿\★\☆]{1,}',
                
                # *号组合
                r'\*[\w\W]{1,5}?\*'  # 星号强调内容
            ]
            
            for pattern in emoji_patterns:
                emojis = list(re.finditer(pattern, part))
                for i, match in enumerate(emojis):
                    # 避免处理过长的内容，可能是动作描写而非颜文字
                    if len(match.group()) <= 15 and not any(p in match.group() for p in current_protected_parts.values()):
                        # 检查是否包含足够的表情符号字符
                        chars_count = sum(1 for c in match.group() if c in emoticon_chars_set)
                        if chars_count >= 2 or len(match.group()) <= 5:
                            placeholder = f"__EMOJI_{part_index}_{i}__"
                            current_protected_parts[placeholder] = match.group()
                            part = part.replace(match.group(), placeholder)
                            
            # 将处理后的部分和它的保护内容存储起来
            processed_parts.append({
                "content": part,
                "protected_parts": current_protected_parts
            })
            
            # 更新全局保护部分
            protected_parts.update(current_protected_parts)
        
        # 4. 特殊处理：如果只有一个部分且没有$分隔符，尝试处理 \ 分隔符
        if len(processed_parts) == 1:
            part = processed_parts[0]["content"]
            slash_parts = part.split('\\')
            if len(slash_parts) > 1:  # 确认有实际分隔
                # 重新处理使用\分隔的部分
                processed_parts = []
                for slash_idx, slash_part in enumerate(slash_parts):
                    slash_part = slash_part.strip()
                    if not slash_part:
                        continue
                    
                    # 为每个部分创建新的保护项
                    slash_protected_parts = {}
                    processed_parts.append({
                        "content": slash_part,
                        "protected_parts": slash_protected_parts
                    })
        
        # 5. 重新组合文本，使用$作为分隔符
        result_parts = []
        for part_info in processed_parts:
            part = part_info["content"]
            
            # 恢复该部分的保护内容
            for placeholder, content in part_info["protected_parts"].items():
                part = part.replace(placeholder, content)
                
            result_parts.append(part)
            
        # 6. 以$连接各部分，确保分隔符在括号外面
        result = "$".join(result_parts)
            
        return result

    def _clean_memory_content(self, assistant_message: str) -> str:
        """
        清理存入记忆的助手回复内容
        
        Args:
            assistant_message: 助手回复内容
            
        Returns:
            str: 清理后的内容
        """
        if not assistant_message:
            return ""
        
        # 使用_filter_special_markers去除所有特殊标记和占位符
        cleaned = self._filter_special_markers(assistant_message)
        
        # 移除$和￥分隔符
        cleaned = cleaned.replace("$", " ").replace("￥", " ")
        
        # 移除[memory_number:...]标记
        cleaned = re.sub(r'\s*\[memory_number:.*?\]$', '', cleaned)
        
        # 移除潜在的指令、模板和系统提示
        cleaned = re.sub(r'\[\/?(?:system|assistant|user|AI|human)\]', '', cleaned)
        
        # 移除多余的空白字符
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned

    def _clean_ai_response(self, response: str) -> str:
        """
        清理AI回复，移除系统提示词和框架
        
        Args:
            response: 原始AI回复
            
        Returns:
            str: 清理后的回复
        """
        if not response:
            return ""
        
        # 使用_filter_special_markers过滤特殊标记
        cleaned = self._filter_special_markers(response)
            
        # 移除常见的提示词框架标记
        pattern_list = [
            r'<\/?(?:response|answer|reply|message|output)>',
            r'\[(?:assistant|AI)[^\]]*\](?:.*?)(?:\[\/(?:assistant|AI)\])?',
            r'\{\{(?:assistant|AI)[^\}]*\}\}(?:.*?)(?:\{\{\/(?:assistant|AI)\}\})?',
        ]  # 添加右方括号关闭列表
        
        protected_marks = {}
        # 初始化占位符索引
        placeholder_index = 0
        
        # 保护括号对
        bracket_types = [
            (r'\(', r'\)'),   # 小括号
            (r'\[', r'\]'),   # 中括号
            (r'\{', r'\}'),   # 大括号
            (r'（', r'）'),   # 中文小括号
            (r'【', r'】'),   # 中文中括号
            (r'「', r'」'),   # 中文书名号
            (r'『', r'』'),   # 中文书名号
            (r'《', r'》'),   # 中文角括号
        ]
        
        # 保护完整的括号对
        for left, right in bracket_types:
            # 查找所有成对的括号
            pattern = f"{left}(.*?){right}"
            matches = re.finditer(pattern, cleaned, re.DOTALL)
            for match in matches:
                # 简单保护括号内容，不添加分隔符
                full_match = match.group(0)
                # 使用Unicode特殊字符作为占位符前缀后缀，避免与正常文本混淆
                placeholder = f"❄️括号保护{placeholder_index}❄️"
                placeholder_index += 1
                protected_marks[placeholder] = full_match
                cleaned = cleaned.replace(full_match, placeholder)
        
        # 如果文本以括号开头，特殊处理
        for left, _ in bracket_types:
            if re.match(f"^\\s*{left}", cleaned):
                pattern = f"^\\s*{left}.*?(?=$|\\$|￥)"
                match = re.search(pattern, cleaned, re.DOTALL)
                if match:
                    placeholder = f"❄️起始括号{placeholder_index}❄️"
                    placeholder_index += 1
                    protected_marks[placeholder] = match.group(0)
                    cleaned = cleaned.replace(match.group(0), placeholder)
        
        # 如果文本以括号结尾，特殊处理
        for _, right in bracket_types:
            if re.search(f"{right}\\s*$", cleaned):
                pattern = f"(?<=^|\\$|￥).*?{right}\\s*$"
                match = re.search(pattern, cleaned, re.DOTALL)
                if match:
                    placeholder = f"❄️结束括号{placeholder_index}❄️"
                    placeholder_index += 1
                    protected_marks[placeholder] = match.group(0)
                    cleaned = cleaned.replace(match.group(0), placeholder)
        
        # 2. 标记并保护特定符号
        for char in "!！?？.,，。;；:：":
            # 处理$分隔符前的特殊标点
            pattern = re.escape(char) + r'+\s*\$'
            matches = re.finditer(pattern, cleaned)
            for match in matches:
                placeholder = f"❄️标点保护{placeholder_index}❄️"
                placeholder_index += 1
                protected_marks[placeholder] = char + '$'
                cleaned = cleaned.replace(match.group(0), placeholder)
                
            # 处理￥分隔符前的特殊标点
            pattern = re.escape(char) + r'+\s*￥'
            matches = re.finditer(pattern, cleaned)
            for match in matches:
                placeholder = f"❄️标点保护{placeholder_index}❄️"
                placeholder_index += 1
                protected_marks[placeholder] = char + '￥'
                cleaned = cleaned.replace(match.group(0), placeholder)
        
        # 3. 清理需要过滤的标点符号（普通标点）
        filter_punctuation = "、_-+=*&#@~"
        
        # 清理分隔符$前的标点
        result = re.sub(r'[' + re.escape(filter_punctuation) + r']+\s*\$', '$', cleaned)
        
        # 清理分隔符$后的标点
        result = re.sub(r'\$\s*[' + re.escape(filter_punctuation) + r']+', '$', result)
        
        # 清理分隔符￥前的标点
        result = re.sub(r'[' + re.escape(filter_punctuation) + r']+\s*￥', '￥', result)
        
        # 清理分隔符￥后的标点
        result = re.sub(r'￥\s*[' + re.escape(filter_punctuation) + r']+', '￥', result)
        
        # 4. 恢复所有保护的标记
        for placeholder, content in protected_marks.items():
            result = result.replace(placeholder, content)
        
        # 5. 处理分隔符周围可能存在的空格问题
        result = re.sub(r'\s*\$\s*', '$', result)
        result = re.sub(r'\s*￥\s*', '￥', result)

        return result
    
    def _clean_part_punctuation(self, part: str) -> str:
        """
        清理分段后的文本部分的标点符号，主要处理分段开头和结尾
        同时清理@用户名及其后面的空格（包括微信特殊的U+2005空格）
        保留括号等成对标点符号
        
        Args:
            part: 文本部分
            
        Returns:
            str: 清理后的文本
        """
        if not part:
            return ""
            
        # 定义需要过滤的标点符号（不包括括号和引号等成对符号）
        punct_chars = "、~_-+=*&#@"
        
        
        # 首先清理所有@用户名（包括其后的空格和周围的标点符号）
        # 1. 查找所有@开头的用户名及其后的特殊空格
        cleaned_part = re.sub(r'@\S+[\u2005\u0020\u3000]?', '', part)
        
        # 2. 处理可能残留的@符号
        cleaned_part = re.sub(r'@\S+', '', cleaned_part)
        
        # 3. 清理可能残留的特殊空格
        cleaned_part = re.sub(r'[\u2005\u3000]+', ' ', cleaned_part)
        
        # 清理部分开头和结尾的标点符号（只清理特定标点，保留括号等）
        cleaned_part = cleaned_part.strip()
        
        # 使用正则表达式一次性清理开头的指定标点
        cleaned_part = re.sub(f'^[{re.escape(punct_chars)}]+', '', cleaned_part).strip()
    
        # 使用正则表达式一次性清理结尾的指定标点
        cleaned_part = re.sub(f'[{re.escape(punct_chars)}]+$', '', cleaned_part).strip()
        
        # 删除可能因清理造成的多余空格
        cleaned_part = re.sub(r'\s+', ' ', cleaned_part).strip()
        
        return cleaned_part

    def _clean_delimiter_punctuation(self, text: str) -> str:
        """
        清理分隔符周围的标点符号，确保分隔符前后的标点符号合理
        
        Args:
            text: 包含分隔符的文本
            
        Returns:
            str: 清理后的文本
        """
        if not text:
            return ""
            
        # 清理$分隔符前后的标点符号（避免句子结尾和开头都有标点）
        # 1. 清理$前的标点符号（保留句号、问号、感叹号等句子结束符号）
        cleaned_text = re.sub(r'[,，、;；:：]\$', '$', text)
        
        # 2. 清理$后的标点符号（清理所有标点，因为新句子不应以标点开始）
        cleaned_text = re.sub(r'\$[,.，,、;；:：!！?？]', '$', cleaned_text)
        
        # 3. 确保分隔符周围没有多余的空格
        cleaned_text = re.sub(r'\s*\$\s*', '$', cleaned_text)
        
        return cleaned_text

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

        # 过滤掉可能的占位符和特殊标记
        filtered_content = self._filter_special_markers(content)
        
        # 保护成对符号内的内容，防止在内部添加分隔符
        protected_content = filtered_content
        protected_marks = {}
        placeholder_index = 0
        
        # 保护符号对
        bracket_types = [
            (r'\(', r'\)'),   # 小括号
            (r'\[', r'\]'),   # 中括号
            (r'\{', r'\}'),   # 大括号
            (r'（', r'）'),   # 中文小括号
            (r'【', r'】'),   # 中文中括号
            (r'「', r'」'),   # 中文书名号
            (r'『', r'』'),   # 中文书名号
            (r'《', r'》'),   # 中文角括号
            (r'“', r'”'),     # 中文双引号
            (r'‘', r'’'),     # 中文单引号
            (r'"', r'"'),     # 英文双引号
            (r'\'', r'\''),   # 英文单引号
        ]
        
        # 保护完整的括号对
        for left, right in bracket_types:
            # 查找所有成对的括号
            pattern = f"{left}(.*?){right}"
            matches = list(re.finditer(pattern, protected_content, re.DOTALL))
            # 从后向前替换，避免嵌套问题
            for match in reversed(matches):
                full_match = match.group(0)
                placeholder = f"❄️BRACKET{placeholder_index}❄️"
                placeholder_index += 1
                protected_marks[placeholder] = full_match
                protected_content = protected_content[:match.start()] + placeholder + protected_content[match.end():]
        
        # 保护省略号 (中文省略号、连续的点)
        ellipsis_patterns = [
            r'……',                 # 中文省略号
            r'\.{3,}',             # 英文省略号 (至少3个点)
            r'。{2,}'               # 中文句号省略
        ]
        
        for pattern in ellipsis_patterns:
            matches = list(re.finditer(pattern, protected_content))
            # 从后向前替换，避免位置变化
            for match in reversed(matches):
                full_match = match.group(0)
                placeholder = f"❄️ELLIPSIS{placeholder_index}❄️"
                placeholder_index += 1
                protected_marks[placeholder] = full_match
                protected_content = protected_content[:match.start()] + placeholder + protected_content[match.end():]
        
        # 先将连续的换行符替换为特殊标记
        protected_content = re.sub(r'\n{2,}', '###DOUBLE_NEWLINE###', protected_content)
        # 将单个换行符替换为$分隔符
        protected_content = protected_content.replace('\n', '$')
        # 将特殊标记也转为$分隔符，确保每个句子单独一段
        protected_content = protected_content.replace('###DOUBLE_NEWLINE###', '$')
        
        # 首先使用_clean_delimiter_punctuation处理分隔符周围的标点符号
        cleaned_content = self._clean_delimiter_punctuation(protected_content)
        
        # 替换连续的多个$为单个$
        content_with_markers = re.sub(r"\${2,}", "$", cleaned_content)
        
        # 恢复所有保护的标记
        for placeholder, original in protected_marks.items():
            content_with_markers = content_with_markers.replace(placeholder, original)
        
        # 分割消息成不同部分
        dollar_parts = re.split(r"\$", content_with_markers)
        
        # 剔除空部分
        dollar_parts = [part for part in dollar_parts if part.strip()]

        # 如果没有找到$分隔符，或者只有一部分，尝试使用句号等标点符号分割
        if len(dollar_parts) <= 1:
            # 检查是否包含表情符号或特殊字符
            has_emoji = bool(
                re.search(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]', content_with_markers)
            )
            # 如果没有表情符号，使用句号等进行二次分割，但避免分割省略号和成对符号内部
            if not has_emoji:
                # 重新保护特殊内容
                protected_content = content_with_markers
                protected_marks = {}
                placeholder_index = 0
                
                # 再次保护括号对
                for left, right in bracket_types:
                    pattern = f"{left}(.*?){right}"
                    matches = list(re.finditer(pattern, protected_content, re.DOTALL))
                    for match in reversed(matches):
                        full_match = match.group(0)
                        placeholder = f"❄️BRACKET{placeholder_index}❄️"
                        placeholder_index += 1
                        protected_marks[placeholder] = full_match
                        protected_content = protected_content[:match.start()] + placeholder + protected_content[match.end():]
                
                # 保护省略号
                for pattern in ellipsis_patterns:
                    matches = list(re.finditer(pattern, protected_content))
                    for match in reversed(matches):
                        full_match = match.group(0)
                        placeholder = f"❄️ELLIPSIS{placeholder_index}❄️"
                        placeholder_index += 1
                        protected_marks[placeholder] = full_match
                        protected_content = protected_content[:match.start()] + placeholder + protected_content[match.end():]
                
                # 将句号、问号、感叹号等作为分隔点 (但保留这些标点)
                pattern = r'([。！？\.!?])'
                parts = re.split(pattern, protected_content)
                
                # 重新组合分割后的内容，保留标点符号
                merged_parts = []
                for i in range(0, len(parts), 2):
                    if i+1 < len(parts):
                        merged_parts.append(parts[i] + parts[i+1])
                    else:
                        merged_parts.append(parts[i])
                
                # 恢复保护的特殊内容
                for i, part in enumerate(merged_parts):
                    for placeholder, original in protected_marks.items():
                        merged_parts[i] = merged_parts[i].replace(placeholder, original)
                
                # 过滤掉空部分
                merged_parts = [part for part in merged_parts if part.strip()]
                
                if len(merged_parts) > 1:
                    dollar_parts = merged_parts

        # 清理每个部分的标点符号和特殊字符
        cleaned_parts = []
        for part in dollar_parts:
            cleaned_part = self._clean_part_punctuation(part)
            # 再次过滤特殊标记
            cleaned_part = self._filter_special_markers(cleaned_part)
            if cleaned_part.strip():
                cleaned_parts.append(cleaned_part)

        # 将全部内容组合为保存到记忆的格式
        memory_content = " ".join(cleaned_parts)
        
        # 过滤记忆内容中的特殊标记和字符
        memory_content = self._filter_special_markers(memory_content)
        
        # 统计分段数量和总长度
        sentence_count = len(cleaned_parts)
        total_length = sum(len(part) for part in cleaned_parts)

        return {
            "parts": cleaned_parts,
            "memory_content": memory_content,
            "total_length": total_length,
            "sentence_count": sentence_count,
        }
        
    def _filter_special_markers(self, text: str) -> str:
        """
        过滤掉特殊标记和占位符
        
        Args:
            text: 待过滤的文本
            
        Returns:
            str: 过滤后的文本
        """
        if not text:
            return ""
            
        # 过滤Unicode特殊符号和占位符
        filtered = re.sub(r'❄️[^❄️]*❄️', '', text)
        
        # 过滤英文下划线占位符 (防止历史占位符仍在文本中)
        filtered = re.sub(r'__[A-Z_]+\d+__', '', filtered)
        
        # 过滤可能存在的内部指令或特殊标记
        filtered = re.sub(r'\[\/?(?:记忆|任务|指令|MEMORY|TASK|INSTRUCTION)\]', '', filtered)
        
        # 过滤可能存在的Markdown格式占位符
        filtered = re.sub(r'<!--.*?-->', '', filtered)
        filtered = re.sub(r'<\/?placeholder[^>]*>', '', filtered)
        
        # 过滤可能存在的控制字符
        filtered = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', filtered)
        
        # 过滤多余的空格
        filtered = re.sub(r'\s+', ' ', filtered).strip()
        
        return filtered

    def _split_message_for_sending(self, text):
        """将消息分割成适合发送的多个部分"""
        if not text:
            return {"parts": [], "total_length": 0, "sentence_count": 0}

        # 使用处理函数获取分段和记忆内容
        processed = self._process_for_sending_and_memory(text)

        # 添加简要日志
        logger.info(f"消息分割: 共 {len(processed['parts'])} 个部分")
        
        # 返回处理结果
        return processed

    def _send_split_messages(self, messages, chat_id, at_sender_name=None):
        """发送分割后的消息"""
        if not messages or not isinstance(messages, dict) or not messages.get("parts"):
            return False

        # 添加发送锁，确保一个消息的所有部分发送完毕后才能发送下一个消息
        if not hasattr(self, "send_message_lock"):
            self.send_message_lock = threading.Lock()
            
        # 添加消息内容哈希缓存，防止相同消息短时间内重复发送
        if not hasattr(self, "recent_sent_messages"):
            self.recent_sent_messages = {}

        # 计算当前消息的内容哈希
        message_hash = hash(str(messages["parts"]))
        current_time = time.time()
        
        # 检查是否在短时间内已经发送过相同内容的消息
        # 如果5秒内发送过相同内容到相同接收者，则忽略这次发送
        if chat_id in self.recent_sent_messages:
            for sent_hash, sent_time in list(self.recent_sent_messages[chat_id].items()):
                # 清理过期记录（超过30秒）
                if current_time - sent_time > 30:
                    self.recent_sent_messages[chat_id].pop(sent_hash, None)
                # 检查是否是短时间内的重复消息
                elif sent_hash == message_hash and current_time - sent_time < 5:
                    logger.warning(f"检测到短时间内重复发送相同消息，已跳过。间隔: {current_time - sent_time:.2f}秒")
                    return True

        # 使用锁确保消息发送的原子性
        with self.send_message_lock:
            # 修复：确保 start_send_time 在此处定义
            start_send_time = time.time()
            
            # 记录已发送的消息，防止重复发送
            sent_messages = set()

            # 计算自然的发送间隔
            base_interval = 0.5  # 基础间隔时间（秒）

            # 检查消息内容是否已经包含@标记，避免重复@
            first_part = messages["parts"][0] if messages["parts"] else ""
            already_has_at = bool(re.search(r"^@[^\s]+", first_part))

            # 检查是否是群聊消息
            is_group_chat = False
            sender_name = at_sender_name  # 优先使用传入的艾特发送者名称

            # 只有当消息不包含@标记，且没有提供艾特发送者名称时才尝试从最近消息获取
            if not already_has_at and not sender_name and hasattr(self, "group_chat_memory"):
                is_group_chat = chat_id in self.group_chat_memory.group_chats
                if is_group_chat:
                    # 从最近的群聊消息中获取发送者名称
                    recent_messages = self.group_chat_memory.get_memory_from_file(
                        chat_id, limit=1
                    )
                    if recent_messages:
                        sender_name = recent_messages[0].get("sender_name")
                        logger.info(f"从最近消息获取发送者名称: {sender_name}")
            elif sender_name:
                # 如果提供了艾特发送者名称，设置为群聊消息
                is_group_chat = chat_id in (self.group_chat_memory.group_chats if hasattr(self, "group_chat_memory") else [])
                logger.info(f"使用传入的艾特发送者名称: {sender_name}")

            # 修复：移除所有parts中的$符号，并确保不会重复发送相同内容
            # 预处理所有消息部分，从而避免重复发送
            processed_parts = []
            
            for part in messages["parts"]:
                if part.strip():
                    # 处理消息中的$分隔符并去除空格
                    processed_part = part.replace("$", "").strip()
                    
                    # 额外过滤特殊标记、占位符和不适合发送的内容
                    processed_part = self._filter_special_markers(processed_part)
                    
                    # 如果清理后不为空，添加到待发送列表
                    if processed_part and processed_part not in [p["content"] for p in processed_parts]:
                        processed_parts.append({
                            "original": part,
                            "content": processed_part
                        })

            # 发送每一部分消息
            for i, part_info in enumerate(processed_parts):
                processed_part = part_info["content"]
                original_part = part_info["original"]
                
                # 如果已经发送过，跳过
                if original_part in sent_messages:
                    continue
                    
                # 模拟自然发送行为
                time.sleep(base_interval)

                # 添加：再次检查是否有新消息中断发送（在sleep之后）
                if chat_id in self.last_received_message_timestamp and \
                   self.last_received_message_timestamp[chat_id] > start_send_time:
                    logger.info(f"检测到来自 {chat_id} 的新消息，在延迟后中断当前消息发送。")
                    return False # 指示发送被中断

                # 处理群聊@提及
                if i == 0 and is_group_chat and sender_name and not already_has_at:
                    send_content = f"@{sender_name}\u2005{processed_part}"
                else:
                    send_content = processed_part

                # 发送消息
                logger.info(f"发送消息片段 {i+1}/{len(processed_parts)}")
                self.wx.SendMsg(send_content, chat_id)
                sent_messages.add(original_part)

                # 根据消息长度动态调整下一条消息的等待时间
                wait_time = base_interval + random.uniform(0.3, 0.7) * (
                    len(processed_part) / 50
                )
                time.sleep(wait_time)
            
            # 记录此次发送的消息哈希和时间
            if chat_id not in self.recent_sent_messages:
                self.recent_sent_messages[chat_id] = {}
            self.recent_sent_messages[chat_id][message_hash] = current_time
            
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

            # 进行AI回复内容的情感分析并发送表情包 - 完全异步模式
            if hasattr(self, 'emoji_handler') and self.emoji_handler.enabled:
                try:
                    # 异步处理表情包发送，不等待结果
                    def emoji_callback(emoji_path):
                        try:
                            if emoji_path and os.path.exists(emoji_path):
                                logger.info(f"发送私聊AI回复情感表情包: {emoji_path}")
                                if hasattr(self, 'wx') and self.wx:
                                    try:
                                        self.wx.SendFiles(filepath=emoji_path, who=user_id)
                                        logger.info(f"成功通过wxauto发送私聊表情包文件: {emoji_path}")
                                        time.sleep(0.5) # 短暂等待
                                        self.emoji_sent_this_cycle = True # 标记已发送
                                    except Exception as e:
                                        logger.error(f"通过wxauto发送私聊表情包失败: {str(e)}")
                                else:
                                    logger.error("wx实例不可用，无法发送表情包")
                        except Exception as e:
                            logger.error(f"表情回调处理失败: {str(e)}", exc_info=True)
                    
                    # 异步处理表情分析，不等待结果
                    logger.info(f"异步处理私聊表情分析: 用户={user_id}")
                    self.emoji_handler.get_emotion_emoji(
                        cleaned_response, 
                        user_id,
                        callback=emoji_callback
                    )
                except Exception as e:
                    logger.error(f"处理AI回复表情包失败: {str(e)}", exc_info=True)
                    
            # 不等待表情处理，直接处理文本消息
                    
            # 处理回复，添加分隔符并清理标点
            processed = self._split_message_for_sending(cleaned_response)

            # 如果设置了memory_id，更新记忆
            if hasattr(self, "memory_handler") and memory_id:
                try:
                    # 使用memory_content作为存储内容
                    memory_content = processed.get("memory_content", cleaned_response)
                    # 更新记忆
                    self.memory_handler.update_memory(memory_id, memory_content)
                    logger.info(f"记忆已更新: {memory_id}")
                except Exception as memory_e:
                    logger.error(f"更新记忆失败: {str(memory_e)}")

            # 返回分割后的消息对象
            return processed

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

            # 添加：重置表情发送标记
            self.emoji_sent_this_cycle = False

            # 检查消息类型
            if isinstance(message, dict) and "Type" in message:
                msg_type = message["Type"]
                content = message.get("Content", "")
                # 尝试更可靠地获取发送者昵称和判断群聊
                sender_name = message.get("ActualNickName", message.get("Who", who))
                username = who.split('@')[0] if '@' in who else who # 基础用户ID提取
                is_group = "@chatroom" in who # 基础群聊检测
                is_self_message = message.get("IsSelf", False)

                if msg_type == 1:  # 文本消息
                    return self.process_text_message(
                        content, who, source, is_self_message, sender_name, username, is_group
                    )
                elif msg_type == 3:  # 图片消息
                    # 图片消息的内容字段通常是图片路径
                    image_path = content
                    return self.process_image_message(
                        image_path, who, is_self_message, sender_name, username, is_group
                    )
                elif msg_type == 47: # 动画表情消息 (Sticker)
                    logger.info(f"处理动画表情消息 (Type 47): 来自 {sender_name} ({username}) in {who}")
                    if is_self_message:
                        logger.info("自己发送的动画表情，跳过处理。")
                        return None

                    # 尝试从消息体获取图片路径 (wxauto可能将路径放在不同字段)
                    image_path = message.get("ImagePath", message.get("FileName"))

                    if not image_path or not os.path.exists(image_path):
                        # 如果直接获取路径失败，检查Content字段是否为有效路径
                        if os.path.exists(content):
                            image_path = content
                        else:
                            logger.warning(f"无法找到动画表情 (Type 47) 的图像路径。 消息体: {message}")
                            # Fallback: 发送一个通用描述给处理流程
                            recognized_content = "[收到一个动画表情，无法找到图片文件]"
                            return self.handle_user_message(
                                content=recognized_content,
                                chat_id=who,
                                sender_name=sender_name,
                                username=username,
                                is_group=is_group,
                                is_image_recognition=False, # 标记未经过识别
                                is_self_message=is_self_message,
                                is_at=False
                            )

                    # 检查图像识别服务是否可用且启用
                    recognition_result = None
                    if hasattr(self, "image_recognition_service") and self.image_recognition_service:
                        # 检查图像识别服务是否启用
                        if hasattr(self.image_recognition_service, 'enabled') and self.image_recognition_service.enabled:
                            logger.info(f"图像识别服务已启用，尝试识别表情图像: {image_path}")
                            try:
                                # 调用识别实现
                                recognition_result = self.image_recognition_service._recognize_image_impl(image_path, is_group)
                                if recognition_result:
                                    logger.info(f"表情识别成功: {recognition_result}")
                                    # 将识别结果作为消息内容处理
                                    final_content = f"[用户发送了一个表情，内容是: {recognition_result}]"
                                    return self.handle_user_message(
                                        content=final_content,
                                        chat_id=who,
                                        sender_name=sender_name,
                                        username=username,
                                        is_group=is_group,
                                        is_image_recognition=True,
                                        is_self_message=is_self_message,
                                        is_at=False
                                    )
                                else:
                                    logger.warning("表情识别未返回有效结果。")
                            except Exception as rec_err:
                                logger.error(f"调用图像识别时出错: {rec_err}", exc_info=True)
                        else:
                            logger.info("图像识别服务存在但未启用 (相关配置未填写?)，跳过表情识别。")
                    else:
                        logger.warning("图像识别服务 (image_recognition_service) 不可用，跳过表情识别。")

                    # 如果识别失败或服务不可用，返回默认描述
                    default_content = "[收到一个动画表情]"
                    return self.handle_user_message(
                        content=default_content,
                        chat_id=who,
                        sender_name=sender_name,
                        username=username,
                        is_group=is_group,
                        is_image_recognition=False,
                        is_self_message=is_self_message,
                        is_at=False
                    )
                else:
                    logger.warning(f"收到未处理的消息类型: {msg_type}，内容: {content[:50]}...")
                    # 可以选择忽略或返回通用提示
                    return None # 暂时忽略其他未处理类型
            else:
                # 如果消息不是字典格式或没有Type，尝试作为纯文本处理
                # 但需要识别发送者和群聊信息，这比较困难，暂时只处理已知格式
                logger.warning(f"收到未知格式的消息，尝试作为文本处理: {str(message)[:100]}")
                # 提取基础信息，可能不准确
                sender_name = who
                username = who.split('@')[0] if '@' in who else who
                is_group = "@chatroom" in who
                return self.process_text_message(str(message), who, source, False, sender_name, username, is_group)

        except Exception as e:
            logger.error(f"处理消息时发生严重错误: {str(e)}", exc_info=True)
            return "抱歉，处理您的消息时出现了错误，请稍后再试。"
        finally:
            # 确保处理完成后重置回复状态
            self.set_replying_status(False)

    def process_image_message(
        self, image_path: str, who: str, is_self_message: bool = False,
        sender_name: str = None, username: str = None, is_group: bool = False # 添加新参数
    ):
        """处理图片消息，识别图片内容"""
        try:
            # 如果是自己发送的图片，直接跳过处理
            if is_self_message:
                logger.info(f"检测到自己发送的图片，跳过识别: {image_path}")
                return None

            # 获取当前时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

            # 设置所有处理器为"正在回复"状态
            self.set_replying_status(True)

            try:
                # # 判断是否是群聊 (通过检查who是否在group_chat_memory中的群聊列表)
                # is_group_chat = False # 使用传入的 is_group 参数
                # if hasattr(self, "group_chat_memory"):
                #     is_group_chat = who in self.group_chat_memory.group_chats
                
                # 私聊：直接处理图片
                if not is_group:
                    if (
                        hasattr(self, "image_recognition_service")
                        and self.image_recognition_service
                        and hasattr(self.image_recognition_service, 'enabled') # 检查启用状态
                        and self.image_recognition_service.enabled
                    ):
                        logger.info(f"开始识别私聊图片: {image_path}")
                        # 调用实现方法，传入 is_group=False
                        result = self.image_recognition_service._recognize_image_impl(
                            image_path, False
                        )
                        if result:
                            logger.info(f"私聊图片识别结果: {result}")
                            # 将识别结果作为消息内容处理
                            final_content = f"[收到一张图片，内容是: {result}]"
                            # 需要 sender_name 和 username，如果它们是None，需要回退
                            sender_name = sender_name or username or who.split('@')[0]
                            username = username or who.split('@')[0]
                            
                            return self.handle_user_message(
                                content=final_content,
                                chat_id=who,
                                sender_name=sender_name,
                                username=username,
                                is_group=False,
                                is_image_recognition=True,
                                is_self_message=is_self_message,
                                is_at=False
                            )
                        else:
                            logger.warning("私聊图片识别未返回结果。")
                            return None # 或者返回一个提示
                    else:
                        logger.info("图像识别服务未启用或不可用，跳过私聊图片识别")
                        return None # 或者返回一个提示
                # 群聊：保存图片信息，等待被@引用时处理
                else:
                    # 保存图片路径到群图片缓存
                    self._save_group_image_info(who, image_path, current_time)
                    logger.info(f"群聊图片已保存，等待被@引用: {image_path}")
                    return None  # 群聊不立即回复
            finally:
                # 重置回复状态
                self.set_replying_status(False)

        except Exception as e:
            logger.error(f"处理图片消息失败: {str(e)}", exc_info=True)
            return "抱歉，处理图片时出现错误"
            
    def _save_group_image_info(self, group_id: str, image_path: str, timestamp: str):
        """保存群聊图片信息到缓存"""
        # 确保图片缓存字典存在
        if not hasattr(self, "group_image_cache"):
            self.group_image_cache = {}
        
        # 确保群ID的列表存在
        if group_id not in self.group_image_cache:
            self.group_image_cache[group_id] = []
        
        # 添加图片信息到缓存 (保留最近的10张图片)
        self.group_image_cache[group_id].append({
            "image_path": image_path,
            "timestamp": timestamp
        })
        
        # 只保留最近的10张图片
        if len(self.group_image_cache[group_id]) > 10:
            self.group_image_cache[group_id].pop(0)

    def _handle_emoji_message(
        self, content: str, chat_id: str, user_id: str, is_self_emoji: bool = False
    ):
        """处理表情包请求"""
        try:
            if not hasattr(self, "emoji_handler") or not self.emoji_handler:
                return "抱歉，表情包功能暂不可用"
                
            if not self.emoji_handler.enabled:
                logger.warning("表情包功能已禁用，跳过处理")
                return "表情包功能已禁用"

            logger.info(f"检测到表情包请求")
            
            # 定义回调函数处理表情包发送
            def send_emoji_callback(emoji_path):
                if emoji_path and os.path.exists(emoji_path):
                    logger.info(f"准备发送表情包: {emoji_path}")
                    if hasattr(self, 'wx') and self.wx:
                        try:
                            self.wx.SendFiles(filepath=emoji_path, who=chat_id)
                            logger.info(f"成功发送表情包文件: {emoji_path}")
                            time.sleep(0.5) # 短暂等待
                            self.emoji_sent_this_cycle = True # 标记已发送
                        except Exception as e:
                            logger.error(f"发送表情包文件失败: {str(e)}")
                    else:
                        logger.error("wx实例不可用，无法发送表情包")
            
            # 调用表情包处理函数并传递回调
            result = self.emoji_handler.get_emotion_emoji(
                content, user_id, callback=send_emoji_callback, is_self_emoji=is_self_emoji
            )
            
            # 修改：处理返回结果，成功发送后返回 None
            if result and isinstance(result, str) and os.path.exists(result):
                # 如果获取到表情包路径
                logger.info(f"表情包请求获取到路径: {result}")
                # # 如果提供了回调函数，交给回调处理 (保留，以防万一)
                # if callback:
                #     threading.Timer(0.5, lambda: callback(result)).start()
                #     return None # 返回 None 表示已处理
                # 如果有wxauto实例，直接发送
                if hasattr(self, 'wx') and self.wx:
                    try:
                        self.wx.SendFiles(filepath=result, who=chat_id)
                        logger.info(f"已发送表情包: {result}")
                        return None # 返回 None 表示已处理
                    except Exception as e:
                        logger.error(f"发送表情包失败: {str(e)}")
                        return "发送表情包失败" # 返回错误信息
                else:
                    # 既没有回调也没有wx实例，返回路径供调用者处理
                    logger.warning("wx实例不可用，无法直接发送表情包请求的表情")
                    return result # 返回路径
            elif isinstance(result, str):
                 # 如果返回的是字符串但不是有效路径，则认为是错误或状态信息
                 logger.info(f"表情包请求处理结果: {result}")
                 return result # 返回如 "未找到合适的表情包" 等信息
            else:
                 # 如果返回 None 或其他非字符串，则表示未找到或出错
                 return "未找到合适的表情包"
            
            # 移除旧逻辑
            # # 处理返回结果
            # if result and isinstance(result, str):
            #     logger.info(f"表情包请求处理结果: {result}")
            #     
            #     # 如果是文件路径，直接发送
            #     if os.path.exists(result) and not self.is_debug:
            #         logger.info(f"直接发送表情包: {result}")
            #         if hasattr(self, 'wx') and self.wx:
            #             self.wx.SendFiles(filepath=result, who=chat_id)
            #             return "表情包已发送"
            #     
            #     # 如果不是文件路径，返回提示信息
            #     return "正在为您准备表情包，请稍等..."
            # 
            # return "正在为您准备表情包，请稍等..."
            
        except Exception as e:
            logger.error(f"处理表情包请求出错: {str(e)}", exc_info=True)
            return "处理表情包请求时出错，请稍后再试"

    def process_text_message(
        self,
        content: str,
        who: str,
        source: str = "wechat",
        is_self_message: bool = False,
        sender_name: str = None, # 添加新参数
        username: str = None,    # 添加新参数
        is_group: bool = False   # 添加新参数
    ):
        """处理文本消息"""
        try:
            # 如果内容为空，直接返回
            if not content or not content.strip():
                return None

            # 移除：不再直接处理表情包请求
            # # 检查是否是表情包请求
            # if (
            #     hasattr(self, "emoji_handler")
            #     and self.emoji_handler
            #     and self.emoji_handler.is_emoji_request(content)
            # ):
            #     logger.info(f"检测到表情包请求: {content}")
            #     return self._handle_emoji_message(content, who, who, is_self_message)

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
                # 生成消息唯一标识符，用于跟踪表情包发送状态
                message_id = f"{who}_{int(time.time())}_{hash(response[:20])}"
                
                # 进行AI回复内容的情感分析并发送表情包 - 完全异步模式
                should_process_emoji = True
                with self.emoji_lock:
                    if message_id in self.emoji_sent_tracker:
                        # 已经为该消息发送过表情包，不再处理
                        should_process_emoji = False
                        logger.info(f"文本消息已经发送过表情包，跳过表情处理: {message_id}")
                    else:
                        # 标记该消息已处理表情包
                        self.emoji_sent_tracker[message_id] = True
                        # 清理旧跟踪记录
                        current_time = time.time()
                        for old_id in list(self.emoji_sent_tracker.keys()):
                            if current_time - int(old_id.split('_')[1]) > 60:  # 60秒后清除
                                self.emoji_sent_tracker.pop(old_id, None)
                
                if should_process_emoji and hasattr(self, 'emoji_handler') and self.emoji_handler.enabled:
                    try:
                        # 修改：同步获取表情路径
                        emoji_path = self.emoji_handler.get_emotion_emoji(
                            response, 
                            who
                        )
                        
                        # 如果获取到路径，先发送表情
                        if emoji_path and os.path.exists(emoji_path):
                            logger.info(f"发送文本处理AI回复情感表情包: {emoji_path}")
                            if hasattr(self, 'wx') and self.wx:
                                try:
                                    self.wx.SendFiles(filepath=emoji_path, who=who)
                                    logger.info(f"成功通过wxauto发送文本处理表情包文件: {emoji_path}")
                                    time.sleep(0.5) # 短暂等待
                                    self.emoji_sent_this_cycle = True # 标记已发送
                                except Exception as e:
                                    logger.error(f"通过wxauto发送文本处理表情包失败: {str(e)}")
                            else:
                                logger.error("wx实例不可用，无法发送表情包")
                        # 移除回调逻辑
                        # def emoji_callback(emoji_path):
                        #     try:
                        #         if emoji_path and os.path.exists(emoji_path):
                        #             logger.info(f"发送文本处理AI回复情感表情包: {emoji_path}")
                        #             if hasattr(self, 'wx') and self.wx:
                        #                 try:
                        #                     self.wx.SendFiles(filepath=emoji_path, who=who)
                        #                     logger.info(f"成功通过wxauto发送文本处理表情包文件: {emoji_path}")
                        #                 except Exception as e:
                        #                     logger.error(f"通过wxauto发送文本处理表情包失败: {str(e)}")
                        #             else:
                        #                 logger.error("wx实例不可用，无法发送表情包")
                        #         else:
                        #             logger.error("wx实例不可用，无法发送表情包")
                        #     except Exception as e:
                        #         logger.error(f"表情回调处理失败: {str(e)}", exc_info=True)
                        
                        # 异步处理表情，不等待结果
                        # logger.info(f"异步处理文本消息表情分析: 用户={who}")
                        # self.emoji_handler.get_emotion_emoji(
                        #     response, 
                        #     who,
                        #     callback=emoji_callback
                        # )
                    except Exception as e:
                        logger.error(f"处理AI回复表情包失败: {str(e)}", exc_info=True)
                
                # 在表情发送后处理文本
                split_messages = self._split_message_for_sending(response)
                
                # 检查是否是群聊 (使用传入的 is_group 参数)
                # is_group_chat = False
                # sender_name = None # 使用传入的 sender_name 参数
                
                # if hasattr(self, "group_chat_memory"):
                #     is_group_chat = who in self.group_chat_memory.group_chats
                #     if is_group_chat:
                #         # 从群聊记忆中获取最近一条消息的发送者名称
                #         recent_messages = self.group_chat_memory.get_memory_from_file(
                #             who, limit=1
                #         )
                #         if recent_messages:
                #             sender_name = recent_messages[0].get("sender_name")
                #             logger.info(f"群聊消息获取发送者: {sender_name}")
                
                # 如果是群聊消息，传递发送者名称
                if is_group and sender_name:
                    self._send_split_messages(split_messages, who, sender_name)
                else:
                    self._send_split_messages(split_messages, who)
                
                # 修复：将对话存入记忆
                try:
                    if hasattr(self, "memory_handler") and self.memory_handler:
                        # 如果是群聊消息
                        if is_group:
                            # 将消息存入群聊记忆
                            if hasattr(self, "group_chat_memory") and self.group_chat_memory:
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                                # 将消息存入群聊记忆
                                self.group_chat_memory.add_message(
                                    who,  # 群聊ID
                                    sender_name or "未知用户",  # 发送者 (使用传入的sender_name)
                                    content,  # 用户原始消息
                                    is_at=False # 文本消息通常不是@
                                )
                                
                                # 更新助手回复
                                self.group_chat_memory.update_assistant_response(
                                    who,
                                    timestamp,
                                    split_messages.get("memory_content", response)
                                )
                                logger.info(f"成功记录群聊对话到记忆: {who}")
                        else:
                            # 普通私聊消息记忆
                            # 私聊时 username 通常等于 who
                            memory_user_id = username or who
                            self.memory_handler.remember(
                                content, response, memory_user_id
                            )
                            logger.info(f"成功记录对话到个人记忆: {memory_user_id}")
                except Exception as e:
                    logger.error(f"记录对话到记忆失败: {str(e)}")

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
                try:
                    # 获取队列锁并处理队列内容
                    with self.auto_task_queue_lock:
                        # 检查队列是否为空
                        if not self.auto_task_message_queue:
                            time.sleep(1)  # 队列为空时休眠减少CPU使用
                            continue
                            
                        # 复制当前队列并清空原队列，避免处理时的并发问题
                        current_queue = self.auto_task_message_queue.copy()
                        self.auto_task_message_queue.clear()
                        
                    # 释放锁后处理消息
                    if current_queue:
                        logger.info(f"开始处理自动任务消息队列，当前队列长度: {len(current_queue)}")
                        
                        # 处理复制的队列中的每条消息
                        for message_dict in current_queue:
                            try:
                                # 验证消息格式
                                if "chat_id" not in message_dict or "content" not in message_dict:
                                    logger.warning(f"无效的自动任务消息格式: {message_dict}")
                                    continue
                                    
                                # 获取消息信息
                                chat_id = message_dict["chat_id"]
                                content = message_dict["content"]
                                
                                # 记录消息处理，包含更多细节有助于调试
                                logger.info(f"处理自动任务消息: {message_dict}")
                                
                                # 分割并发送消息
                                messages = self._split_message_for_sending(content)
                                self._send_split_messages(messages, chat_id)
                                
                            except Exception as e:
                                # 单独处理每条消息的异常，不影响其他消息
                                logger.error(f"处理自动任务消息时出错: {str(e)}", exc_info=True)
                                
                except Exception as e:
                    # 处理主循环的异常
                    logger.error(f"自动任务消息处理线程出错: {str(e)}", exc_info=True)
                    time.sleep(5)  # 出错时等待一段时间再继续
                    
                # 即使队列处理完成也要短暂休眠，避免CPU占用过高
                time.sleep(0.1)

        # 使用守护线程而不是Timer，确保程序退出时线程自动结束
        auto_task_thread = threading.Thread(target=_process_auto_task_message, daemon=True)
        auto_task_thread.start()
        logger.info("自动任务消息处理线程已启动")
        
    def add_to_auto_task_queue(self, chat_id: str, content: str):
        """
        线程安全地添加消息到自动任务队列
        
        Args:
            chat_id: 接收消息的聊天ID
            content: 要发送的消息内容
        """
        # 创建消息字典
        message_dict = {
            "chat_id": chat_id,
            "content": content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        
        # 线程安全地添加到队列
        with self.auto_task_queue_lock:
            self.auto_task_message_queue.append(message_dict)
            
        logger.debug(f"已添加消息到自动任务队列: chat_id={chat_id}, content_length={len(content)}")

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
        self, timestamp, current_time=None, time_format="%Y-%m-%d %H:%M"
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

            # 最大时间差为3天(72小时)
            max_hours = 72.0
            time_diff_hours = min(time_diff_hours, max_hours)
            
            # 分段式衰减函数
            # 1. 24小时内: 缓慢衰减
            # 2. 24-72小时: 快速衰减
            # 3. 72小时后: 稳定在略高于最小阈值
            
            min_weight = 0.15  # 最小权重阈值
            
            if time_diff_hours <= 24.0:
                # 24小时内缓慢衰减：从1.0到0.7
                weight = 1.0 - (0.3 * time_diff_hours / 24.0)
            elif time_diff_hours <= max_hours:
                # 24-72小时快速衰减：从0.7到min_weight
                remaining_decay = 0.7 - min_weight
                normalized_time = (time_diff_hours - 24.0) / (max_hours - 24.0)
                weight = 0.7 - (remaining_decay * normalized_time)
            else:
                # 72小时后稳定在最小值
                weight = min_weight

            # 确保权重在[min_weight, 1]范围内
            weight = max(min_weight, min(1.0, weight))

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
            list: 经过时间排序和筛选后的上下文消息
        """
        if not context_messages:
            logger.debug("上下文消息列表为空，返回空列表")
            return []

        # 如果未指定max_turns，使用配置的值
        if max_turns is None:
            max_turns = self.group_context_turns

        logger.debug(f"将获取最近的 {max_turns} 条消息作为上下文")

        try:
            # 无差别获取群聊中最近的消息，不再按用户过滤
            # 确保每条消息都有timestamp字段
            for msg in context_messages:
                if "timestamp" not in msg or not msg["timestamp"]:
                    # 如果消息没有时间戳，设置一个默认的较早时间戳
                    msg["timestamp"] = "2000-01-01 00:00:00"
                    logger.warning(f"发现没有时间戳的消息: {msg.get('content', '无内容')[:30]}...")
            
            # 按时间戳排序（从早到晚）
            sorted_msgs = sorted(
                context_messages, 
                key=lambda x: x.get("timestamp", "2000-01-01 00:00:00")
            )
            
            # 获取最近的max_turns条消息
            recent_msgs = sorted_msgs[-max_turns:] if max_turns > 0 else sorted_msgs
            
            logger.debug(f"共筛选出 {len(recent_msgs)} 条最近消息作为上下文")
            
            # 记录一些消息的时间戳信息，用于调试
            if recent_msgs and len(recent_msgs) > 0:
                first_ts = recent_msgs[0].get("timestamp", "unknown")
                last_ts = recent_msgs[-1].get("timestamp", "unknown")
                logger.debug(f"上下文消息时间范围: {first_ts} 至 {last_ts}")
            
            return recent_msgs
            
        except Exception as e:
            logger.error(f"筛选上下文消息时出错: {str(e)}")
            # 发生错误时，尝试返回原始消息列表的最后max_turns条
            try:
                return context_messages[-max_turns:] if max_turns > 0 and len(context_messages) > max_turns else context_messages
            except:
                return []

    def increment_unanswered_counter(self, username: str):
        """
        增加指定用户的未回答计数器
        
        Args:
            username: 用户名
        """
        try:
            with self.queue_lock:
                # 初始化计数器（如果不存在）
                if username not in self.unanswered_counters:
                    self.unanswered_counters[username] = 0
                
                # 增加计数器
                self.unanswered_counters[username] += 1
                
                # 记录日志
                logger.info(f"增加用户 {username} 的未回答计数器，当前值: {self.unanswered_counters[username]}")
                
                # 如果未回答次数超过阈值，可以在这里添加额外处理逻辑
                if self.unanswered_counters[username] >= 3:
                    logger.warning(f"用户 {username} 的未回答计数已达到3次，考虑后续处理")
        except Exception as e:
            logger.error(f"增加未回答计数器失败: {str(e)}")

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

            # 获取RAG查询结果，传入当前上下文用户ID进行发送者一致性检查
            current_user_id = user_id if user_id else (
                self.group_user_mapping.get(group_id, {}).get('current_user_id') if hasattr(self, 'group_user_mapping') else None
            )
            results = await self.rag_manager.query(query, top_k * 2, context_user_id=current_user_id)

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
                    # 获取发送者身份标记
                    is_assistant = metadata.get("is_assistant", False)
                    ai_name = metadata.get("ai_name", self.robot_name)
                    
                    # 创建包含清晰发送者信息的结果
                    filtered_result = {
                        "timestamp": metadata.get("timestamp", ""),
                        "sender_name": msg_sender,
                        "human_message": metadata.get("human_message", ""),
                        "assistant_message": metadata.get("assistant_message", ""),
                        "score": result.get("score", 0.0),
                        "sender_id": metadata.get("user_id", ""),  # 使用user_id作为sender_id
                        "is_assistant": is_assistant,
                        "ai_name": ai_name,
                        # 添加格式化消息，确保发送者信息明确
                        "formatted_message": result.get("formatted_message", "")
                    }
                    
                    # 添加发送者一致性信息
                    if "processed_info" in result:
                        filtered_result["senders"] = result["processed_info"].get("senders", [])
                        filtered_result["primary_sender"] = result["processed_info"].get("primary_sender")
                        # 标记是否与当前上下文用户匹配
                        filtered_result["is_primary_sender"] = (
                            filtered_result["primary_sender"] == current_user_id
                            if current_user_id and filtered_result.get("primary_sender")
                            else False
                        )
                    
                    filtered_results.append(filtered_result)
                elif (
                    msg_type == "private_message"
                    and user_id
                    and metadata.get("user_id") == user_id
                ):
                    # 私聊消息处理
                    # 获取发送者身份标记
                    is_assistant = metadata.get("is_assistant", False)
                    ai_name = metadata.get("ai_name", self.robot_name)
                    
                    # 创建包含清晰发送者信息的结果
                    filtered_result = {
                        "timestamp": metadata.get("timestamp", ""),
                        "sender_name": msg_sender,
                        "human_message": metadata.get("human_message", ""),
                        "assistant_message": metadata.get("assistant_message", ""),
                        "score": result.get("score", 0.0),
                        "sender_id": metadata.get("user_id", ""),  # 使用user_id作为sender_id
                        "is_assistant": is_assistant,
                        "ai_name": ai_name,
                        # 添加格式化消息，确保发送者信息明确
                        "formatted_message": result.get("formatted_message", "")
                    }
                    
                    # 添加发送者一致性信息
                    if "processed_info" in result:
                        filtered_result["senders"] = result["processed_info"].get("senders", [])
                        filtered_result["primary_sender"] = result["processed_info"].get("primary_sender")
                        # 标记是否与当前用户匹配
                        filtered_result["is_primary_sender"] = (
                            filtered_result["sender_id"] == user_id
                            if user_id
                            else False
                        )
                    
                    filtered_results.append(filtered_result)

            # 按得分排序，但优先考虑与当前上下文用户匹配的消息
            if current_user_id:
                # 优先返回与当前用户匹配的结果，再按得分排序
                filtered_results.sort(
                    key=lambda x: (
                        # 先按是否为主要发送者排序（优先True）
                        not x.get("is_primary_sender", False),
                        # 再按得分降序排序
                        -x.get("score", 0)
                    )
                )
            else:
                # 仅按得分排序
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

    def _find_recent_image_in_group(self, group_id: str) -> Optional[Dict]:
        """在群组图片缓存中查找最近的图片"""
        if not hasattr(self, "group_image_cache") or group_id not in self.group_image_cache:
            return None
        
        # 获取最近的图片（列表最后一项）
        if self.group_image_cache[group_id]:
            return self.group_image_cache[group_id][-1]
            
        return None

    # 添加在MessageHandler类中的方法
    def _update_current_group_sender(self, group_id: str, sender_name: str, username: str):
        """
        更新群聊的当前发送者信息，用于后续RAG检索时进行发送者一致性检查
        
        Args:
            group_id: 群聊ID
            sender_name: 发送者名称
            username: 发送者微信ID
        """
        try:
            # 确保group_user_mapping属性存在
            if not hasattr(self, 'group_user_mapping'):
                self.group_user_mapping = {}
                
            # 更新当前群聊的发送者信息
            if group_id not in self.group_user_mapping:
                self.group_user_mapping[group_id] = {}
                
            self.group_user_mapping[group_id].update({
                'current_user_id': username,
                'current_sender_name': sender_name,
                'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            
            # 记录群聊最近的几位发言者，用于多人对话场景
            if 'recent_senders' not in self.group_user_mapping[group_id]:
                self.group_user_mapping[group_id]['recent_senders'] = []
                
            # 添加到最近发言者列表，避免重复
            recent_senders = self.group_user_mapping[group_id]['recent_senders']
            existing_sender = None
            for sender in recent_senders:
                if sender.get('user_id') == username:
                    existing_sender = sender
                    break
                    
            if existing_sender:
                # 更新现有发言者的时间戳
                existing_sender['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            else:
                # 添加新发言者
                recent_senders.append({
                    'user_id': username,
                    'sender_name': sender_name,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                
                # 保持最近发言者列表不超过10人
                if len(recent_senders) > 10:
                    # 移除最旧的发言者
                    recent_senders.sort(key=lambda x: x.get('timestamp', ''))
                    self.group_user_mapping[group_id]['recent_senders'] = recent_senders[-10:]
        except Exception as e:
            logger.error(f"更新群聊发送者信息失败: {str(e)}")

    def _remember_conversation(self, user_id: str, user_message: str, assistant_response: str) -> None:
        """将对话存入记忆
        
        Args:
            user_id: 用户ID
            user_message: 用户消息
            assistant_response: 助手回复
        """
        try:
            # 确保ID和消息都不为空
            if not user_id or not user_message or not assistant_response:
                return
                
            # 打印调试信息确认字段分配正确
            logger.debug(f"记忆存储: 用户ID={user_id}, 用户消息={user_message[:30]}..., 助手回复={assistant_response[:30]}...")
                
            # 确保键字段顺序正确
            self.memory_handler.remember(
                user_id=user_id,
                user_message=user_message,  # 用户消息 - 人类消息
                assistant_response=assistant_response  # 助手回复 - AI消息
            )
        except Exception as e:
            logger.error(f"记忆对话失败: {str(e)}")

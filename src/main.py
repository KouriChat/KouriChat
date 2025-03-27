import logging
import random
from datetime import datetime, timedelta
import threading
import time
import os
import shutil
import win32gui
import win32con
from src.config import config
from src.config import config as rag_config  # 修改导入为主配置，但保留原有别名
from wxauto import WeChat
import re
from src.handlers.emoji import EmojiHandler
from src.handlers.message import MessageHandler
from src.handlers.file import FileHandler
from src.services.ai.llm_service import LLMService
from src.services.ai.image_recognition_service import ImageRecognitionService
from src.api_client.wrapper import APIWrapper
from src.handlers.emotion import (
    SentimentResourceLoader,
    SentimentAnalyzer,
)  # 导入情感分析模块
from src.utils.logger import LoggerConfig
from src.utils.console import print_status
from colorama import init, Style, Fore
from src.AutoTasker.autoTasker import AutoTasker
import sys
import asyncio
from difflib import SequenceMatcher


def _run_async(coro):
    """
    运行异步函数并返回结果

    Args:
        coro: 异步协程对象

    Returns:
        协程运行结果
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    else:
        return loop.run_until_complete(coro)


# 创建一个事件对象来控制线程的终止
stop_event = threading.Event()

# 获取项目根目录
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 初始化全局变量
ROBOT_WX_NAME = ""
wx_listening_chats = set()
files_handler = None
emoji_handler = None
image_handler = None
voice_handler = None
memory_handler = None
moonshot_ai = None
message_handler = None
listener_thread = None
chat_bot = None
countdown_timer = None
is_countdown_running = False
countdown_end_time = None
wait = 1  # 消息队列接受消息时间间隔

# 检查并初始化配置文件
# config_path = os.path.join(root_dir, 'src', 'config', 'config.json')
# config_template_path = os.path.join(root_dir, 'src', 'config', 'config.json.template')
# # 初始化ROBOT_WX_NAME 变量
# ROBOT_WX_NAME = ""
# 初始化微信监听聊天记录集合
# wx_listening_chats = set()
# if not os.path.exists(config_path) and os.path.exists(config_template_path):

# 配置日志
# 清除所有现有日志处理器
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logger_config = LoggerConfig(root_dir)
logger = logger_config.setup_logger("main")
listen_list = config.user.listen_list
queue_lock = threading.Lock()  # 队列访问锁
user_queues = {}  # 用户消息队列管理
chat_contexts = {}  # 存储上下文
# 初始化colorama
init()


# ... 现有ChatBot类代码...


class DebugBot:
    """调试模式下的聊天机器人模拟器"""

    def __init__(self, message_handler, moonshot_ai, memory_handler):
        self.message_handler = message_handler
        self.moonshot_ai = moonshot_ai
        self.memory_handler = memory_handler
        self.user_queues = {}
        self.queue_lock = threading.Lock()
        self.ai_last_reply_time = {}
        self.robot_name = "DebugBot"
        # 添加日志处理器相关属性
        self._log_buffer = []
        self._original_handlers = None
        self._is_input_mode = False
        # 日志颜色
        self.ai_color = Fore.CYAN
        self.system_color = Fore.YELLOW
        self.error_color = Fore.RED
        logger.info("调试机器人已初始化")

    def _pause_logging(self):
        """暂停日志输出并等待日志队列清空"""
        # 保存当前的处理器
        logger = logging.getLogger("main")
        self._original_handlers = logger.handlers[:]

        # 移除所有控制台处理器
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                logger.removeHandler(handler)

        # 等待确保日志队列处理完毕
        time.sleep(0.5)
        sys.stdout.flush()
        self._is_input_mode = True

        # 添加一个明显的分隔
        print("\n" + "=" * 50)
        print(f"{Fore.GREEN}[等待用户输入]{Style.RESET_ALL}")

    def _resume_logging(self):
        """恢复日志输出"""
        if self._original_handlers:
            logger = logging.getLogger("main")
            # 恢复原来的处理器
            for handler in self._original_handlers:
                if handler not in logger.handlers:
                    logger.addHandler(handler)
        self._is_input_mode = False

    def log_colored_message(self, message, color=None):
        """使用logger记录带颜色的消息"""
        if color:
            formatted_msg = f"{color}{message}{Style.RESET_ALL}"
            logger.info(formatted_msg)
        else:
            logger.info(message)

    def process_user_messages(self, chat_id):
        """模拟消息处理"""
        try:
            with self.queue_lock:
                if chat_id not in self.user_queues:
                    return
                user_data = self.user_queues.pop(chat_id)
                messages = user_data["messages"]

            self.log_colored_message(
                f"[处理消息队列] - 内容: {' | '.join(messages)}", self.system_color
            )

            # 暂停日志确保用户可以输入
            self._pause_logging()
            response = input("[请输入AI回复] >>> ")
            print("-" * 50)  # 添加分隔线
            self._resume_logging()

            if response:
                # 使用彩色日志显示AI回复
                self.log_colored_message(f"[AI回复] {response}", self.ai_color)
                logger.info(
                    f"调试模式对话记录 - 用户输入: {messages}\nAI回复: {response}"
                )

        except Exception as e:
            logger.error(f"调试消息处理失败: {str(e)}")

    def handle_wxauto_message(self, msg, chatName, is_group=False):
        """控制台交互处理"""
        # 暂停日志确保用户可以输入
        self._pause_logging()

        try:
            user_input = input("[请输入测试消息] >>> ")
            print("-" * 50)  # 添加分隔线使输入更清晰
        finally:
            # 确保恢复日志输出
            self._resume_logging()

        # 记录用户输入
        self.log_colored_message(f"[用户输入] {user_input}", Fore.WHITE)

        # 对于调试模式，直接调用_handle_text_message方法处理消息
        reply = self.message_handler._handle_text_message(
            content=user_input,
            chat_id=chatName,
            sender_name="debug_user",
            username="debug_user",
            is_group=False,
        )

        # 只在这一个地方显示AI回复
        if reply:
            self.log_colored_message(f"\n[AI回复开始] {'-'*30}", self.system_color)
            for msg in reply:
                if isinstance(msg, str) and msg.startswith(("http", "/")):
                    self.log_colored_message(f"[AI发送图片] {msg}", self.ai_color)
                else:
                    self.log_colored_message(f"[AI回复] {msg}", self.ai_color)
            self.log_colored_message(f"[AI回复结束] {'-'*30}\n", self.system_color)
        else:
            self.log_colored_message("[没有收到AI回复]", self.error_color)

        # 处理完成提示
        self.log_colored_message(f"[处理完成] {'-'*30}", self.system_color)

        return reply


class ChatBot:
    def __init__(self, message_handler, moonshot_ai, memory_handler):
        self.message_handler = message_handler
        self.moonshot_ai = moonshot_ai
        self.memory_handler = memory_handler
        self.user_queues = {}  # 将user_queues移到类的实例变量
        self.queue_lock = threading.Lock()  # 将queue_lock也移到类的实例变量
        self.ai_last_reply_time = {}  # 新增：记录AI 最后回复的时间
        self.group_message_queues = {}  # 新增：群聊消息队列
        self.group_queue_lock = threading.Lock()  # 新增：群聊队列锁

        # 获取机器人的微信名称
        self.wx = WeChat()
        self.robot_name = self.wx.A_MyIcon.Name

        # 将wx实例传递给message_handler
        self.message_handler.wx = self.wx

    def process_user_messages(self, chat_id):
        """处理用户消息队列"""
        try:
            logger.info(f"开始处理消息队列- 聊天ID: {chat_id}")

            # 确定是否是群聊消息
            is_group_chat = False
            messages = []
            sender_name = ""
            username = ""
            is_group = False
            is_at = False  # 添加is_at标志

            # 先尝试获取群聊消息
            with self.group_queue_lock:
                if chat_id in self.group_message_queues:
                    is_group_chat = True
                    group_data = self.group_message_queues.pop(chat_id)
                    messages = group_data["messages"]
                    sender_name = group_data["sender_name"]
                    username = group_data["username"]
                    is_group = True
                    is_at = group_data.get("is_at", False)  # 从群聊数据中获取is_at标志

            # 如果不是群聊消息，则获取私聊消息
            if not is_group_chat:
                with self.queue_lock:
                    if chat_id not in self.user_queues:
                        logger.warning(f"未找到消息队列 {chat_id}")
                        return
                    user_data = self.user_queues.pop(chat_id)
                    messages = user_data["messages"]
                    sender_name = user_data["sender_name"]
                    username = user_data["username"]
                    is_group = user_data.get("is_group", False)
                    is_at = user_data.get("is_at", False)  # 从用户数据中获取is_at标志

            logger.info(
                f"队列信息 - 发送者: {sender_name}, 消息数: {len(messages)}, 是否群聊: {is_group}"
            )

            # 增强的消息去重处理
            if len(messages) > 1:
                # 1. 移除完全相同的消息（不限于连续）
                seen_messages = set()
                unique_messages = []
                for msg in messages:
                    if msg not in seen_messages:
                        seen_messages.add(msg)
                        unique_messages.append(msg)

                # 2. 检查语义相似度（使用简单的字符串相似度）
                def similarity(a, b):
                    return SequenceMatcher(None, a, b).ratio()

                # 3. 合并相似度高的消息
                final_messages = []
                skip_indices = set()
                for i in range(len(unique_messages)):
                    if i in skip_indices:
                        continue
                    current_msg = unique_messages[i]
                    similar_msgs = []

                    # 检查后续消息是否相似
                    for j in range(i + 1, len(unique_messages)):
                        if j not in skip_indices:
                            sim_ratio = similarity(current_msg, unique_messages[j])
                            if sim_ratio > 0.8:  # 相似度阈值
                                similar_msgs.append(unique_messages[j])
                                skip_indices.add(j)

                    if similar_msgs:
                        # 选择最长的消息作为代表
                        best_msg = max([current_msg] + similar_msgs, key=len)
                        final_messages.append(best_msg)
                    else:
                        final_messages.append(current_msg)

                # 4. 检查时间线一致性
                time_patterns = [
                    r"昨[天晚]",
                    r"今[天晚]",
                    r"刚才",
                    r"(\d+)点",
                    r"早上|上午|中午|下午|晚上",
                ]

                # 按时间顺序排序消息
                def extract_time_info(msg):
                    for pattern in time_patterns:
                        if re.search(pattern, msg):
                            return True
                    return False

                # 分离带时间信息的消息和普通消息
                time_messages = [
                    msg for msg in final_messages if extract_time_info(msg)
                ]
                normal_messages = [
                    msg for msg in final_messages if not extract_time_info(msg)
                ]

                # 重新组合消息，确保时间顺序正确
                messages = time_messages + normal_messages

                # 记录去重结果
                logger.info(
                    f"消息队列优化: 从 {len(messages)} 条减少到 {len(final_messages)} 条"
                )
                logger.debug(f"去重后的消息: {messages}")

            # 合并消息内容
            is_image_recognition = any(
                "发送了图片" in msg or "发送了表情包：" in msg for msg in messages
            )

            # 优化消息合并逻辑
            if len(messages) > 1:
                # 智能合并消息
                content_parts = []
                current_context = {
                    "location": None,  # 地点
                    "time": None,  # 时间
                    "activity": None,  # 活动
                    "status": None,  # 状态
                }

                # 定义场景识别模式
                patterns = {
                    "location": r"在(实验室|家|学校|公司|办公室|图书馆|食堂|宿舍|教室|外面|路上|商场|医院|咖啡厅|餐厅)",
                    "time": r"([早中下晚][上午饭]|凌晨|半夜|\d+点|\d+:\d+)",
                    "activity": r"(工作|学习|睡觉|休息|实验|写代码|看书|吃饭|上课|开会|散步|运动|锻炼|购物|聊天|玩游戏)",
                    "status": r"(累了|困了|饿了|忙|闲|开心|难过|紧张|兴奋|疲惫|生病|精神|有事|没事)",
                }

                def extract_context(text, timestamp=None):
                    """提取文本中的场景信息，考虑时间戳"""
                    context = {}

                    # 首先从时间戳中提取时间信息（如果有）
                    if timestamp:
                        try:
                            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                            hour = dt.hour
                            if 5 <= hour < 12:
                                context["time"] = "早上"
                            elif 12 <= hour < 14:
                                context["time"] = "中午"
                            elif 14 <= hour < 18:
                                context["time"] = "下午"
                            elif 18 <= hour < 24:
                                context["time"] = "晚上"
                            else:
                                context["time"] = "凌晨"
                        except Exception as e:
                            logger.debug(f"解析时间戳失败: {str(e)}")

                    # 检查文本是否包含历史对话标记
                    if "以下是之前的对话记录：" in text or "以上是历史对话内容" in text:
                        return {}  # 如果是历史记录，不提取场景信息

                    # 从当前文本中提取场景信息
                    for key, pattern in patterns.items():
                        match = re.search(pattern, text)
                        if match:
                            # 确保提取的场景信息不是历史记录的一部分
                            # 检查匹配文本前后是否有历史记录标记
                            start_pos = match.start()
                            end_pos = match.end()
                            context_before = text[max(0, start_pos - 50) : start_pos]
                            context_after = text[end_pos : min(len(text), end_pos + 50)]

                            if not any(
                                marker in context_before or marker in context_after
                                for marker in ["对话记录：", "历史对话", "上次聊天"]
                            ):
                                context[key] = match.group()

                    return context

                def context_changed(old_ctx, new_ctx, msg_time=None):
                    """判断场景是否发生显著变化，考虑时间连续性"""
                    if not old_ctx or not new_ctx:
                        return False

                    # 计算显式声明的变化
                    explicit_changes = sum(
                        1 for k in new_ctx if k in old_ctx and old_ctx[k] != new_ctx[k]
                    )

                    # 计算新增的维度
                    additions = sum(1 for k in new_ctx if k not in old_ctx)

                    # 检查时间连续性
                    time_changed = False
                    if msg_time and "time" in new_ctx:
                        try:
                            current_time = datetime.strptime(
                                msg_time, "%Y-%m-%d %H:%M:%S"
                            )
                            if "last_time" in old_ctx:
                                time_diff = current_time - old_ctx["last_time"]
                                # 如果时间间隔超过2小时，认为是场景变化
                                if time_diff.total_seconds() > 7200:  # 2小时 = 7200秒
                                    time_changed = True
                        except Exception as e:
                            logger.debug(f"时间连续性检查失败: {str(e)}")

                    # 如果有显著变化或新增维度，认为场景发生转换
                    return explicit_changes + additions >= 1 or time_changed

                # 处理每条消息
                for msg in messages:
                    # 提取时间戳
                    timestamp_match = re.search(
                        r"\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}", msg
                    )
                    current_timestamp = (
                        timestamp_match.group() if timestamp_match else None
                    )

                    # 提取当前消息的场景信息
                    new_context = extract_context(msg, current_timestamp)

                    # 如果提取到了有效的场景信息
                    if new_context:
                        # 如果检测到场景变化，添加优雅的场景转换提示
                        if context_changed(
                            current_context, new_context, current_timestamp
                        ):
                            # 构建场景转换描述
                            transition_parts = []
                            for key in ["time", "location", "activity", "status"]:
                                if key in new_context and (
                                    key not in current_context
                                    or current_context[key] != new_context[key]
                                ):
                                    transition_parts.append(new_context[key])

                            if transition_parts:
                                transition_text = "，".join(transition_parts)
                                content_parts.append(
                                    f"\n[场景切换：{transition_text}]\n"
                                )

                        # 更新当前场景
                        current_context.update(new_context)
                        if current_timestamp:
                            try:
                                current_context["last_time"] = datetime.strptime(
                                    current_timestamp, "%Y-%m-%d %H:%M:%S"
                                )
                            except Exception as e:
                                logger.debug(f"更新时间戳失败: {str(e)}")

                    # 添加消息
                    content_parts.append(msg)

                content = "\n".join(content_parts)
            else:
                content = messages[0]

            # 记录处理前的消息内容，用于防止重复处理
            chat_key = f"{chat_id}_{username}"
            current_content_hash = hash(content)

            # 检查是否是重复内容
            if (
                hasattr(self, "last_processed_content")
                and chat_key in self.last_processed_content
            ):
                last_hash, last_time = self.last_processed_content.get(
                    chat_key, (None, 0)
                )
                # 如果内容相同且时间间隔小于5秒，可能是重复处理
                if last_hash == current_content_hash and time.time() - last_time < 5:
                    logger.warning(f"检测到可能的重复处理，跳过: {chat_id}")
                    return

            # 更新最后处理的内容记录
            if not hasattr(self, "last_processed_content"):
                self.last_processed_content = {}
            self.last_processed_content[chat_key] = (current_content_hash, time.time())

            # 直接调用 MessageHandler 的handle_user_message 方法，传递is_at参数
            response = self.message_handler.handle_user_message(
                content=content,
                chat_id=chat_id,
                sender_name=sender_name,
                username=username,
                is_group=is_group,
                is_image_recognition=is_image_recognition,
                is_at=is_at,  # 传递is_at标志
            )
            logger.info(f"消息已处理- 聊天ID: {chat_id}")

            # 记录对话内容
            if response and isinstance(response, str):
                logger.info(
                    f"对话记录 - 用户: {username}\n用户: {content}\nAI: {response}"
                )
            else:
                logger.debug(f"无有效响应内容 - 用户ID: {username}")

            # 记录 AI 最后回复的时间
            self.ai_last_reply_time[username] = time.time()

            # 处理完用户消息后，检查是否需要重置计数器
            with self.queue_lock:
                if username in self.message_handler.unanswered_counters:
                    if username in self.ai_last_reply_time:
                        elapsed_time = time.time() - self.ai_last_reply_time[username]
                        if elapsed_time <= 30 * 60:  # 检查是否在 30 分钟内
                            self.message_handler.unanswered_counters[username] = 0
                            logger.info(
                                f"用户 {username} 的未回复计数器: {self.message_handler.unanswered_counters[username]}"
                            )
                        else:
                            logger.info(
                                f"用户 {username} 30 分钟后回复，未回复计数器: {self.message_handler.unanswered_counters[username]}"
                            )

        except Exception as e:
            logger.error(f"处理消息队列失败: {str(e)}", exc_info=True)

    def handle_wxauto_message(self, msg, chatName, is_group=False):
        try:
            username = msg.sender
            content = getattr(msg, "content", None) or getattr(msg, "text", None)

            # 添加详细日志
            logger.info(
                f"收到消息 - 来源: {chatName}, 发送者: {username}, 是否群聊: {is_group}"
            )
            logger.info(f"原始消息内容: {content}")

            # 添加未回复计数器状态日志
            if hasattr(self.message_handler, "unanswered_counters"):
                if chatName in self.message_handler.unanswered_counters:
                    counter_value = self.message_handler.unanswered_counters.get(
                        chatName, 0
                    )
                    logger.info(
                        f"聊天 {chatName} 的当前未回复计数器值: {counter_value}"
                    )
                else:
                    logger.info(f"聊天 {chatName} 不在未回复计数器中")

            # 保存原始内容用于后续比较
            original_content = content

            # 先判断是否是群聊@消息
            is_at_robot = False
            if is_group and self.robot_name and content:
                # 使用更全面的@检测逻辑
                robot_name = self.robot_name

                # 1. 正则表达式匹配常见的@模式
                # 允许各种类型的空格字符和机器人名称周围的一些变化
                robot_name_pattern = re.escape(robot_name).replace(
                    "\\ ", "[ \u2005\u00a0\u200b\u3000]*"
                )
                at_pattern = re.compile(
                    f"@{robot_name_pattern}[\\s\u2005\u00a0\u200b\u3000]?"
                )
                is_at_robot = bool(at_pattern.search(content))

                # 2. 使用原有的模式列表
                if not is_at_robot:
                    at_patterns = [
                        f"@{self.robot_name} ",  # 标准空格
                        f"@{self.robot_name}\u2005",  # 特殊空格
                        f"@{self.robot_name}\u00a0",  # 不间断空格
                        f"@{self.robot_name}\u200b",  # 零宽空格
                        f"@{self.robot_name}\u3000",  # 全角空格
                        f"@{self.robot_name}",  # 无空格
                    ]
                    is_at_robot = any(pattern in content for pattern in at_patterns)

                # 3. 检查近似匹配（处理名称中有可能的错误）
                if not is_at_robot and content.startswith("@"):
                    import difflib

                    # 提取@后面的第一个词
                    at_name_match = re.match(
                        r"@([^ \u2005\u00A0\u200B\u3000]+)", content
                    )
                    if at_name_match:
                        at_name = at_name_match.group(1)
                        # 检查名称相似度
                        similarity_ratio = difflib.SequenceMatcher(
                            None, at_name, robot_name
                        ).ratio()
                        if similarity_ratio > 0.8:  # 80%相似度作为阈值
                            is_at_robot = True
                            logger.info(
                                f"基于名称相似度检测到@机器人: {at_name} vs {robot_name}, 相似度: {similarity_ratio:.2f}"
                            )

                logger.info(f"群聊消息@状态检查: {is_at_robot}")

                # 如果确认是@机器人的消息，移除@部分
                if is_at_robot:
                    logger.info(f"处理群聊@消息 - 机器人名称: {self.robot_name}")

                    # 先尝试使用正则表达式移除@部分
                    new_content = re.sub(
                        f"@{re.escape(robot_name)}[\\s\u2005\u00a0\u200b\u3000]?",
                        "",
                        content,
                        1,
                    ).strip()

                    # 如果正则替换没有改变内容，再使用原来的模式尝试
                    if new_content == content:
                        # 使用原有的移除逻辑
                        for pattern in at_patterns:
                            if pattern in content:
                                content = content.replace(pattern, "").strip()
                                logger.info(f"移除@后的消息内容: {content}")
                                break
                    else:
                        # 使用正则替换结果
                        content = new_content
                        logger.info(f"使用正则表达式移除@后的消息内容: {content}")

                    # 检查是否真的移除了@部分
                    if original_content == content:
                        logger.warning("虽检测到@机器人，但移除操作无效")
                        # 不要将is_at_robot设置为False，仍然尝试处理
                        # 尝试简单移除消息开头的@部分
                        if content.startswith("@"):
                            first_space = content.find(" ")
                            if first_space > 0:
                                content = content[first_space + 1 :].strip()
                                logger.info(f"使用简单方法移除@后的内容: {content}")
                    else:
                        logger.info("成功识别并移除@机器人部分")

            # 如果是群聊消息，检查发送者是否在监听列表中
            if is_group and username not in listen_list:
                if not is_at_robot:
                    logger.debug(
                        f"群聊消息发送者 {username} 不在监听列表中且未@机器人，跳过处理"
                    )
                    return None
                else:
                    logger.info(f"非监听列表用户 {username} @了机器人，继续处理消息")

            # 增加重复消息检查
            message_key = f"{chatName}_{username}_{hash(content)}"
            current_time = time.time()

            # 检查是否是短时间内的重复消息
            if hasattr(self, "_processed_messages"):
                self._processed_messages = {
                    k: v
                    for k, v in self._processed_messages.items()
                    if current_time - v < 60
                }

                if message_key in self._processed_messages:
                    if current_time - self._processed_messages[message_key] < 5:
                        logger.warning(
                            f"检测到短时间内的重复消息，已忽略 {content[:20]}..."
                        )
                        return None
            else:
                self._processed_messages = {}

            # 记录当前消息处理时间
            self._processed_messages[message_key] = current_time

            # 初始化变量
            img_path = None
            files_path = None
            is_emoji = False
            is_image_recognition = False

            # 处理图片、文件和表情消息
            if content and content.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".bmp")
            ):
                logger.info(f"检测到图片消息: {content}")
                img_path = content
                is_emoji = False
                content = None

            if content and content.lower().endswith(
                (".txt", ".docx", ".doc", ".ppt", ".pptx", ".xlsx", ".xls")
            ):
                logger.info(f"检测到文件消息: {content}")
                files_path = content
                is_emoji = False
                content = None

            if content and "[动画表情]" in content:
                logger.info("检测到动画表情")
                # 不再使用截图功能，直接将动画表情标记为特定类型的文本消息
                is_emoji = True
                content = "发送了一个动画表情"

            if img_path:
                logger.info(
                    f"开始处理图片/表情 - 路径: {img_path}, 是否表情: {is_emoji}"
                )
                recognized_text = self.moonshot_ai.recognize_image(img_path, is_emoji)
                logger.info(f"图片/表情识别结果: {recognized_text}")
                content = (
                    recognized_text
                    if content is None
                    else f"{content} {recognized_text}"
                )
                is_image_recognition = True

            if files_path:
                logger.info(f"开始处理文件 - 路径：{files_path}")
                return self.message_handler.handle_user_message(
                    content=files_path,
                    chat_id=chatName,
                    sender_name=username,
                    username=username,
                    is_group=is_group,
                )

            if content:
                # 如果是群聊@消息，再移除@部分
                if emoji_handler.is_emoji_request(content):
                    logger.info("检测到表情包请求")
                    emoji_path = emoji_handler.get_emotion_emoji(content, username)
                    if emoji_path:
                        logger.info(f"准备发送情感表情包: {emoji_path}")
                        self.message_handler.wx.SendFiles(emoji_path, chatName)

                sender_name = username
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                group_info = f"在群聊里" if is_group else "私聊"
                time_aware_content = (
                    f"(此时时间为{current_time}) ta{group_info}对你说{content}"
                )

                # 根据消息类型选择不同的处理方式
                if is_group:
                    # 只有@机器人的消息才进入群聊消息队列
                    if is_at_robot:
                        with self.group_queue_lock:
                            if chatName not in self.group_message_queues:
                                self.group_message_queues[chatName] = {
                                    "messages": [],
                                    "sender_name": sender_name,
                                    "username": username,
                                    "last_message_time": current_time,
                                    "is_at": is_at_robot,
                                }
                            self.group_message_queues[chatName]["messages"].append(
                                time_aware_content
                            )

                            # 设置处理延迟
                            if (
                                len(self.group_message_queues[chatName]["messages"])
                                == 1
                            ):
                                threading.Timer(
                                    1.0, self.process_user_messages, args=[chatName]
                                ).start()
                    else:
                        # 非@消息，直接保存到群聊记忆但不处理
                        if hasattr(self.message_handler, "group_chat_memory"):
                            self.message_handler.group_chat_memory.add_message(
                                chatName, sender_name, content, False
                            )
                            logger.debug(f"非@消息已保存到群聊记忆: {content[:30]}...")
                else:
                    # 私聊消息使用原有的队列机制
                    with self.queue_lock:
                        if chatName not in self.user_queues:
                            self.user_queues[chatName] = {
                                "messages": [],
                                "sender_name": sender_name,
                                "username": username,
                                "last_message_time": current_time,
                                "is_at": False,  # 私聊消息不需要@标志
                            }
                        self.user_queues[chatName]["messages"].append(
                            time_aware_content
                        )

                        # 设置处理延迟
                        if len(self.user_queues[chatName]["messages"]) == 1:
                            threading.Timer(
                                1.0, self.process_user_messages, args=[chatName]
                            ).start()

                # 处理未回复消息计时器
                if username in self.message_handler.unanswered_timers:
                    self.message_handler.unanswered_timers[username].cancel()

                # 30分钟后增加未回复计数
                def increase_counter_after_delay(username):
                    with self.queue_lock:
                        self.message_handler.increment_unanswered_counter(username)

                timer = threading.Timer(
                    1800.0, increase_counter_after_delay, args=[username]
                )
                timer.start()
                self.message_handler.unanswered_timers[username] = timer

        except Exception as e:
            logger.error(f"消息处理失败: {str(e)}", exc_info=True)


# 读取提示文件
avatar_dir = os.path.join(
    root_dir, "data", "avatars", config.behavior.context.avatar_dir
)
prompt_path = os.path.join(avatar_dir, "avatar.md")
with open(prompt_path, "r", encoding="utf-8") as file:
    prompt_content = file.read()
countdown_end_time = None  # 新增倒计时结束时间


def is_quiet_time() -> bool:
    """检查当前是否在安静时间段内"""
    try:
        current_time = datetime.now().time()

        # 从配置中读取安静时间设置
        quiet_start_str = config.behavior.quiet_time.start
        quiet_end_str = config.behavior.quiet_time.end

        # 记录当前读取的安静时间设置
        logger.debug(f"当前安静时间设置: 开始={quiet_start_str}, 结束={quiet_end_str}")

        # 确保时间格式正确
        if not quiet_start_str or not quiet_end_str:
            logger.warning("安静时间设置为空，默认不在安静时间")
            return False

        # 处理特殊格式
        if quiet_start_str == "1320":
            quiet_start_str = "22:00"
        if quiet_end_str == "1320":
            quiet_end_str = "08:00"

        # 如果格式不包含冒号，尝试转换
        if quiet_start_str and ":" not in quiet_start_str:
            try:
                hour = int(quiet_start_str) // 100
                minute = int(quiet_start_str) % 100
                quiet_start_str = f"{hour:02d}:{minute:02d}"
                logger.info(
                    f"转换安静时间开始格式: {config.behavior.quiet_time.start} -> {quiet_start_str}"
                )
            except (ValueError, TypeError):
                logger.warning(f"无法转换安静时间开始格式: {quiet_start_str}")

        if quiet_end_str and ":" not in quiet_end_str:
            try:
                hour = int(quiet_end_str) // 100
                minute = int(quiet_end_str) % 100
                quiet_end_str = f"{hour:02d}:{minute:02d}"
                logger.info(
                    f"转换安静时间结束格式: {config.behavior.quiet_time.end} -> {quiet_end_str}"
                )
            except (ValueError, TypeError):
                logger.warning(f"无法转换安静时间结束格式: {quiet_end_str}")

        # 解析时间
        quiet_start = datetime.strptime(quiet_start_str, "%H:%M").time()
        quiet_end = datetime.strptime(quiet_end_str, "%H:%M").time()

        # 记录解析后的时间
        logger.debug(
            f"解析后的安静时间: 开始={quiet_start}, 结束={quiet_end}, 当前时间={current_time}"
        )

        if quiet_start <= quiet_end:
            # 如果安静时间不跨天
            is_quiet = quiet_start <= current_time <= quiet_end
            logger.debug(f"安静时间不跨天，是否在安静时间内: {is_quiet}")
            return is_quiet
        else:
            # 如果安静时间跨天（比如22:00到次天8:00）
            is_quiet = current_time >= quiet_start or current_time <= quiet_end
            logger.debug(f"安静时间跨天，是否在安静时间内: {is_quiet}")
            return is_quiet
    except Exception as e:
        logger.error(f"检查安静时间出错: {str(e)}")
        return False  # 出错时默认不在安静时间


def get_random_countdown_time():
    """获取随机倒计时时长"""
    try:
        # 检查是否在调试模式
        debug_mode = getattr(config, "debug", False)
        if debug_mode:
            logger.info("调试模式下使用短倒计时: 1-2分钟")
            return random.uniform(60, 120)  # 1-2分钟

        # 检查配置是否存在
        if (
            not hasattr(config, "behavior")
            or not hasattr(config.behavior, "auto_message")
            or not hasattr(config.behavior.auto_message, "min_hours")
            or not hasattr(config.behavior.auto_message, "max_hours")
        ):
            logger.error("配置文件中缺少倒计时设置，使用默认值1-3小时")
            return random.uniform(3600, 10800)  # 默认1-3小时

        # 直接从配置中读取最小和最大小时数
        min_hours = float(config.behavior.auto_message.min_hours)
        max_hours = float(config.behavior.auto_message.max_hours)

        # 如果两个值都是0，设置为默认值
        if min_hours == 0 and max_hours == 0:
            logger.warning("配置的倒计时范围都为0，使用默认值1-3小时")
            min_hours = 1.0
            max_hours = 3.0

        # 确保最小值不大于最大值
        if min_hours > max_hours:
            logger.warning(
                f"配置错误：min_hours({min_hours})大于max_hours({max_hours})，将交换它们"
            )
            min_hours, max_hours = max_hours, min_hours

        # 确保有最小值
        if min_hours < 0.01:  # 至少36秒
            min_hours = 0.01
            logger.warning(f"min_hours太小，已调整为{min_hours}小时")

        # 将小时转换为秒
        min_seconds = int(min_hours * 3600)
        max_seconds = int(max_hours * 3600)

        logger.debug(f"从配置读取的倒计时范围：{min_hours}小时到{max_hours}小时")
        return random.uniform(min_seconds, max_seconds)
    except Exception as e:
        logger.error(f"获取倒计时时间失败 {str(e)}，使用默认值1-3小时")
        # 返回默认值：1-3小时
        return random.uniform(3600, 10800)


def get_personality_summary(prompt_content_param: str = None) -> str:
    """从完整人设中提取关键性格特点"""
    try:
        # 如果未提供prompt_content参数，使用全局的prompt_content
        if prompt_content_param is None:
            # 使用全局变量
            global prompt_content
            prompt_content_to_use = prompt_content
            if prompt_content_to_use is None or not prompt_content_to_use:
                logger.warning("未提供prompt_content且全局变量为空，返回默认性格描述")
                return "友好、耐心、善解人意的助手"
        else:
            prompt_content_to_use = prompt_content_param

        # 查找核心人格部分
        core_start = prompt_content_to_use.find("# 性格")
        if core_start == -1:
            return prompt_content_to_use[:500]  # 如果找不到标记，返回500字符

        # 找到下一个标题或文件结尾
        next_title = prompt_content_to_use.find("#", core_start + 1)
        if next_title == -1:
            core_content = prompt_content_to_use[core_start:]
        else:
            core_content = prompt_content_to_use[core_start:next_title]

        # 提取关键内容
        core_lines = [
            line.strip()
            for line in core_content.split("\n")
            if line.strip() and not line.startswith("#")
        ]

        # 返回处理后的内容
        return "\n".join(core_lines[:5])  # 只取一条关键特征
    except Exception as e:
        logger.error(f"提取性格特点失败: {str(e)}")
        return "请参考上下文"  # 返回默认特征


def is_already_listening(wx_instance, chat_name):
    """
    检查是否已经添加了监听

    Args:
        wx_instance: WeChat 实例
        chat_name: 聊天名称

    Returns:
        bool: 是否已经添加了监听
    """
    try:
        # 尝试使用内置方法（如果存在）
        if hasattr(wx_instance, "IsListening"):
            return wx_instance.IsListening(chat_name)

        # 如果内置方法不存在，我们无法确定是否已经在监听
        # 可以通过其他方式检查，例如检查是否有相关的事件处理器
        # 但由于我们没有足够的信息，暂时返回False
        logger.warning(
            f"wxauto 模块没有 IsListening 方法，无法确定是否已经在监听 {chat_name}"
        )
        return False
    except Exception as e:
        logger.error(f"检查监听状态失败 {str(e)}")
        # 出错时返回False，让程序尝试添加监听
        return False


def auto_send_message():
    """自动发送消息- 调用message_handler中的方法"""
    try:
        logger.info("开始执行auto_send_message函数")
        logger.info(f"当前监听列表: {listen_list}")

        # 调用message_handler中的auto_send_message方法
        # 如果是安静时间，不发送消息，但仍然需要启动新的倒计时
        if is_quiet_time():
            logger.info("当前是安静时间，跳过主动发送，但仍会继续倒计时")
        else:
            # 检查message_handler的状态
            if not message_handler:
                logger.error("message_handler未初始化")
                return

            # 检查未回复计数器状态
            unanswered_summary = {}
            for chat_id in listen_list:
                if chat_id in message_handler.unanswered_counters:
                    unanswered_summary[chat_id] = message_handler.unanswered_counters[
                        chat_id
                    ]
            logger.info(f"未回复计数器状态: {unanswered_summary}")

            # 只有在非安静时间才执行发送消息
            logger.info("开始调用message_handler.auto_send_message方法")
            message_handler.auto_send_message(
                listen_list=listen_list,
                robot_wx_name=ROBOT_WX_NAME,
                get_personality_summary=get_personality_summary,
                is_quiet_time=is_quiet_time,
                start_countdown=start_countdown,
            )
            logger.info("自动消息发送完成，开始新的倒计时")
    except Exception as e:
        logger.error(f"自动发送消息执行失败: {str(e)}", exc_info=True)

    # 不管是否执行成功或是否在安静时间，都要启动新的倒计时
    logger.info("启动新的倒计时")
    start_countdown()


def start_countdown():
    """开始新的倒计时"""
    global countdown_timer, is_countdown_running, countdown_end_time

    if countdown_timer:
        countdown_timer.cancel()
        logger.info("已取消之前的倒计时")

    countdown_seconds = get_random_countdown_time()
    countdown_end_time = datetime.now() + timedelta(
        seconds=countdown_seconds
    )  # 设置结束时间

    # 输出预计的完成时间
    end_time_str = countdown_end_time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"倒计时将在 {end_time_str} 结束")

    # 计算小时和分钟，提供更详细的日志
    hours = int(countdown_seconds // 3600)
    minutes = int((countdown_seconds % 3600) // 60)
    seconds = int(countdown_seconds % 60)

    if hours > 0:
        logger.info(f"开始新的倒计时: {hours}小时{minutes}分钟{seconds}秒")
    else:
        logger.info(f"开始新的倒计时: {minutes}分钟{seconds}秒")

    # 添加配置信息日志
    try:
        if (
            hasattr(config, "behavior")
            and hasattr(config.behavior, "auto_message")
            and hasattr(config.behavior.auto_message, "min_hours")
            and hasattr(config.behavior.auto_message, "max_hours")
        ):
            min_hours = float(config.behavior.auto_message.min_hours)
            max_hours = float(config.behavior.auto_message.max_hours)
            logger.info(f"配置的倒计时范围: {min_hours:.1f}小时 - {max_hours:.1f}小时")
        else:
            logger.info("使用默认倒计时范围: 1.0小时 - 3.0小时")
    except Exception as e:
        logger.warning(f"无法读取配置的倒计时范围: {str(e)}")

    # 创建倒计时线程并确保超时回调确实被调用
    countdown_timer = threading.Timer(countdown_seconds, auto_send_message)
    countdown_timer.daemon = True
    countdown_timer.start()
    logger.info(f"倒计时线程已启动，线程ID: {countdown_timer.ident}")
    is_countdown_running = True


def message_listener():
    global wx_listening_chats  # 使用全局变量跟踪已添加的监听集合

    wx = None
    reconnect_attempts = 0
    max_reconnect_attempts = 3
    reconnect_delay = 30  # 重连等待时间（秒）
    last_reconnect_time = 0

    while not stop_event.is_set():
        try:
            current_time = time.time()

            if wx is None:
                # 检查是否需要重置重连计数
                if current_time - last_reconnect_time > 300:  # 5分钟无错误，重置计数
                    reconnect_attempts = 0

                # 检查重连次数
                if reconnect_attempts >= max_reconnect_attempts:
                    logger.error("等待一段时间后重试...")
                    time.sleep(reconnect_delay)
                    reconnect_attempts = 0
                    last_reconnect_time = current_time
                    continue

                try:
                    wx = WeChat()
                    if not wx.GetSessionList():
                        logger.error("未检测到微信会话列表，请确保微信已登录")
                        wx = None  # 重置 wx 对象
                        reconnect_attempts += 1
                        last_reconnect_time = current_time
                        time.sleep(5)
                        continue

                    # 重新添加监听
                    for chat_name in listen_list:
                        try:
                            if wx.ChatWith(chat_name):
                                # 使用全局变量检查是否已经添加了监听
                                if chat_name not in wx_listening_chats:
                                    wx.AddListenChat(
                                        who=chat_name, savepic=True, savefile=True
                                    )
                                    logger.info(f"重新添加监听: {chat_name}")
                                    wx_listening_chats.add(
                                        chat_name
                                    )  # 记录已添加监听的聊天
                                else:
                                    logger.info(f"已存在监听，跳过: {chat_name}")
                        except Exception as e:
                            logger.error(f"重新添加监听失败 {chat_name}: {str(e)}")

                    # 成功初始化，重置计数
                    reconnect_attempts = 0
                    last_reconnect_time = current_time
                    logger.info("微信监听恢复正常")

                    # 确保message_handler和chat_bot都有最新的wx对象
                    message_handler.wx = wx
                    chat_bot.wx = wx

                except Exception as e:
                    logger.error(f"微信初始化失败 {str(e)}")
                    wx = None
                    reconnect_attempts += 1
                    last_reconnect_time = current_time
                    time.sleep(5)
                    continue

            # 正常的消息处理逻辑
            msgs = wx.GetListenMessage()
            if not msgs:
                time.sleep(wait)
                continue

            # 确保在处理消息前message_handler有最新的wx对象
            message_handler.wx = wx
            chat_bot.wx = wx

            for chat in msgs:
                who = chat.who
                if not who:
                    continue

                # 检查是否是配置中的监听对象
                if who not in listen_list:
                    logger.debug(f"跳过非监听对象的消息: {who}")
                    continue

                one_msgs = msgs.get(chat)
                if not one_msgs:
                    continue

                for msg in one_msgs:
                    try:
                        msgtype = msg.type
                        content = msg.content
                        if not content:
                            continue
                        if msgtype != "friend":
                            logger.debug(f"非好友消息，忽略! 消息类型: {msgtype}")
                            continue
                        # 接收窗口名跟发送人一样，代表是私聊，否则是群聊
                        if who == msg.sender:
                            # 私聊消息处理
                            chat_bot.handle_wxauto_message(msg, msg.sender)
                        else:
                            # 群聊消息处理，无论是否@机器人都传递到处理函数
                            # 设置is_group=True标记为群聊消息
                            is_at_robot = False
                            if ROBOT_WX_NAME != "":
                                is_at_robot = bool(
                                    re.search(f"@{ROBOT_WX_NAME}", msg.content)
                                ) or bool(
                                    re.search(f"@{ROBOT_WX_NAME}\u2005", msg.content)
                                )

                            # 所有群聊消息都进行处理，但传递正确的群聊ID
                            chat_bot.handle_wxauto_message(msg, who, is_group=True)

                            # 对于非@消息，记录日志
                            if not is_at_robot:
                                logger.debug(f"群聊非@消息，已处理: {content[:30]}...")
                    except Exception as e:
                        logger.debug(f"处理单条消息失败: {str(e)}")
                        continue

        except Exception as e:
            logger.debug(f"消息监听出错: {str(e)}")
            wx = None
        time.sleep(wait)


def initialize_wx_listener():
    """
    初始化微信监听，包含重试机制
    """
    global wx_listening_chats  # 使用全局变量跟踪已添加的监听集合

    max_retries = 3
    retry_delay = 2  # 秒

    for attempt in range(max_retries):
        try:
            wx = WeChat()
            if not wx.GetSessionList():
                logger.error("未检测到微信会话列表，请确保微信已登录")
                time.sleep(retry_delay)
                continue

            # 循环添加监听对象
            for chat_name in listen_list:
                try:
                    # 检查会话是否存在
                    if not wx.ChatWith(chat_name):
                        logger.error(f"找不到会话 {chat_name}")
                        continue

                    # 使用全局变量检查是否已经添加了监听
                    if chat_name not in wx_listening_chats:
                        # 尝试添加监听
                        wx.AddListenChat(who=chat_name, savepic=True, savefile=True)
                        logger.info(f"成功添加监听: {chat_name}")
                        wx_listening_chats.add(chat_name)  # 记录已添加监听的聊天
                    else:
                        logger.info(f"已存在监听，跳过: {chat_name}")

                    time.sleep(0.5)  # 添加短暂延迟，避免操作过快
                except Exception as e:
                    logger.error(f"添加监听失败 {chat_name}: {str(e)}")
                    continue

            return wx

        except Exception as e:
            logger.error(f"初始化微信失败(尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise Exception("微信初始化失败，请检查微信是否正常运行")

    return None


def initialize_auto_tasks(message_handler):
    """初始化自动任务系统"""
    print_status("初始化自动任务系统..", "info", "CLOCK")

    try:
        # 创建AutoTasker实例
        auto_tasker = AutoTasker(message_handler)
        print_status("创建AutoTasker实例成功", "success", "CHECK")

        # 清空现有任务
        auto_tasker.scheduler.remove_all_jobs()
        print_status("清空现有任务", "info", "CLEAN")

        # 检查listen_list是否为空
        if not listen_list:
            print_status("监听列表为空，无法添加任务", "warning", "WARNING")
            return auto_tasker

        # 从配置文件读取任务信息
        if hasattr(config, "behavior") and hasattr(
            config.behavior, "schedule_settings"
        ):
            schedule_settings = config.behavior.schedule_settings
            if hasattr(schedule_settings, "tasks") and schedule_settings.tasks:
                tasks = schedule_settings.tasks
                if tasks:
                    print_status(
                        f"从配置文件读取到 {len(tasks)} 个任务", "info", "TASK"
                    )
                    tasks_added = 0

                    # 遍历所有任务并添加
                    for task in tasks:
                        try:
                            # 检查任务必要字段
                            required_fields = [
                                "task_id",
                                "content",
                                "schedule_type",
                                "schedule_time",
                            ]
                            if not all(
                                hasattr(task, field) for field in required_fields
                            ):
                                print_status(
                                    f"任务缺少必要字段: {task}", "warning", "WARNING"
                                )
                                continue

                            # 添加定时任务
                            auto_tasker.add_task(
                                task_id=task.task_id,
                                chat_id=listen_list[
                                    0
                                ],  # 使用 listen_list 中的第一个聊天ID
                                content=task.content,
                                schedule_type=task.schedule_type,
                                schedule_time=task.schedule_time,
                            )
                            tasks_added += 1
                            print_status(
                                f"成功添加任务 {task.task_id}: {task.content}",
                                "success",
                                "CHECK",
                            )
                        except Exception as e:
                            print_status(
                                f"添加任务 {task.task_id} 失败: {str(e)}",
                                "error",
                                "ERROR",
                            )
                            logger.error(f"添加任务 {task.task_id} 失败: {str(e)}")

                    print_status(
                        f"成功添加 {tasks_added}/{len(tasks)} 个任务", "info", "TASK"
                    )
                else:
                    print_status("配置文件中没有找到任务", "warning", "WARNING")
            else:
                print_status(
                    "schedule_settings.tasks 不存在或为空", "warning", "WARNING"
                )
        else:
            print_status("未找到任务配置信息", "warning", "WARNING")

        return auto_tasker

    except Exception as e:
        print_status(f"初始化自动任务系统失败 {str(e)}", "error", "ERROR")
        logger.error(f"初始化自动任务系统失败 {str(e)}", exc_info=True)
        # 返回一个空的AutoTasker实例，避免程序崩溃
        return AutoTasker(message_handler)


def main(debug_mode=True):
    global files_handler, emoji_handler, image_handler, voice_handler, memory_handler, moonshot_ai, message_handler, listener_thread, chat_bot, wx, ROBOT_WX_NAME

    # 初始化listener_thread为None，避免引用错误
    listener_thread = None
    wx = None  # 初始化wx为None

    # 修正路径格式，使用正确的路径拼接
    avatar_dir = os.path.join(
        root_dir, "data", "avatars", config.behavior.context.avatar_dir
    )
    prompt_path = os.path.join(avatar_dir, "avatar.md")

    # 确保avatar目录存在
    if not os.path.exists(avatar_dir):
        try:
            os.makedirs(avatar_dir, exist_ok=True)
            logger.info(f"创建角色目录: {avatar_dir}")
        except Exception as e:
            logger.error(f"创建角色目录失败: {str(e)}")

    # 确保avatar.md文件存在
    if not os.path.exists(prompt_path):
        try:
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(
                    "# 核心人格\n这是一个默认的人设文件，请修改为你想要的角色设定。"
                )
            logger.info(f"创建默认人设文件: {prompt_path}")
        except Exception as e:
            logger.error(f"创建人设文件失败: {str(e)}")

    if debug_mode:
        ROBOT_WX_NAME = "Debuger"

    logger.info("开始预热情感分析模块..")
    sentiment_resource_loader = SentimentResourceLoader()
    sentiment_analyzer = SentimentAnalyzer(sentiment_resource_loader)
    logger.info("情感分析模块预热完成")

    # try:
    # 设置wxauto日志路径
    automation_log_dir = os.path.join(root_dir, "logs", "automation")
    if not os.path.exists(automation_log_dir):
        os.makedirs(automation_log_dir)
    os.environ["WXAUTO_LOG_PATH"] = os.path.join(
        automation_log_dir, "AutomationLog.txt"
    )

    files_handler = FileHandler()

    emoji_handler = EmojiHandler(
        root_dir=root_dir,
        wx_instance=wx,  # 如果不需要可以移除
        sentiment_analyzer=sentiment_analyzer,
    )

    # 图像和语音功能已移除
    image_handler = None
    voice_handler = None
    with open(prompt_path, "r", encoding="utf-8") as f:
        # 添加更多API配置日志
        logger.info("============ LLM服务初始化 ============")
        logger.info(f"模型名称: {config.llm.model}")
        logger.info(f"API基础URL: {config.llm.base_url}")
        logger.info(
            f"API密钥后4位: {config.llm.api_key[-4:] if config.llm.api_key else 'None'}"
        )
        logger.info(f"温度参数: {config.llm.temperature}")
        logger.info(f"最大Token数: {config.llm.max_tokens}")
        logger.info("正在测试API连接...")

        # 尝试测试连接
        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                try:
                    test_url = config.llm.base_url
                    if test_url.endswith("/"):
                        test_url = test_url.rstrip("/")
                    logger.info(f"测试连接到: {test_url}")
                    response = client.get(
                        f"{test_url}/models",
                        headers={"Authorization": f"Bearer {config.llm.api_key}"},
                    )
                    logger.info(f"API连接测试响应码: {response.status_code}")
                    if response.status_code == 200:
                        logger.info("API连接测试成功!")
                    else:
                        logger.warning(
                            f"API连接测试返回非200状态码: {response.status_code}"
                        )
                except Exception as e:
                    logger.error(f"API连接测试失败: {str(e)}")
        except ImportError:
            logger.warning("无法导入httpx库，跳过API连接测试")
        except Exception as e:
            logger.error(f"测试API连接时出错: {str(e)}")
        logger.info("====================================")

        deepseek = LLMService(
            sys_prompt=f.read(),
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            model=config.llm.model,
            max_token=int(config.llm.max_tokens),  # 确保转换为整数
            temperature=float(config.llm.temperature),  # 同时也确保temperature是浮点数
            max_groups=int(
                config.behavior.context.max_groups
            ),  # 确保max_groups也是整数
        )

    # 在初始化memory_handler前添加此日志
    logger.info(f"配置文件中的模型: {config.llm.model}")
    logger.info(f"API基础URL: {config.llm.base_url}")
    logger.info(f"温度参数: {config.llm.temperature}")

    # 创建API包装器
    api_wrapper = APIWrapper(api_key=config.llm.api_key, base_url=config.llm.base_url)

    # 初始化新的记忆系统
    try:
        from src.handlers.memory import init_memory

        logger.info("正在初始化新的三层记忆系统...")
        memory_handler = init_memory(root_dir, api_wrapper)
        if memory_handler:
            logger.info("记忆系统初始化成功")
            # 获取记忆系统统计信息
            try:
                stats = memory_handler.get_memory_stats()
                logger.info(
                    f"记忆系统统计: 记忆条数={stats.get('memory_count', 0)}, 嵌入数={stats.get('embedding_count', 0)}"
                )
            except Exception as stats_err:
                logger.warning(f"获取记忆统计信息失败: {str(stats_err)}")
        else:
            logger.warning("记忆系统初始化返回空处理器")
    except Exception as e:
        logger.error(f"初始化记忆系统失败: {str(e)}")
        memory_handler = None
        logger.warning("记忆系统已禁用")

    # 关键优化：注册上下文处理函数，将被移除的对话保存到记忆系统
    if memory_handler:
        try:
            # 定义上下文处理函数
            @deepseek.llm.context_handler
            def handle_removed_context(user_id, user_msg, ai_msg):
                """当上下文移除消息时，将对话保存到记忆系统"""
                try:
                    if user_msg and ai_msg:
                        # 移除"[当前用户问题]"标记
                        if "[当前用户问题]" in user_msg:
                            user_msg = user_msg.replace("[当前用户问题]", "").strip()

                        logger.info(f"将移除的上下文对话保存到记忆: 用户={user_id}")
                        memory_handler.remember(user_msg, ai_msg, user_id)
                except Exception as e:
                    logger.error(f"处理移除的上下文失败: {str(e)}")

            logger.info("已成功注册上下文处理函数，超出上下文的对话将保存到记忆系统")
        except Exception as ctx_err:
            logger.error(f"注册上下文处理函数失败: {str(ctx_err)}")

    moonshot_ai = ImageRecognitionService(
        api_key=config.media.image_recognition.api_key,
        base_url=config.media.image_recognition.base_url,
        temperature=config.media.image_recognition.temperature,
        model=config.media.image_recognition.model,
    )

    moonshot_ai = ImageRecognitionService(
        api_key=config.media.image_recognition.api_key,
        base_url=config.media.image_recognition.base_url,
        temperature=config.media.image_recognition.temperature,
        model=config.media.image_recognition.model,
    )

    message_handler = MessageHandler(
        root_dir=root_dir,
        llm=deepseek,
        robot_name=ROBOT_WX_NAME,  # 使用动态获取的机器人名称
        prompt_content=prompt_content,
        image_handler=image_handler,
        emoji_handler=emoji_handler,
        voice_handler=voice_handler,
        memory_handler=memory_handler,
        is_debug=debug_mode,
    )

    if debug_mode:
        # 设置日志颜色和级别
        logger.setLevel(logging.DEBUG)
        # 使用正确导入的init函数
        init(autoreset=True)  # 使用已导入的init而不是colorama_init
        logger.info(f"{Fore.YELLOW}调试模式已启用{Style.RESET_ALL}")

        # 初始化调试机器人
        global chat_bot
        chat_bot = DebugBot(
            message_handler=message_handler,
            moonshot_ai=moonshot_ai,
            memory_handler=memory_handler,
        )

        # 启动控制台交互循环
        while True:
            chat_bot.handle_wxauto_message(None, "debug_chat")
            time.sleep(1)
    else:
        # 确保在创建 ChatBot 实例时传递 memory_handler
        chat_bot = ChatBot(message_handler, moonshot_ai, memory_handler)

        # 设置监听列表
        global listen_list

        listen_list = config.user.listen_list

        # 初始化微信监听
        print_status("初始化微信监听..", "info", "BOT")
        wx = initialize_wx_listener()
        if not wx:
            print_status(
                "微信初始化失败，请确保微信已登录并保持在前台运行!", "error", "CROSS"
            )
            return
        print_status("微信监听初始化完成", "success", "CHECK")
        print_status("检查短期记忆..", "info", "SEARCH")

        # 启动消息监听线程
        print_status("启动消息监听线程...", "info", "ANTENNA")
        listener_thread = threading.Thread(target=message_listener)
        listener_thread.daemon = True  # 确保线程是守护线程
        listener_thread.start()
        print_status("消息监听已启动", "success", "CHECK")

        # 启动主动消息
        print_status("启动主动消息系统...", "info", "CLOCK")
        start_countdown()
        print_status("主动消息系统已启动", "success", "CHECK")

        print("-" * 50)
        print_status("系统初始化完成", "success", "STAR_2")
        print("=" * 50)

        # 初始化自动任务系统
        auto_tasker = initialize_auto_tasks(message_handler)
        if not auto_tasker:
            print_status("自动任务系统初始化失败", "error", "ERROR")
            return

            # 主循环
            # 在主循环中的重连逻辑
        while True:
            time.sleep(20)
            if listener_thread is None or not listener_thread.is_alive():
                print_status("监听线程已断开，尝试重新连接..", "warning", "SYNC")
                try:
                    # 添加检查，避免在短时间内多次重试
                    last_restart_time = getattr(main, "last_restart_time", 0)
                    current_time = time.time()
                    if current_time - last_restart_time < 20:  # 至少间隔20秒
                        print_status("上次重启尝试时间过短，等待..", "warning", "WAIT")
                        time.sleep(10)  # 增加等待时间
                        continue

                    main.last_restart_time = current_time
                    wx = initialize_wx_listener()
                    if wx:
                        listener_thread = threading.Thread(target=message_listener)
                        listener_thread.daemon = True
                        listener_thread.start()
                        print_status("重新连接成功", "success", "CHECK")
                        time.sleep(10)  # 添加短暂延迟，确保线程正常启动
                    else:
                        print_status(
                            "重新连接失败，将等待20秒后重试", "warning", "WARNING"
                        )
                        time.sleep(20)
                except Exception as e:
                    print_status(f"重新连接失败: {str(e)}", "error", "CROSS")
                    time.sleep(10)  # 失败后等待更长时间

        #     # 设置事件以停止线程
        #     stop_event.set()

        # 关闭监听线程
        if listener_thread is not None and listener_thread.is_alive():
            print_status("正在关闭监听线程...", "info", "SYNC")
            try:
                listener_thread.join(timeout=2)
                if listener_thread.is_alive():
                    print_status("无法正常停止监听线程", "warning", "WARNING")
            except Exception as e:
                print_status(f"清理线程时出错 {str(e)}", "error", "ERROR")

    #     print_status("正在关闭系统...", "warning", "STOP")
    #     print_status("系统已退出", "info", "BYE")
    #     print("\n")


#
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_status("用户终止程序", "warning", "STOP")
        print_status("感谢使用，再见！", "info", "BYE")
        print("\n")
    except Exception as e:
        print_status(f"程序异常退出 {str(e)}", "error", "ERROR")

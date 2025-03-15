import logging
import random
from datetime import datetime, timedelta
import threading
import time
import os
import shutil
import win32gui
import win32con
from src.config.rag_config import config, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL, MAX_TOKEN, TEMPERATURE, MAX_GROUPS
from wxauto import WeChat
import re
from handlers.emoji import EmojiHandler
from handlers.image import ImageHandler
from handlers.message import MessageHandler
from handlers.voice import VoiceHandler
from src.handlers.file import FileHandler
from src.services.ai.llm_service import LLMService
from src.services.ai.image_recognition_service import ImageRecognitionService
from src.handlers.memory import MemoryHandler
from src.handlers.emotion import SentimentResourceLoader, SentimentAnalyzer  # 导入情感分析模块
from src.utils.logger import LoggerConfig
from utils.console import print_status
from colorama import init, Style, Fore
from src.AutoTasker.autoTasker import AutoTasker
import sys

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
logger = logger_config.setup_logger('main')
listen_list = config.user.listen_list
queue_lock = threading.Lock()  # 队列访问锁
user_queues = {}  # 用户消息队列管理
chat_contexts = {}  # 存储上下文
# 初始化colorama
init()

# 预热情感分析模块（全局单例）
logger.info("开始预热情感分析模块..")
sentiment_resource_loader = SentimentResourceLoader()
sentiment_analyzer = SentimentAnalyzer(sentiment_resource_loader)
logger.info("情感分析模块预热完成")

# 在初始化memory_handler前添加此日志
logger.info(f"配置文件中的模型: {config.llm.model}")
logger.info(f"常量MODEL的值 {MODEL}")

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
        logger = logging.getLogger('main')
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
        print("\n" + "="*50)
        print(f"{Fore.GREEN}[等待用户输入]{Style.RESET_ALL}")

    def _resume_logging(self):
        """恢复日志输出"""
        if self._original_handlers:
            logger = logging.getLogger('main')
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
                messages = user_data['messages']

            self.log_colored_message(f"[处理消息队列] - 内容: {' | '.join(messages)}", self.system_color)
            
            # 暂停日志确保用户可以输入
            self._pause_logging()
            response = input("[请输入AI回复] >>> ")
            print("-"*50)  # 添加分隔线
            self._resume_logging()

            if response:
                # 使用彩色日志显示AI回复
                self.log_colored_message(f"[AI回复] {response}", self.ai_color)
                self.memory_handler.add_short_memory(
                    "用户调试输入",
                    response,
                    "debug_user"
                )

        except Exception as e:
            logger.error(f"调试消息处理失败: {str(e)}")

    def handle_wxauto_message(self, msg, chatName, is_group=False):
        """控制台交互处理"""
        # 暂停日志确保用户可以输入
        self._pause_logging()
        
        try:
            user_input = input("[请输入测试消息] >>> ")
            print("-"*50)  # 添加分隔线使输入更清晰
        finally:
            # 确保恢复日志输出
            self._resume_logging()
        
        # 记录用户输入
        self.log_colored_message(f"[用户输入] {user_input}", Fore.WHITE)
        
        # 模拟消息处理流程
        result = self.message_handler.handle_user_message(
            content=user_input,
            chat_id=chatName,
            sender_name="debug_user",
            username="debug_user",
            is_group=False
        )
        
        # 如果有回复，显示为彩色
        if result:
            reply_text = result[0] if isinstance(result, list) else result
            self.log_colored_message(f"[AI回复摘要] {reply_text[:50]}...", self.ai_color)
        
        # 处理完成提示
        self.log_colored_message(f"[处理完成] {'-'*30}", self.system_color)
        
        return result


class ChatBot:
    def __init__(self, message_handler, moonshot_ai, memory_handler):
        self.message_handler = message_handler
        self.moonshot_ai = moonshot_ai
        self.memory_handler = memory_handler
        self.user_queues = {}  # 将user_queues移到类的实例变量
        self.queue_lock = threading.Lock()  # 将queue_lock也移到类的实例变量
        self.ai_last_reply_time = {}  # 新增：记录AI 最后回复的时间
        # self.unanswered_counters = {}  # 新增：每个用户的未回复计数器, 移动到MessageHandler

        # 获取机器人的微信名称
        self.wx = WeChat()
        self.robot_name = self.wx.A_MyIcon.Name  # 移除括号，直接访问Name属性
        # logger.info(f"机器人名称为 {self.robot_name}")
        
        # 将wx实例传递给message_handler
        self.message_handler.wx = self.wx

    def process_user_messages(self, chat_id):
        """处理用户消息队列"""
        try:
            logger.info(f"开始处理消息队列- 聊天ID: {chat_id}")
            with self.queue_lock:
                if chat_id not in self.user_queues:
                    logger.warning(f"未找到消息队列 {chat_id}")
                    return
                user_data = self.user_queues.pop(chat_id)
                messages = user_data['messages']
                sender_name = user_data['sender_name']
                username = user_data['username']
                is_group = user_data.get('is_group', False)

            logger.info(f"队列信息 - 发送者: {sender_name}, 消息数: {len(messages)}, 是否群聊: {is_group}")

            # 消息去重处理
            if len(messages) > 1:
                # 移除完全相同的连续消息
                unique_messages = [messages[0]]
                for i in range(1, len(messages)):
                    if messages[i] != messages[i - 1]:
                        unique_messages.append(messages[i])

                # 检查是否有重复消息被移除
                if len(unique_messages) < len(messages):
                    logger.info(f"消息队列去重: 从 {len(messages)} 条减少到 {len(unique_messages)} 条")
                    messages = unique_messages

            # 合并消息内容
            is_image_recognition = any("发送了图片" in msg or "发送了表情包：" in msg for msg in messages)

            # 优化消息合并逻辑
            if len(messages) > 1:
                # 第一条消息通常包含时间戳和问候语，保持原样
                # 后续消息直接拼接，避免重复的问候语
                content = messages[0]
                for i in range(1, len(messages)):
                    content += f"\n{messages[i]}"
            else:
                content = messages[0]

            # 记录处理前的消息内容，用于防止重复处理
            chat_key = f"{chat_id}_{username}"
            current_content_hash = hash(content)

            # 检查是否是重复内容
            if hasattr(self, 'last_processed_content') and chat_key in self.last_processed_content:
                last_hash, last_time = self.last_processed_content.get(chat_key, (None, 0))
                # 如果内容相同且时间间隔小于5秒，可能是重复处理
                if last_hash == current_content_hash and time.time() - last_time < 5:
                    logger.warning(f"检测到可能的重复处理，跳过: {chat_id}")
                    return

            # 更新最后处理的内容记录
            if not hasattr(self, 'last_processed_content'):
                self.last_processed_content = {}
            self.last_processed_content[chat_key] = (current_content_hash, time.time())

            # 直接调用 MessageHandler 的handle_user_message 方法
            response = self.message_handler.handle_user_message(
                content=content,
                chat_id=chat_id,
                sender_name=sender_name,
                username=username,
                is_group=is_group,
                is_image_recognition=is_image_recognition
            )
            logger.info(f"消息已处理- 聊天ID: {chat_id}")

            # 确保记忆保存功能被调用
            if response and isinstance(response, str):
                # 如果 handle_user_message 返回了回复内容，则保存到记忆
                self.memory_handler.add_short_memory(content, response, username)
                logger.info(f"已保存消息到记忆 - 用户ID: {username}")

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
                                f"用户 {username} 的未回复计数器: {self.message_handler.unanswered_counters[username]}")
                        else:
                            logger.info(
                                f"用户 {username} 30 分钟后回复，未回复计数器: {self.message_handler.unanswered_counters[username]}")

        except Exception as e:
            logger.error(f"处理消息队列失败: {str(e)}", exc_info=True)

    def handle_wxauto_message(self, msg, chatName, is_group=False):
        try:
            username = msg.sender
            content = getattr(msg, 'content', None) or getattr(msg, 'text', None)

            # 添加详细日志
            logger.info(f"收到消息 - 来源: {chatName}, 发送者: {username}, 是否群聊: {is_group}")
            logger.info(f"原始消息内容: {content}")

            # 增加重复消息检查
            message_key = f"{chatName}_{username}_{hash(content)}"
            current_time = time.time()

            # 检查是否是短时间内的重复消息
            if hasattr(self, '_processed_messages'):
                # 清理超过60秒的旧记录，减少内存占用
                self._processed_messages = {k: v for k, v in self._processed_messages.items()
                                            if current_time - v < 60}

                if message_key in self._processed_messages:
                    if current_time - self._processed_messages[message_key] < 5:  # 5秒内的重复消息
                        logger.warning(f"检测到短时间内的重复消息，已忽略 {content[:20]}...")
                        return
            else:
                self._processed_messages = {}

            # 记录当前消息处理时间
            self._processed_messages[message_key] = current_time

            # 其余消息处理逻辑保持不变
            img_path = None
            files_path = None
            is_emoji = False
            is_image_recognition = False  # 新增标记，用于标识是否是图片识别结果

            # 如果是群聊@消息，移除@机器人的部分
            if is_group and self.robot_name and content:
                logger.info(f"处理群聊@消息 - 机器人名称: {self.robot_name}")
                original_content = content
                content = re.sub(f'@{self.robot_name}\u2005', '', content).strip()
                logger.info(f"移除@后的消息内容: {content}")
                if original_content == content:
                    logger.info("未检测到@机器人，但是继续处理")

            if content and content.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                logger.info(f"检测到图片消息: {content}")
                img_path = content
                is_emoji = False
                content = None

            if content and content.lower().endswith(('.txt', '.docx', '.doc', '.ppt', '.pptx', '.xlsx', '.xls')):
                logger.info(f"检测到文件消息: {content}")
                files_path = content
                is_emoji = False
                content = None

            # 检查是否是"[动画表情]"
            if content and "[动画表情]" in content:
                logger.info("检测到动画表情")
                # 修改方法名调用
                img_path = emoji_handler.capture_emoji_screenshot(username)

                logger.info(f"表情截图保存路径: {img_path}")
                is_emoji = True
                content = None

            if img_path:
                logger.info(f"开始处理图片/表情 - 路径: {img_path}, 是否表情: {is_emoji}")
                recognized_text = self.moonshot_ai.recognize_image(img_path, is_emoji)
                logger.info(f"图片/表情识别结果: {recognized_text}")
                content = recognized_text if content is None else f"{content} {recognized_text}"
                is_image_recognition = True  # 标记这是图片识别结果

            if files_path:
                logger.info(f"开始处理文件 - 路径：{files_path}")
                # 调用 Message _handle_file_request 处理方法
                return self.message_handler.handle_user_message(
                    content=files_path,
                    chat_id=chatName,
                    sender_name=username,
                    username=username,
                    is_group=is_group
                )

            # 情感分析处理
            if content:
                # 检测是否为表情包请求
                if emoji_handler.is_emoji_request(content):
                    logger.info("检测到表情包请求")
                    # 使用AI识别的情感选择表情
                    emoji_path = emoji_handler.get_emotion_emoji(content)
                    if emoji_path:
                        logger.info(f"准备发送情感表情包: {emoji_path}")
                        self.message_handler.wx.SendFiles(emoji_path, chatName)

                sender_name = username
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                group_info = f"在群聊里" if is_group else "私聊"
                time_aware_content = f"(此时时间为{current_time}) ta{group_info}对你说{content}"  #去掉用户名，防止出现私聊时出现用户名的情
                logger.info(f"格式化后的消息 {time_aware_content}")

                # 使用MessageHandler的消息缓存功能处理消息
                self.message_handler.handle_user_message(
                    content=time_aware_content,
                    chat_id=chatName,
                    sender_name=sender_name,
                    username=username,
                    is_group=is_group,
                    is_image_recognition=is_image_recognition
                )

                # 启动或取消未回复消息计时器
                if username in self.message_handler.unanswered_timers:
                    self.message_handler.unanswered_timers[username].cancel()
                    #logger.info(f"取消用户 {username} 的未回复计时器")

                # 30分钟后增加未回复计数
                def increase_counter_after_delay(username):
                    with self.queue_lock:
                        self.message_handler.increase_unanswered_counter(username)

                timer = threading.Timer(1800.0, increase_counter_after_delay, args=[username])
                timer.start()
                self.message_handler.unanswered_timers[username] = timer
                #logger.info(f"为用户{username} 启动未回复计时器")

        except Exception as e:
            logger.error(f"消息处理失败: {str(e)}", exc_info=True)


# 读取提示文件
avatar_dir = os.path.join(root_dir, config.behavior.context.avatar_dir)
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
        if quiet_start_str == '1320':
            quiet_start_str = '13:20'
        if quiet_end_str == '1320':
            quiet_end_str = '13:20'
            
        # 如果格式不包含冒号，尝试转换
        if quiet_start_str and ':' not in quiet_start_str:
            try:
                hour = int(quiet_start_str) // 100
                minute = int(quiet_start_str) % 100
                quiet_start_str = f"{hour:02d}:{minute:02d}"
                logger.info(f"转换安静时间开始格式: {config.behavior.quiet_time.start} -> {quiet_start_str}")
            except (ValueError, TypeError):
                logger.warning(f"无法转换安静时间开始格式: {quiet_start_str}")
                
        if quiet_end_str and ':' not in quiet_end_str:
            try:
                hour = int(quiet_end_str) // 100
                minute = int(quiet_end_str) % 100
                quiet_end_str = f"{hour:02d}:{minute:02d}"
                logger.info(f"转换安静时间结束格式: {config.behavior.quiet_time.end} -> {quiet_end_str}")
            except (ValueError, TypeError):
                logger.warning(f"无法转换安静时间结束格式: {quiet_end_str}")
        
        # 解析时间
        quiet_start = datetime.strptime(quiet_start_str, "%H:%M").time()
        quiet_end = datetime.strptime(quiet_end_str, "%H:%M").time()
        
        # 记录解析后的时间
        logger.debug(f"解析后的安静时间: 开始={quiet_start}, 结束={quiet_end}, 当前时间={current_time}")

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
        # 检查配置是否存在
        if not hasattr(config, 'behavior') or not hasattr(config.behavior, 'auto_message') or \
           not hasattr(config.behavior.auto_message, 'min_hours') or \
           not hasattr(config.behavior.auto_message, 'max_hours'):
            logger.error("配置文件中缺少倒计时设置，使用默认值1-3小时")
            return random.uniform(3600, 10800)  # 默认1-3小时
            
        # 直接从配置中读取最小和最大小时数
        min_hours = float(config.behavior.auto_message.min_hours)
        max_hours = float(config.behavior.auto_message.max_hours)
        
        # 确保最小值不大于最大值
        if min_hours > max_hours:
            logger.warning(f"配置错误：min_hours({min_hours})大于max_hours({max_hours})，将交换它们")
            min_hours, max_hours = max_hours, min_hours
            
        # 将小时转换为秒
        min_seconds = int(min_hours * 3600)
        max_seconds = int(max_hours * 3600)
        
        logger.debug(f"从配置读取的倒计时范围：{min_hours}小时到{max_hours}小时")
        return random.uniform(min_seconds, max_seconds)
    except Exception as e:
        logger.error(f"获取倒计时时间失败 {str(e)}，使用默认值1-3小时")
        # 返回默认值：1-3小时
        return random.uniform(3600, 10800)


def get_personality_summary(prompt_content: str) -> str:
    """从完整人设中提取关键性格特点"""
    try:
        # 查找核心人格部分
        core_start = prompt_content.find("# 性格")
        if core_start == -1:
            return prompt_content[:500]  # 如果找不到标记，返回500字符

        # 找到下一个标题或文件结尾
        next_title = prompt_content.find("#", core_start + 1)
        if next_title == -1:
            core_content = prompt_content[core_start:]
        else:
            core_content = prompt_content[core_start:next_title]

        # 提取关键内容
        core_lines = [line.strip() for line in core_content.split('\n')
                      if line.strip() and not line.startswith('#')]

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
        if hasattr(wx_instance, 'IsListening'):
            return wx_instance.IsListening(chat_name)
        
        # 如果内置方法不存在，我们无法确定是否已经在监听
        # 可以通过其他方式检查，例如检查是否有相关的事件处理器
        # 但由于我们没有足够的信息，暂时返回False
        logger.warning(f"wxauto 模块没有 IsListening 方法，无法确定是否已经在监听 {chat_name}")
        return False
    except Exception as e:
        logger.error(f"检查监听状态失败 {str(e)}")
        # 出错时返回False，让程序尝试添加监听
        return False


def auto_send_message():
    """自动发送消息- 调用message_handler中的方法"""
    # 调用message_handler中的auto_send_message方法
    message_handler.auto_send_message(
        listen_list=listen_list,
        robot_wx_name=ROBOT_WX_NAME,
        get_personality_summary=get_personality_summary,
        is_quiet_time=is_quiet_time,
        start_countdown=start_countdown
    )
    # 最后启动新的倒计时
    start_countdown()


def start_countdown():
    """开始新的倒计时"""
    global countdown_timer, is_countdown_running, countdown_end_time

    if countdown_timer:
        countdown_timer.cancel()

    countdown_seconds = get_random_countdown_time()
    countdown_end_time = datetime.now() + timedelta(seconds=countdown_seconds)  # 设置结束时间
    
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
        if hasattr(config, 'behavior') and hasattr(config.behavior, 'auto_message') and \
           hasattr(config.behavior.auto_message, 'min_hours') and \
           hasattr(config.behavior.auto_message, 'max_hours'):
            min_hours = float(config.behavior.auto_message.min_hours)
            max_hours = float(config.behavior.auto_message.max_hours)
            logger.info(f"配置的倒计时范围: {min_hours:.1f}小时 - {max_hours:.1f}小时")
        else:
            logger.info("使用默认倒计时范围: 1.0小时 - 3.0小时")
    except Exception as e:
        logger.warning(f"无法读取配置的倒计时范围: {str(e)}")

    countdown_timer = threading.Timer(countdown_seconds, auto_send_message)
    countdown_timer.daemon = True
    countdown_timer.start()
    is_countdown_running = True


def message_listener():
    global wx_listening_chats  # 使用全局变量跟踪已添加的监听集合
    
    wx = None
    last_window_check = 0
    check_interval = 600  # 10分钟检查一次
    reconnect_attempts = 0
    max_reconnect_attempts = 3
    reconnect_delay = 10  # 重连等待时间（秒）
    last_reconnect_time = 0

    while not stop_event.is_set():
        try:
            current_time = time.time()

            if wx is None or (current_time - last_window_check > check_interval):
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
                                    wx.AddListenChat(who=chat_name, savepic=True, savefile=True)
                                    logger.info(f"重新添加监听: {chat_name}")
                                    wx_listening_chats.add(chat_name)  # 记录已添加监听的聊天
                                else:
                                    logger.info(f"已存在监听，跳过: {chat_name}")
                        except Exception as e:
                            logger.error(f"重新添加监听失败 {chat_name}: {str(e)}")

                    # 成功初始化，重置计数
                    reconnect_attempts = 0
                    last_window_check = current_time
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

                one_msgs = msgs.get(chat)
                if not one_msgs:
                    continue

                for msg in one_msgs:
                    try:
                        msgtype = msg.type
                        content = msg.content
                        if not content:
                            continue
                        if msgtype != 'friend':
                            logger.debug(f"非好友消息，忽略! 消息类型: {msgtype}")
                            continue
                            # 接收窗口名跟发送人一样，代表是私聊，否则是群聊
                        if who == msg.sender:
                            chat_bot.handle_wxauto_message(msg, msg.sender)  # 处理私聊信息
                        elif ROBOT_WX_NAME != '' and (bool(re.search(f'@{ROBOT_WX_NAME}\u2005', msg.content)) or bool(
                                re.search(f'{ROBOT_WX_NAME}\u2005', msg.content))):
                            # 修改：在群聊被@时或者被叫名字，传入群聊ID(who)作为回复目标
                            chat_bot.handle_wxauto_message(msg, who, is_group=True)
                        else:
                            logger.debug(f"非需要处理消息，可能是群聊非@消息: {content}")
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
        if hasattr(config, 'behavior') and hasattr(config.behavior, 'schedule_settings'):
            schedule_settings = config.behavior.schedule_settings
            if hasattr(schedule_settings, 'tasks') and schedule_settings.tasks:
                tasks = schedule_settings.tasks
                if tasks:
                    print_status(f"从配置文件读取到 {len(tasks)} 个任务", "info", "TASK")
                    tasks_added = 0

                    # 遍历所有任务并添加
                    for task in tasks:
                        try:
                            # 检查任务必要字段
                            required_fields = ['task_id', 'content', 'schedule_type', 'schedule_time']
                            if not all(hasattr(task, field) for field in required_fields):
                                print_status(f"任务缺少必要字段: {task}", "warning", "WARNING")
                                continue

                            # 添加定时任务
                            auto_tasker.add_task(
                                task_id=task.task_id,
                                chat_id=listen_list[0],  # 使用 listen_list 中的第一个聊天ID
                                content=task.content,
                                schedule_type=task.schedule_type,
                                schedule_time=task.schedule_time
                            )
                            tasks_added += 1
                            print_status(f"成功添加任务 {task.task_id}: {task.content}", "success", "CHECK")
                        except Exception as e:
                            print_status(f"添加任务 {task.task_id} 失败: {str(e)}", "error", "ERROR")
                            logger.error(f"添加任务 {task.task_id} 失败: {str(e)}")

                    print_status(f"成功添加 {tasks_added}/{len(tasks)} 个任务", "info", "TASK")
                else:
                    print_status("配置文件中没有找到任务", "warning", "WARNING")
            else:
                print_status("schedule_settings.tasks 不存在或为空", "warning", "WARNING")
        else:
            print_status("未找到任务配置信息", "warning", "WARNING")

        return auto_tasker

    except Exception as e:
        print_status(f"初始化自动任务系统失败 {str(e)}", "error", "ERROR")
        logger.error(f"初始化自动任务系统失败 {str(e)}", exc_info=True)
        # 返回一个空的AutoTasker实例，避免程序崩溃
        return AutoTasker(message_handler)


def main(debug_mode=False):
    global files_handler, emoji_handler, image_handler, \
        voice_handler, memory_handler, moonshot_ai, \
        message_handler, listener_thread, chat_bot, wx, ROBOT_WX_NAME
    
    # 初始化listener_thread为None，避免引用错误
    listener_thread = None
    wx = None  # 初始化wx为None

    if debug_mode: ROBOT_WX_NAME = "Debuger"

    # try:
        # 设置wxauto日志路径

        automation_log_dir = os.path.join(root_dir, "logs", "automation")
        if not os.path.exists(automation_log_dir):
            os.makedirs(automation_log_dir)
        os.environ["WXAUTO_LOG_PATH"] = os.path.join(automation_log_dir, "AutomationLog.txt")

        files_handler = FileHandler()
        emoji_handler = EmojiHandler(root_dir)
        image_handler = ImageHandler(
            root_dir=root_dir,
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            image_model=config.media.image_generation.model
        )
        voice_handler = VoiceHandler(
            root_dir=root_dir,
            tts_api_url=config.media.text_to_speech.tts_api_url
        )
        memory_handler = MemoryHandler(
            root_dir=root_dir,
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            model=config.llm.model,
            max_token=config.llm.max_tokens,
            temperature=config.llm.temperature,
            max_groups=config.behavior.context.max_groups,
            bot_name=ROBOT_WX_NAME
        )


    deepseek = LLMService(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        model=config.llm.model,
        max_token=config.llm.max_tokens,
        temperature=config.llm.temperature,
        max_groups=config.behavior.context.max_groups,
    )
    
    memory_handler = MemoryHandler(
        root_dir=root_dir,
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        model=config.llm.model,
        max_token=config.llm.max_tokens,
        temperature=config.llm.temperature,
        max_groups=config.behavior.context.max_groups,
        bot_name=ROBOT_WX_NAME,
        llm=deepseek
    )
    moonshot_ai = ImageRecognitionService(
        api_key=config.media.image_recognition.api_key,
        base_url=config.media.image_recognition.base_url,
        temperature=config.media.image_recognition.temperature,
        model=config.media.image_recognition.model
    )

    moonshot_ai = ImageRecognitionService(
        api_key=config.media.image_recognition.api_key,
        base_url=config.media.image_recognition.base_url,
        temperature=config.media.image_recognition.temperature,
        model=config.media.image_recognition.model
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
        is_debug=debug_mode
    )


        # 获取机器人名称- 移到前面，优先获取
        try:
            wx = WeChat()
            ROBOT_WX_NAME = wx.A_MyIcon.Name
            logger.info(f"获取到机器人名称: {ROBOT_WX_NAME}")
            # 不在这里添加监听，避免重复添加
            # 监听将在 initialize_wx_listener 函数中统一处理
        except Exception as e:
            logger.error(f"获取机器人名称失败 {str(e)}")
            ROBOT_WX_NAME = ""  # 设置默认值

        message_handler = MessageHandler(
            root_dir=root_dir,
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            model=config.llm.model,
            max_token=config.llm.max_tokens,
            temperature=config.llm.temperature,
            max_groups=config.behavior.context.max_groups,
            robot_name=ROBOT_WX_NAME,  # 使用动态获取的机器人名称
            prompt_content=prompt_content,
            image_handler=image_handler,
            emoji_handler=emoji_handler,
            voice_handler=voice_handler,
            memory_handler=memory_handler,
            is_debug=debug_mode,
            wx=wx  # 传递wx对象
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
                memory_handler=memory_handler
            )

            # 启动控制台交互循环
            while True:
                chat_bot.handle_wxauto_message(None, "debug_chat")
                time.sleep(1)
        else:
            # 确保在创建ChatBot 实例时传入memory_handler
            chat_bot = ChatBot(message_handler, moonshot_ai, memory_handler)

            # 设置监听列表
            global listen_list

            listen_list = config.user.listen_list

            # 初始化微信监听
            print_status("初始化微信监听..", "info", "BOT")
            wx = initialize_wx_listener()
            if not wx:
                print_status("微信初始化失败，请确保微信已登录并保持在前台运行!", "error", "CROSS")
                return
            print_status("微信监听初始化完成", "success", "CHECK")
            print_status("检查短期记忆..", "info", "SEARCH")

            # 移除summarize_memories 的调用
            # memory_handler.summarize_memories()  # 启动时处理残留记忆

            # 移除记忆维护线程
            """
            def memory_maintenance():
                while True:
                    try:
                        memory_handler.summarize_memories()
                        time.sleep(3600)  # 每小时检查一次
                    except Exception as e:
                        logger.error(f"记忆维护失败: {str(e)}")
    
            print_status("启动记忆维护线程...", "info", "BRAIN")
            memory_thread = threading.Thread(target=memory_maintenance)
            memory_thread.daemon = True
            memory_thread.start()
            """

            print_status("验证记忆存储路径...", "info", "FILE")
            memory_dir = os.path.join(root_dir, "data", "memory")
            if not os.path.exists(memory_dir):
                os.makedirs(memory_dir)
                print_status(f"创建记忆目录: {memory_dir}", "success", "CHECK")

            avatar_dir = os.path.join(root_dir, config.behavior.context.avatar_dir)
            prompt_path = os.path.join(avatar_dir, "avatar.md")
            if not os.path.exists(prompt_path):
                with open(prompt_path, "w", encoding="utf-8") as f:
                    f.write("# 核心人格\n[默认内容]")
                print_status(f"创建人设提示文件", "warning", "WARNING")

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
                time.sleep(5)
                if listener_thread is None or not listener_thread.is_alive():
                    print_status("监听线程已断开，尝试重新连接..", "warning", "SYNC")
                    try:
                        # 添加检查，避免在短时间内多次重试
                        last_restart_time = getattr(main, 'last_restart_time', 0)
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
                            print_status("重新连接失败，将等待20秒后重试", "warning", "WARNING")
                            time.sleep(20)
                    except Exception as e:
                        print_status(f"重新连接失败: {str(e)}", "error", "CROSS")
                        time.sleep(10)  # 失败后等待更长时间

    except Exception as e:
        print_status(f"主程序异常 {str(e)}", "error", "ERROR")
        logger.error(f"主程序异常 {str(e)}", exc_info=True)  # 添加详细日志记录
    finally:
        # 清理资源
        if countdown_timer:
            countdown_timer.cancel()

        # 设置事件以停止线程
        stop_event.set()

        # 关闭监听线程
        if listener_thread is not None and listener_thread.is_alive():
            print_status("正在关闭监听线程...", "info", "SYNC")
            try:
                listener_thread.join(timeout=2)
                if listener_thread.is_alive():
                    print_status("无法正常停止监听线程", "warning", "WARNING")
            except Exception as e:
                print_status(f"清理线程时出错 {str(e)}", "error", "ERROR")

        print_status("正在关闭系统...", "warning", "STOP")
        print_status("系统已退出", "info", "BYE")
        print("\n")

# if debug_mode:
#         # 设置日志颜色和级别
#         logger.setLevel(logging.DEBUG)
#         # 使用正确导入的init函数
#         init(autoreset=True)  # 使用已导入的init而不是colorama_init
#         logger.info(f"{Fore.YELLOW}调试模式已启用{Style.RESET_ALL}")
# 
#         # 初始化调试机器人
#         global chat_bot, wx
#         chat_bot = DebugBot(
#             message_handler=message_handler,
#             moonshot_ai=moonshot_ai,
#             memory_handler=memory_handler
#         )
# 
#         # 启动控制台交互循环
#         while True:
#             chat_bot.handle_wxauto_message(None, "debug_chat")
#             time.sleep(1)
#     else:
#         # 确保在创建 ChatBot 实例时传递 memory_handler
#         chat_bot = ChatBot(message_handler, moonshot_ai, memory_handler)
# 
#         # 设置监听列表
#         global listen_list
# 
#         listen_list = config.user.listen_list
# 
#         # 获取机器人名称 - 移到前面，优先获取
#         try:
#             wx = WeChat()
#             ROBOT_WX_NAME = wx.A_MyIcon.Name
#             logger.info(f"获取到机器人名称: {ROBOT_WX_NAME}")
#             # 循环添加监听对象
#             for i in listen_list:
#                 wx.AddListenChat(who=i, savepic=True, savefile=True)
#         except Exception as e:
#             logger.error(f"获取机器人名称失败: {str(e)}")
#             ROBOT_WX_NAME = ""  # 设置默认值
# 
#         # 初始化微信监听
#         print_status("初始化微信监听...", "info", "BOT")
#         wx = initialize_wx_listener()
#         if not wx:
#             print_status("微信初始化失败，请确保微信已登录并保持在前台运行!", "error", "CROSS")
#             return
#         print_status("微信监听初始化完成", "success", "CHECK")
#         print_status("检查短期记忆...", "info", "SEARCH")
# 
#         # 移除对 summarize_memories 的调用
#         # memory_handler.summarize_memories()  # 启动时处理残留记忆
# 
#         # 移除记忆维护线程
#         """
#         def memory_maintenance():
#             while True:
#                 try:
#                     memory_handler.summarize_memories()
#                     time.sleep(3600)  # 每小时检查一次
#                 except Exception as e:
#                     logger.error(f"记忆维护失败: {str(e)}")
# 
#         print_status("启动记忆维护线程...", "info", "BRAIN")
#         memory_thread = threading.Thread(target=memory_maintenance)
#         memory_thread.daemon = True
#         memory_thread.start()
#         """
# 
#         print_status("验证记忆存储路径...", "info", "FILE")
#         memory_dir = os.path.join(root_dir, "data", "memory")
#         if not os.path.exists(memory_dir):
#             os.makedirs(memory_dir)
#             print_status(f"创建记忆目录: {memory_dir}", "success", "CHECK")
# 
#         avatar_dir = os.path.join(root_dir, config.behavior.context.avatar_dir)
#         prompt_path = os.path.join(avatar_dir, "avatar.md")
#         if not os.path.exists(prompt_path):
#             with open(prompt_path, "w", encoding="utf-8") as f:
#                 f.write("# 核心人格\n[默认内容]")
#             print_status(f"创建人设提示文件", "warning", "WARNING")
# 
#         # 启动消息监听线程
#         print_status("启动消息监听线程...", "info", "ANTENNA")
#         listener_thread = threading.Thread(target=message_listener)
#         listener_thread.daemon = True  # 确保线程是守护线程
#         listener_thread.start()
#         print_status("消息监听已启动", "success", "CHECK")
# 
#         # 启动主动消息
#         print_status("启动主动消息系统...", "info", "CLOCK")
#         start_countdown()
#         print_status("主动消息系统已启动", "success", "CHECK")
# 
#         print("-" * 50)
#         print_status("系统初始化完成", "success", "STAR_2")
#         print("=" * 50)
# 
#         # 初始化自动任务系统
#         auto_tasker = initialize_auto_tasks(message_handler)
#         if not auto_tasker:
#             print_status("自动任务系统初始化失败", "error", "ERROR")
#             return
# 
#         # 主循环
#         # 在主循环中的重连逻辑
#         while True:
#             time.sleep(5)
#             if not listener_thread.is_alive():
#                 print_status("监听线程已断开，尝试重新连接...", "warning", "SYNC")
#                 try:
#                     # 添加检查，避免在短时间内多次重启
#                     last_restart_time = getattr(main, 'last_restart_time', 0)
#                     current_time = time.time()
#                     if current_time - last_restart_time < 20:  # 至少间隔20秒
#                         print_status("上次重启尝试时间过短，等待...", "warning", "WAIT")
#                         time.sleep(10)  # 增加等待时间
#                         continue
# 
#                     main.last_restart_time = current_time
#                     wx = initialize_wx_listener()
#                     if wx:
#                         listener_thread = threading.Thread(target=message_listener)
#                         listener_thread.daemon = True
#                         listener_thread.start()
#                         print_status("重新连接成功", "success", "CHECK")
#                         time.sleep(10)  # 添加短暂延迟，确保线程正常启动
#                     else:
#                         print_status("重新连接失败，将在20秒后重试", "warning", "WARNING")
#                         time.sleep(20)
#                 except Exception as e:
#                     print_status(f"重新连接失败: {str(e)}", "error", "CROSS")
#                     time.sleep(10)  # 失败后等待更长时间
# 
#     # except Exception as e:
#         print_status(f"主程序异常: {str(e)}", "error", "ERROR")
#         logger.error(f"主程序异常: {str(e)}", exc_info=True)  # 添加详细日志记录
#     # finally:
#     #     # 清理资源
#     #     if countdown_timer:
#     #         countdown_timer.cancel()
#     # 
#     #     # 设置事件以停止线程
#     #     stop_event.set()
#     # 
#     #     # 关闭监听线程
#     #     if listener_thread and listener_thread.is_alive():
#     #         print_status("正在关闭监听线程...", "info", "SYNC")
#     #         listener_thread.join(timeout=2)
#     #         if listener_thread.is_alive():
#     #             print_status("监听线程未能正常关闭", "warning", "WARNING")
#     # 
#     #     print_status("正在关闭系统...", "warning", "STOP")
#     #     print_status("系统已退出", "info", "BYE")
#     #     print("\n")



#
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_status("用户终止程序", "warning", "STOP")
        print_status("感谢使用，再见！", "info", "BYE")
        print("\n")
    except Exception as e:
        print_status(f"程序异常退出 {str(e)}", "error", "ERROR")

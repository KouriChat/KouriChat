import logging
import random
from datetime import datetime, timedelta
import threading
import time
import os
import shutil
from src.utils.console import print_status

# 率先初始化网络适配器以覆盖所有网络库
try:
    from src.autoupdate.core.manager import initialize_system
    initialize_system()
    print_status("网络适配器初始化成功", "success", "CHECK")
except Exception as e:
    print_status(f"网络适配器初始化失败: {str(e)}", "error", "CROSS")

# 导入其余模块
from data.config import config, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL, MAX_TOKEN, TEMPERATURE, MAX_GROUPS
from wxauto import WeChat
import re
from src.handlers.emoji import EmojiHandler
from src.handlers.image import ImageHandler
from src.handlers.message import MessageHandler
from src.services.ai.llm_service import LLMService
from src.services.ai.image_recognition_service import ImageRecognitionService
from modules.memory.memory_service import MemoryService
from modules.memory.content_generator import ContentGenerator
from src.utils.logger import LoggerConfig
from colorama import init, Style
from src.AutoTasker.autoTasker import AutoTasker
from src.handlers.autosend import AutoSendHandler
import queue
from collections import defaultdict

# 创建一个事件对象来控制线程的终止
stop_event = threading.Event()

# 获取项目根目录
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 检查并初始化配置文件
config_path = os.path.join(root_dir, 'src', 'config', 'config.json')
config_template_path = os.path.join(root_dir, 'src', 'config', 'config.json.template')

if not os.path.exists(config_path) and os.path.exists(config_template_path):
    logger = logging.getLogger('main')
    logger.info("配置文件不存在，正在从模板创建...")
    shutil.copy2(config_template_path, config_path)
    logger.info(f"已从模板创建配置文件: {config_path}")

# 初始化colorama
init()

# 全局变量
logger = None
listen_list = []

def initialize_logging():
    """初始化日志系统"""
    global logger, listen_list

    # 清除所有现有日志处理器
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logger_config = LoggerConfig(root_dir)
    logger = logger_config.setup_logger('main')
    listen_list = config.user.listen_list
    
    # 确保autoupdate模块的日志级别设置为DEBUG
    logging.getLogger("autoupdate").setLevel(logging.DEBUG)
    logging.getLogger("autoupdate.core").setLevel(logging.DEBUG)
    logging.getLogger("autoupdate.interceptor").setLevel(logging.DEBUG)
    logging.getLogger("autoupdate.network_optimizer").setLevel(logging.DEBUG)

# 消息队列接受消息时间间隔
wait = 1

# 添加消息队列用于分发
private_message_queue = queue.Queue()
group_message_queue = queue.Queue()

class PrivateChatBot:
    """专门处理私聊的机器人"""
    def __init__(self, message_handler, image_recognition_service, auto_sender, emoji_handler):
        self.message_handler = message_handler
        self.image_recognition_service = image_recognition_service
        self.auto_sender = auto_sender
        self.emoji_handler = emoji_handler
        self.wx = WeChat()
        self.robot_name = self.wx.A_MyIcon.Name
        logger.info(f"私聊机器人初始化完成 - 机器人名称: {self.robot_name}")
        
        # 私聊始终使用默认人设
        from data.config import config
        default_avatar_path = config.behavior.context.avatar_dir
        self.current_avatar = os.path.basename(default_avatar_path)
        logger.info(f"私聊机器人使用默认人设: {self.current_avatar}")

    def handle_private_message(self, msg, chat_name):
        """处理私聊消息"""
        try:
            username = msg.sender
            content = getattr(msg, 'content', None) or getattr(msg, 'text', None)

            # 重置倒计时
            self.auto_sender.start_countdown()

            logger.info(f"[私聊] 收到消息 - 来自: {username}")
            logger.debug(f"[私聊] 消息内容: {content}")

            img_path = None
            is_emoji = False
            is_image_recognition = False

            if content and content.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                img_path = content
                is_emoji = False
                content = None

            # 检查动画表情
            if content and "[动画表情]" in content:
                img_path = self.emoji_handler.capture_and_save_screenshot(username)
                is_emoji = True
                content = None

            if img_path:
                recognized_text = self.image_recognition_service.recognize_image(img_path, is_emoji)
                content = recognized_text if content is None else f"{content} {recognized_text}"
                is_image_recognition = True

            # 处理消息
            if content:
                self.message_handler.handle_user_message(
                    content=content,
                    chat_id=chat_name,
                    sender_name=username,
                    username=username,
                    is_group=False,
                    is_image_recognition=is_image_recognition
                )

        except Exception as e:
            logger.error(f"[私聊] 消息处理失败: {str(e)}")

class GroupChatBot:
    """专门处理群聊的机器人"""
    def __init__(self, message_handler_class, base_config, auto_sender, emoji_handler, image_recognition_service):
        # 为群聊创建独立的消息处理器实例
        self.message_handlers = {}  # 为每个群聊维护独立的处理器
        self.message_handler_class = message_handler_class
        self.base_config = base_config
        self.auto_sender = auto_sender
        self.emoji_handler = emoji_handler
        self.image_recognition_service = image_recognition_service
        self.wx = WeChat()
        self.robot_name = self.wx.A_MyIcon.Name
        logger.info(f"群聊机器人初始化完成 - 机器人名称: {self.robot_name}")

    def get_group_handler(self, group_name, group_config=None):
        """获取或创建群聊专用的消息处理器"""
        if group_name not in self.message_handlers:
            # 为每个群聊创建独立的处理器
            avatar_path = group_config.avatar if group_config and group_config.avatar else self.base_config.behavior.context.avatar_dir
            
            # 读取群聊专用人设内容
            full_avatar_path = os.path.join(root_dir, avatar_path)
            prompt_path = os.path.join(full_avatar_path, "avatar.md")
            group_prompt_content = ""
            
            if os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as file:
                    group_prompt_content = file.read()
            else:
                logger.error(f"群聊人设文件不存在: {prompt_path}")
                group_prompt_content = prompt_content  # 使用默认人设内容作为备选
            
            # 创建群聊专用的处理器实例，直接使用正确的人设内容
            handler = self.message_handler_class(
                root_dir=root_dir,
                api_key=self.base_config.llm.api_key,
                base_url=self.base_config.llm.base_url,
                model=self.base_config.llm.model,
                max_token=self.base_config.llm.max_tokens,
                temperature=self.base_config.llm.temperature,
                max_groups=self.base_config.behavior.context.max_groups,
                robot_name=self.robot_name,
                prompt_content=group_prompt_content,  # 使用正确的群聊人设内容
                image_handler=image_handler,
                emoji_handler=self.emoji_handler,
                memory_service=memory_service,
                content_generator=content_generator
            )
            
            # 手动设置群聊专用属性（避免初始化时使用全局配置）
            handler.current_avatar = os.path.basename(full_avatar_path)
            handler.avatar_real_names = handler._extract_avatar_names(full_avatar_path)
            
            self.message_handlers[group_name] = handler
            logger.info(f"[群聊] 为群聊 '{group_name}' 创建专用处理器，使用人设: {handler.current_avatar}, 识别名字: {handler.avatar_real_names}")
        
        return self.message_handlers[group_name]

    def handle_group_message(self, msg, group_name, group_config=None):
        """处理群聊消息"""
        try:
            username = msg.sender
            content = getattr(msg, 'content', None) or getattr(msg, 'text', None)

            logger.info(f"[群聊] 收到消息 - 群聊: {group_name}, 发送者: {username}")
            logger.debug(f"[群聊] 消息内容: {content}")

            # 获取群聊专用的处理器
            handler = self.get_group_handler(group_name, group_config)

            img_path = None
            is_emoji = False
            is_image_recognition = False

            # 处理群聊@消息
            if self.robot_name and content:
                content = re.sub(f'@{self.robot_name}\u2005', '', content).strip()

            if content and content.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                img_path = content
                is_emoji = False
                content = None

            # 检查动画表情
            if content and "[动画表情]" in content:
                img_path = self.emoji_handler.capture_and_save_screenshot(username)
                is_emoji = True
                content = None

            if img_path:
                recognized_text = self.image_recognition_service.recognize_image(img_path, is_emoji)
                content = recognized_text if content is None else f"{content} {recognized_text}"
                is_image_recognition = True

            # 处理消息
            if content:
                handler.handle_user_message(
                    content=content,
                    chat_id=group_name,
                    sender_name=username,
                    username=username,
                    is_group=True,
                    is_image_recognition=is_image_recognition
                )

        except Exception as e:
            logger.error(f"[群聊] 消息处理失败: {str(e)}")

def private_message_processor():
    """私聊消息处理线程"""
    logger.info("私聊消息处理线程启动")
    
    while not stop_event.is_set():
        try:
            # 从队列获取私聊消息
            msg_data = private_message_queue.get(timeout=1)
            if msg_data is None:  # 退出信号
                break
                
            msg, chat_name = msg_data
            private_chat_bot.handle_private_message(msg, chat_name)
            private_message_queue.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"私聊消息处理线程出错: {str(e)}")

def group_message_processor():
    """群聊消息处理线程"""
    logger.info("群聊消息处理线程启动")
    
    while not stop_event.is_set():
        try:
            # 从队列获取群聊消息
            msg_data = group_message_queue.get(timeout=1)
            if msg_data is None:  # 退出信号
                break
                
            msg, group_name, group_config = msg_data
            group_chat_bot.handle_group_message(msg, group_name, group_config)
            group_message_queue.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"群聊消息处理线程出错: {str(e)}")

# 全局变量
prompt_content = ""
emoji_handler = None
image_handler = None
memory_service = None
content_generator = None
message_handler = None
image_recognition_service = None
auto_sender = None
private_chat_bot = None
group_chat_bot = None
ROBOT_WX_NAME = ""
processed_messages = set()
last_processed_content = {}

def initialize_services():
    """初始化服务实例"""
    global prompt_content, emoji_handler, image_handler, memory_service, content_generator
    global message_handler, image_recognition_service, auto_sender, private_chat_bot, group_chat_bot, ROBOT_WX_NAME

    # 尝试获取热更新模块状态信息以确认其状态
    try:
        from src.autoupdate.core.manager import get_manager
        try:
            status = get_manager().get_status()
            if status:
                print_status(f"热更新模块已就绪", "success", "CHECK")
            else:
                print_status("热更新模块状态异常", "warning", "CROSS")
            
        except Exception as e:
            print_status(f"检查热更新模块状态时出现异常: {e}", "error", "ERROR")
            
    except Exception as e:
        print_status(f"检查热更新模块状态时出现异常: {e}", "error", "ERROR")

    # 读取提示文件
    avatar_dir = os.path.join(root_dir, config.behavior.context.avatar_dir)
    prompt_path = os.path.join(avatar_dir, "avatar.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as file:
            prompt_content = file.read()

        # 处理无法读取文件的情况
    else:
        raise FileNotFoundError(f"avatar.md 文件不存在: {prompt_path}")

    # 创建服务实例
    emoji_handler = EmojiHandler(root_dir)
    image_handler = ImageHandler(
        root_dir=root_dir,
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        image_model=config.media.image_generation.model
    )
    memory_service = MemoryService(
        root_dir=root_dir,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        model=MODEL,
        max_token=MAX_TOKEN,
        temperature=TEMPERATURE,
        max_groups=MAX_GROUPS
    )

    content_generator = ContentGenerator(
        root_dir=root_dir,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        model=MODEL,
        max_token=MAX_TOKEN,
        temperature=TEMPERATURE
    )
    # 创建图像识别服务
    image_recognition_service = ImageRecognitionService(
        api_key=config.media.image_recognition.api_key,
        base_url=config.media.image_recognition.base_url,
        temperature=config.media.image_recognition.temperature,
        model=config.media.image_recognition.model
    )

    # 获取机器人名称
    try:
        wx = WeChat()
        ROBOT_WX_NAME = wx.A_MyIcon.Name  # 使用Name属性而非方法
        logger.info(f"获取到机器人名称: {ROBOT_WX_NAME}")
    except Exception as e:
        logger.warning(f"获取机器人名称失败: {str(e)}")
        ROBOT_WX_NAME = ""

    # 创建消息处理器
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
        memory_service=memory_service,  # 使用新的记忆服务
        content_generator=content_generator  # 直接传递内容生成器实例
    )

    # 创建主动消息处理器
    auto_sender = AutoSendHandler(message_handler, config, listen_list)

    # 创建并行聊天机器人实例 
    private_chat_bot = PrivateChatBot(message_handler, image_recognition_service, auto_sender, emoji_handler)
    group_chat_bot = GroupChatBot(MessageHandler, config, auto_sender, emoji_handler, image_recognition_service)

    # 启动主动消息倒计时
    auto_sender.start_countdown()

def message_dispatcher():
    """消息分发器 - 将消息分发到对应的处理队列"""
    global ROBOT_WX_NAME, logger, wait, processed_messages, last_processed_content

    wx = None
    last_window_check = 0
    check_interval = 600

    logger.info("消息分发器启动")

    while not stop_event.is_set():
        try:
            current_time = time.time()

            if wx is None or (current_time - last_window_check > check_interval):
                wx = WeChat()
                if not wx.GetSessionList():
                    time.sleep(5)
                    continue
                last_window_check = current_time

            msgs = wx.GetListenMessage()
            if not msgs:
                time.sleep(wait)
                continue

            for chat in msgs:
                who = chat.who
                if not who:
                    continue

                one_msgs = msgs.get(chat)
                if not one_msgs:
                    continue

                for msg in one_msgs:
                    try:
                        msg_id = getattr(msg, 'id', None)
                        msgtype = msg.type
                        content = msg.content
                        
                        if msg_id and msg_id in processed_messages:
                            logger.debug(f"跳过已处理的消息ID: {msg_id}")
                            continue
                        if not content:
                            continue
                        if msgtype != 'friend':
                            logger.debug(f"非好友消息，忽略! 消息类型: {msgtype}")
                            continue
                        
                        # 检查消息来源是否在监听列表中
                        if who not in listen_list:
                            logger.debug(f"消息来源不在监听列表中，忽略: {who}")
                            continue
                        
                        if msg_id:
                            processed_messages.add(msg_id)
                        last_processed_content[who] = content            
                            
                        # 接收窗口名跟发送人一样，代表是私聊，否则是群聊
                        if who == msg.sender:
                            # 私聊消息 - 放入私聊队列
                            logger.debug(f"[分发] 私聊消息 -> 私聊队列: {who}")
                            private_message_queue.put((msg, msg.sender))
                        else:
                            # 群聊消息 - 检查触发条件后放入群聊队列
                            trigger_reason = ""
                            should_respond = False
                            group_config = None
                            
                            # 导入配置
                            from data.config import config
                            
                            # 首先检查群聊配置
                            if config and hasattr(config, 'user') and config.user.group_chat_config:
                                for gc_config in config.user.group_chat_config:
                                    if gc_config.group_name == who:  # who 是群聊名称
                                        group_config = gc_config
                                        # 检查群聊配置中的触发词
                                        for trigger in gc_config.triggers:
                                            if trigger and trigger in msg.content:
                                                trigger_reason = f"群聊配置触发词({trigger})"
                                                should_respond = True
                                                break
                                        break
                            
                            # 如果没有找到群聊配置或没有触发，使用默认逻辑
                            if not should_respond:
                                # 检查@机器人名字
                                at_trigger_enabled = True  # 默认启用
                                if group_config is not None:
                                    at_trigger_enabled = group_config.enable_at_trigger
                                
                                if at_trigger_enabled and ROBOT_WX_NAME and bool(re.search(f'@{ROBOT_WX_NAME}\u2005', msg.content)):
                                    trigger_reason = f"被@了机器人名字({ROBOT_WX_NAME})"
                                    should_respond = True
                                # 检查群聊的人设名字（获取当前群聊的专用处理器）
                                elif group_config:
                                    # 临时获取群聊处理器来检查人设名字
                                    temp_handler = group_chat_bot.get_group_handler(who, group_config)
                                    if hasattr(temp_handler, 'avatar_real_names'):
                                        for name in temp_handler.avatar_real_names:
                                            if name and name in msg.content:
                                                trigger_reason = f"提到了群聊人设名字({name})"
                                                should_respond = True
                                                break
                            
                            if should_respond:
                                logger.debug(f"[分发] 群聊消息触发响应 - 原因: {trigger_reason} -> 群聊队列: {who}")
                                group_message_queue.put((msg, who, group_config))
                            else:
                                logger.debug(f"群聊消息未触发响应 - 群聊:{who}, 内容: {content}")
                                
                    except Exception as e:
                        logger.debug(f"分发单条消息失败: {str(e)}")
                        continue

        except Exception as e:
            logger.debug(f"消息分发出错: {str(e)}")
            wx = None
        time.sleep(wait)

def initialize_wx_listener():
    """
    初始化微信监听，包含重试机制
    """
    # 使用全局变量
    global listen_list, logger

    max_retries = 3
    retry_delay = 2  # 秒

    for attempt in range(max_retries):
        try:
            wx = WeChat()
            if not wx.GetSessionList():
                logger.error("未检测到微信会话列表，请确保微信已登录")
                time.sleep(retry_delay)
                continue

            # 循环添加监听对象，设置保存图片和语音消息
            for chat_name in listen_list:
                try:
                    # 先检查会话是否存在
                    if not wx.ChatWith(chat_name):
                        logger.error(f"找不到会话: {chat_name}")
                        continue

                    # 尝试添加监听，设置savepic=True, savevoice=True
                    wx.AddListenChat(who=chat_name, savepic=True, savevoice=True)
                    logger.info(f"成功添加监听: {chat_name}")
                    time.sleep(0.5)  # 添加短暂延迟，避免操作过快
                except Exception as e:
                    logger.error(f"添加监听失败 {chat_name}: {str(e)}")
                    continue

            return wx

        except Exception as e:
            logger.error(f"初始化微信失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise Exception("微信初始化失败，请检查微信是否正常运行")

    return None

def initialize_auto_tasks(message_handler):
    """初始化自动任务系统"""
    print_status("初始化自动任务系统...", "info", "CLOCK")

    try:
        # 导入config变量
        from data.config import config

        # 创建AutoTasker实例
        auto_tasker = AutoTasker(message_handler)
        print_status("创建AutoTasker实例成功", "success", "CHECK")

        # 清空现有任务
        auto_tasker.scheduler.remove_all_jobs()
        print_status("清空现有任务", "info", "CLEAN")

        # 从配置文件读取任务信息
        if hasattr(config, 'behavior') and hasattr(config.behavior, 'schedule_settings'):
            schedule_settings = config.behavior.schedule_settings
            if schedule_settings and schedule_settings.tasks:  # 直接检查 tasks 列表
                tasks = schedule_settings.tasks
                if tasks:
                    print_status(f"从配置文件读取到 {len(tasks)} 个任务", "info", "TASK")
                    tasks_added = 0

                    # 遍历所有任务并添加
                    for task in tasks:
                        try:
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

                    print_status(f"成功添加 {tasks_added}/{len(tasks)} 个任务", "info", "TASK")
                else:
                    print_status("配置文件中没有找到任务", "warning", "WARNING")
        else:
            print_status("未找到任务配置信息", "warning", "WARNING")
            print_status(f"当前 behavior 属性: {dir(config.behavior)}", "info", "INFO")

        return auto_tasker

    except Exception as e:
        print_status(f"初始化自动任务系统失败: {str(e)}", "error", "ERROR")
        logger.error(f"初始化自动任务系统失败: {str(e)}")
        return None

def switch_avatar(new_avatar_name):
    # 使用全局变量
    global emoji_handler, private_chat_bot, group_chat_bot, root_dir

    # 导入config变量
    from data.config import config

    # 更新配置
    config.behavior.context.avatar_dir = f"avatars/{new_avatar_name}"

    # 重新初始化 emoji_handler
    emoji_handler = EmojiHandler(root_dir)

    # 更新私聊和群聊机器人中的 emoji_handler
    if private_chat_bot:
        private_chat_bot.emoji_handler = emoji_handler
        private_chat_bot.message_handler.emoji_handler = emoji_handler
    
    if group_chat_bot:
        group_chat_bot.emoji_handler = emoji_handler
        # 更新所有群聊的emoji_handler
        for group_handler in group_chat_bot.message_handlers.values():
            group_handler.emoji_handler = emoji_handler

def main():
    # 初始化变量
    dispatcher_thread = None
    private_thread = None
    group_thread = None

    try:
        # 初始化日志系统
        initialize_logging()

        # 初始化服务实例
        initialize_services()

        # 设置wxauto日志路径
        automation_log_dir = os.path.join(root_dir, "logs", "automation")
        if not os.path.exists(automation_log_dir):
            os.makedirs(automation_log_dir)
        os.environ["WXAUTO_LOG_PATH"] = os.path.join(automation_log_dir, "AutomationLog.txt")

        # 初始化微信监听
        print_status("初始化微信监听...", "info", "BOT")
        wx = initialize_wx_listener()
        if not wx:
            print_status("微信初始化失败，请确保微信已登录并保持在前台运行!", "error", "CROSS")
            return
        print_status("微信监听初始化完成", "success", "CHECK")

        # 验证记忆目录
        print_status("验证角色记忆存储路径...", "info", "FILE")
        avatar_dir = os.path.join(root_dir, config.behavior.context.avatar_dir)
        avatar_name = os.path.basename(avatar_dir)
        memory_dir = os.path.join(avatar_dir, "memory")
        if not os.path.exists(memory_dir):
            os.makedirs(memory_dir)
            print_status(f"创建角色记忆目录: {memory_dir}", "success", "CHECK")

        # 初始化记忆文件 - 为每个监听用户创建独立的记忆文件
        print_status("初始化记忆文件...", "info", "FILE")

        # 为每个监听的用户创建独立记忆
        for user_name in listen_list:
            print_status(f"为用户 '{user_name}' 创建独立记忆...", "info", "USER")
            # 使用用户名作为用户ID
            memory_service.initialize_memory_files(avatar_name, user_id=user_name)
            print_status(f"用户 '{user_name}' 记忆初始化完成", "success", "CHECK")

        avatar_dir = os.path.join(root_dir, config.behavior.context.avatar_dir)
        prompt_path = os.path.join(avatar_dir, "avatar.md")
        if not os.path.exists(prompt_path):
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write("# 核心人格\n[默认内容]")
            print_status(f"创建人设提示文件", "warning", "WARNING")
        # 启动并行消息处理系统
        print_status("启动并行消息处理系统...", "info", "ANTENNA")
        
        # 启动消息分发线程
        dispatcher_thread = threading.Thread(target=message_dispatcher, name="MessageDispatcher")
        dispatcher_thread.daemon = True
        
        # 启动私聊处理线程
        private_thread = threading.Thread(target=private_message_processor, name="PrivateProcessor")
        private_thread.daemon = True
        
        # 启动群聊处理线程
        group_thread = threading.Thread(target=group_message_processor, name="GroupProcessor")
        group_thread.daemon = True
        
        # 启动所有线程
        dispatcher_thread.start()
        private_thread.start()
        group_thread.start()
        
        print_status("并行消息处理系统已启动", "success", "CHECK")
        print_status("  ├─ 消息分发器线程", "info", "ANTENNA")
        print_status("  ├─ 私聊处理器线程", "info", "USER")
        print_status("  └─ 群聊处理器线程", "info", "USERS")

        # 初始化主动消息系统
        print_status("初始化主动消息系统...", "info", "CLOCK")
        print_status("主动消息系统已启动", "success", "CHECK")

        print("-" * 50)
        print_status("系统初始化完成", "success", "STAR_2")
        print("=" * 50)

        # 初始化自动任务系统
        auto_tasker = initialize_auto_tasks(message_handler)
        if not auto_tasker:
            print_status("自动任务系统初始化失败", "error", "ERROR")
            return

        # 主循环 - 监控并行处理线程状态
        while True:
            time.sleep(1)
            
            # 检查关键线程状态
            threads_status = [
                ("消息分发器", dispatcher_thread),
                ("私聊处理器", private_thread),
                ("群聊处理器", group_thread)
            ]
            
            dead_threads = []
            for thread_name, thread in threads_status:
                if not thread.is_alive():
                    dead_threads.append(thread_name)
            
            if dead_threads:
                print_status(f"检测到线程异常: {', '.join(dead_threads)}", "warning", "WARNING")
                # 这里可以添加重启逻辑，暂时先记录
                time.sleep(5)

    except Exception as e:
        print_status(f"主程序异常: {str(e)}", "error", "ERROR")
        logger.error(f"主程序异常: {str(e)}", exc_info=True)
    finally:
        # 清理资源
        if 'auto_sender' in locals():
            auto_sender.stop()

        # 设置事件以停止线程
        stop_event.set()

        # 向队列发送退出信号
        try:
            private_message_queue.put(None)
            group_message_queue.put(None)
        except:
            pass

        # 等待所有处理线程结束
        threads_to_wait = [
            ("消息分发器", dispatcher_thread),
            ("私聊处理器", private_thread),
            ("群聊处理器", group_thread)
        ]
        
        for thread_name, thread in threads_to_wait:
            if thread and thread.is_alive():
                print_status(f"正在关闭{thread_name}线程...", "info", "SYNC")
                thread.join(timeout=3)
                if thread.is_alive():
                    print_status(f"{thread_name}线程未能正常关闭", "warning", "WARNING")

        print_status("正在关闭系统...", "warning", "STOP")
        print_status("系统已退出", "info", "BYE")
        print("\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_status("用户终止程序", "warning", "STOP")
        print_status("感谢使用，再见！", "info", "BYE")
        print("\n")
    except Exception as e:
        print_status(f"程序异常退出: {str(e)}", "error", "ERROR")

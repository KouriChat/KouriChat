import base64
import requests
import logging
import random
from datetime import datetime
import threading
import time
import os
import shutil
from services.database import Session, ChatMessage
from config.settings import (
    DEEPSEEK_API_KEY, MAX_TOKEN, TEMPERATURE, MODEL, DEEPSEEK_BASE_URL, LISTEN_LIST,
    IMAGE_MODEL, TEMP_IMAGE_DIR, MAX_GROUPS, PROMPT_NAME, EMOJI_DIR, TTS_API_URL, VOICE_DIR,
    MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_TEMPERATURE,
    AUTO_MESSAGE, MIN_COUNTDOWN_HOURS, MAX_COUNTDOWN_HOURS,
    QUIET_TIME_START, QUIET_TIME_END
)
from wxauto import WeChat
import re
import pyautogui
from handlers.emoji import EmojiHandler
from handlers.image import ImageHandler
from handlers.message import MessageHandler
from handlers.voice import VoiceHandler
from services.ai.moonshot import MoonShotAI
from services.ai.deepseek import DeepSeekAI
from utils.cleanup import cleanup_pycache, CleanupUtils
from utils.logger import LoggerConfig
from colorama import init, Fore, Style

# 获取项目根目录
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logger_config = LoggerConfig(root_dir)
logger = logger_config.setup_logger('main')
listen_list = LISTEN_LIST
queue_lock = threading.Lock()  # 队列访问锁
user_queues = {}  # 用户消息队列管理
chat_contexts = {}  # 存储上下文
# 初始化colorama
init()

class ChatBot:
    def __init__(self, message_handler, moonshot_ai):
        self.message_handler = message_handler
        self.moonshot_ai = moonshot_ai
        self.user_queues = {}  # 将user_queues移到类的实例变量
        self.queue_lock = threading.Lock()  # 将queue_lock也移到类的实例变量
        
        # 获取机器人的微信名称
        self.wx = WeChat()
        self.robot_name = self.wx.A_MyIcon.Name  # 移除括号，直接访问Name属性
        logger.info(f"机器人名称: {self.robot_name}")

    def process_user_messages(self, chat_id):
        """处理用户消息队列"""
        try:
            logger.info(f"开始处理消息队列 - 聊天ID: {chat_id}")
            
            with self.queue_lock:
                if chat_id not in self.user_queues:
                    logger.warning(f"未找到消息队列: {chat_id}")
                    return
                user_data = self.user_queues.pop(chat_id)
                messages = user_data['messages']
                sender_name = user_data['sender_name']
                username = user_data['username']
                is_group = user_data.get('is_group', False)
                
            logger.info(f"队列信息 - 发送者: {sender_name}, 消息数: {len(messages)}, 是否群聊: {is_group}")
            logger.info(f"消息内容: {messages}")

            # 处理消息
            self.message_handler.add_to_queue(
                chat_id=chat_id,
                content='\n'.join(messages),
                sender_name=sender_name,
                username=username,
                is_group=is_group
            )
            logger.info(f"消息已添加到处理队列 - 聊天ID: {chat_id}")
            
        except Exception as e:
            logger.error(f"处理消息队列失败: {str(e)}", exc_info=True)

    def handle_wxauto_message(self, msg, chatName, is_group=False):
        try:
            username = msg.sender
            content = getattr(msg, 'content', None) or getattr(msg, 'text', None)
            
            # 添加详细日志
            logger.info(f"收到消息 - 来源: {chatName}, 发送者: {username}, 是否群聊: {is_group}")
            logger.info(f"原始消息内容: {content}")
            
            img_path = None
            is_emoji = False
            
            # 如果是群聊@消息，移除@机器人的部分
            if is_group and self.robot_name and content:
                logger.info(f"处理群聊@消息 - 机器人名称: {self.robot_name}")
                original_content = content
                content = re.sub(f'@{self.robot_name}\u2005', '', content).strip()
                logger.info(f"移除@后的消息内容: {content}")
                if original_content == content:
                    logger.info("未检测到@机器人，跳过处理")
                    return
            
            if content and content.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                logger.info(f"检测到图片消息: {content}")
                img_path = content
                is_emoji = False
                content = None

            # 检查是否是"[动画表情]"
            if content and "[动画表情]" in content:
                logger.info("检测到动画表情")
                img_path = emoji_handler.capture_and_save_screenshot(username)
                logger.info(f"表情截图保存路径: {img_path}")
                is_emoji = True
                content = None

            if img_path:
                logger.info(f"开始处理图片/表情 - 路径: {img_path}, 是否表情: {is_emoji}")
                recognized_text = self.moonshot_ai.recognize_image(img_path, is_emoji)
                logger.info(f"图片/表情识别结果: {recognized_text}")
                content = recognized_text if content is None else f"{content} {recognized_text}"

            if content:
                logger.info(f"处理文本消息 - 发送者: {username}, 内容: {content}")
                sender_name = username

            sender_name = username
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            time_aware_content = f"[{current_time}] {content}"
            logger.info(f"格式化后的消息: {time_aware_content}")

            with self.queue_lock:
                if chatName not in self.user_queues:
                    logger.info(f"创建新的消息队列 - 聊天ID: {chatName}")
                    self.user_queues[chatName] = {
                        'timer': threading.Timer(5.0, self.process_user_messages, args=[chatName]),
                        'messages': [time_aware_content],
                        'sender_name': sender_name,
                        'username': username,
                        'is_group': is_group
                    }
                    self.user_queues[chatName]['timer'].start()
                    logger.info(f"消息队列创建完成 - 是否群聊: {is_group}, 发送者: {sender_name}")
                else:
                    logger.info(f"更新现有消息队列 - 聊天ID: {chatName}")
                    self.user_queues[chatName]['timer'].cancel()
                    self.user_queues[chatName]['messages'].append(time_aware_content)
                    self.user_queues[chatName]['timer'] = threading.Timer(5.0, self.process_user_messages, args=[chatName])
                    self.user_queues[chatName]['timer'].start()
                    logger.info("消息队列更新完成")

        except Exception as e:
            logger.error(f"消息处理失败: {str(e)}", exc_info=True)

# 读取提示文件
file_path = os.path.join(root_dir, "data", "avatars", "ATRI", "ATRI.md")
with open(file_path, "r", encoding="utf-8") as file:
    prompt_content = file.read()

# 创建全局实例
emoji_handler = EmojiHandler(root_dir)
image_handler = ImageHandler(
    root_dir=root_dir,
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    image_model=IMAGE_MODEL
)
voice_handler = VoiceHandler(
    root_dir=root_dir,
    tts_api_url=TTS_API_URL
)
moonshot_ai = MoonShotAI(
    api_key=MOONSHOT_API_KEY,
    base_url=MOONSHOT_BASE_URL,
    temperature=MOONSHOT_TEMPERATURE
)

# 获取机器人名称
wx = WeChat()
ROBOT_WX_NAME = wx.A_MyIcon.Name
# logger.info(f"获取到机器人名称: {ROBOT_WX_NAME}")

message_handler = MessageHandler(
    root_dir=root_dir,
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    model=MODEL,
    max_token=MAX_TOKEN,
    temperature=TEMPERATURE,
    max_groups=MAX_GROUPS,
    robot_name=ROBOT_WX_NAME,  # 使用动态获取的机器人名称
    prompt_content=prompt_content,
    image_handler=image_handler,
    emoji_handler=emoji_handler,
    voice_handler=voice_handler
)
chat_bot = ChatBot(message_handler, moonshot_ai)

# 设置监听列表
listen_list = LISTEN_LIST

# 循环添加监听对象
for i in listen_list:
    wx.AddListenChat(who=i, savepic=True)

# 消息队列接受消息时间间隔
wait = 1

# 全局变量
last_chat_time = None
countdown_timer = None
is_countdown_running = False

# 创建全局实例
cleanup_utils = CleanupUtils(root_dir)

def update_last_chat_time():
    """更新最后一次聊天时间"""
    global last_chat_time
    last_chat_time = datetime.now()
    logger.info(f"更新最后聊天时间: {last_chat_time}")

def is_quiet_time() -> bool:
    """检查当前是否在安静时间段内"""
    try:
        current_time = datetime.now().time()
        quiet_start = datetime.strptime(QUIET_TIME_START, "%H:%M").time()
        quiet_end = datetime.strptime(QUIET_TIME_END, "%H:%M").time()
        
        if quiet_start <= quiet_end:
            # 如果安静时间不跨天
            return quiet_start <= current_time <= quiet_end
        else:
            # 如果安静时间跨天（比如22:00到次日08:00）
            return current_time >= quiet_start or current_time <= quiet_end
    except Exception as e:
        logger.error(f"检查安静时间出错: {str(e)}")
        return False  # 出错时默认不在安静时间

def get_random_countdown_time():
    """获取随机倒计时时间"""
    return random.randint(
        MIN_COUNTDOWN_HOURS * 3600,
        MAX_COUNTDOWN_HOURS * 3600
    )

def auto_send_message():
    """自动发送消息"""
    if is_quiet_time():
        logger.info("当前处于安静时间，跳过自动发送消息")
        start_countdown()
        return
        
    if listen_list:
        user_id = random.choice(listen_list)
        logger.info(f"自动发送消息到 {user_id}: {AUTO_MESSAGE}")
        try:
            message_handler.add_to_queue(
                chat_id=user_id,
                content=AUTO_MESSAGE,
                sender_name="System",
                username="System",
                is_group=False
            )
            start_countdown()
        except Exception as e:
            logger.error(f"自动发送消息失败: {str(e)}")
            start_countdown()
    else:
        logger.error("没有可用的聊天对象")
        start_countdown()

def start_countdown():
    """开始新的倒计时"""
    global countdown_timer, is_countdown_running
    
    if countdown_timer:
        countdown_timer.cancel()
    
    countdown_seconds = get_random_countdown_time()
    logger.info(f"开始新的倒计时: {countdown_seconds/3600:.2f}小时")
    
    countdown_timer = threading.Timer(countdown_seconds, auto_send_message)
    countdown_timer.daemon = True  # 设置为守护线程
    countdown_timer.start()
    is_countdown_running = True

def message_listener():
    wx = None
    last_window_check = 0
    check_interval = 600
    
    while True:
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
                        msgtype = msg.type
                        content = msg.content
                        if not content:
                            continue
                        if msgtype != 'friend':
                            logger.debug(f"非好友消息，忽略! 消息类型: {msgtype}")
                            continue  
                            # 接收窗口名跟发送人一样，代表是私聊，否则是群聊
                        if who == msg.sender:

                            chat_bot.handle_wxauto_message(msg, msg.sender) # 处理私聊信息
                        elif ROBOT_WX_NAME != '' and bool(re.search(f'@{ROBOT_WX_NAME}\u2005', msg.content)): 
                            # 修改：在群聊被@时，传入群聊ID(who)作为回复目标
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
    max_retries = 3
    retry_delay = 2  # 秒
    
    for attempt in range(max_retries):
        try:
            wx = WeChat()
            if not wx.GetSessionList():
                logger.error("未检测到微信会话列表，请确保微信已登录")
                time.sleep(retry_delay)
                continue
                
            # 循环添加监听对象，修改savepic参数为False
            for chat_name in listen_list:
                try:
                    # 先检查会话是否存在
                    if not wx.ChatWith(chat_name):
                        logger.error(f"找不到会话: {chat_name}")
                        continue
                        
                    # 尝试添加监听，设置savepic=False
                    wx.AddListenChat(who=chat_name, savepic=True)
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

def print_banner():
    """打印启动横幅"""
    banner = f"""
{Fore.CYAN}
╔══════════════════════════════════════════════╗
║          My Dream Moments - AI Chat          ║
║            Created with ❤️  by umaru          ║
╚══════════════════════════════════════════════╝
{Style.RESET_ALL}"""
    print(banner)

def print_status(message: str, status: str = "info", emoji: str = ""):
    """打印状态信息"""
    colors = {
        "success": Fore.GREEN,
        "info": Fore.BLUE,
        "warning": Fore.YELLOW,
        "error": Fore.RED
    }
    color = colors.get(status, Fore.WHITE)
    print(f"{color}{emoji} {message}{Style.RESET_ALL}")

def main():
    listener_thread = None  # 在函数开始时定义线程变量
    try:
        print_banner()
        print_status("系统启动中...", "info", "🚀")
        print("-" * 50)
        
        # 清理缓存
        print_status("清理系统缓存...", "info", "🧹")
        cleanup_pycache()
        logger_config.cleanup_old_logs()
        cleanup_utils.cleanup_all()
        image_handler.cleanup_temp_dir()
        voice_handler.cleanup_voice_dir()
        print_status("缓存清理完成", "success", "✨")
        
        # 检查系统目录
        print_status("检查系统目录...", "info", "📂")
        required_dirs = ['data', 'logs', 'src/config']
        for dir_name in required_dirs:
            dir_path = os.path.join(root_dir, dir_name)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                print_status(f"创建目录: {dir_name}", "info", "📁")
        print_status("目录检查完成", "success", "✅")
        
        # 初始化微信监听
        print_status("初始化微信监听...", "info", "🤖")
        wx = initialize_wx_listener()
        if not wx:
            print_status("微信初始化失败，请确保微信已登录并保持在前台运行!", "error", "❌")
            return
        print_status("微信监听初始化完成", "success", "✅")

        # 启动消息监听线程
        print_status("启动消息监听线程...", "info", "📡")
        listener_thread = threading.Thread(target=message_listener)
        listener_thread.daemon = True  # 确保线程是守护线程
        listener_thread.start()
        print_status("消息监听已启动", "success", "✅")

        # 启动自动消息
        print_status("启动自动消息系统...", "info", "⏰")
        start_countdown()
        print_status("自动消息系统已启动", "success", "✅")
        
        print("-" * 50)
        print_status("系统初始化完成", "success", "🌟")
        print("=" * 50)
        
        # 主循环
        while True:
            time.sleep(1)
            if not listener_thread.is_alive():
                print_status("监听线程已断开，尝试重新连接...", "warning", "🔄")
                try:
                    wx = initialize_wx_listener()
                    if wx:
                        listener_thread = threading.Thread(target=message_listener)
                        listener_thread.daemon = True
                        listener_thread.start()
                        print_status("重新连接成功", "success", "✅")
                except Exception as e:
                    print_status(f"重新连接失败: {str(e)}", "error", "❌")
                    time.sleep(5)

    except Exception as e:
        print_status(f"主程序异常: {str(e)}", "error", "💥")
    finally:
        # 清理资源
        if countdown_timer:
            countdown_timer.cancel()
        
        # 关闭监听线程
        if listener_thread and listener_thread.is_alive():
            # 设置一个事件或标志来通知线程退出
            print_status("正在关闭监听线程...", "info", "🔄")
            # 等待线程结束，但设置超时时间避免无限等待
            listener_thread.join(timeout=2)
            if listener_thread.is_alive():
                print_status("监听线程未能正常关闭", "warning", "⚠️")
        
        print_status("正在关闭系统...", "warning", "🛑")
        print_status("系统已退出", "info", "👋")
        print("\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_status("用户终止程序", "warning", "🛑")
        print_status("感谢使用，再见！", "info", "👋")
        print("\n")
    except Exception as e:
        print_status(f"程序异常退出: {str(e)}", "error", "💥")

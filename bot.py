import base64
import requests
import logging
import random
from datetime import datetime
import threading
import time
import os
import shutil
from database import Session, ChatMessage
from config import (
    DEEPSEEK_API_KEY, MAX_TOKEN, ROBOT_WX_NAME, TEMPERATURE, MODEL, DEEPSEEK_BASE_URL, LISTEN_LIST,
    IMAGE_MODEL, TEMP_IMAGE_DIR, MAX_GROUPS, PROMPT_NAME, EMOJI_DIR, TTS_API_URL, VOICE_DIR,
    MOONSHOT_API_KEY, MOONSHOT_BASE_URL, MOONSHOT_TEMPERATURE,
    AUTO_MESSAGE, MIN_COUNTDOWN_HOURS, MAX_COUNTDOWN_HOURS,
    QUIET_TIME_START, QUIET_TIME_END
)
from wxauto import WeChat
from openai import OpenAI
import requests
from typing import Optional
import re
import pyautogui

# 获取微信窗口对象
wx = WeChat()

# 设置监听列表
listen_list = LISTEN_LIST

# 循环添加监听对象，修改savepic参数全要为True（要保存图片，才能识别图片）
for i in listen_list:
    wx.AddListenChat(who=i, savepic=True)

# 修改等待时间为更短的间隔（消息队列接受消息时间间隔）
wait = 1  # 要想接受更多的消息就把时间改长

# 初始化OpenAI客户端（替换原有requests方式）
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    default_headers={"Content-Type": "application/json"}  # 添加默认请求头
)

# 获取程序根目录
root_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(root_dir, "prompts", PROMPT_NAME)

# 新增全局变量
user_queues = {}  # 用户消息队列管理
queue_lock = threading.Lock()  # 队列访问锁
chat_contexts = {}  # 存储上下文

# 添加新的全局变量
last_chat_time = None  # 最后一次聊天时间
countdown_timer = None  # 倒计时定时器
is_countdown_running = False  # 倒计时运行状态标志

# 读取文件内容到变量
with open(file_path, "r", encoding="utf-8") as file:
    prompt_content = file.read()


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加图像生成相关常量
IMAGE_API_URL = f"{DEEPSEEK_BASE_URL}/images/generations"  # 需要在config.py中添加基础URL

# 添加临时目录初始化
temp_dir = os.path.join(root_dir, TEMP_IMAGE_DIR)
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)
#保存聊天记录到数据库
def save_message(sender_id, sender_name, message, reply):
    # 保存聊天记录到数据库
    try:
        session = Session()
        chat_message = ChatMessage(
            sender_id=sender_id,
            sender_name=sender_name,
            message=message,
            reply=reply
        )
        session.add(chat_message)
        session.commit()
        session.close()
    except Exception as e:
        print(f"保存消息失败: {str(e)}")
def master_cofig(message: str) -> tuple[bool, str]:
    """
    判断是否为主人配置命令,并返回相应回复
    
    Args:
        message: 用户发送的消息
        
    Returns:
        tuple: (是否为配置命令, 回复消息)
    """
    global prompt_content

    # 主人配置关键词与对应回复
    master_commands = {
        "/help": """1. 切换角色 - 使用/prompt xxx.md来切换AI角色"""
    }
    
    # 检查是否是prompt切换命令
    if message.startswith("/prompt"):
        try:
            # 获取提示词文件名
            prompt_file = message.split(" ")[1].strip()
            # 拼接完整路径
            prompt_path = os.path.join(root_dir, "prompts", prompt_file)
            
            # 检查文件是否存在
            if not os.path.exists(prompt_path):
                return True, f"提示词文件 {prompt_file} 不存在!"
                
            # 读取新的提示词文件
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_content = f.read()
                
            # 清空所有用户的对话上下文
            chat_contexts.clear()
            
            return True, f"已成功切换到 {prompt_file} 角色设定"
            
        except Exception as e:
            logger.error(f"切换提示词失败: {str(e)}")
            return True, "切换角色失败,请检查命令格式是否正确(/prompt xxx.md)"
    
    # 检查其他命令
    for command, reply in master_commands.items():
        if command in message:
            return True, reply
            
    return False, ""

# 判断是否需要随机图像
def is_random_image_request(message: str) -> bool:
    """检查消息是否为请求图片的模式"""
    # 基础词组
    basic_patterns = [
        r'来个图',
        r'来张图',
        r'来点图',
        r'想看图',
    ]
    
    # 将消息转换为小写以进行不区分大小写的匹配(emm，好像没什么用)
    message = message.lower()
    
    # 1. 检查基础模式
    if any(pattern in message for pattern in basic_patterns):
        return True
        
    # 2. 检查更复杂的模式
    complex_patterns = [
        r'来[张个幅]图',
        r'发[张个幅]图',
        r'看[张个幅]图',
    ]
    
    if any(re.search(pattern, message) for pattern in complex_patterns):
        return True
        
    return False
# 获取随机图片(这个是壁纸不是表情包)
def get_random_image() -> Optional[str]:
    """从API获取随机图片并保存"""
    try:
        # 使用配置文件中定义的临时目录
        temp_dir = os.path.join(root_dir, TEMP_IMAGE_DIR)
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # 获取图片链接
        response = requests.get('https://t.mwm.moe/pc')
        if response.status_code == 200:
            # 生成唯一文件名
            timestamp = int(time.time())
            image_path = os.path.join(temp_dir, f'image_{timestamp}.jpg')
            
            # 保存图片
            with open(image_path, 'wb') as f:
                f.write(response.content)
            
            return image_path
    except Exception as e:
        logger.error(f"获取图片失败: {str(e)}")
    return None
#调用api生成图片
def generate_image(prompt: str) -> Optional[str]:
    """
    调用API生成图片，保存到临时目录并返回路径
    """
    try:
        logger.info(f"开始生成图片，提示词: {prompt}")
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": IMAGE_MODEL,
            "prompt": prompt
        }
        
        response = requests.post(
            f"{DEEPSEEK_BASE_URL}/images/generations",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        
        result = response.json()
        if "data" in result and len(result["data"]) > 0:
            # 下载图片并保存到临时目录
            img_url = result["data"][0]["url"]
            img_response = requests.get(img_url)
            if img_response.status_code == 200:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_path = os.path.join(temp_dir, f"image_{timestamp}.jpg")
                with open(temp_path, "wb") as f:
                    f.write(img_response.content)
                logger.info(f"图片已保存到: {temp_path}")
                return temp_path
        logger.error("API返回的数据中没有图片URL")
        return None
        
    except Exception as e:
        logger.error(f"图像生成失败: {str(e)}")
        return None
#判断是否需要图像生成
def is_image_generation_request(text: str) -> bool:
    """
    判断是否为图像生成请求
    """
    # 基础动词
    draw_verbs = ["画", "绘", "生成", "创建", "做"]
    
    # 图像相关词
    image_nouns = ["图", "图片", "画", "照片", "插画", "像"]
    
    # 数量词
    quantity = ["一下", "一个", "一张", "个", "张", "幅"]
    
    # 组合模式
    patterns = [
        # 直接画xxx模式
        r"画.*[猫狗人物花草山水]",
        r"画.*[一个张只条串份副幅]",
        # 帮我画xxx模式
        r"帮.*画.*",
        r"给.*画.*",
        # 生成xxx图片模式
        r"生成.*图",
        r"创建.*图",
        # 能不能画xxx模式
        r"能.*画.*吗",
        r"可以.*画.*吗",
        # 想要xxx图模式
        r"要.*[张个幅].*图",
        r"想要.*图",
        # 其他常见模式
        r"做[一个张]*.*图",
        r"画画",
        r"画一画",
    ]
    
    # 1. 检查正则表达式模式
    if any(re.search(pattern, text) for pattern in patterns):
        return True
        
    # 2. 检查动词+名词组合
    for verb in draw_verbs:
        for noun in image_nouns:
            if f"{verb}{noun}" in text:
                return True
            # 检查带数量词的组合
            for q in quantity:
                if f"{verb}{q}{noun}" in text:
                    return True
                if f"{verb}{noun}{q}" in text:
                    return True
    
    # 3. 检查特定短语
    special_phrases = [
        "帮我画", "给我画", "帮画", "给画",
        "能画吗", "可以画吗", "会画吗",
        "想要图", "要图", "需要图",
    ]
    
    if any(phrase in text for phrase in special_phrases):
        return True
    
    return False
#表情包选取模块
def is_emoji_request(text: str) -> bool:
    """
    判断是否为表情包请求
    """
    # 直接请求表情包的关键词
    emoji_keywords = ["表情包", "表情", "斗图", "gif", "动图"]
    
    # 情感表达关键词
    emotion_keywords = ["开心", "难过", "生气", "委屈", "高兴", "伤心",
                       "哭", "笑", "怒", "喜", "悲", "乐", "泪", "哈哈",
                       "呜呜", "嘿嘿", "嘻嘻", "哼", "啊啊", "呵呵","可爱"]
    
    # 检查直接请求
    if any(keyword in text.lower() for keyword in emoji_keywords):
        return True
        
    # 检查情感表达
    if any(keyword in text for keyword in emotion_keywords):
        return True
        
    return False
#表情包模块
def get_random_emoji() -> Optional[str]:
    """
    从表情包目录随机获取一个表情包
    """
    try:
        emoji_dir = os.path.join(root_dir, EMOJI_DIR)
        if not os.path.exists(emoji_dir):
            logger.error(f"表情包目录不存在: {emoji_dir}")
            return None
            
        emoji_files = [f for f in os.listdir(emoji_dir) 
                      if f.lower().endswith(('.gif', '.jpg', '.png', '.jpeg'))]
        
        if not emoji_files:
            return None
            
        random_emoji = random.choice(emoji_files)
        return os.path.join(emoji_dir, random_emoji)
    except Exception as e:
        logger.error(f"获取表情包失败: {str(e)}")
        return None
# 获取DeepSeek API回复
def get_deepseek_response(message, user_id):
    try:
         # 首先检查是否为随机图片请求
        if is_random_image_request(message):
            image_path = get_random_image()
            if image_path:
                try:
                    # 发送图片
                    wx.SendFiles(filepath=image_path, who=user_id)
                    # 删除临时图片
                    os.remove(image_path)
                    # 清理wxauto文件
                    cleanup_wxauto_files()
                    return "给主人你找了一张好看的图片哦~"
                except Exception as e:
                    logger.error(f"发送图片失败: {str(e)}")
                    return "抱歉主人，图片发送失败了..."
                finally:
                    try:
                        if os.path.exists(image_path):
                            os.remove(image_path)
                    except Exception as e:
                        logger.error(f"删除临时图片失败: {str(e)}")
        # 检查是否为图像生成请求
        if is_image_generation_request(message):
            image_path = generate_image(message)
            if image_path:
                # 直接使用生成的本地图片路径，不需要再次下载
                return f"[IMAGE]{image_path}[/IMAGE]\n这是按照主人您的要求生成的图片\\(^o^)/~"
            else:
                return "抱歉主人，图片生成失败，请稍后重试。"

        # 文本处理逻辑
        print(f"调用 DeepSeek API - 用户ID: {user_id}, 消息: {message}")
        with queue_lock:
            if user_id not in chat_contexts:
                chat_contexts[user_id] = []

            chat_contexts[user_id].append({"role": "user", "content": message})

            while len(chat_contexts[user_id]) > MAX_GROUPS * 2:
                if len(chat_contexts[user_id]) >= 2:
                    del chat_contexts[user_id][0]
                    del chat_contexts[user_id][0]
                else:
                    del chat_contexts[user_id][0]

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": prompt_content},
                    *chat_contexts[user_id][-MAX_GROUPS * 2:]
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKEN,
                stream=False
            )
        except Exception as api_error:
            logger.error(f"API调用失败: {api_error}")
            return "抱歉主人，我现在有点累，请稍后再试..."

        if not response.choices:
            logger.error("API返回空choices: %s", response)
            return "抱歉主人，服务响应异常，请稍后再试"

        reply = response.choices[0].message.content
        print(f"API响应 - 用户ID: {user_id}")
        print(f"响应内容: {reply}")

        # 清理wxauto文件
        cleanup_wxauto_files()

        # 清理screenshot文件
        clean_up_screenshot ()

        # 更新最后聊天时间
        update_last_chat_time()
        
        with queue_lock:
            chat_contexts[user_id].append({"role": "assistant", "content": reply})
            
        return reply

    except Exception as e:
        logger.error(f"DeepSeek调用失败: {str(e)}", exc_info=True)
        return "抱歉主人，刚刚不小心睡着了..."

#判断是否需要语音
def is_voice_request(text: str) -> bool:
    """
    判断是否为语音请求，减少语音关键词，避免误判
    """
    voice_keywords = ["语音"]
    return any(keyword in text for keyword in voice_keywords)

#语音模块
def generate_voice(text: str) -> Optional[str]:
    """
    调用TTS API生成语音
    """
    try:
        # 确保语音目录存在
        voice_dir = os.path.join(root_dir, VOICE_DIR)
        if not os.path.exists(voice_dir):
            os.makedirs(voice_dir)
            
        # 生成唯一的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        voice_path = os.path.join(voice_dir, f"voice_{timestamp}.wav")
        
        # 调用TTS API
        response = requests.get(f"{TTS_API_URL}?text={text}", stream=True)
        if response.status_code == 200:
            with open(voice_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return voice_path
        else:
            logger.error(f"语音生成失败: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"语音生成失败: {str(e)}")
        return None

def process_user_messages(chat_id):
    with queue_lock:
        if chat_id not in user_queues:
            return
        user_data = user_queues.pop(chat_id)
        messages = user_data['messages']
        sender_name = user_data['sender_name']
        username = user_data['username']
        is_group = user_data.get('is_group', False)  # 获取是否为群聊标记

    # 优化消息合并逻辑，只保留最后5条消息
    messages = messages[-5:]  # 限制处理的消息数量
    merged_message = ' \\ '.join(messages)
    print(f"处理合并消息 ({sender_name}): {merged_message}")

    try:
        # 首先检查是否为语音请求
        if is_voice_request(merged_message):
            reply = get_deepseek_response(merged_message, chat_id)
            if "</think>" in reply:
                reply = reply.split("</think>", 1)[1].strip()
            
            voice_path = generate_voice(reply)
            if voice_path:
                try:
                    wx.SendFiles(filepath=voice_path, who=chat_id)
                    cleanup_wxauto_files()  # 添加清理
                except Exception as e:
                    logger.error(f"发送语音失败: {e}")
                    if is_group:
                        reply = f"@{sender_name} {reply}"
                    wx.SendMsg(msg=reply, who=chat_id)
                finally:
                    try:
                        os.remove(voice_path)
                    except Exception as e:
                        logger.error(f"删除临时语音文件失败: {e}")
            else:
                if is_group:
                    reply = f"@{sender_name} {reply}"
                wx.SendMsg(msg=reply, who=chat_id)
            
            # 异步保存消息记录
            threading.Thread(target=save_message, args=(username, sender_name, merged_message, reply)).start()
            return

        # 检查是否需要发送表情包
        if is_emoji_request(merged_message):
            emoji_path = get_random_emoji()
            if emoji_path:
                try:
                    wx.SendFiles(filepath=emoji_path, who=chat_id)
                except Exception as e:
                    logger.error(f"发送表情包失败: {e}")

        # 获取API回复（只调用一次）
        reply = get_deepseek_response(merged_message, chat_id)
        if "</think>" in reply:
            reply = reply.split("</think>", 1)[1].strip()

        # 处理回复
        if '[IMAGE]' in reply:
            # 处理图片回复
            img_path = reply.split('[IMAGE]')[1].split('[/IMAGE]')[0].strip()
            logger.info(f"准备发送图片: {img_path}")
            if os.path.exists(img_path):
                try:
                    wx.SendFiles(filepath=img_path, who=chat_id)
                    cleanup_wxauto_files()  # 添加清理
                    logger.info(f"图片发送成功: {img_path}")
                    text_msg = reply.split('[/IMAGE]')[1].strip()
                    if text_msg:
                        if is_group:
                            text_msg = f"@{sender_name} {text_msg}"
                        wx.SendMsg(msg=text_msg, who=chat_id)
                except Exception as e:
                    logger.error(f"发送图片失败: {e}")
                finally:
                    try:
                        os.remove(img_path)
                        logger.info(f"已删除临时图片: {img_path}")
                    except Exception as e:
                        logger.error(f"删除临时图片失败: {e}")
            else:
                logger.error(f"图片文件不存在: {img_path}")
                error_msg = "抱歉，图片生成失败了..."
                if is_group:
                    error_msg = f"@{sender_name} {error_msg}"
                wx.SendMsg(msg=error_msg, who=chat_id)
        elif '\\' in reply:
            parts = [p.strip() for p in reply.split('\\') if p.strip()]
            for idx, part in enumerate(parts):
                if is_group:
                    if idx == 0:
                        part = f"@{sender_name} {part}"
                wx.SendMsg(msg=part, who=chat_id)
                time.sleep(random.randint(2,4))
        else:
            if is_group:
                reply = f"@{sender_name} {reply}"
            wx.SendMsg(msg=reply, who=chat_id)
            
    except Exception as e:
        logger.error(f"发送回复失败: {e}")

    # 异步保存消息记录
    threading.Thread(target=save_message, args=(username, sender_name, merged_message, reply)).start()


def message_listener():
    wx = None
    last_window_check = 0
    check_interval = 600  # 每600秒检查一次窗口状态,检查是否活动(是否在聊天界面)
    
    while True:
        try:
            current_time = time.time()
            
            # 只在必要时初始化或重新获取微信窗口，不输出提示
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
                        # 只输出实际的消息内容
                        # 接收窗口名跟发送人一样，代表是私聊，否则是群聊
                        if who == msg.sender:
                            handle_wxauto_message(msg, msg.sender) # 处理私聊信息
                        elif ROBOT_WX_NAME != '' and bool(re.search(f'@{ROBOT_WX_NAME}\u2005', msg.content)): 
                            # 修改：在群聊被@时，传入群聊ID(who)作为回复目标
                            handle_wxauto_message(msg, who, is_group=True) # 处理群聊信息，只有@当前机器人才会处理
                        # TODO(jett): 这里看需要要不要打日志，群聊信息太多可能日志会很多    
                        else:
                            logger.debug(f"非需要处理消息，可能是群聊非@消息: {content}")   
                    except Exception as e:
                        logger.debug(f"不好了主人！处理单条消息失败: {e}")
                        continue
                        
        except Exception as e:
            logger.debug(f"不好了主人！消息监听出错: {e}")
            wx = None  # 出错时重置微信对象
        time.sleep(wait)

def recognize_image_with_moonshot(image_path, is_emoji=False):
    """使用Moonshot AI识别图片内容并返回文本"""
    with open(image_path, 'rb') as img_file:
        image_content = base64.b64encode(img_file.read()).decode('utf-8')
    headers = {
        'Authorization': f'Bearer {MOONSHOT_API_KEY}',
        'Content-Type': 'application/json'
    }
    text_prompt = "请描述这个图片" if not is_emoji else "请描述这个聊天窗口的最后一张表情包"
    data = {
        "model": "moonshot-v1-8k-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}},
                    {"type": "text", "text": text_prompt}
                ]
            }
        ],
        "temperature": MOONSHOT_TEMPERATURE
    }
    try:
        response = requests.post(f"{MOONSHOT_BASE_URL}/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        recognized_text = result['choices'][0]['message']['content']
        if is_emoji:
            # 如果recognized_text包含“最后一张表情包是”，只保留后面的文本
            if "最后一张表情包是" in recognized_text:
                recognized_text = recognized_text.split("最后一张表情包是", 1)[1].strip()
            recognized_text = "发送了表情包：" + recognized_text
        else :
            recognized_text = "发送了图片：" + recognized_text
        logger.info(f"Moonshot AI图片识别结果: {recognized_text}")
        return recognized_text

    except Exception as e:
        logger.error(f"调用Moonshot AI识别图片失败: {e}")
        return ""

def handle_wxauto_message(msg, chatName, is_group=False):
    try:
        username = msg.sender  # 获取发送者的昵称或唯一标识
        content = getattr(msg, 'content', None) or getattr(msg, 'text', None)  # 获取消息内容
        img_path = None  # 初始化图片路径
        is_emoji = False
        
        # 如果是群聊@消息，移除@机器人的部分
        if is_group and ROBOT_WX_NAME and content:
            content = re.sub(f'@{ROBOT_WX_NAME}\u2005', '', content).strip()
        
        if content and content.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            img_path = content  # 如果消息内容是图片路径，则赋值给img_path
            is_emoji = False
            content = None  # 将内容置为空，因为我们只处理图片

        # 检查是否是"[动画表情]"
        if content and "[动画表情]" in content:
            # 对聊天对象的窗口进行截图，并保存到指定目录           
            img_path = capture_and_save_screenshot(username)
            is_emoji = True  # 设置为动画表情
            content = None  # 将内容置为空，不再处理该消息

        if img_path:
            logger.info(f"处理图片消息 - {username}: {img_path}")
            recognized_text = recognize_image_with_moonshot(img_path, is_emoji)
            content = recognized_text if content is None else f"{content} {recognized_text}"

        if content:
            logger.info(f"处理消息 - {username}: {content}")
            sender_name = username  # 使用昵称作为发送者名称

        sender_name = username
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_aware_content = f"[{current_time}] {content}"

        is_command, reply = master_cofig(content)
        if is_command:
            wx.SendMsg(msg=reply, who=chatName)
            return

        with queue_lock:
            if chatName not in user_queues:
                # 减少等待时间为5秒
                user_queues[chatName] = {
                    'timer': threading.Timer(5.0, process_user_messages, args=[chatName]),
                    'messages': [time_aware_content],
                    'sender_name': sender_name,
                    'username': username,
                    'is_group': is_group  # 添加群聊标记
                }
                user_queues[chatName]['timer'].start()
            else:
                # 重置现有定时器
                user_queues[chatName]['timer'].cancel()
                user_queues[chatName]['messages'].append(time_aware_content)
                user_queues[chatName]['timer'] = threading.Timer(5.0, process_user_messages, args=[chatName])
                user_queues[chatName]['timer'].start()

    except Exception as e:
        print(f"消息处理失败: {e}")


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
                    wx.AddListenChat(who=i, savepic=True)
                    logger.info(f"成功添加监听: {chat_name}")
                    time.sleep(0.5)  # 添加短暂延迟，避免操作过快
                except Exception as e:
                    logger.error(f"添加监听失败 {chat_name}: {e}")
                    continue
                    
            return wx
            
        except Exception as e:
            logger.error(f"初始化微信失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise Exception("微信初始化失败，请检查微信是否正常运行")
    
    return None

def cleanup_temp_dir():
    """清理临时目录中的旧图片"""
    try:
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        logger.info(f"清理旧临时文件: {file_path}")
                except Exception as e:
                    logger.error(f"清理文件失败 {file_path}: {e}")
    except Exception as e:
        logger.error(f"清理临时目录失败: {e}")

#更新最后聊天时间
def update_last_chat_time():
    """
    更新最后一次聊天时间
    """
    global last_chat_time
    last_chat_time = datetime.now()
    logger.info(f"更新最后聊天时间: {last_chat_time}")

def is_quiet_time() -> bool:
    """
    检查当前是否在安静时间段内
    """
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
        logger.error(f"检查安静时间出错: {e}")
        return False  # 出错时默认不在安静时间

def get_random_countdown_time():
    """
    获取随机倒计时时间（以秒为单位）
    """
    return random.randint(
        MIN_COUNTDOWN_HOURS * 3600,
        MAX_COUNTDOWN_HOURS * 3600
    )

def auto_send_message():
    """
    模拟发送消息到API
    """
    # 检查是否在安静时间
    if is_quiet_time():
        logger.info("当前处于安静时间，跳过自动发送消息")
        start_countdown()  # 重新开始倒计时
        return
        
    # 从listen_list中随机选择一个聊天对象
    if listen_list:
        user_id = random.choice(listen_list)
        logger.info(f"自动发送消息到 {user_id}: {AUTO_MESSAGE}")
        try:
            reply = get_deepseek_response(AUTO_MESSAGE, user_id)
            if reply:
                if '\\' in reply:
                    parts = [p.strip() for p in reply.split('\\') if p.strip()]
                    for part in parts:
                        wx.SendMsg(msg=part, who=user_id)
                        time.sleep(random.randint(1,2))
                else:
                    wx.SendMsg(msg=reply, who=user_id)
            start_countdown()  # 重新开始倒计时
        except Exception as e:
            logger.error(f"自动发送消息失败: {e}")
            start_countdown()  # 即使失败也重新开始倒计时
    else:
        logger.error("没有可用的聊天对象")
        start_countdown()  # 没有聊天对象时也重新开始倒计时

def start_countdown():
    """
    开始新的倒计时
    """
    global countdown_timer, is_countdown_running
    
    if countdown_timer:
        countdown_timer.cancel()
    
    countdown_seconds = get_random_countdown_time()
    logger.info(f"开始新的倒计时: {countdown_seconds/3600:.2f}小时")
    
    countdown_timer = threading.Timer(countdown_seconds, auto_send_message)
    countdown_timer.daemon = True  # 设置为守护线程
    countdown_timer.start()
    is_countdown_running = True

def cleanup_wxauto_files():
    """
    清理当前目录下的wxauto文件夹中的文件和子文件夹
    """
    try:
        # 当前目录下的wxauto文件夹路径
        wxauto_dir = os.path.join(os.getcwd(), "wxauto文件")
        print(f"正在检查目录: {wxauto_dir}")
        if not os.path.exists(wxauto_dir):
            print("wxauto文件夹不存在，无需清理")
            return
            
        files = os.listdir(wxauto_dir)
        if not files:
            print("wxauto文件夹为空，无需清理")
            return
            
        deleted_count = 0
        for file in files:
            try:
                file_path = os.path.join(wxauto_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    # print(f"已删除文件: {file_path}")
                    deleted_count += 1
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    # print(f"已删除文件夹: {file_path}")
                    deleted_count += 1
            except Exception as e:
                # print(f"删除失败 {file_path}: {e}")
                continue
                
        print(f"清理完成，共删除 {deleted_count} 个文件/文件夹")
    except Exception as e:
        print(f"清理wxauto文件夹时发生错误: {e}")

def clean_up_screenshot ():
    # 检查是否存在该目录
    if os.path.isdir("screenshot"):
        # 递归删除目录及其内容
        shutil.rmtree("screenshot")
        print(f"目录 creenshot 已成功删除")
    else:
        print(f"目录 screenshot 不存在，无需删除")

def capture_and_save_screenshot(who):
    screenshot_folder = os.path.join(root_dir, 'screenshot')
    if not os.path.exists(screenshot_folder):
        os.makedirs(screenshot_folder)
    
    screenshot_path = os.path.join(screenshot_folder, f'{who}_{datetime.now().strftime("%Y%m%d%H%M%S")}.png')
    
    try:
        # 激活并定位微信聊天窗口
        wx_chat = WeChat()
        wx_chat.ChatWith(who)
        chat_window = pyautogui.getWindowsWithTitle(who)[0]
        
        # 确保窗口被前置和激活
        if not chat_window.isActive:
            chat_window.activate()
        if not chat_window.isMaximized:
            chat_window.maximize()
        
        # 获取窗口的坐标和大小
        x, y, width, height = chat_window.left, chat_window.top, chat_window.width, chat_window.height

        time.sleep(wait)

        # 截取指定窗口区域的屏幕
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        screenshot.save(screenshot_path)
        logger.info(f'已保存截图: {screenshot_path}')
        return screenshot_path
    except Exception as e:
        logger.error(f'保存截图失败: {e}')


def main():
    try:
        # 清理临时目录
        cleanup_temp_dir()
        # 清理wxauto文件夹
        cleanup_wxauto_files()
        #清理screenshot文件
        clean_up_screenshot()
        
        # 使用新的初始化函数
        wx = initialize_wx_listener()
        if not wx:
            print("微信初始化失败，请确保微信已登录并保持在前台运行!")
            return

        # 启动消息监听线程
        print("启动消息监听...")
        listener_thread = threading.Thread(target=message_listener)
        listener_thread.daemon = True
        listener_thread.start()

        # 启动倒计时
        start_countdown()

        # 主循环
        while True:
            time.sleep(1)
            if not listener_thread.is_alive():
                logger.warning("监听线程已断开，尝试重新连接...")
                try:
                    wx = initialize_wx_listener()  # 重新初始化
                    if wx:
                        listener_thread = threading.Thread(target=message_listener)
                        listener_thread.daemon = True
                        listener_thread.start()
                except Exception as e:
                    logger.error(f"重新连接失败: {e}")
                    time.sleep(5)  # 等待一段时间后重试

    except Exception as e:
        logger.error(f"主程序异常: {e}")
    finally:
        # 清理倒计时
        if countdown_timer:
            countdown_timer.cancel()
        print("程序退出")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户终止程序")
    except Exception as e:
        print(f"程序异常退出: {e}")

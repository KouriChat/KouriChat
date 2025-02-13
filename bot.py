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
import json
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type
)
from colorama import init, Fore, Back, Style
init(autoreset=True)
from traceback import format_exc

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
logging.SUCCESS = 25
logging.addLevelName(logging.SUCCESS, 'SUCCESS')

def success(self, message, *args, **kws):
    if self.isEnabledFor(logging.SUCCESS):
        self._log(logging.SUCCESS, message, args, **kws)
logging.Logger.success = success

# --------------- 配置日志格式 ---------------
logging.basicConfig(
    level=logging.INFO,
    format=f'{Fore.CYAN}%(asctime)s.%(msecs)03d{Style.RESET_ALL} '
           f'[{Fore.YELLOW}%(threadName)s{Style.RESET_ALL}] '
           f'{Fore.BLUE}%(name)-12s{Style.RESET_ALL} '
           f'{Fore.MAGENTA}%(levelname)-8s{Style.RESET_ALL} '
           f'▶ {Fore.WHITE}%(message)s{Style.RESET_ALL}',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# ✅ 新增的全局 logger 定义
logger = logging.getLogger(__name__)  # 确保在所有函数之前定义
logger.setLevel(logging.INFO)  # 额外保险的日志级别设置

# 添加图像生成相关常量 ⬇️（后续代码保持不变）
IMAGE_API_URL = f"{DEEPSEEK_BASE_URL}/images/generations"

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
def get_deepseek_response(message: str, user_id: str) -> str:
    """
    优化版DeepSeek响应处理 - 支持分条回复的完整解决方案
    新增功能：
    1. API响应JSON结构校验
    2. 智能分隔符保留机制
    3. 安全字符白名单
    4. 响应稳定性三重校验
    """

    # ======================
    # 内部工具函数
    # ======================
    start_time = time.time()

    def sanitize_response(raw_text: str) -> str:
        """安全清洗与分条预处理"""
        try:
            # 替换原来的字符白名单检测，转为仅删除高危字符
            danger_chars = {'\x00', '\u202e', '\u200b'}  # 定义真正危险的字符

            # 构建安全替换表
            safe_table = str.maketrans({
                ord(c): '' for c in danger_chars  # 直接删除高危字符
            })

            # 替换危险字符
            base_clean = raw_text.translate(safe_table)

            # 处理分隔符标准化
            return re.sub(
                r'(?:\n{2,}|\\{2,}|\\n)',
                '\\\\',
                base_clean.replace('\r\n', '\n')
            )
        except re.error as e:
            logger.error(f"正则处理异常: {str(e)}，原始内容: {raw_text[:50]}...")
            return "消息处理异常，请稍后再试"

    def validate_api_response(response_json: dict) -> bool:
        """严格校验API响应结构"""
        required_keys = ['id', 'choices', 'created', 'model']
        if not all(key in response_json for key in required_keys):
            return False

        if not isinstance(response_json['choices'], list) or len(response_json['choices']) == 0:
            return False

        choice = response_json['choices'][0]
        return 'message' in choice and 'content' in choice['message']

    # ======================
    # 主逻辑
    # ======================
    try:
        # 安全检查前置
        if not message or len(message.strip()) < 1:
            logger.error("空消息请求")
            return "主人好像发了空白信息呢...(歪头)"

        # 安全检查 - 恶意指令检测
        if any(re.search(p, message, re.I) for p in [
            r'\b(rm -rf|sudo|shutdown|replicate)\b',
            r'(;|\||`|$)\s*(wget|curl|python)'
        ]):
            logger.warning(f"危险指令拦截: {message[:50]}...")
            return "收到神秘指令已自动过滤！ヽ(ﾟДﾟ)ﾉ"

        # 图片请求处理
        if handle_image_requests(message, user_id):  # 提取成独立函数
            return ""  # 图片处理不触发文字回复

        # 管理上下文（带错误恢复机制）
        with queue_lock:
            try:
                # 初始化或恢复损坏的上下文
                if not isinstance(chat_contexts.get(user_id), list):
                    chat_contexts[user_id] = []

                ctx = chat_contexts[user_id]
                ctx.append({"role": "user", "content": message})

                # 上下文循环缓存
                if len(ctx) > MAX_GROUPS * 2:
                    del ctx[:-MAX_GROUPS * 2]  # 保留最近对话
            except Exception as e:
                logger.error(f"上下文恢复失败: {str(e)}")
                chat_contexts[user_id] = [{"role": "user", "content": message}]

        # 带熔断机制的API调用
        @retry(
            stop=stop_after_attempt(2),
            wait=wait_random_exponential(multiplier=1, max=8),
            retry=retry_if_exception_type((
                    requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    json.JSONDecodeError
            )),
            before_sleep=lambda retry_state: logger.warning(
                f"API重试中（第{retry_state.attempt_number}次）..."
            )
        )
        def safe_api_call() -> str:
            """带三级校验的API调用"""
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
                content = response.choices[0].message.content
                # 添加响应格式清洁度校验
                if any(c in content for c in {'\x00', '\u202e'}):
                    logger.warning("检测到二进制干扰字符")
                    raise ValueError("Invalid character detected")

                return content  # 返回正确的内容变量


                # 校验响应长度合理性
                if len(raw_content) < MAX_TOKEN // 10:
                    logger.warning(f"响应过短: {len(raw_content)} chars")
                    raise ValueError("Response too short")

                logger.success(
                    f"{Fore.GREEN}✅ API响应接收{Style.RESET_ALL} | "
                    f"耗时：{time.time() - start_time:.2f}s | "
                    f"Token用量：{response.usage.total_tokens}"
                )

                # 第一层校验 - 原始响应结构
                response_json = response.model_dump()
                if not validate_api_response(response_json):
                    logger.error("非法API响应结构: %s", response_json)
                    raise ValueError("Invalid API response structure")

                # 第二层校验 - 内容有效性
                content = response_json['choices'][0]['message']['content']
                if not content or len(content) < 2:
                    logger.error("空内容响应")
                    raise ValueError("Empty content")

                # 第三层校验 - 敏感词过滤
                if re.search(r'(暴力|色情|政治敏感)', content):
                    logger.warning("触发内容过滤: %s", content[:50])
                    raise ValueError("Content policy violation")

                return content
            except AttributeError as e:
                logger.error("对象结构异常: %s", str(e))
                raise

        try:
            # 执行API调用
            raw_reply = safe_api_call()

            # 结果后处理
            clean_reply = sanitize_response(raw_reply)

            # 上下文存档（带异常保护）
            if clean_reply:
                with queue_lock:
                    chat_contexts[user_id].append(
                        {"role": "assistant", "content": clean_reply}
                    )

            # 触发资源维护
            def cleanup_temp_files():
                """集中清理所有临时资源"""
                try:
                    cleanup_temp_dir()  # 清理图片临时目录
                    cleanup_wxauto_files()  # 清理微信缓存文件
                    clean_up_screenshot()  # 清理截图目录
                    logger.info("✅ 全系统临时文件清理完成")
                except Exception as e:
                    logger.error(f"清理失败: {str(e)}")
            threading.Thread(target=cleanup_temp_dir).start()


            # 返回前智能截断
            return smart_truncate(clean_reply)  # 新增智能截断函数

        except Exception as api_error:
            logger.error("API调用终级失败: %s", str(api_error))
            return random.choice([
                "呜~好像有些混乱了，请再说一遍嘛~",
                "刚才信号好像飘走了...(´･ω･`)",
                "系统需要重启大脑啦！(＞﹏＜)"
            ])

    except Exception as e:
        logger.exception("全局异常突破防护: %s", str(e))
        return "出现未知错误，需要主人检查日志啦！"


def smart_truncate(text: str, max_len: int = MAX_TOKEN * 3) -> str:
    """智能截断保护分隔符完整性"""
    if len(text) <= max_len:
        return text

    # 寻找最近的合法分隔符
    cutoff = text.rfind('\\\\', 0, max_len)
    if cutoff != -1:
        return text[:cutoff + 2] + "…（后续内容已截断）"
    return text[:max_len] + "…"


def handle_image_requests(message: str, user_id: str) -> bool:
    """集中处理所有图像请求"""
    try:
        if is_random_image_request(message):
            # 处理随机图片...
            return True
        elif is_image_generation_request(message):
            # 处理生成图片...
            return True
        return False
    except Exception as e:
        logger.error("图像处理异常: %s", str(e))
        return False

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
    messages = messages[-6:]  # 限制处理的消息数量
    merged_message = ' \\ '.join(messages)
    logger.debug(
        f"{Fore.CYAN}🔀 合并消息处理{Style.RESET_ALL} | "
        f"来自：{Fore.YELLOW}{sender_name}{Style.RESET_ALL} | "
        f"内容片段：{merged_message[:30]}..."
    )

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
                    #过一段时间开发
                    #logger.info(f"{Fore.MAGENTA}🔊 发送语音{Style.RESET_ALL} | 时长：{get_audio_duration(voice_path)}s")
                    cleanup_wxauto_files()  # 添加清理
                except Exception as e:
                    logger.error(f"发送语音失败: {str(e)}")
                    if is_group:
                        reply = f"@{sender_name} {reply}"
                    wx.SendMsg(msg=reply, who=chat_id)


                finally:
                    try:
                        os.remove(voice_path)
                    except Exception as e:
                        logger.error(f"删除临时语音文件失败: {str(e)}")
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
                    logger.info(f"{Fore.YELLOW}😀 发送表情{Style.RESET_ALL} | 文件：{os.path.basename(emoji_path)}")
                except Exception as e:
                    logger.error(f"发送表情包失败: {str(e)}")

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
                    logger.info(f"{Fore.BLUE}🖼 发送图片{Style.RESET_ALL} | 路径：{os.path.basename(img_path)}")
                    cleanup_wxauto_files()
                    cleanup_wxauto_files()  # 添加清理
                    logger.info(f"图片发送成功: {img_path}")
                    text_msg = reply.split('[/IMAGE]')[1].strip()
                    if text_msg:
                        if is_group:
                            text_msg = f"@{sender_name} {text_msg}"
                        wx.SendMsg(msg=text_msg, who=chat_id)
                except Exception as e:
                    logger.error(f"发送图片失败: {str(e)}")
                finally:
                    try:
                        os.remove(img_path)
                        logger.info(f"已删除临时图片: {img_path}")
                    except Exception as e:
                        logger.error(f"删除临时图片失败: {str(e)}")
            else:
                logger.error(f"图片文件不存在: {img_path}")
                error_msg = "抱歉，图片生成失败了..."
                if is_group:
                    error_msg = f"@{sender_name} {error_msg}"
                wx.SendMsg(msg=error_msg, who=chat_id)
        elif '\\' in reply:
            parts = [p.strip() for p in reply.split('\\') if p.strip()]
            for idx, part in enumerate(parts):
                display_part = part.replace('\n', '↵').replace('\r', '↩')  # 转义符号显示
                truncated_part = (display_part[:60] + '...') if len(display_part) > 60 else display_part
                logger.info(
                    f"{Fore.GREEN}✂️ 分段消息{Style.RESET_ALL} | "
                    f"接收：{Fore.YELLOW}{sender_name}{Style.RESET_ALL} | "
                    f"第 {idx + 1}/{len(parts)} 条 | "
                    f"内容：{Fore.WHITE}{truncated_part}{Style.RESET_ALL}"
                )
                if is_group:
                    if idx == 0:
                        part = f"@{sender_name} {part}"
                wx.SendMsg(msg=part, who=chat_id)
                time.sleep(random.randint(2,4))
        else:
            # ============ 新增完整回复日志 ============
            display_text = reply.replace('\n', '↵').replace('\r', '↩')  # 换行符转义
            truncated_text = (display_text[:120] + '...') if len(display_text) > 120 else display_text
            log_title = "👤 私聊回复" if not is_group else "👥 群聊回复"

            logger.info(
                f"{Fore.CYAN}{log_title}{Style.RESET_ALL} | "
                f"发送到：{Fore.YELLOW}{sender_name}{Style.RESET_ALL} | "
                f"长度：{Fore.MAGENTA}{len(reply)}字{Style.RESET_ALL} | "
                f"摘要：{Fore.WHITE}{truncated_text}{Style.RESET_ALL}"
            )
            # ============ 新增内容结束 ============
            if is_group:
                reply = f"@{sender_name} {reply}"
            wx.SendMsg(msg=reply, who=chat_id)
            
    except Exception as e:
        logger.error(f"发送回复失败: {str(e)}")

    # 异步保存消息记录
    threading.Thread(target=save_message, args=(username, sender_name, merged_message, reply)).start()


def message_listener():
    wx = None
    last_window_check = 0
    check_interval = 600  # 每600秒检查一次窗口状态,检查是否活动(是否在聊天界面)
    cycle_count = 0

    while True:
        try:
            # 每5次循环记录一次状态
            if cycle_count % 5 == 0:
                logger.debug(
                    f"{Fore.WHITE}🔄 监听周期检查{Style.RESET_ALL} | "
                    f"运行中队列：{len(user_queues)} | "
                    f"最后窗口检查：{time.time() - last_window_check:.1f}s前"
                )
            cycle_count += 1
    

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
                        logger.debug(f"不好了主人！处理单条消息失败: {str(e)}")
                        wx = None
                        continue
                        
        except Exception as e:
            logger.debug(f"不好了主人！消息监听出错: {str(e)}")
            wx = None  # 出错时重置微信对象
        time.sleep(wait)

def recognize_image_with_moonshot(image_path, is_emoji=False):
    """使用Moonshot AI识别图片内容并返回文本"""
    logger.debug(
        f"{Fore.CYAN}🖼️ 开始图片识别{Style.RESET_ALL} | "
        f"路径：{os.path.basename(image_path)} | "
        f"大小：{os.path.getsize(image_path) // 1024}KB"
    )
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
        logger.success(
            f"{Fore.GREEN}🎯 图片识别成功{Style.RESET_ALL} | "
            f"耗时：{response.elapsed.total_seconds():.2f}s | 结果长度：{len(recognized_text)}字符"
        )
        return recognized_text

    except Exception as e:
        logger.error(f"调用Moonshot AI识别图片失败: {str(e)}")
        return ""

def handle_wxauto_message(msg, chatName, is_group=False):
    try:
        username = msg.sender  # 获取发送者的昵称或唯一标识
        sender_name = username  # 确保sender_name被初始化

        content = getattr(msg, 'content', None) or getattr(msg, 'text', None)
        img_path = None
        is_emoji = False
        msg_type_icon = "👥" if is_group else "👤"

        # ================= 现在可以安全地记录日志 =================
        logger.info(
            f"{Fore.MAGENTA}{msg_type_icon} 接收消息{Style.RESET_ALL} | "
            f"来源：{Fore.CYAN}{sender_name}{Style.RESET_ALL} | "
            f"内容类型：{['文本', '图片'][bool(img_path)]}"
        )
        
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
        print(f"消息处理失败: {str(e)}")


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
                    logger.error(f"清理文件失败 {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"清理临时目录失败: {str(e)}")

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
        logger.error(f"检查安静时间出错: {str(e)}")
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
                        time.sleep(random.randint(2, 4))
                else:
                    wx.SendMsg(msg=reply, who=user_id)
            start_countdown()  # 重新开始倒计时
        except Exception as e:
            logger.error(f"自动发送消息失败: {str(e)}")
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
    清理微信缓存文件 - 完整增强版
    """
    try:
        wxauto_dir = os.path.join(os.getcwd(), "wxauto文件")
        logger.debug(
            f"{Fore.WHITE}🧹 开始清理微信缓存{Style.RESET_ALL}\n"
            f"| 目录: {Fore.CYAN}{wxauto_dir}{Style.RESET_ALL}"
        )

        if not os.path.exists(wxauto_dir):
            logger.info(
                f"{Fore.BLUE}ℹ️ 无需清理{Style.RESET_ALL}\n"
                f"| 原因: {Fore.YELLOW}目录不存在{Style.RESET_ALL}"
            )
            return

        if not os.listdir(wxauto_dir):
            logger.info(
                f"{Fore.BLUE}ℹ️ 无需清理{Style.RESET_ALL}\n"
                f"| 原因: {Fore.YELLOW}目录为空{Style.RESET_ALL}"
            )
            return

        deleted_count = 0
        error_count = 0
        start_time = time.time()

        logger.debug(f"{Fore.WHITE}🔍 正在扫描文件...{Style.RESET_ALL}")
        for root, dirs, files in os.walk(wxauto_dir, topdown=False):
            for name in files + dirs:
                target_path = os.path.join(root, name)
                try:
                    if os.path.isfile(target_path):
                        os.remove(target_path)
                        logger.debug(
                            f"{Fore.GREEN}🗑️ 删除文件{Style.RESET_ALL}\n"
                            f"| 路径: {Fore.CYAN}{target_path}{Style.RESET_ALL}"
                        )
                        deleted_count += 1
                    elif os.path.isdir(target_path):
                        shutil.rmtree(target_path)
                        logger.debug(
                            f"{Fore.GREEN}🗂️ 删除目录{Style.RESET_ALL}\n"
                            f"| 路径: {Fore.CYAN}{target_path}{Style.RESET_ALL}"
                        )
                        deleted_count += 1
                except Exception as e:
                    error_count += 1
                    logger.error(
                        f"{Fore.RED}❌ 删除失败{Style.RESET_ALL}\n"
                        f"| 路径: {Fore.YELLOW}{target_path}{Style.RESET_ALL}\n"
                        f"| 错误: {e.__class__.__name__}: {str(e)}"
                    )

        time_cost = time.time() - start_time
        if deleted_count > 0:
            logger.success(
                f"{Fore.GREEN}✅ 清理完成{Style.RESET_ALL}\n"
                f"| 删除项目: {Fore.CYAN}{deleted_count}{Style.RESET_ALL}\n"
                f"| 失败次数: {Fore.RED if error_count > 0 else Fore.GREEN}{error_count}{Style.RESET_ALL}\n"
                f"| 耗时: {Fore.YELLOW}{time_cost:.2f}s{Style.RESET_ALL}"
            )
        else:
            logger.info(
                f"{Fore.BLUE}ℹ️ 无需清理{Style.RESET_ALL}\n"
                f"| 原因: {Fore.YELLOW}没有可删除内容{Style.RESET_ALL}"
            )

    except Exception as e:
        logger.critical(
            f"{Fore.RED}💥 清理严重错误{Style.RESET_ALL}\n"
            f"| 异常类型: {e.__class__.__name__}\n"
            f"| 错误细节: {str(e)}"
        )


def clean_up_screenshot ():
    # 检查是否存在该目录
    if os.path.isdir("screenshot"):
        # 递归删除目录及其内容
        shutil.rmtree("screenshot")
        logger.info(f"{Fore.BLUE}🗑 删除截图目录{Style.RESET_ALL} 路径：screenshot")
    else:
        logger.debug(f"{Fore.WHITE}📦 截图目录不存在{Style.RESET_ALL}")

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
        logger.error(f'保存截图失败: {str(e)}')


def main():
    try:
        # 初始化日志
        logger.info(f"{Fore.BLUE}⏳ 初始化核心组件{Style.RESET_ALL}")
        logger.debug(
            f"{Fore.WHITE}⚙️ 运行配置{Style.RESET_ALL}\n"
            f"| 模型: {Fore.CYAN}{MODEL}{Style.RESET_ALL}\n"
            f"| 最大Token: {Fore.CYAN}{MAX_TOKEN}{Style.RESET_ALL}\n"
            f"| 监听列表: {Fore.YELLOW}{len(LISTEN_LIST)}个{Style.RESET_ALL}\n"
            f"| 自动消息间隔: {Fore.GREEN}{MIN_COUNTDOWN_HOURS}-{MAX_COUNTDOWN_HOURS}小时{Style.RESET_ALL}"
        )

        # 初始化清理
        logger.debug(f"{Fore.WHITE}🧹 启动清理流程{Style.RESET_ALL}")
        cleanup_temp_dir()
        cleanup_wxauto_files()
        clean_up_screenshot()
        logger.success(f"{Fore.GREEN}✅ 清理完成{Style.RESET_ALL}")

        # 微信初始化
        logger.info(f"{Fore.BLUE}🔍 正在连接微信客户端{Style.RESET_ALL}")
        wx = initialize_wx_listener()
        if not wx:
            logger.critical(f"{Fore.RED}❌ 微信初始化失败，请确保：\n"
                            f"1. 微信客户端已登录\n"
                            f"2. 窗口保持前台运行\n"
                            f"3. 不要最小化窗口{Style.RESET_ALL}")
            return

        # 启动核心服务
        logger.info(f"{Fore.BLUE}🚦 启动核心服务{Style.RESET_ALL}")

        # 消息监听线程
        logger.info(
            f"{Fore.GREEN}📡 启动消息监听{Style.RESET_ALL}\n"
            f"| 线程模式: {Fore.YELLOW}守护线程{Style.RESET_ALL}\n"
            f"| 检查间隔: {Fore.CYAN}{wait}s{Style.RESET_ALL}\n"
            f"| 队列上限: {Fore.MAGENTA}{MAX_GROUPS}{Style.RESET_ALL}"
        )
        listener_thread = threading.Thread(
            target=message_listener,
            name="MessageListener",
            daemon=True
        )
        listener_thread.start()

        # 自动消息倒计时
        logger.info(
            f"{Fore.BLUE}⏰ 初始化自动消息服务{Style.RESET_ALL}\n"
            f"| 安静时段: {Fore.YELLOW}{QUIET_TIME_START}-{QUIET_TIME_END}{Style.RESET_ALL}"
        )
        start_countdown()

        # 主循环监控
        logger.info(f"{Fore.GREEN}🤖 机器人服务已就绪{Style.RESET_ALL}")
        while True:
            time.sleep(10)
            # 线程健康检查
            if not listener_thread.is_alive():
                logger.warning(
                    f"{Fore.YELLOW}⚠️ 监听线程异常断开{Style.RESET_ALL}\n"
                    f"| 存活状态: {Fore.RED}已停止{Style.RESET_ALL}\n"
                    f"| 尝试重新初始化..."
                )
                try:
                    wx = initialize_wx_listener()
                    if wx:
                        listener_thread = threading.Thread(
                            target=message_listener,
                            name="MessageListener_Restart",
                            daemon=True
                        )
                        listener_thread.start()
                        logger.success(f"{Fore.GREEN}🎉 线程恢复成功{Style.RESET_ALL}")
                except Exception as e:
                    logger.error(
                        f"{Fore.RED}❌ 重连失败{Style.RESET_ALL}\n"
                        f"| 错误: {e}\n"
                        f"| 将在5秒后重试..."
                    )
                    time.sleep(5)

    except Exception as e:
        logger.critical(
            f"{Fore.RED}💥 致命错误导致崩溃{Style.RESET_ALL}\n"
            f"| 异常类型: {type(e).__name__}\n"
            f"| 错误详情: {str(e)}\n"
            f"| 追踪信息: \n{format_exc()}"
        )
    except KeyboardInterrupt:
        logger.info(f"{Fore.YELLOW}👋 用户主动终止程序{Style.RESET_ALL}")
    finally:
        # 清理资源
        if countdown_timer:
            countdown_timer.cancel()
            logger.info(f"{Fore.BLUE}⏹ 已停止自动消息服务{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}🗑 正在释放系统资源...{Style.RESET_ALL}")
        cleanup_temp_dir()
        cleanup_wxauto_files()
        time.sleep(1)
        logger.success(f"{Fore.GREEN}🏁 系统安全关闭{Style.RESET_ALL}")


if __name__ == '__main__':
    main()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户终止程序")
    except Exception as e:
        print(f"程序异常退出: {str(e)}")

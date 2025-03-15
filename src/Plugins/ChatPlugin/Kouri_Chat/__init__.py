from datetime import datetime
from pathlib import Path
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_session import EventSession
from nonebot.log import logger
import random
import os
import time
import requests
from src.services.ai.image_recognition_service import ImageRecognitionService
from config import config, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL, MAX_TOKEN, TEMPERATURE, MAX_GROUPS
from oneBotMain import message_handler,moonshot_ai,emoji_handler,voice_handler,image_handler
from nonebot import on_message
from nonebot.adapters.onebot.v11 import  MessageEvent
from nonebot_plugin_alconna import (
    Audio,
    Args,
    At,
    Image,
    Text,
    UniMessage,
    on_alconna,
)
def ensure_group(session: Uninfo) -> bool:
    """
    是否在群聊中

    参数:
        session: Uninfo

    返回:
        bool: bool
    """
    return bool(session.group)

def ensure_private(session: EventSession) -> bool:
    """
    是否在私聊中

    参数:
        session: session

    返回:
        bool: bool
    """
    return not session.id3 and not session.id2

class NetworkError(Exception):
    pass

_matcher = on_message(rule=ensure_private, priority=999)
# 没有实现：5分钟未回复计数器功能，自动任务功能，目前只开了私信 （由on_message rule保证）
@_matcher.handle()
async def _(event: MessageEvent, session: Uninfo):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    UserMsg= f"[{current_time}] 该用户的昵称是：'{event.sender.nickname}'，ta私聊对你说 " #str
    for iterator in event.message:
        if iterator.type == "text":
            UserMsg += str(iterator.data["text"])
        elif iterator.type == "image":
            # 开始处理图片
            url = str(iterator.data["url"])
            Dir = os.path.join(Path(__file__).resolve().parent.parent.parent.parent.parent,'qqImgTemp') # py->...->handlers->src->kourichat
            os.makedirs(Dir, exist_ok=True)
            SavePath= os.path.join(
                Dir, 
                f'{event.user_id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.png'
            )
            logger.info(SavePath)
            logger.info(url)
            try:
                # 获取图片
                response = requests.get(url)
                if response.status_code == 200:
                    # 保存图片
                    with open(SavePath, 'wb') as f:
                        f.write(response.content)
            except Exception as e:
                logger.error(f"获取图片失败: {str(e)}")
                raise NetworkError("网络环境异常")
            logger.info(f"开始处理图片/表情 - 路径: {SavePath}")
            recognized_text = moonshot_ai.recognize_image(SavePath, True)
            UserMsg += recognized_text
        else:
            logger.error(f"不支持的消息类型")
    # 检测是否为表情包请求
    if emoji_handler.is_emoji_request(UserMsg):
        logger.info("检测到表情包请求")
        # 使用AI识别的情感选择表情包
        emoji_path = emoji_handler.get_emotion_emoji(UserMsg)
        if emoji_path:
            logger.info(f"准备发送情感表情包: {emoji_path}")
            await UniMessage.image(emoji_path).send()
    logger.info(f"处理消息 - 发送者: {event.sender.nickname} 内容: {UserMsg}")
    is_image_recognition = (UserMsg.count("发送了图片：")!=0 or UserMsg.count("发送了表情包：")!=0)
    #检查是否为语音请求
    if voice_handler.is_voice_request(UserMsg):
        reply=message_handler.QQ_handle_voice_request(content=UserMsg, qqid=event.user_id,sender_name=event.sender.nickname)
        try:
            if os.path.isfile(reply):
                await UniMessage.audio(path=reply).send()
                try:
                    os.remove(reply)
                except Exception as e:
                    logger.error(f"删除临时语音文件失败: {str(e)}")
            else:
                await UniMessage.text(text=reply).send()
        except Exception as e:
            logger.error(f"发送消息失败: {str(e)}")
            
    # 检查是否为随机图片请求
    elif image_handler.is_random_image_request(UserMsg):
        reply=message_handler.QQ_handle_random_image_request(content=UserMsg,qqid=event.user_id,sender_name=event.sender.nickname)
        defaultReply= "给主人你找了一张好看的图片哦~"
        try:
            if os.path.isfile(reply):
                await UniMessage.image(path=reply).send()
                await UniMessage.text(text=defaultReply).send()
                try:
                    os.remove(reply)
                except Exception as e:
                    logger.error(f"删除临时图片文件失败: {str(e)}")
            else:
                await UniMessage.text(text= "抱歉主人，图片发送失败了...").send()
        except Exception as e:
            logger.error(f"发送消息失败: {str(e)}")
    elif not is_image_recognition and image_handler.is_image_generation_request(UserMsg):
        reply=message_handler.QQ_handle_image_generation_request(content=UserMsg,qqid=event.user_id,sender_name=event.sender.nickname)
        defaultReply="这是按照主人您的要求生成的图片\\(^o^)/~"
        try:
            if os.path.isfile(reply):
                await UniMessage.image(path=reply).send()
                await UniMessage.text(text=defaultReply).send()
                try:
                    os.remove(reply)
                except Exception as e:
                    logger.error(f"删除临时图片文件失败: {str(e)}")
            else:
                await UniMessage.text(text= "抱歉主人，图片生成失败了...").send()
        except Exception as e:
            logger.error(f"发送消息失败: {str(e)}")
    else:
         # 处理普通文本回复
        MsgList=message_handler.QQ_handle_text_message(content=UserMsg,qqid=event.user_id,sender_name=event.sender.nickname)
        for iterator in MsgList:
            if os.path.isfile(iterator):
                await UniMessage.image(path=iterator).send()
            else:
                await UniMessage.text(text=iterator).send()
                time.sleep(random.uniform(1.5,2.5))
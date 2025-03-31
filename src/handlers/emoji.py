"""
表情包处理模块
负责处理表情包相关功能，包括:
- 表情包请求识别
- 表情包选择
- 文件管理
"""

import os
import random
import logging
import re
from datetime import datetime
from typing import Tuple, Optional, Callable
import threading
import queue
import time
from src.config.rag_config import config
from src.webui.routes.avatar import AVATARS_DIR

# 基础表情包触发概率配置（巧可酱快来修改）
EMOJI_TRIGGER_RATE = 0.3  # 基础触发概率30%
TRIGGER_RATE_INCREMENT = 0.15  # 未触发时概率增加量
MAX_TRIGGER_RATE = 0.8  # 最大触发概率

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger('main')

from src.handlers.file import FileHandler

class EmojiHandler:
    def __init__(self, root_dir, wx_instance=None, sentiment_analyzer=None):
        self.root_dir = root_dir
        self.wx = wx_instance  # 使用传入的 WeChat 实例
        self.sentiment_analyzer = sentiment_analyzer  # 情感分析器实例
        avatar_name = config.behavior.context.avatar_dir
        self.emoji_dir = os.path.join(AVATARS_DIR, avatar_name,"emojis")
        
        # 使用任务队列替代处理锁
        self.task_queue = queue.Queue()
        self.is_replying = False
        self.worker_thread = threading.Thread(target=self._process_emoji_queue, daemon=True)
        self.worker_thread.start()
        
        # 情感目录映射（实在没办法了，要适配之前的文件结构）
        # 相信后人的智慧喵~
        self.emotion_dir_map = {
            'Happy': 'happy',
            'Sad': 'sad',
            'Anger': 'angry',
            'Neutral': 'neutral',
            'Surprise': 'happy',
            'Fear': 'sad',
            'Depress': 'sad',
            'Dislike': 'angry'
        }
        
        # 触发概率状态维护 {user_id: current_prob}
        self.trigger_states = {}
        
        # 确保目录存在
        os.makedirs(self.emoji_dir, exist_ok=True)

    def is_emoji_request(self, text: str) -> bool:
        """判断是否为表情包请求"""
        # 使用更明确的表情包关键词，确保与图片识别不混淆
        emoji_keywords = ["发表情", "来个表情包", "表情包", "斗图", "发个表情", "发个gif", "发个动图"]
        # 使用完整匹配而不是部分匹配，避免误判
        return any(keyword in text.lower() for keyword in emoji_keywords)

    def _get_emotion_dir(self, emotion_type: str) -> str:
        """将情感分析结果映射到目录"""
        return self.emotion_dir_map.get(emotion_type, 'neutral')

    def _update_trigger_prob(self, user_id: str, triggered: bool):
        """更新触发概率状态"""
        current_prob = self.trigger_states.get(user_id, EMOJI_TRIGGER_RATE)
        
        if triggered:
            # 触发后重置概率
            new_prob = EMOJI_TRIGGER_RATE
        else:
            # 未触发时增加概率（使用指数衰减）
            new_prob = min(current_prob + TRIGGER_RATE_INCREMENT * (1 - current_prob), MAX_TRIGGER_RATE)
        
        self.trigger_states[user_id] = new_prob
        logger.debug(f"用户 {user_id} 触发概率更新: {current_prob:.2f} -> {new_prob:.2f}")

    def should_send_emoji(self, user_id: str) -> bool:
        """判断是否应该发送表情包"""
        current_prob = self.trigger_states.get(user_id, EMOJI_TRIGGER_RATE)
        if random.random() < current_prob:
            self._update_trigger_prob(user_id, True)
            return True
        self._update_trigger_prob(user_id, False)
        return False

    def _process_emoji_queue(self):
        """后台线程处理表情包任务队列"""
        while True:
            try:
                # 等待队列中的任务
                task = self.task_queue.get()
                if task is None:
                    continue
                    
                # 如果正在回复，等待回复结束
                while self.is_replying:
                    time.sleep(0.5)
                    
                # 解析任务
                text, user_id, callback = task
                
                # 执行表情包获取
                result = self._get_emotion_emoji_impl(text, user_id)
                if callback and result:
                    callback(result)
                    
            except Exception as e:
                logger.error(f"处理表情包队列时出错: {str(e)}")
            finally:
                # 标记任务完成
                try:
                    self.task_queue.task_done()
                except:
                    pass
                time.sleep(0.1)
    
    def set_replying_status(self, is_replying: bool):
        """设置当前是否在进行回复"""
        self.is_replying = is_replying
        logger.debug(f"表情包处理回复状态已更新: {'正在回复' if is_replying else '回复结束'}")

    def _get_emotion_emoji_impl(self, text: str, user_id: str) -> Optional[str]:
        """实际执行表情包获取的内部方法"""
        try:
            if not self.sentiment_analyzer:
                logger.warning("情感分析器未初始化")
                return None
                
            # 获取情感分析结果
            result = self.sentiment_analyzer.analyze(text)
            emotion = result.get('sentiment_type', 'Neutral')
            
            # 映射到目录
            target_emotion = self._get_emotion_dir(emotion)
            target_dir = os.path.join(self.emoji_dir, target_emotion)
            
            # 回退机制处理
            if not os.path.exists(target_dir):
                if os.path.exists(self.emoji_dir):
                    logger.warning(f"情感目录 {target_emotion} 不存在，使用根目录")
                    target_dir = self.emoji_dir
                else:
                    logger.error(f"表情包根目录不存在: {self.emoji_dir}")
                    return None

            # 获取有效表情包文件
            emoji_files = [f for f in os.listdir(target_dir)
                          if f.lower().endswith(('.gif', '.jpg', '.png', '.jpeg'))]
            
            if not emoji_files:
                logger.warning(f"目录中未找到表情包: {target_dir}")
                return None
                
            # 判断是否触发
            if not self.should_send_emoji(user_id):
                logger.info(f"未触发表情发送（用户 {user_id}）")
                return None
                
            # 随机选择并返回路径
            selected = random.choice(emoji_files)
            logger.info(f"已选择 {target_emotion} 表情包: {selected}")
            return os.path.join(target_dir, selected)
        except Exception as e:
            logger.error(f"获取表情包失败: {str(e)}", exc_info=True)
            return None

    def get_emotion_emoji(self, text: str, user_id: str, callback: Callable = None, is_self_emoji: bool = False) -> Optional[str]:
        """将表情包获取任务添加到队列"""
        try:
            # 如果是自己发送的表情包，直接跳过处理
            if is_self_emoji:
                logger.info(f"检测到自己发送的表情包，跳过获取和识别")
                return None
                
            # 添加到任务队列
            self.task_queue.put((text, user_id, callback))
            logger.info(f"已添加表情包获取任务到队列，用户: {user_id}")
            return "表情包请求已添加到队列，将在消息回复后处理"
        except Exception as e:
            logger.error(f"添加表情包获取任务失败: {str(e)}")
            return None

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
from typing import Tuple, Optional, Callable, Deque, Dict, List
from collections import deque, defaultdict
import threading
import queue
import time
from src.config import config
from src.webui.routes.avatar import AVATARS_DIR
from src.handlers.file import FileHandler

# 基础表情包触发概率配置（巧可酱快来修改）
EMOJI_TRIGGER_RATE = 0.6  # 基础触发概率50%
TRIGGER_RATE_INCREMENT = 0.2  # 未触发时概率增加量
MAX_TRIGGER_RATE = 1  # 最大触发概率
LRU_CACHE_SIZE = 3  # 每个用户的LRU缓存大小
PREFERENCE_WEIGHT = 0.2  # 偏好学习权重

# 修改logger获取方式，确保与main模块一致
logger = logging.getLogger("main")


class EmojiHandler:
    def __init__(self, root_dir, wx_instance=None, sentiment_analyzer=None):
        self.root_dir = root_dir
        self.wx = wx_instance  # 使用传入的 WeChat 实例
        self.sentiment_analyzer = sentiment_analyzer  # 情感分析器实例
        avatar_name = config.behavior.context.avatar_dir
        self.emoji_dir = os.path.join(AVATARS_DIR, avatar_name, "emojis")

        # 功能开关属性
        self._enabled = True  # 默认启用表情功能
        self._enable_stats = False  # 统计功能默认关闭

        # 使用任务队列替代处理锁
        self.task_queue = queue.Queue()
        self.is_replying = False
        self.worker_thread = threading.Thread(
            target=self._process_emoji_queue, daemon=True
        )
        self.worker_thread.start()

        # 情感目录映射（实在没办法了，要适配之前的文件结构）
        # 相信后人的智慧喵~
        self.emotion_dir_map = {
            "Happy": "happy",
            "Sad": "sad",
            "Anger": "angry",
            "Neutral": "neutral",
            "Surprise": "happy",
            "Fear": "sad",
            "Depress": "sad",
            "Dislike": "angry",
        }

        # 触发概率状态维护 {user_id: current_prob}
        self.trigger_states = {}
        self.lru_cache = defaultdict(deque)  # {user_id: Deque[path]}
        self.user_prefs = defaultdict(dict)  # {user_id: {path: weight}}
        self.usage_stats = defaultdict(int)  # {path: count}
        
        # 文件监控
        self.file_handler = FileHandler()
        self._setup_file_watcher()
        
        # 确保目录存在
        os.makedirs(self.emoji_dir, exist_ok=True)

    def _setup_file_watcher(self):
        """设置文件变更监听（使用FileHandler实现）"""
        def reload_callback():
            logger.info("检测到表情包目录变更，刷新缓存")
            self._clear_caches()
        try:
            self.file_handler.watch_directory(
                self.emoji_dir,
                callback=reload_callback,
                extensions=[".gif", ".jpg", ".png", ".jpeg"] # 添加jpeg支持
            )
        except Exception as e:
            logger.error(f"初始化文件监视失败: {str(e)}")
    @property
    
    def enabled(self) -> bool:
        """表情功能是否启用"""
        return self._enabled
    @enabled.setter
    
    def enabled(self, value: bool):
        """设置表情功能开关状态"""
        self._enabled = value
        logger.info(f"表情功能已{'启用' if value else '禁用'}")
    
    def enable_statistics(self, enable: bool = True):
        """启用/禁用使用统计功能"""
        self._enable_stats = enable
        logger.info(f"使用统计功能已{'启用' if enable else '禁用'}")
    
    def _clear_caches(self):
        """清空所有缓存"""
        self.lru_cache.clear()
        self.user_prefs.clear() # 清空用户偏好
        self.usage_stats.clear() # 清空使用统计
        logger.debug("已清空所有缓存")
    
    def _update_usage_stats(self, path: str):
        """更新使用统计"""
        if self._enable_stats:
            self.usage_stats[path] += 1
            logger.debug(f"更新使用统计: {path} -> {self.usage_stats[path]}")
    
    def _update_user_preference(self, user_id: str, path: str):
        """更新用户偏好"""
        current = self.user_prefs[user_id].get(path, 0.0)
        self.user_prefs[user_id][path] = current + PREFERENCE_WEIGHT
        logger.debug(f"更新用户偏好: {user_id} - {path}")
    
    def _get_weighted_choice(self, files: List[str], user_id: str) -> str:
        """基于用户偏好的加权随机选择"""
        if not files:
            raise ValueError("候选表情列表不能为空")
        weights = [1.0 + self.user_prefs[user_id].get(f, 0.0) for f in files]
        return random.choices(files, weights=weights, k=1)[0]
    
    def _filter_cached(self, candidates: List[str], user_id: str) -> List[str]:
        """过滤最近使用过的表情"""
        cached = self.lru_cache[user_id]
        return [p for p in candidates if p not in cached]
    
    def _update_lru_cache(self, user_id: str, path: str):
        """更新LRU缓存"""
        cache = self.lru_cache[user_id]
        if path in cache:
            cache.remove(path)
        cache.appendleft(path)
        if len(cache) > LRU_CACHE_SIZE:
            cache.pop()


    def is_emoji_request(self, text: str) -> bool:
        """判断是否为表情包请求"""
        # 使用更明确的表情包关键词，确保与图片识别不混淆
        emoji_keywords = [
            "发表情",
            "来个表情包",
            "表情包",
            "斗图",
            "发个表情",
            "发个gif",
            "发个动图",
        ]
        # 使用完整匹配而不是部分匹配，避免误判
        return any(keyword in text.lower() for keyword in emoji_keywords)

    def _get_emotion_dir(self, emotion_type: str) -> str:
        """将情感分析结果映射到目录"""
        return self.emotion_dir_map.get(emotion_type, "neutral")

    def _update_trigger_prob(self, user_id: str, triggered: bool):
        """更新触发概率状态"""
        current_prob = self.trigger_states.get(user_id, EMOJI_TRIGGER_RATE)

        if triggered:
            # 触发后重置概率
            new_prob = EMOJI_TRIGGER_RATE
        else:
            # 未触发时增加概率（使用指数衰减）
            new_prob = min(
                current_prob + TRIGGER_RATE_INCREMENT * (1 - current_prob),
                MAX_TRIGGER_RATE,
            )

        self.trigger_states[user_id] = new_prob
        logger.debug(
            f"用户 {user_id} 触发概率更新: {current_prob:.2f} -> {new_prob:.2f}"
        )

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
        logger.debug(
            f"表情包处理回复状态已更新: {'正在回复' if is_replying else '回复结束'}"
        )

    def _get_emotion_emoji_impl(self, text: str, user_id: str) -> Optional[str]:
        """实际执行表情包获取的内部方法"""
        try:
            if not self.sentiment_analyzer:
                logger.warning("情感分析器未初始化")
                return None

            # 获取情感分析结果
            result = self.sentiment_analyzer.analyze(text)
            emotion = result.get("sentiment_type", "Neutral")

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
            candidates = [
                os.path.join(target_dir, f)
                for f in os.listdir(target_dir)
                if f.lower().endswith((".gif", ".jpg", ".png", ".jpeg"))
            ]

            if not candidates:
                logger.warning(f"目录中未找到表情包: {target_dir}")
                return None
            
            # 过滤最近使用过的表情
            valid_candidates = self._filter_cached(candidates, user_id)
            if not valid_candidates:
                logger.warning(f"未找到合适的候选表情 (用户: {user_id})")
                # 可以选择返回None，或者清空LRU缓存重新选择
                self.lru_cache[user_id].clear()
                valid_candidates = candidates  # 清空缓存后重新选择

            # 判断是否触发
            if not self.should_send_emoji(user_id):
                logger.info(f"未触发表情发送（用户 {user_id}）")
                return None

             # 基于用户偏好的加权随机选择
            selected = self._get_weighted_choice(valid_candidates, user_id)
            
            # 更新使用统计和用户偏好
            self._update_usage_stats(selected)
            self._update_user_preference(user_id, selected)
            
            # 更新LRU缓存
            self._update_lru_cache(user_id, selected)
            logger.info(f"已选择 {target_emotion} 表情包: {os.path.basename(selected)}")
            return selected
        
        except Exception as e:
            logger.error(f"获取表情包失败: {str(e)}", exc_info=True)
            return None

    def get_emotion_emoji(
        self,
        text: str,
        user_id: str,
        callback: Callable = None,
        is_self_emoji: bool = False,
    ) -> Optional[str]:
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

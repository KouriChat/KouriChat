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

# 表情包触发与学习配置
# ===================================
# EMOJI_TRIGGER_RATE: 基础表情包触发概率(0.0-1.0)
#   - 值越大，表情触发阈值越低，AI越容易发送表情包
#   - 0.6 意味着当随机"欲望值"大于0.4(1-0.6)时会触发表情包
#   - 从另一角度理解：欲望值范围0-1，阈值为(1-概率)，欲望>阈值时发送表情
EMOJI_TRIGGER_RATE = 0.6  # 基础触发概率60%

# TRIGGER_RATE_INCREMENT: 未触发时阈值降低量(0.0-1.0)
#   - 如果一次AI回复没有触发表情包，下次的阈值会降低
#   - 使用指数增长公式确保不会立即达到最低阈值
#   - 0.2 表示每次未触发，阈值降低约0.2左右(取决于当前阈值)
TRIGGER_RATE_INCREMENT = 0.2  # 未触发时概率增加量

# MAX_TRIGGER_RATE: 最大触发概率，对应最低阈值(0.0-1.0)
#   - 触发概率的上限，即使多次未触发也不会超过这个值
#   - 1.0 表示多次未触发后，阈值可以降低到0，任何欲望值都会触发表情
MAX_TRIGGER_RATE = 1.0  # 最大触发概率

# LRU_CACHE_SIZE: 每个用户最近使用表情包的记忆量
#   - 系统会避免连续发送相同或最近发送过的表情包
#   - 值越大，表情包重复的概率越低
#   - 3 表示记住最近3个发送过的表情包并避免重复发送
LRU_CACHE_SIZE = 3  # 每个用户的LRU缓存大小

# PREFERENCE_WEIGHT: 用户表情偏好学习权重(0.0-1.0)
#   - 系统会学习用户对哪类表情包的偏好
#   - 当表情包被使用后，下次选中该表情的权重会增加这个值
#   - 0.2 表示每次使用表情后，再次选中该表情的概率增加20%
PREFERENCE_WEIGHT = 0.2  # 偏好学习权重
# ===================================

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
        # 使用PREFERENCE_WEIGHT增量增加对该表情的偏好权重
        self.user_prefs[user_id][path] = current + PREFERENCE_WEIGHT
        logger.debug(f"更新用户偏好: {user_id} - {path}, 权重增加: {PREFERENCE_WEIGHT}, 新权重: {current + PREFERENCE_WEIGHT:.2f}")
    
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
        # 如果路径已在缓存中，先移除它
        if path in cache:
            cache.remove(path)
        # 将路径添加到缓存前端
        cache.appendleft(path)
        # 如果缓存超过了LRU_CACHE_SIZE定义的大小，移除最后一项
        if len(cache) > LRU_CACHE_SIZE:
            old_path = cache.pop()
            logger.debug(f"LRU缓存超过大小限制 {LRU_CACHE_SIZE}，移除最旧项: {os.path.basename(old_path)}")
        logger.debug(f"更新用户 {user_id} 的LRU缓存，当前大小: {len(cache)}/{LRU_CACHE_SIZE}")


    def is_emoji_request(self, text: str) -> bool:
        """判断是否为表情包请求"""
        # 转换为小写便于匹配
        text_lower = text.lower()
        
        # 使用更明确的表情包关键词，确保与图片识别不混淆
        emoji_keywords = [
            "发表情",
            "来个表情包",
            "表情包",
            "斗图",
            "发个表情",
            "发个gif",
            "发个动图",
            "表情",
            "发个表情包",
            "发一个表情包",
            "发张表情",
            "表情包来",
            "发送表情",
            "表情包发一个",
            "表情来一个",
            "来个表情",
            "来张表情",
        ]
        
        # 短语匹配，确保是明确的表情包请求
        for keyword in emoji_keywords:
            if keyword in text_lower:
                return True
                
        # 正则表达式匹配更复杂的表达方式
        patterns = [
            r'发.{0,2}表情',  # 匹配"发个表情"、"发一表情"等
            r'表情.{0,2}发',  # 匹配"表情给发"、"表情包发"等
            r'来.{0,2}表情',  # 匹配"来个表情"等
            r'表情.{0,2}来',  # 匹配"表情包来一个"等
            r'(发|给|来).{0,2}(表情|动图|gif)',  # 组合模式
        ]
        
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False

    def _get_emotion_dir(self, emotion_type: str) -> str:
        """将情感分析结果映射到目录"""
        return self.emotion_dir_map.get(emotion_type, "neutral")

    def _update_trigger_prob(self, user_id: str, triggered: bool):
        """更新触发概率状态"""
        current_prob = self.trigger_states.get(user_id, EMOJI_TRIGGER_RATE)

        if triggered:
            # 触发后重置概率到基础概率EMOJI_TRIGGER_RATE
            new_prob = EMOJI_TRIGGER_RATE
            logger.info(f"用户 {user_id} 已发送表情，重置阈值到基础值: {EMOJI_TRIGGER_RATE}")
        else:
            # 未触发时增加概率（降低阈值），使用TRIGGER_RATE_INCREMENT增量，但不超过MAX_TRIGGER_RATE上限
            # 使用指数式增长方式，随着连续未触发次数增加而增速降低
            new_prob = min(
                current_prob + TRIGGER_RATE_INCREMENT * (1 - current_prob / MAX_TRIGGER_RATE),
                MAX_TRIGGER_RATE,
            )
            logger.info(f"用户 {user_id} 未发送表情，降低下次阈值: {1-current_prob:.2f} -> {1-new_prob:.2f}，调整量: {TRIGGER_RATE_INCREMENT}，上限: {MAX_TRIGGER_RATE}")

        self.trigger_states[user_id] = new_prob
        logger.debug(
            f"用户 {user_id} 表情阈值更新: {1-current_prob:.2f} -> {1-new_prob:.2f}"
        )

    def should_send_emoji(self, user_id: str) -> bool:
        """判断是否应该发送表情包"""
        # 从状态中获取当前概率，如果没有则使用基础概率EMOJI_TRIGGER_RATE
        current_prob = self.trigger_states.get(user_id, EMOJI_TRIGGER_RATE)
        # 确保使用至少EMOJI_TRIGGER_RATE的概率
        adjusted_prob = max(current_prob, EMOJI_TRIGGER_RATE)  
        
        # 生成0-1之间的随机值，代表当前"发送表情包的欲望"
        random_value = random.random()
        
        # 修改判断逻辑：当随机值(欲望)大于概率阈值时发送表情包
        # 欲望值越高，越容易触发表情包发送
        should_send = random_value > (1 - adjusted_prob)
        
        # 添加详细日志，帮助诊断问题
        logger.info(f"表情触发判断 - 用户: {user_id}, 基础概率: {EMOJI_TRIGGER_RATE}, 当前概率: {current_prob:.2f}, 调整后概率: {adjusted_prob:.2f}, 随机欲望值: {random_value:.2f}, 阈值: {1-adjusted_prob:.2f}, 结果: {'发送' if should_send else '不发送'}")
        
        if should_send:
            self._update_trigger_prob(user_id, True)
            return True
        self._update_trigger_prob(user_id, False)
        return False

    def _process_emoji_queue(self):
        """处理表情包任务队列"""
        while True:
            try:
                # 等待队列中的任务
                task = self.task_queue.get()
                if task is None:
                    time.sleep(0.5)
                    continue

                # 不再等待回复结束，直接处理表情包任务
                # 注释掉等待逻辑，避免阻塞表情发送
                # if self.is_replying:
                #     logger.debug("表情处理器正在回复中，但仍继续处理表情任务")

                # 解析任务
                text, user_id, callback = task
                
                # 记录更详细的处理信息
                is_request = self.is_emoji_request(text)
                logger.info(f"处理表情包任务: {'表情请求' if is_request else 'AI回复'}, 用户: {user_id}, 文本长度: {len(text)}")

                # 执行表情包获取
                result = self._get_emotion_emoji_impl(text, user_id)
                
                # 如果获取到表情包路径
                if result:
                    logger.info(f"获取到表情包: {result}")
                    # 如果提供了回调函数，调用回调
                    if callback and os.path.exists(result):
                        # 不再添加延迟，直接调用回调发送表情包
                        logger.info(f"通过回调发送表情包: {result}")
                        callback(result)
                    elif hasattr(self, 'wx') and self.wx and os.path.exists(result):
                        # 如果有wx实例但没有回调，尝试直接发送
                        try:
                            self.wx.SendFiles(filepath=result, who=user_id)
                            logger.info(f"直接发送表情包成功: {result}")
                        except Exception as e:
                            logger.error(f"直接发送表情包失败: {str(e)}")
                else:
                    logger.info(f"未获取到表情包或判断不发送，用户: {user_id}")

            except Exception as e:
                logger.error(f"处理表情包队列时出错: {str(e)}", exc_info=True)
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
            # 记录文本内容，帮助诊断
            logger.info(f"表情处理文本(前20字符): {text[:20]}...")
            
            # 检查是否是表情包请求，请求情况下100%发送
            is_request = self.is_emoji_request(text)
            if is_request:
                logger.info("检测到明确的表情包请求，将100%发送")
            
            if not self.sentiment_analyzer and not is_request:
                logger.warning("情感分析器未初始化")
                return None

            # 获取表情包目录
            target_emotion = "neutral"  # 默认为中性
            target_dir = ""
            
            if is_request:
                # 表情包请求时随机选择情感目录
                emotion_dirs = []
                try:
                    if os.path.exists(self.emoji_dir):
                        emotion_dirs = [
                            d for d in os.listdir(self.emoji_dir) 
                            if os.path.isdir(os.path.join(self.emoji_dir, d))
                        ]
                except Exception as e:
                    logger.error(f"获取表情包目录失败: {str(e)}")
                
                # 如果存在情感目录，随机选择一个
                if emotion_dirs:
                    target_emotion = random.choice(emotion_dirs)
                
                # 构建表情包目录路径
                target_dir = os.path.join(self.emoji_dir, target_emotion)
                if not os.path.exists(target_dir):
                    target_dir = self.emoji_dir  # 回退到根目录
                
                logger.info(f"表情包请求，选择了情感目录: {target_emotion}")
            else:
                # 正常AI回复，使用情感分析
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
                        
                # 对于AI回复，判断是否触发表情包发送
                # 表情包请求时跳过概率判断，AI回复时则进行判断
                if not is_request:
                    send_emoji = self.should_send_emoji(user_id)
                    if not send_emoji:
                        logger.info(f"根据概率判断不发送表情包（用户 {user_id}）")
                        return None
                    else:
                        logger.info(f"根据概率判断将发送表情包（用户 {user_id}）")

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
                
            # 避免空内容或过短内容的表情分析
            if not text or len(text.strip()) < 5:
                logger.info(f"消息内容过短，跳过表情分析: {text}")
                return None
                
            # 表情包请求需要立即处理，AI回复则添加到队列
            if self.is_emoji_request(text):
                # 表情包请求，直接处理而不是添加到队列
                logger.info(f"直接处理表情包请求: {text}")
                emoji_path = self._get_emotion_emoji_impl(text, user_id)
                
                # 如果获取到表情包路径
                if emoji_path and os.path.exists(emoji_path):
                    # 如果提供了回调函数，交给回调处理
                    if callback:
                        threading.Timer(0.5, lambda: callback(emoji_path)).start()
                        return "表情包处理中..."
                    # 如果有wxauto实例，直接发送
                    elif hasattr(self, 'wx') and self.wx:
                        try:
                            self.wx.SendFiles(filepath=emoji_path, who=user_id)
                            logger.info(f"已发送表情包: {emoji_path}")
                            return "表情包已发送"
                        except Exception as e:
                            logger.error(f"发送表情包失败: {str(e)}")
                            return "发送表情包失败"
                    else:
                        # 既没有回调也没有wx实例，返回路径
                        return emoji_path
                else:
                    return "未找到合适的表情包"
            else:
                # AI回复情感分析，添加到队列处理
                logger.info(f"AI回复情感分析处理: 用户={user_id}, 内容长度={len(text)}")
                self.task_queue.put((text, user_id, callback))
                return None
        except Exception as e:
            logger.error(f"添加表情包获取任务失败: {str(e)}")
            return None

    def update_wx_instance(self, wx_instance):
        """更新微信实例"""
        if wx_instance:
            self.wx = wx_instance
            logger.info("表情包处理器更新了微信实例")
        else:
            logger.warning("尝试更新表情包处理器的微信实例为空")

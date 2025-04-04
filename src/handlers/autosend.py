"""
自动发送消息处理模块
负责处理自动发送消息的逻辑，包括:
- 倒计时管理
- 消息发送
- 安静时间控制
"""

import logging
import random
import threading
from datetime import datetime, timedelta

logger = logging.getLogger('main')

class AutoSendHandler:
    def __init__(self, message_handler, config, listen_list):
        self.message_handler = message_handler
        self.config = config
        self.listen_list = listen_list
        
        # 计时器相关
        self.countdown_timer = None
        self.is_countdown_running = False
        self.countdown_end_time = None
        self.unanswered_count = 0
        self.last_chat_time = None

    def update_last_chat_time(self):
        """更新最后一次聊天时间"""
        self.last_chat_time = datetime.now()
        self.unanswered_count = 0
        logger.info(f"更新最后聊天时间: {self.last_chat_time}，重置未回复计数器为0")

    def is_quiet_time(self) -> bool:
        """检查当前是否在安静时间段内"""
        try:
            current_time = datetime.now().time()
            quiet_start = datetime.strptime(self.config.behavior.quiet_time.start, "%H:%M").time()
            quiet_end = datetime.strptime(self.config.behavior.quiet_time.end, "%H:%M").time()
            
            if quiet_start <= quiet_end:
                # 如果安静时间不跨天
                return quiet_start <= current_time <= quiet_end
            else:
                # 如果安静时间跨天（比如22:00到次日08:00）
                return current_time >= quiet_start or current_time <= quiet_end
        except Exception as e:
            logger.error(f"检查安静时间出错: {str(e)}")
            return False

    def get_random_countdown_time(self):
        """获取随机倒计时时间"""
        min_seconds = int(self.config.behavior.auto_message.min_hours * 3600)
        max_seconds = int(self.config.behavior.auto_message.max_hours * 3600)
        return random.uniform(min_seconds, max_seconds)

    def auto_send_message(self):
        """自动发送消息"""
        if self.is_quiet_time():
            logger.info("当前处于安静时间，跳过自动发送消息")
            self.start_countdown()
            return
            
        if self.listen_list:
            user_id = random.choice(self.listen_list)
            self.unanswered_count += 1
            reply_content = f"{self.config.behavior.auto_message.content} 这是对方第{self.unanswered_count}次未回复你, 你可以选择模拟对方未回复后的小脾气"
            logger.info(f"自动发送消息到 {user_id}: {reply_content}")
            try:
                self.message_handler.add_to_queue(
                    chat_id=user_id,
                    content=reply_content,
                    sender_name="System",
                    username="System",
                    is_group=False
                )
                self.start_countdown()
            except Exception as e:
                logger.error(f"自动发送消息失败: {str(e)}")
                self.start_countdown()
        else:
            logger.error("没有可用的聊天对象")
            self.start_countdown()

    def start_countdown(self):
        """开始新的倒计时"""
        if self.countdown_timer:
            self.countdown_timer.cancel()
        
        countdown_seconds = self.get_random_countdown_time()
        self.countdown_end_time = datetime.now() + timedelta(seconds=countdown_seconds)
        logger.info(f"开始新的倒计时: {countdown_seconds/3600:.2f}小时")
        
        self.countdown_timer = threading.Timer(countdown_seconds, self.auto_send_message)
        self.countdown_timer.daemon = True
        self.countdown_timer.start()
        self.is_countdown_running = True

    def stop(self):
        """停止自动发送消息"""
        if self.countdown_timer:
            self.countdown_timer.cancel()
            self.countdown_timer = None
        self.is_countdown_running = False
        logger.info("自动发送消息已停止") 
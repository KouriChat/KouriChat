"""
记忆处理模块
负责短期记忆和长期记忆的管理
"""

import os
import sqlite3
from datetime import datetime
import logging
from typing import List, Dict
import requests
import json

logger = logging.getLogger(__name__)


class MemoryHandler:
    def __init__(self, root_dir: str, api_endpoint: str):
        self.root_dir = root_dir
        self.api_endpoint = api_endpoint
        self.short_memory_path = os.path.join(root_dir, "data", "memory", "short_memory.txt")
        self.long_memory_path = os.path.join(root_dir, "data", "memory", "long_memory.db")

        # 初始化长期记忆数据库
        os.makedirs(os.path.dirname(self.long_memory_path), exist_ok=True)
        self._init_long_memory_db()

    def _init_long_memory_db(self):
        """初始化长期记忆数据库"""
        conn = sqlite3.connect(self.long_memory_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS memories
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      content TEXT,
                      weight REAL,
                      timestamp DATETIME)''')
        conn.commit()
        conn.close()

    def add_to_short_memory(self, user_msg: str, bot_reply: str):
        """添加消息到短期记忆"""
        try:
            with open(self.short_memory_path, "a", encoding="utf-8") as f:
                f.write(f"User: {user_msg}\nBot: {bot_reply}\n")

            # 检查是否达到15条
            with open(self.short_memory_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if len(lines) >= 30:  # 每条消息占2行
                    self.summarize_memories()
        except Exception as e:
            logger.error(f"写入短期记忆失败: {str(e)}")

    def summarize_memories(self):
        """调用API进行记忆提炼"""
        try:
            with open(self.short_memory_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 调用记忆提炼API
            response = requests.post(
                self.api_endpoint,
                json={"text": content},
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                result = response.json()
                summary = result.get("summary")
                weight = result.get("weight", 1.0)  # 默认权重

                # 存入长期记忆
                conn = sqlite3.connect(self.long_memory_path)
                c = conn.cursor()
                c.execute("INSERT INTO memories (content, weight, timestamp) VALUES (?, ?, ?)",
                          (summary, weight, datetime.now()))
                conn.commit()
                conn.close()

                # 清空短期记忆
                open(self.short_memory_path, "w").close()

        except Exception as e:
            logger.error(f"记忆提炼失败: {str(e)}")

    def get_relevant_memories(self, query: str, top_n: int = 3) -> List[Dict]:
        """从长期记忆中获取相关记忆"""
        try:
            conn = sqlite3.connect(self.long_memory_path)
            c = conn.cursor()

            # 简单关键词匹配（实际应使用更复杂的NLP处理）
            c.execute("SELECT content, weight FROM memories ORDER BY weight DESC")
            results = []
            for row in c.fetchall():
                if query in row[0]:
                    results.append({"content": row[0], "weight": row[1]})
                if len(results) >= top_n:
                    break

            conn.close()
            return results
        except Exception as e:
            logger.error(f"查询长期记忆失败: {str(e)}")
            return []
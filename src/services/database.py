"""
数据库服务模块
提供数据库相关功能，包括:
- 定义数据库模型
- 创建数据库连接
- 管理会话
- 存储聊天记录
"""

import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 创建基类
Base = declarative_base()

# 获取项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db_path = os.path.join(project_root, 'data', 'database', 'chat_history.db')

# 确保数据库目录存在
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# 创建数据库连接
engine = create_engine(f'sqlite:///{db_path}')

# 创建会话工厂
Session = sessionmaker(bind=engine)

class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(String(100))  # 发送者微信ID
    sender_name = Column(String(100))  # 发送者昵称
    message = Column(Text)  # 发送的消息
    reply = Column(Text)  # 机器人的回复
    created_at = Column(DateTime, default=datetime.now)

# 创建数据库表
Base.metadata.create_all(engine) 
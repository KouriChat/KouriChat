"""
数据库服务模块
提供数据库相关功能，包括:
- 定义数据库模型
- 创建数据库连接
- 管理会话
- 存储聊天记录
"""

import os
import logging
import sqlite3
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, inspect, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 获取logger
logger = logging.getLogger('main')

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
    is_group = Column(Boolean, default=False)  # 是否是群聊消息
    
    def __init__(self, sender_id=None, sender_name=None, message=None, reply=None, created_at=None, is_group=False):
        self.sender_id = sender_id
        self.sender_name = sender_name
        self.message = message
        self.reply = reply
        self.created_at = created_at or datetime.now()
        self.is_group = is_group

def ensure_table_structure():
    """确保数据库表结构与模型定义一致"""
    try:
        # 使用原生SQLite连接检查表结构
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            logger.info("chat_messages表不存在，将创建新表")
            Base.metadata.create_all(engine)
            conn.close()
            return
        
        # 获取现有列
        cursor.execute("PRAGMA table_info(chat_messages)")
        columns = cursor.fetchall()
        existing_columns = [col[1] for col in columns]
        logger.info(f"现有列: {existing_columns}")
        
        # 检查是否缺少列
        model_columns = [column.name for column in ChatMessage.__table__.columns]
        missing_columns = [col for col in model_columns if col not in existing_columns]
        
        if missing_columns:
            logger.info(f"发现缺少的列: {missing_columns}")
            
            # 添加缺少的列
            for column_name in missing_columns:
                column = ChatMessage.__table__.columns[column_name]
                column_type = str(column.type)
                
                # 处理默认值
                default_value = None
                if column.default:
                    default_value = column.default.arg
                    if isinstance(default_value, bool):
                        default_value = 1 if default_value else 0
                
                # 构建ALTER TABLE语句
                alter_stmt = f"ALTER TABLE chat_messages ADD COLUMN {column_name} {column_type}"
                if default_value is not None:
                    alter_stmt += f" DEFAULT {default_value}"
                
                logger.info(f"执行SQL: {alter_stmt}")
                cursor.execute(alter_stmt)
            
            conn.commit()
            logger.info("表结构更新完成")
        
        conn.close()
        
        # 重要：刷新SQLAlchemy的表元数据缓存
        # 这是解决问题的关键步骤
        logger.info("刷新SQLAlchemy元数据缓存")
        metadata = MetaData()
        metadata.reflect(bind=engine)
        if 'chat_messages' in metadata.tables:
            # 删除旧的表对象
            metadata.remove(metadata.tables['chat_messages'])
        
        # 重新绑定表
        Base.metadata.create_all(engine)
        
        # 验证表结构
        inspector = inspect(engine)
        actual_columns = [column['name'] for column in inspector.get_columns('chat_messages')]
        logger.info(f"更新后的表列: {actual_columns}")
        
        # 检查是否所有列都存在
        for column in model_columns:
            if column not in actual_columns:
                logger.error(f"列 {column} 在更新后仍然缺失!")
            else:
                logger.debug(f"列 {column} 已正确存在")
        
    except Exception as e:
        logger.error(f"确保表结构时出错: {str(e)}", exc_info=True)

# 确保表结构与模型定义一致
ensure_table_structure() 
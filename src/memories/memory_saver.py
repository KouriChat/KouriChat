import abc
import os
import sqlite3
import logging
from typing import List, Optional, Dict, Any

class MemorySaver(abc.ABC):
    """记忆存储器基类，定义了存储记忆的通用接口"""
    
    def __init__(self, table_name: str):
        """
        初始化记忆存储器
        :param table_name: 表名
        """
        self.table_name = table_name
    
    @abc.abstractmethod
    def setup(self):
        """创建必要的表结构"""
        pass
    
    @abc.abstractmethod
    def add(self, memory: str):
        """
        添加新的记忆
        :param memory: 记忆内容
        """
        pass
    
    @abc.abstractmethod
    def load(self) -> List[str]:
        """
        加载所有记忆
        :return: 记忆列表
        """
        pass
    
    @abc.abstractmethod
    def clear(self):
        """清除所有记忆"""
        pass


class SQLiteMemorySaver(MemorySaver):
    """SQLite实现的记忆存储器"""
    
    def __init__(self, table_name: str, db_path: str):
        """
        初始化SQLite记忆存储器
        :param table_name: 表名
        :param db_path: SQLite数据库文件路径
        """
        super().__init__(table_name)
        self.db_path = db_path
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.setup()
    
    def _get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def setup(self):
        """创建必要的表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            conn.commit()
    
    def add(self, memory: str):
        """添加新的记忆"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT INTO {self.table_name} (memory) VALUES (?)",
                (memory,)
            )
            conn.commit()
    
    def load(self) -> List[str]:
        """加载所有记忆"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT memory FROM {self.table_name} ORDER BY created_at ASC")
            return [row[0] for row in cursor.fetchall()]
    
    def clear(self):
        """清除所有记忆"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {self.table_name}")
            conn.commit()


class MySQLMemorySaver(MemorySaver):
    """MySQL实现的记忆存储器"""
    
    def __init__(self, table_name: str, db_config: Dict[str, Any]):
        """
        初始化MySQL记忆存储器
        :param table_name: 表名
        :param db_config: 数据库配置，包含host, port, user, password, database等
        """
        super().__init__(table_name)
        self.db_config = db_config
        self.setup()
        
    def _get_connection(self):
        """获取数据库连接"""
        try:
            # 尝试多种MySQL驱动
            # try:
            import mysql.connector
            return mysql.connector.connect(
                host=self.db_config.get('host', 'localhost'),
                port=self.db_config.get('port', 3306),
                user=self.db_config.get('user', 'root'),
                password=self.db_config.get('password', ''),
                database=self.db_config.get('database', '')
            )
            # 这里暂时注释，如果mysql-connector-python不存在，则使用pymysql
            # except ImportError:
            #     # 如果没有mysql-connector-python，尝试使用pymysql
            #     import pymysql
            #     return pymysql.connect(
            #         host=self.db_config.get('host', 'localhost'),
            #         port=self.db_config.get('port', 3306),
            #         user=self.db_config.get('user', 'root'),
            #         password=self.db_config.get('password', ''),
            #         database=self.db_config.get('database', '')
            #     )
        except ImportError:
            logging.error("请安装MySQL驱动: pip install mysql-connector-python 或 pip install pymysql")
            raise
    
    def setup(self):
        """创建必要的表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                memory TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            conn.commit()
    
    def add(self, memory: str):
        """添加新的记忆"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT INTO {self.table_name} (memory) VALUES (%s)",
                (memory,)
            )
            conn.commit()
    
    def load(self) -> List[str]:
        """加载所有记忆"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT memory FROM {self.table_name} ORDER BY created_at ASC")
            return [row[0] for row in cursor.fetchall()]
    
    def clear(self):
        """清除所有记忆"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {self.table_name}")
            conn.commit()


def create_memory_saver(table_name: str, config: Dict[str, Any]) -> MemorySaver:
    """
    创建记忆存储器实例
    :param table_name: 表名
    :param config: 配置信息
    :return: 记忆存储器实例
    """
    db_type = config.get('type', 'sqlite').lower()
    
    if db_type == 'sqlite':
        db_path = config.get('sqlite_path', './data/database/memory.db')
        return SQLiteMemorySaver(table_name, db_path)
    elif db_type == 'mysql':
        db_config = {
            'host': config.get('host', 'localhost'),
            'port': config.get('port', 3306),
            'user': config.get('user', 'root'),
            'password': config.get('password', ''),
            'database': config.get('database', '')
        }
        return MySQLMemorySaver(table_name, db_config)
    else:
        raise ValueError(f"不支持的数据库类型: {db_type}") 
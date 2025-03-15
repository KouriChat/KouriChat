"""
数据库修复脚本
用于修复数据库表结构，确保与模型定义一致
"""

import os
import sys
import sqlite3
import logging
from pathlib import Path
import shutil
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入数据库模型
from src.services.database import Base, engine, ChatMessage, db_path

def backup_database():
    """备份数据库文件"""
    if not os.path.exists(db_path):
        logger.warning(f"数据库文件不存在: {db_path}")
        return False
    
    backup_path = f"{db_path}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"数据库已备份到: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"备份数据库失败: {str(e)}")
        return False

def export_data():
    """导出数据库中的数据"""
    if not os.path.exists(db_path):
        logger.warning(f"数据库文件不存在: {db_path}")
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
        if cursor.fetchone() is None:
            logger.warning("chat_messages表不存在，无需导出数据")
            conn.close()
            return []
        
        # 获取表结构
        cursor.execute("PRAGMA table_info(chat_messages)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        logger.info(f"现有列: {column_names}")
        
        # 导出数据
        cursor.execute("SELECT * FROM chat_messages")
        rows = cursor.fetchall()
        logger.info(f"导出了 {len(rows)} 条记录")
        
        # 创建数据字典列表
        data = []
        for row in rows:
            record = {}
            for i, col_name in enumerate(column_names):
                record[col_name] = row[i]
            data.append(record)
        
        conn.close()
        return data
    
    except Exception as e:
        logger.error(f"导出数据失败: {str(e)}")
        return []

def recreate_table():
    """删除并重新创建表"""
    try:
        # 删除表
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
        if cursor.fetchone() is not None:
            cursor.execute("DROP TABLE chat_messages")
            logger.info("已删除chat_messages表")
        
        conn.close()
        
        # 使用SQLAlchemy重新创建表
        Base.metadata.create_all(engine)
        logger.info("已重新创建chat_messages表")
        
        return True
    
    except Exception as e:
        logger.error(f"重新创建表失败: {str(e)}")
        return False

def import_data(data):
    """导入数据到新表"""
    if not data:
        logger.info("没有数据需要导入")
        return True
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取新表结构
        cursor.execute("PRAGMA table_info(chat_messages)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        logger.info(f"新表列: {column_names}")
        
        # 准备导入数据
        imported_count = 0
        for record in data:
            # 过滤掉不在新表中的列
            filtered_record = {k: v for k, v in record.items() if k in column_names}
            
            # 确保is_group列有值
            if 'is_group' in column_names and 'is_group' not in filtered_record:
                filtered_record['is_group'] = 0
            
            # 构建INSERT语句
            columns_str = ', '.join(filtered_record.keys())
            placeholders = ', '.join(['?' for _ in filtered_record])
            values = list(filtered_record.values())
            
            sql = f"INSERT INTO chat_messages ({columns_str}) VALUES ({placeholders})"
            cursor.execute(sql, values)
            imported_count += 1
        
        conn.commit()
        logger.info(f"成功导入 {imported_count} 条记录")
        conn.close()
        
        return True
    
    except Exception as e:
        logger.error(f"导入数据失败: {str(e)}")
        return False

def verify_table_structure():
    """验证表结构是否与模型定义一致"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取表结构
        cursor.execute("PRAGMA table_info(chat_messages)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 获取模型定义的列
        model_columns = [column.name for column in ChatMessage.__table__.columns]
        
        # 检查是否所有模型列都在表中
        missing_columns = [col for col in model_columns if col not in column_names]
        if missing_columns:
            logger.error(f"表中缺少以下列: {missing_columns}")
            return False
        
        logger.info("表结构验证通过，所有列都存在")
        return True
    
    except Exception as e:
        logger.error(f"验证表结构失败: {str(e)}")
        return False

def fix_database():
    """修复数据库"""
    logger.info("开始修复数据库...")
    
    # 备份数据库
    if not backup_database():
        logger.warning("跳过备份，继续修复")
    
    # 导出数据
    data = export_data()
    
    # 重新创建表
    if not recreate_table():
        logger.error("重新创建表失败，修复中止")
        return False
    
    # 导入数据
    if not import_data(data):
        logger.error("导入数据失败，修复中止")
        return False
    
    # 验证表结构
    if not verify_table_structure():
        logger.error("表结构验证失败，可能需要手动检查")
        return False
    
    logger.info("数据库修复完成")
    return True

if __name__ == "__main__":
    fix_database() 
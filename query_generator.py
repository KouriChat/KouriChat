from datetime import datetime
from query_optimizer import optimize_query
import logging

# 获取logger
logger = logging.getLogger(__name__)

def generate_enhanced_query(context, user_message):
    """生成优化后的增强查询"""
    # 构建基本查询
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    query = f"(此时时间为{timestamp}) ta私聊对你说 {user_message}"
    
    # 添加上下文（如果有）
    if context:
        # 修改：使用更简洁的提示词
        query += f"(上次的对话内容，只是提醒)"
    
    # 优化查询
    optimized_query = optimize_query(query)
    
    # 使用优化后的日志输出函数
    from logger_config import log_enhanced_query
    log_enhanced_query(optimized_query)
    
    return optimized_query 
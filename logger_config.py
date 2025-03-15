import time
import logging

# 获取或创建logger
logger = logging.getLogger(__name__)

def retry_with_exponential_backoff(func, max_retries=3, initial_delay=1):
    """指数退避重试函数"""
    def wrapper(*args, **kwargs):
        delay = initial_delay
        last_exception = None
        
        for retry in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if retry < max_retries - 1:
                    logger.info(f"操作失败，{delay}秒后重试 ({retry+1}/{max_retries})...")
                    time.sleep(delay)
                    delay *= 2
        
        logger.error(f"操作失败，已达到最大重试次数: {str(last_exception)}")
        raise last_exception
    
    return wrapper 

def log_enhanced_query(query):
    """优化增强查询的日志输出"""
    # 如果查询过长，截断显示
    max_log_length = 100
    if len(query) > max_log_length:
        truncated_query = query[:max_log_length] + "...[截断]"
        logger.info(f"执行增强查询: '{truncated_query}'")
    else:
        logger.info(f"执行增强查询: '{query}'") 
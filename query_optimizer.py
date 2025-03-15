def optimize_query(query):
    """优化增强查询，移除冗余内容"""
    # 移除重复的提示文本
    redundant_patterns = [
        r'\(上次的对话内容，只是提醒，无需进行互动，处理重点请放在后面的新内容\)+'
    ]
    
    optimized_query = query
    for pattern in redundant_patterns:
        import re
        optimized_query = re.sub(pattern, '(上次的对话内容，只是提醒)', optimized_query)
    
    # 限制查询长度
    max_length = 1000
    if len(optimized_query) > max_length:
        optimized_query = optimized_query[:max_length] + "..."
    
    return optimized_query 
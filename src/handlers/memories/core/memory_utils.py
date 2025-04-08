"""
记忆核心工具函数 - 提供基础的记忆处理功能
"""
import os
import re
import functools
import logging
import json
from typing import Dict, List, Any, Optional, Tuple, Union, Callable

# 设置日志
logger = logging.getLogger('main')

# 缓存装饰器
def memory_cache(func):
    """
    记忆缓存装饰器 - 用于缓存记忆相关操作
    
    Args:
        func: 需要缓存的函数
        
    Returns:
        装饰后的函数
    """
    cache = {}
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 创建缓存键
        key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
        
        # 检查缓存
        if key in cache:
            logger.debug(f"从缓存获取结果: {key}")
            return cache[key]
            
        # 执行函数
        result = await func(*args, **kwargs)
        
        # 缓存结果
        cache[key] = result
        
        # 限制缓存大小
        if len(cache) > 100:
            # 删除最旧的项
            oldest_key = next(iter(cache))
            del cache[oldest_key]
            
        return result
        
    return wrapper

def get_memory_path(root_dir: str) -> str:
    """
    获取记忆文件路径
    
    Args:
        root_dir: 根目录路径
        
    Returns:
        str: 记忆文件路径
    """
    try:
        from src.config import config
        
        # 获取当前角色目录
        current_avatar = config.behavior.context.avatar_dir
        if not current_avatar:
            logger.error("未设置当前角色")
            return os.path.join(root_dir, "data", "memory", "memory.json")
            
        # 构建角色专属目录路径
        avatar_dir = os.path.join(root_dir, 'data', 'avatars', current_avatar)
        
        # 确保目录存在
        os.makedirs(avatar_dir, exist_ok=True)
        
        memory_path = os.path.join(avatar_dir, "memory.json")
        
        # 如果记忆文件不存在，创建空的记忆文件
        if not os.path.exists(memory_path):
            with open(memory_path, 'w', encoding='utf-8') as f:
                json.dump({"memories": {}, "embeddings": {}}, f, ensure_ascii=False, indent=2)
            logger.info(f"为角色 {current_avatar} 创建新的记忆文件")
            
        return memory_path
    except Exception as e:
        logger.error(f"获取记忆文件路径失败: {str(e)}")
        # 如果出错，返回默认路径
        return os.path.join(root_dir, "data", "memory", "memory.json")

def clean_memory_content(key: str, value: str) -> Tuple[str, str]:
    """
    清理记忆内容，去除无关字符和格式化
    
    Args:
        key: 用户消息
        value: 助手回复
        
    Returns:
        Tuple[str, str]: 清理后的用户消息和助手回复
    """
    try:
        # 基本清理
        user_message = key.strip() if isinstance(key, str) else "" if key is None else str(key)
        ai_reply = value.strip() if isinstance(value, str) else "" if value is None else str(value)
        
        # 系统提示词过滤规则
        system_prompts = [
            # 基础提示词
            r'请注意保持自然的回复长度，与用户消息风格协调。',
            r'请用.*?的语气回复',
            r'请用.*?的风格回复',
            r'请扮演.*?回复',
            r'请模仿.*?回复',
            r'请用.*?的性格回复',
            r'记住你现在是.*?',
            r'你现在是.*?',
            r'你扮演的是.*?',
            r'请控制回复长度在.*?字以内',
            r'请简短回复，控制在.*?内',
            r'请在.*?字内回复',
            
            # 历史记录和上下文提示
            r'以下是之前的对话记录：.*?来的新内容\)',
            r'\(以上是历史对话内容.*?专注处理接下来的新内容\)',
            r'以下是相关记忆内容：.*?请结合这些记忆来回答用户的问题。',
            r'对话\d+:\n用户:.*?\nAI:.*?',
            
            # 时间戳和对话标识
            r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?\].*?说[：:]\s*',
            r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?\]\[.*?\] ：',  # 新格式: [timestamp][username] ：
            r'\(此时时间为\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?\)\s*',
            r'ta(?:\s*)私聊(?:\s*)对(?:\s*)你(?:\s*)说(?:：|:)?\s*',
            r'ta(?:\s*)在群聊里(?:\s*)对(?:\s*)你(?:\s*)说(?:：|:)?\s*',
            
            # 系统标签和指令
            r'<.*?>.*?</.*?>',  # HTML标签
            r'\[系统提示\].*?\[/系统提示\]',
            r'\[系统\].*?\[/系统\]',
            r'\[提示\].*?\[/提示\]',
            r'\[系统指令\].*?(?:\[/系统指令\]|\n)',
            r'</think>.*?$',  # 思考过程标记
            r'<think>.*?</think>',  # Gemini 2.5 Pro思考过程标记
            
            # 角色设定和规则
            r'character\.json的设定如下.*?(?=\n)',
            r'你必须遵守以下规则：.*?(?=\n)',
            r'请记住以下设定：.*?(?=\n)',
            r'你需要遵循以下规则：.*?(?=\n)',
            r'请严格按照以下规则回复：.*?(?=\n)',
            r'请以你的身份回应用户的结束语。',
            
            # 长度和风格控制
            r'\n\n请注意：你的回复应当与用户消息的长度相当，控制在约\d+个字符和\d+个句子左右。',
            r'\n\n请简短回复，控制在一两句话内。',
            r'\n\n请注意保持自然的回复长度，与用户消息风格协调。',
            r'\n\n请保持简洁明了的回复。',
            
            # 其他系统提示
            r'请你回应用户的结束语',
            r'根据我的记忆，我们之前聊过这些内容：.*?(?=\n)',
            r'还有\d+条相关记忆',
            
            # 记忆编号标记 - 使用更严格的规则
            r'\s*memory_number:.*?$',  # 移除memory_number及之后所有内容到行尾
            r'\s*memory_number:.*',    # 移除整行包含memory_number的内容
        ]
        
        # 应用所有过滤规则
        for pattern in system_prompts:
            user_message = re.sub(pattern, '', user_message, flags=re.DOTALL|re.IGNORECASE)
            ai_reply = re.sub(pattern, '', ai_reply, flags=re.DOTALL|re.IGNORECASE)
        
        # 移除其它特殊指令和标记
        user_message = remove_special_instructions(user_message)
        ai_reply = remove_special_instructions(ai_reply)
        
        # 注意：保留$符号，它用于分隔记忆键的不同部分
        
        # 移除多余的空白字符，但保留$符号两侧的空格以便于格式化
        user_message = re.sub(r'(?<!\$)\s+(?!\$)', ' ', user_message).strip()
        ai_reply = re.sub(r'(?<!\$)\s+(?!\$)', ' ', ai_reply).strip()
        
        # 美化$符号格式，确保两边有空格
        user_message = re.sub(r'\s*\$\s*', ' $ ', user_message)
        ai_reply = re.sub(r'\s*\$\s*', ' $ ', ai_reply)
        
        # 截断过长的内容
        if len(user_message) > 500:
            user_message = user_message[:497] + "..."
        if len(ai_reply) > 500:
            ai_reply = ai_reply[:497] + "..."
            
        return user_message, ai_reply
    except Exception as e:
        logger.error(f"清理记忆内容失败: {str(e)}")
        return key, value

def remove_special_instructions(text: str) -> str:
    """
    移除特殊指令和标记
    
    Args:
        text: 输入文本
        
    Returns:
        str: 清理后的文本
    """
    try:
        # 移除Markdown代码块
        text = re.sub(r'```[a-zA-Z]*\n[\s\S]*?\n```', '', text)
        
        # 移除思考过程标记 (DeepSeek-r1和Gemini 2.5 Pro格式)
        text = re.sub(r'</think>.*?$', '', text, flags=re.DOTALL)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 移除HTML标签
        text = re.sub(r'<[^>]*>', '', text)
        
        # 移除系统指令模式
        text = re.sub(r'\[系统指令\].*?(\[\/系统指令\]|\n)', '', text)
        
        # 移除URL
        text = re.sub(r'https?://\S+', '[链接]', text)
        
        # 移除多余的空行
        text = re.sub(r'\n\s*\n', '\n', text)
        
        return text.strip()
    except Exception as e:
        logger.error(f"移除特殊指令失败: {str(e)}")
        return text

def clean_dialog_memory(sender_text: str, receiver_text: str) -> Tuple[str, str]:
    """
    清理对话记忆，专用于格式化对话内容
    
    Args:
        sender_text: 发送者文本
        receiver_text: 接收者文本
        
    Returns:
        Tuple[str, str]: 清理后的发送者和接收者文本
    """
    try:
        # 基本清理
        sender_clean = sender_text.strip()
        receiver_clean = receiver_text.strip()
        
        # 移除角色名前缀 (例如: "用户: ", "助手: ")
        sender_clean = re.sub(r'^[^:：]*[：:]\s*', '', sender_clean)
        receiver_clean = re.sub(r'^[^:：]*[：:]\s*', '', receiver_clean)
        
        # 移除特殊指令和标记
        sender_clean = remove_special_instructions(sender_clean)
        receiver_clean = remove_special_instructions(receiver_clean)
        
        return sender_clean, receiver_clean
    except Exception as e:
        logger.error(f"清理对话记忆失败: {str(e)}")
        return sender_text, receiver_text

def get_importance_keywords() -> List[str]:
    """
    获取表示重要性的关键词列表
    
    Returns:
        List[str]: 关键词列表
    """
    return [
        "记住", "牢记", "不要忘记", "重要", "必须", "一定要",
        "地址", "电话", "密码", "账号", "名字", "生日",
        "喜欢", "讨厌", "爱好", "兴趣","爱",
        "我的", "我是", "我要", "我想", "我们", "我们的"
    ] 
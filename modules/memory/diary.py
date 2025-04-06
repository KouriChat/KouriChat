"""
日记生成模块
根据最近15轮对话和用户选择的人设，生成一篇500字以内的日记。
可通过调试命令 /diary 触发。
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional
import random
from src.services.ai.llm_service import LLMService
from config import config
import re

logger = logging.getLogger('main')

class DiaryService:
    """
    日记服务模块，生成基于角色视角的日记
    功能：
    1. 从最近对话中提取内容
    2. 结合人设生成第一人称视角的日记
    3. 保存到文件并在聊天中输出
    """
    def __init__(self, root_dir: str, api_key: str, base_url: str, model: str, max_token: int, temperature: float):
        self.root_dir = root_dir
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_token = max_token
        self.temperature = temperature
        self.llm_client = None
    
    def _get_llm_client(self):
        """获取或创建LLM客户端"""
        if not self.llm_client:
            self.llm_client = LLMService(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                max_token=self.max_token,
                temperature=self.temperature,
                max_groups=5  # 这里只需要较小的上下文
            )
        return self.llm_client
    
    def _get_avatar_memory_dir(self, avatar_name: str) -> str:
        """获取角色记忆目录，如果不存在则创建"""
        avatar_memory_dir = os.path.join(self.root_dir, "data", "avatars", avatar_name, "memory")
        os.makedirs(avatar_memory_dir, exist_ok=True)
        return avatar_memory_dir
    
    def _get_short_memory_path(self, avatar_name: str) -> str:
        """获取短期记忆文件路径"""
        memory_dir = self._get_avatar_memory_dir(avatar_name)
        return os.path.join(memory_dir, "short_memory.json")
    
    def _get_avatar_prompt_path(self, avatar_name: str) -> str:
        """获取角色设定文件路径"""
        avatar_dir = os.path.join(self.root_dir, "data", "avatars", avatar_name)
        return os.path.join(avatar_dir, "avatar.md")
    
    def _get_diary_filename(self, avatar_name: str) -> str:
        """生成唯一的日记文件名"""
        memory_dir = self._get_avatar_memory_dir(avatar_name)
        date_str = datetime.now().strftime("%Y-%m-%d")
        base_filename = f"diary_{date_str}"
        
        # 检查是否已存在同名文件，如有需要添加序号
        index = 1
        filename = f"{base_filename}.txt"
        file_path = os.path.join(memory_dir, filename)
        
        while os.path.exists(file_path):
            filename = f"{base_filename}_{index}.txt"
            file_path = os.path.join(memory_dir, filename)
            index += 1
            
        return file_path
    
    def generate_diary(self, avatar_name: str) -> str:
        """
        根据最近对话和角色设定生成日记
        
        Args:
            avatar_name: 角色名称
            
        Returns:
            str: 生成的日记内容，如果发生错误则返回错误消息
        """
        try:
            # 读取短期记忆
            short_memory_path = self._get_short_memory_path(avatar_name)
            if not os.path.exists(short_memory_path):
                logger.error(f"短期记忆文件不存在: {short_memory_path}")
                return "无法找到最近的对话记录，无法生成日记。"
            
            try:
                with open(short_memory_path, "r", encoding="utf-8") as f:
                    short_memory = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"短期记忆文件格式错误: {str(e)}")
                return "对话记录格式错误，无法生成日记。"
            
            if not short_memory:
                logger.warning(f"短期记忆为空: {avatar_name}")
                return "最近没有进行过对话，无法生成日记。"
            
            # 读取角色设定
            avatar_prompt_path = self._get_avatar_prompt_path(avatar_name)
            if not os.path.exists(avatar_prompt_path):
                logger.error(f"角色设定文件不存在: {avatar_prompt_path}")
                return f"无法找到角色 {avatar_name} 的设定文件。"
            
            try:
                with open(avatar_prompt_path, "r", encoding="utf-8") as f:
                    avatar_prompt = f.read()
            except Exception as e:
                logger.error(f"读取角色设定文件失败: {str(e)}")
                return f"读取角色设定文件失败: {str(e)}"
            
            # 获取最近15轮对话（或全部，如果不足15轮）
            recent_conversations = "\n".join([
                f"用户: {conv.get('user', '')}\n"
                f"回复: {conv.get('bot', '')}" 
                for conv in short_memory[-15:]  # 使用最近15轮对话
            ])
            
            # 构建提示词
            current_date = datetime.now().strftime("%Y年%m月%d日")
            prompt = f"""请你以第一人称视角，根据我的角色设定和最近的对话内容，撰写一篇今日日记。

要求：
1. 严格控制在500字以内
2. 以我的角色设定为基础，用第一人称的视角撰写
3. 聚焦今天与用户的互动和感受
4. 可以适当提及昨日的事情作为上下文（如有需要）
5. 包含细节和感受心理活动，但不要过度想象不存在的情节
6. 日记应该有一个适合我的角色的语气和风格
7. 日记的开头应该为"小日记"和今天的日期: {current_date}
8. 结尾可以加入一些期许或者感想，或者写个角色的小秘密。
9. 必须是一段完整的日记，不要分段
10. 绝对不要使用任何符号如:($)或特殊符号来分隔文本,避免使用颜文字，应该为纯文本格式
11. 不要使用表情符号或表情标签(如[love]、[笑脸]等)
12. 确保内容简洁，避免冗长的描述
13. 确保是完整的句子，不要在句子中间断开

你的角色设定:
{avatar_prompt}

最近的对话内容:
{recent_conversations}

请直接以日记格式回复，不要有任何解释或前言。日记格式如下:
{avatar_name}小日记 {current_date}

[日记内容]
"""
            
            # 调用LLM生成日记
            llm = self._get_llm_client()
            diary_content = llm.get_response(
                message=prompt,
                user_id=str(f"diary_{avatar_name}"),
                system_prompt=f"你是一个专注于写作的AI助手。你的任务是以指定角色的第一人称视角，根据对话内容和角色设定，撰写一篇真实、情感丰富的日记。请确保日记以\"{avatar_name}小日记 {current_date}\"为标题，分成2个段落，段落之间使用空行分隔。绝对不要使用任何分行符号($)、表情符号或表情标签([love]等)。保持文本格式简洁，避免使用任何可能导致消息分割的特殊符号。"
            )
            
            # 格式化日记内容，确保段落之间有正确的空行
            diary_content = self._format_diary_content(diary_content, avatar_name)
            
            # 保存日记到文件
            diary_path = self._get_diary_filename(avatar_name)
            try:
                with open(diary_path, "w", encoding="utf-8") as f:
                    f.write(diary_content)
                logger.info(f"已生成{avatar_name}小日记并保存至: {diary_path}")
            except Exception as e:
                logger.error(f"保存日记文件失败: {str(e)}")
                return f"日记生成成功但保存失败: {str(e)}"
            
            return diary_content
            
        except Exception as e:
            error_msg = f"生成日记失败: {str(e)}"
            logger.error(error_msg)
            return f"日记生成失败喵！: {str(e)}"

    def _format_diary_content(self, content: str, avatar_name: str) -> str:
        """
        格式化日记内容，确保内容完整且格式正确
        
        Args:
            content: 原始日记内容
            avatar_name: 角色名称
            
        Returns:
            str: 格式化后的日记内容
        """
        if not content or not content.strip():
            return ""
            
        # 移除可能存在的多余空行和特殊字符
        lines = []
        for line in content.split('\n'):
            # 清理每行内容
            line = line.strip()
            # 移除特殊字符和表情符号
            line = re.sub(r'\[.*?\]', '', line)  # 移除表情标签
            line = re.sub(r'[^\w\s\u4e00-\u9fff，。！？、：；""''（）【】《》\n]', '', line)  # 只保留中文、英文、数字和基本标点
            if line:
                lines.append(line)
        
        if not lines:
            return ""
            
        # 合并所有行为一个段落
        diary_content = ' '.join(lines)
        
        # 确保标题和内容之间有一个空行
        if diary_content.startswith(f"{avatar_name}小日记"):
            parts = diary_content.split('\n', 1)
            if len(parts) > 1:
                diary_content = f"{parts[0]}\n\n{parts[1]}"
        
        # 将内容按句子分割
        sentences = re.split(r'([。！？])', diary_content)
        
        # 重新组织内容，每3-5句话一行
        formatted_lines = []
        current_line = []
        sentence_count = 0
        
        for i in range(0, len(sentences), 2):
            if i + 1 < len(sentences):
                sentence = sentences[i] + sentences[i + 1]
            else:
                sentence = sentences[i]
            
            current_line.append(sentence)
            sentence_count += 1
            
            # 每3-5句话换行
            if sentence_count >= random.randint(3, 5) or i + 2 >= len(sentences):
                formatted_lines.append(''.join(current_line))
                current_line = []
                sentence_count = 0
        
        # 合并所有行
        diary_content = '\n'.join(formatted_lines)
        
        return diary_content 

"""
内容生成模块
根据最近对话和用户选择的人设，生成各种类型的内容。

支持的命令：
- /diary - 生成角色日记
- /state - 查看角色状态
- /letter - 角色给你写的信
- /list - 角色的备忘录
- /pyq - 角色的朋友圈
- /gift - 角色想送的礼物
- /shopping - 角色的购物清单
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import random
from src.services.ai.llm_service import LLMService
from data.config import config
import re

logger = logging.getLogger('main')


class ContentGenerator:
    """
    内容生成服务模块，生成基于角色视角的各种内容
    功能：
    1. 从最近对话中提取内容
    2. 结合人设生成各种类型的内容
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

        # 支持的内容类型及其配置
        self.content_types = {
            'diary': {'max_rounds': 15, 'command': '/diary'},
            'state': {'max_rounds': 10, 'command': '/state'},
            'letter': {'max_rounds': 10, 'command': '/letter'},
            'list': {'max_rounds': 10, 'command': '/list'},
            'pyq': {'max_rounds': 8, 'command': '/pyq'},
            'gift': {'max_rounds': 10, 'command': '/gift'},
            'shopping': {'max_rounds': 8, 'command': '/shopping'}
        }

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

    def _get_avatar_memory_dir(self, avatar_name: str, user_id: str) -> str:
        """获取角色记忆目录，如果不存在则创建"""
        avatar_memory_dir = os.path.join(self.root_dir, "data", "avatars", avatar_name, "memory", user_id)
        os.makedirs(avatar_memory_dir, exist_ok=True)
        return avatar_memory_dir

    def _get_short_memory_path(self, avatar_name: str, user_id: str) -> str:
        """获取短期记忆文件路径"""
        memory_dir = self._get_avatar_memory_dir(avatar_name, user_id)
        return os.path.join(memory_dir, "short_memory.json")

    def _get_avatar_prompt_path(self, avatar_name: str) -> str:
        """获取角色设定文件路径"""
        avatar_dir = os.path.join(self.root_dir, "data", "avatars", avatar_name)
        return os.path.join(avatar_dir, "avatar.md")

    def _get_content_filename(self, content_type: str, avatar_name: str, user_id: str) -> str:
        """
        生成唯一的内容文件名

        Args:
            content_type: 内容类型，如 'diary', 'state', 'letter'
            avatar_name: 角色名称
            user_id: 用户ID

        Returns:
            str: 生成的文件路径
        """
        # 获取基本记忆目录
        base_memory_dir = self._get_avatar_memory_dir(avatar_name, user_id)

        # 判断是否为特殊内容类型（非日记）
        special_content_types = ['state', 'letter', 'list', 'pyq', 'gift', 'shopping']

        if content_type in special_content_types:
            # 如果是特殊内容类型，则创建并使用special_content子目录
            memory_dir = os.path.join(base_memory_dir, "special_content")
            # 确保目录存在
            os.makedirs(memory_dir, exist_ok=True)
            logger.debug(f"使用特殊内容目录: {memory_dir}")
        else:
            # 如果是日记或其他类型，使用原始目录
            memory_dir = base_memory_dir

        date_str = datetime.now().strftime("%Y-%m-%d")
        # 在文件名中体现内容类型和用户ID
        base_filename = f"{content_type}_{user_id}_{date_str}"

        # 检查是否已存在同名文件，如有需要添加序号
        index = 1
        filename = f"{base_filename}.txt"
        file_path = os.path.join(memory_dir, filename)

        while os.path.exists(file_path):
            filename = f"{base_filename}_{index}.txt"
            file_path = os.path.join(memory_dir, filename)
            index += 1

        return file_path

    def _get_diary_filename(self, avatar_name: str, user_id: str) -> str:
        """生成唯一的日记文件名（兼容旧版本）"""
        return self._get_content_filename('diary', avatar_name, user_id)

    def _get_prompt_content(self, prompt_type: str, avatar_name: str, user_id: str, max_rounds: int = 15) -> tuple:
        """
        获取生成提示词所需的内容

        Args:
            prompt_type: 提示词类型，如 'diary', 'state', 'letter'
            avatar_name: 角色名称
            user_id: 用户ID
            max_rounds: 最大对话轮数

        Returns:
            tuple: (角色设定, 最近对话, 提示词模板, 系统提示词) 如果发生错误则返回 (错误信息, None, None, None)
        """
        # 读取短期记忆
        short_memory_path = self._get_short_memory_path(avatar_name, user_id)
        if not os.path.exists(short_memory_path):
            error_msg = f"短期记忆文件不存在: {short_memory_path}"
            logger.error(error_msg)
            return (f"无法找到最近的对话记录，无法生成{prompt_type}。", None, None, None)

        try:
            with open(short_memory_path, "r", encoding="utf-8") as f:
                short_memory = json.load(f)
        except json.JSONDecodeError as e:
            error_msg = f"短期记忆文件格式错误: {str(e)}"
            logger.error(error_msg)
            return (f"对话记录格式错误，无法生成{prompt_type}。", None, None, None)

        if not short_memory:
            logger.warning(f"短期记忆为空: {avatar_name} 用户: {user_id}")
            return (f"最近没有进行过对话，无法生成{prompt_type}。", None, None, None)

        # 读取角色设定
        avatar_prompt_path = self._get_avatar_prompt_path(avatar_name)
        if not os.path.exists(avatar_prompt_path):
            error_msg = f"角色设定文件不存在: {avatar_prompt_path}"
            logger.error(error_msg)
            return (f"无法找到角色 {avatar_name} 的设定文件。", None, None, None)

        try:
            with open(avatar_prompt_path, "r", encoding="utf-8") as f:
                avatar_prompt = f.read()
        except Exception as e:
            error_msg = f"读取角色设定文件失败: {str(e)}"
            logger.error(error_msg)
            return (f"读取角色设定文件失败: {str(e)}", None, None, None)

        # 获取最近对话（或全部，如果不足指定轮数）
        recent_conversations = "\n".join([
            f"用户: {conv.get('user', '')}\n"
            f"回复: {conv.get('bot', '')}"
            for conv in short_memory[-max_rounds:]  # 使用最近max_rounds轮对话
        ])

        # 读取外部提示词
        try:
            # 从当前文件位置获取项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))

            # 读取提示词
            prompt_path = os.path.join(project_root, "src", "base", "prompts", f"{prompt_type}.md")
            if not os.path.exists(prompt_path):
                error_msg = f"{prompt_type}提示词文件不存在: {prompt_path}"
                logger.error(error_msg)
                return (f"{prompt_type}提示词文件不存在，无法生成{prompt_type}。", None, None, None)

            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read().strip()
                logger.debug(f"已加载{prompt_type}提示词模板，长度: {len(prompt_template)} 字节")

            # 使用相同的提示词作为系统提示词
            system_prompt = prompt_template

            # 根据内容类型设置默认系统提示词
            # 使用通用的系统提示词模板，包含变量
            system_prompt = f"你是一个专注于角色扮演的AI助手。你的任务是以{avatar_name}的身份，根据对话内容和角色设定，生成内容。请确保内容符合角色的语气和风格，不要添加任何不必要的解释。绝对不要使用任何分行符号($)、表情符号或表情标签([love]等)。保持文本格式简洁，避免使用任何可能导致消息分割的特殊符号。"

            return (avatar_prompt, recent_conversations, prompt_template, system_prompt)

        except Exception as e:
            error_msg = f"读取{prompt_type}提示词模板失败: {str(e)}"
            logger.error(error_msg)
            return (f"读取{prompt_type}提示词模板失败，无法生成{prompt_type}: {str(e)}", None, None, None)

    def _generate_content(self, content_type: str, avatar_name: str, user_id: str, max_rounds: int = 15,
                          save_to_file: bool = True) -> str:
        """
        通用内容生成方法，可用于生成各种类型的内容

        Args:
            content_type: 内容类型，如 'diary', 'state', 'letter'
            avatar_name: 角色名称
            user_id: 用户ID
            max_rounds: 最大对话轮数
            save_to_file: 是否保存到文件，默认为 True

        Returns:
            str: 生成的内容，如果发生错误则返回错误消息
        """
        try:
            # 使用通用方法获取提示词内容
            result = self._get_prompt_content(content_type, avatar_name, user_id, max_rounds)
            if result[1] is None:  # 如果发生错误
                return result[0]  # 返回错误信息

            avatar_prompt, recent_conversations, prompt_template, system_prompt = result

            # 根据内容类型设置特定变量
            now = datetime.now()
            current_date = now.strftime("%Y年%m月%d日")
            current_time = now.strftime("%H:%M")

            content_type_info = {
                'diary': {
                    'format_name': '日记',
                    'time_info': f"{current_date}"
                },
                'state': {
                    'format_name': '状态栏',
                    'time_info': f"{current_date} {current_time}"
                },
                'letter': {
                    'format_name': '信件或备忘录',
                    'time_info': f"{current_date}"
                },
                'list': {
                    'format_name': '备忘录',
                    'time_info': f"{current_date}"
                },
                'pyq': {
                    'format_name': '朋友圈',
                    'time_info': f"{current_date} {current_time}"
                },
                'gift': {
                    'format_name': '礼物',
                    'time_info': f"{current_date}"
                },
                'shopping': {
                    'format_name': '购物清单',
                    'time_info': f"{current_date}"
                }
            }

            if content_type not in content_type_info:
                return f"不支持的内容类型: {content_type}"

            info = content_type_info[content_type]

            # 准备变量字典，用于替换提示词模板中的变量
            # 获取更多时间格式
            now = datetime.now()
            year = now.strftime("%Y")
            month = now.strftime("%m")
            day = now.strftime("%d")
            weekday = now.strftime("%A")
            weekday_cn = {
                'Monday': '星期一',
                'Tuesday': '星期二',
                'Wednesday': '星期三',
                'Thursday': '星期四',
                'Friday': '星期五',
                'Saturday': '星期六',
                'Sunday': '星期日'
            }.get(weekday, weekday)
            hour = now.strftime("%H")
            minute = now.strftime("%M")
            second = now.strftime("%S")

            # 中文日期格式
            year_cn = f"{year}年"
            month_cn = f"{int(month)}月"
            day_cn = f"{int(day)}日"
            date_cn = f"{year_cn}{month_cn}{day_cn}"
            date_cn_short = f"{month_cn}{day_cn}"
            time_cn = f"{hour}时{minute}分"

            # 其他格式
            date_ymd = f"{year}-{month}-{day}"
            date_mdy = f"{month}/{day}/{year}"
            time_hm = f"{hour}:{minute}"
            time_hms = f"{hour}:{minute}:{second}"

            # 初始化用户相关变量
            user_name = user_id  # 默认使用user_id

            # 尝试从用户配置文件中获取用户信息
            try:
                user_config_path = os.path.join(self.root_dir, "data", "users", f"{user_id}.json")
                if os.path.exists(user_config_path):
                    with open(user_config_path, "r", encoding="utf-8") as f:
                        user_config = json.load(f)

                        # 获取用户名
                        if "name" in user_config:
                            user_name = user_config["name"]
                        elif "nickname" in user_config:
                            user_name = user_config["nickname"]
            except Exception as e:
                logger.warning(f"获取用户信息失败: {str(e)}")

            variables = {
                # 角色相关
                'avatar_name': avatar_name,
                'format_name': info['format_name'],

                # 用户相关
                'user_id': user_id,
                'user_name': user_name,  # 使用获取到的用户名

                # 基本时间
                'current_date': current_date,
                'current_time': current_time,
                'time_info': info['time_info'],

                # 日期组件
                'year': year,
                'month': month,
                'day': day,
                'weekday': weekday,
                'weekday_cn': weekday_cn,
                'hour': hour,
                'minute': minute,
                'second': second,

                # 中文日期
                'year_cn': year_cn,
                'month_cn': month_cn,
                'day_cn': day_cn,
                'date_cn': date_cn,
                'date_cn_short': date_cn_short,
                'time_cn': time_cn,

                # 其他格式
                'date_ymd': date_ymd,
                'date_mdy': date_mdy,
                'time_hm': time_hm,
                'time_hms': time_hms
            }

            # 替换提示词模板中的变量
            template_with_vars = prompt_template
            for var_name, var_value in variables.items():
                # 确保变量值不为 None
                if var_value is None:
                    var_value = ""
                template_with_vars = template_with_vars.replace('{' + var_name + '}', str(var_value))

            # 构建完整的提示词
            prompt = f"""你的角色设定:\n{avatar_prompt}\n\n最近的对话内容:\n{recent_conversations}\n\n当前时间: {info['time_info']}\n{template_with_vars}\n\n请直接以{info['format_name']}格式回复，不要有任何解释或前言。"""

            # 在系统提示词中替换变量
            for var_name, var_value in variables.items():
                # 确保变量值不为 None
                if var_value is None:
                    var_value = ""
                system_prompt = system_prompt.replace('{' + var_name + '}', str(var_value))

            # 调用LLM生成内容
            llm = self._get_llm_client()
            client_id = f"{content_type}_{avatar_name}_{user_id}"
            generated_content = llm.get_response(
                message=prompt,
                user_id=client_id,
                system_prompt=system_prompt
            )

            logger.debug(generated_content)

            # 检查是否为错误响应
            if generated_content.startswith("Error:"):
                logger.error(f"生成{content_type}内容时出现错误: {generated_content}")
                return f"{content_type}生成失败：{generated_content}"

            # 格式化内容
            # 使用通用的格式化方法，传入内容类型和角色名称
            formatted_content = self._format_content(generated_content, content_type, avatar_name)

            # 如果需要保存到文件
            if save_to_file:
                # 使用通用的文件名生成方法
                # 该方法会根据内容类型自动选择适当的目录
                file_path = self._get_content_filename(content_type, avatar_name, user_id)

                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(formatted_content)
                    logger.info(
                        f"已生成{avatar_name}{content_type_info[content_type]['format_name']} 用户: {user_id} 并保存至: {file_path}")
                except Exception as e:
                    logger.error(f"保存{content_type}文件失败: {str(e)}")
                    return f"{content_type}生成成功但保存失败: {str(e)}"

            return formatted_content

        except Exception as e:
            error_msg = f"生成{content_type}失败: {str(e)}"
            logger.error(error_msg)
            return f"{content_type}生成失败: {str(e)}"

    def _generate_content_wrapper(self, content_type: str, avatar_name: str, user_id: str, max_rounds: int,
                                  save_to_file: bool = True) -> str:
        """
        生成内容的通用包装方法

        Args:
            content_type: 内容类型，如 'diary', 'state', 'letter'
            avatar_name: 角色名称
            user_id: 用户ID，用于获取特定用户的记忆
            max_rounds: 最大对话轮数
            save_to_file: 是否保存到文件，默认为 True

        Returns:
            str: 生成的内容，如果发生错误则返回错误消息
        """
        return self._generate_content(content_type, avatar_name, user_id, max_rounds, save_to_file)

    def generate_diary(self, avatar_name: str, user_id: str, save_to_file: bool = True) -> str:
        """生成角色日记"""
        return self._generate_content_wrapper('diary', avatar_name, user_id, 15, save_to_file)

    def generate_state(self, avatar_name: str, user_id: str, save_to_file: bool = True) -> str:
        """生成角色状态信息"""
        return self._generate_content_wrapper('state', avatar_name, user_id, 10, save_to_file)

    def generate_letter(self, avatar_name: str, user_id: str, save_to_file: bool = True) -> str:
        """生成角色给用户写的信"""
        return self._generate_content_wrapper('letter', avatar_name, user_id, 10, save_to_file)

    def generate_list(self, avatar_name: str, user_id: str, save_to_file: bool = True) -> str:
        """生成角色的备忘录"""
        return self._generate_content_wrapper('list', avatar_name, user_id, 10, save_to_file)

    def generate_pyq(self, avatar_name: str, user_id: str, save_to_file: bool = True) -> str:
        """生成角色的朋友圈"""
        return self._generate_content_wrapper('pyq', avatar_name, user_id, 8, save_to_file)

    def generate_gift(self, avatar_name: str, user_id: str, save_to_file: bool = True) -> str:
        """生成角色想送的礼物"""
        return self._generate_content_wrapper('gift', avatar_name, user_id, 10, save_to_file)

    def generate_shopping(self, avatar_name: str, user_id: str, save_to_file: bool = True) -> str:
        """生成角色的购物清单"""
        return self._generate_content_wrapper('shopping', avatar_name, user_id, 8, save_to_file)

    def _clean_text(self, content: str, content_type: str = None) -> list:
        """
        清理文本，移除特殊字符和表情符号

        Args:
            content: 原始内容
            content_type: 内容类型，如 'diary'，用于应用特定的清洗规则

        Returns:
            list: 清理后的行列表
        """
        if not content or not content.strip():
            return []

        # 移除可能存在的多余空行和特殊字符
        lines = []

        # 日记类型使用严格清洗，其他类型保留原有格式
        if content_type == 'diary':
            # 日记使用严格清洗
            for line in content.split('\n'):
                # 清理每行内容
                line = line.strip()
                # 移除特殊字符和表情符号
                line = re.sub(r'\[.*?\]', '', line)  # 移除表情标签
                line = re.sub(r'[^\w\s\u4e00-\u9fff，。！？、：；""''（）【】《》\n]', '', line)  # 只保留中文、英文、数字和基本标点
                if line:
                    lines.append(line)
        else:
            # 非日记类型保留原有格式和换行
            # 先将/n替换为临时标记，以便在分割行后保留用户自定义的换行
            content_with_markers = content.replace('/n', '{{NEWLINE}}')

            for line in content_with_markers.split('\n'):
                # 只移除表情标签，保留其他格式
                line = re.sub(r'\[.*?\]', '', line)  # 移除表情标签
                # 不去除行首尾空白，保留原始格式
                # 将临时标记还原为/n，以便在后续处理中转换为真正的换行符
                line = line.replace('{{NEWLINE}}', '/n')
                # 过滤掉$字符，防止消息被分割
                line = line.replace('$', '')
                line = line.replace('＄', '')  # 全角$符号
                lines.append(line)

        return lines

    def _format_content(self, content: str, content_type: str = None, avatar_name: str = None) -> str:
        """
        格式化内容，确保内容完整且格式正确

        Args:
            content: 原始内容
            content_type: 内容类型，如 'diary'，用于应用特定的格式化规则
            avatar_name: 角色名称，用于日记格式化

        Returns:
            str: 格式化后的内容
        """
        if not content or not content.strip():
            return ""

        return self._format_content_with_paragraphs(content, content_type)

    def _format_diary_content_with_sentences(self, content: str, avatar_name: str) -> str:
        """
        使用基于句子的方式格式化日记内容

        Args:
            content: 原始内容
            avatar_name: 角色名称

        Returns:
            str: 格式化后的内容
        """
        lines = self._clean_text(content, 'diary')
        if not lines:
            return ""

        # 合并所有行为一个段落
        formatted_content = ' '.join(lines)

        # 确保标题和内容之间有一个空行
        if formatted_content.startswith(f"{avatar_name}小日记"):
            parts = formatted_content.split('\n', 1)
            if len(parts) > 1:
                formatted_content = f"{parts[0]}\n\n{parts[1]}"

        # 将内容按句子分割
        sentences = re.split(r'([。！？])', formatted_content)

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
        return '\n'.join(formatted_lines)

    def _format_content_with_paragraphs(self, content: str, content_type: str) -> str:
        """
        保留原始换行符的格式化方法，适用于非日记内容

        Args:
            content: 原始内容
            content_type: 内容类型

        Returns:
            str: 格式化后的内容
        """
        content = content
        content = content.replace('$', ',')
        content = content.replace('＄', ',')
        return content

    def _format_diary_content(self, content: str, avatar_name: str) -> str:
        """格式化日记内容（兼容旧版本）"""
        return self._format_content(content, 'diary', avatar_name)

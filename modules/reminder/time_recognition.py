"""
时间识别服务
负责识别消息中的时间信息和提醒意图
"""

import json
import logging
from datetime import datetime
from typing import Optional, Tuple

# 在文件开头添加日志器声明
import logging
logger = logging.getLogger('main')

"""
整合 src/services/ai/time_recognition_service 的功能
"""
from datetime import datetime
import dateparser

class TimeRecognitionService:
    def __init__(self):
        self._configure_dateparser()
    
    def _configure_dateparser(self):
        dateparser.conf.settings.REPLACE_TIMEZONE = "Asia/Shanghai"
        dateparser.conf.settings.PREFER_DATES_FROM = "future"
    
    def parse_time(self, text: str) -> datetime:
        try:
            return dateparser.parse(
                text,
                languages=['zh'],
                settings={'PREFER_DAY_OF_MONTH': 'first'}
            )
        except Exception as e:
            logger.error(f"时间解析失败: {str(e)}")
            return None

    def __init__(self, llm_service):
        """
        初始化时间识别服务
        Args:
            llm_service: LLM服务实例，用于时间识别
        """
        self.llm_service = llm_service
        self._load_prompts()

    def _load_prompts(self):
        """加载提示词模板"""
        self.system_prompt = """你是一个时间识别助手。你的任务只是分析消息中的时间信息，不需要回复用户。

判断标准：
1. 消息必须明确表达"提醒"、"叫我"、"记得"等提醒意图
2. 消息必须包含具体或相对的时间信息
3. 返回的时间必须是未来的时间点
4. 用户提到模糊的时间，比如我去洗个澡，吃个饭，不应该创建任务，返回:NOT_TIME_RELATED
5. 必须包含具体的时间和具体的提示内容才应该创建提示任务，否则返回:NOT_TIME_RELATED
你必须严格按照以下JSON格式返回，不要添加任何其他内容：
{
    "reminders": [
        {
            "target_time": "YYYY-MM-DD HH:mm:ss",
            "reminder_content": "提醒内容"
        }
    ]
}

示例：
输入: "三分钟后叫我"
输出:
{
    "reminders": [
        {
            "target_time": "2024-03-16 17:42:00",
            "reminder_content": "叫我"
        }
    ]
}

输入: "三分钟后提醒我喝水，五分钟后提醒我吃饭"
输出:
{
    "reminders": [
        {
            "target_time": "2024-03-16 17:42:00",
            "reminder_content": "喝水"
        },
        {
            "target_time": "2024-03-16 17:44:00",
            "reminder_content": "吃饭"
        }
    ]
}

注意事项：
1. 时间必须是24小时制
2. 日期格式必须是 YYYY-MM-DD
3. 如果只提到时间没提到日期，默认是今天或明天（取决于当前时间）
4. 相对时间（如"三分钟后"）需要转换为具体时间点
5. 时间点必须在当前时间之后
6. 必须严格按照JSON格式返回，不要添加任何额外文字
7. 如果不是提醒请求，只返回：NOT_TIME_RELATED

记住：你的回复必须是纯JSON格式或NOT_TIME_RELATED，不要包含任何其他内容。"""

    def _parse_response(self, response: str) -> Optional[list]:
        """
        解析API响应，支持多个提醒
        Args:
            response: API返回的JSON字符串
        Returns:
            Optional[list]: [(目标时间, 提醒内容), ...] 或 None
        """
        try:
            result = json.loads(response)
            if "reminders" not in result:
                return None
                
            reminders = []
            for reminder in result["reminders"]:
                target_time = datetime.strptime(
                    reminder["target_time"], 
                    "%Y-%m-%d %H:%M:%S"
                )
                reminders.append((target_time, reminder["reminder_content"]))
            return reminders
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"解析时间信息失败: {str(e)}")
            return None

    def recognize_time(self, message: str) -> Optional[list]:
        """
        识别消息中的时间信息，支持多个提醒
        Args:
            message: 用户消息
        Returns:
            Optional[list]: [(目标时间, 提醒内容), ...] 或 None
        """
        try:
            current_time = datetime.now()
            user_prompt = f"""当前时间是：{current_time.strftime('%Y-%m-%d %H:%M:%S')}
请严格按照JSON格式分析这条消息中的提醒请求：{message}"""
            
            response = self.llm_service.get_response(
                message=user_prompt,
                system_prompt=self.system_prompt,
                user_id="time_recognition_system"
            )

            # 清理和验证响应
            if not response or response == "NOT_TIME_RELATED":
                return None

            # 清理响应中的非JSON内容
            response = self._clean_response(response)
            if not response:
                return None

            return self._parse_response(response)

        except Exception as e:
            logger.error(f"识别时间信息失败: {str(e)}")
            return None

    def _clean_response(self, response: str) -> Optional[str]:
        """
        清理API响应，提取有效的JSON部分
        Args:
            response: API原始响应
        Returns:
            Optional[str]: 清理后的JSON字符串或None
        """
        try:
            # 移除所有换行和多余空格
            response = ' '.join(response.split())
            
            # 查找第一个 { 和最后一个 }
            start = response.find('{')
            end = response.rfind('}')
            
            if start == -1 or end == -1:
                logger.error("响应中未找到有效的JSON结构")
                return None
            
            # 提取JSON部分
            json_str = response[start:end + 1]
            
            # 验证是否为有效的JSON
            json_obj = json.loads(json_str)
            if "reminders" not in json_obj:
                logger.error("JSON中缺少reminders字段")
                return None
            
            # 验证reminders是否为列表
            if not isinstance(json_obj["reminders"], list):
                logger.error("reminders不是列表类型")
                return None
            
            # 验证每个提醒的格式
            for reminder in json_obj["reminders"]:
                if not isinstance(reminder, dict):
                    logger.error("提醒项不是字典类型")
                    return None
                if "target_time" not in reminder or "reminder_content" not in reminder:
                    logger.error("提醒项缺少必要字段")
                    return None
            
            # 返回格式化的JSON字符串
            return json.dumps(json_obj, ensure_ascii=False)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"响应清理失败: {str(e)}")
            return None

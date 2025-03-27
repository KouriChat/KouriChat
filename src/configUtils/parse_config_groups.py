"""
配置解析模块
提供解析配置并按组分类的功能
"""
import time
import logging
import yaml
import os
from typing import Dict, Any, List

# 获取日志记录器
logger = logging.getLogger(__name__)

# 配置缓存过期时间(秒)
CONFIG_CACHE_EXPIRE = 5

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_available_avatars() -> List[str]:
    """获取可用的人设目录列表"""
    avatar_base_dir = os.path.join(ROOT_DIR, "data/avatars")
    if not os.path.exists(avatar_base_dir):
        return []

    # 获取所有包含 avatar.md 和 emojis 目录的有效人设目录
    avatars = []
    for item in os.listdir(avatar_base_dir):
        avatar_dir = os.path.join(avatar_base_dir, item)
        if os.path.isdir(avatar_dir):
            if os.path.exists(os.path.join(avatar_dir, "avatar.md")) and \
                    os.path.exists(os.path.join(avatar_dir, "emojis")):
                # 只添加人设目录名，不包含路径
                avatars.append(item)

    return avatars

def parse_config_groups() -> Dict[str, Dict[str, Any]]:
    """解析配置文件，将配置项按组分类"""
    from src.config import config
    # 用于缓存结果的静态变量
    if not hasattr(parse_config_groups, 'cache'):
        parse_config_groups.cache = None
        parse_config_groups.cache_time = 0
        
    # 检查缓存是否过期
    current_time = time.time()
    if (parse_config_groups.cache is not None and 
        (current_time - parse_config_groups.cache_time) < CONFIG_CACHE_EXPIRE):
        return parse_config_groups.cache

    try:
        # 基础配置组
        config_groups = {
            "基础配置": {},
            "图像识别API配置": {},
            "主动消息配置": {},
            "Prompt配置": {},
        }

        # 基础配置
        config_groups["基础配置"].update(
            {
                "LISTEN_LIST": {
                    "value": config.user.listen_list,
                    "description": "用户列表(请配置要和bot说话的账号的昵称或者群名，不要写备注！)",
                },
                "DEEPSEEK_BASE_URL": {
                    "value": config.llm.base_url,
                    "description": "API注册地址",
                },
                "MODEL": {"value": config.llm.model, "description": "AI模型选择"},
                "DEEPSEEK_API_KEY": {
                    "value": config.llm.api_key,
                    "description": "API密钥",
                },
                "MAX_TOKEN": {
                    "value": config.llm.max_tokens,
                    "description": "回复最大token数",
                    "type": "number",
                },
                "TEMPERATURE": {
                    "value": float(config.llm.temperature),  # 确保是浮点数
                    "type": "number",
                    "description": "温度参数",
                    "min": 0.0,
                    "max": 1.7,
                },
            }
        )

        # 图像识别API配置
        config_groups["图像识别API配置"].update(
            {
                "MOONSHOT_API_KEY": {
                    "value": config.media.image_recognition.api_key,
                    "description": "识图API密钥",
                },
                "MOONSHOT_BASE_URL": {
                    "value": config.media.image_recognition.base_url,
                    "description": "识图功能 API基础URL",
                },
                "MOONSHOT_TEMPERATURE": {
                    "value": config.media.image_recognition.temperature,
                    "description": "识图功能 温度参数",
                },
                "MOONSHOT_MODEL": {
                    "value": config.media.image_recognition.model,
                    "description": "识图功能 AI模型",
                }
            }
        )

        # 主动消息配置
        config_groups["主动消息配置"].update(
            {
                "AUTO_MESSAGE": {
                    "value": config.behavior.auto_message.content,
                    "description": "自动消息内容",
                },
                "MIN_COUNTDOWN_HOURS": {
                    "value": config.behavior.auto_message.min_hours,
                    "description": "最小倒计时时间（小时）",
                },
                "MAX_COUNTDOWN_HOURS": {
                    "value": config.behavior.auto_message.max_hours,
                    "description": "最大倒计时时间（小时）",
                },
                "QUIET_TIME_START": {
                    "value": config.behavior.quiet_time.start,
                    "description": "安静时间开始",
                },
                "QUIET_TIME_END": {
                    "value": config.behavior.quiet_time.end,
                    "description": "安静时间结束",
                },
            }
        )

        # Prompt配置
        available_avatars = get_available_avatars()
        config_groups["Prompt配置"].update(
            {
                "MAX_GROUPS": {
                    "value": config.behavior.context.max_groups,
                    "description": "最大的上下文轮数",
                },
                "AVATAR_DIR": {
                    "value": config.behavior.context.avatar_dir,
                    "description": "人设目录（自动包含 avatar.md 和 emojis 目录）",
                    "options": available_avatars,
                    "type": "select"
                }
            }
        )

        # 直接从配置文件读取定时任务数据
        tasks = []
        try:
            config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                if 'categories' in config_data and 'schedule_settings' in config_data['categories']:
                    if 'settings' in config_data['categories']['schedule_settings'] and 'tasks' in \
                            config_data['categories']['schedule_settings']['settings']:
                        tasks = config_data['categories']['schedule_settings']['settings']['tasks'].get('value', [])
        except Exception as e:
            logger.error(f"读取任务数据失败: {str(e)}")

        # 将定时任务配置添加到 config_groups 中
        config_groups['定时任务配置'] = {
            'tasks': {
                'value': tasks,
                'type': 'array',
                'description': '定时任务列表'
            }
        }

        logger.debug(f"解析后的定时任务配置: {tasks}")

        # 缓存结果
        parse_config_groups.cache = config_groups
        parse_config_groups.cache_time = current_time

        return config_groups

    except Exception as e:
        logger.error(f"解析配置组失败: {str(e)}")
        return {}

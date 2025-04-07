import os
import json
import logging
import shutil
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

@dataclass
class UserSettings:
    listen_list: List[str]

@dataclass
class LLMSettings:
    api_key: str
    base_url: str
    model: str
    max_tokens: int
    temperature: float

@dataclass
class ImageRecognitionSettings:
    api_key: str
    base_url: str
    temperature: float
    model: str

@dataclass
class ImageGenerationSettings:
    model: str
    temp_dir: str

@dataclass
class TextToSpeechSettings:
    tts_api_url: str
    voice_dir: str

@dataclass
class MediaSettings:
    image_recognition: ImageRecognitionSettings
    image_generation: ImageGenerationSettings
    text_to_speech: TextToSpeechSettings

@dataclass
class AutoMessageSettings:
    content: str
    min_hours: float
    max_hours: float

@dataclass
class QuietTimeSettings:
    start: str
    end: str

@dataclass
class ContextSettings:
    max_groups: int
    avatar_dir: str  # 人设目录路径，prompt文件和表情包目录都将基于此路径

@dataclass
class TaskSettings:
    task_id: str
    chat_id: str
    content: str
    schedule_type: str
    schedule_time: str
    is_active: bool

@dataclass
class ScheduleSettings:
    tasks: List[TaskSettings]

@dataclass
class BehaviorSettings:
    auto_message: AutoMessageSettings
    quiet_time: QuietTimeSettings
    context: ContextSettings
    schedule_settings: ScheduleSettings

@dataclass
class AuthSettings:
    admin_password: str

@dataclass
class Config:
    def __init__(self):
        self.user: UserSettings
        self.llm: LLMSettings
        self.media: MediaSettings
        self.behavior: BehaviorSettings
        self.auth: AuthSettings
        self.load_config()
    
    @property
    def config_dir(self) -> str:
        """返回配置文件所在目录"""
        return os.path.dirname(__file__)
    
    @property
    def config_path(self) -> str:
        """返回配置文件完整路径"""
        return os.path.join(self.config_dir, 'config.json')
    
    @property
    def config_template_path(self) -> str:
        """返回配置模板文件完整路径"""
        return os.path.join(self.config_dir, 'config.json.template')
    
    def save_config(self, config_data: dict) -> bool:
        """保存配置到文件"""
        try:
            # 读取现有配置
            with open(self.config_path, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
            
            # 递归合并配置
            def merge_config(current: dict, new: dict):
                for key, value in new.items():
                    if key in current and isinstance(current[key], dict) and isinstance(value, dict):
                        merge_config(current[key], value)
                    else:
                        current[key] = value
            
            # 合并新配置
            merge_config(current_config, config_data)
            
            # 保存更新后的配置
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(current_config, f, indent=4, ensure_ascii=False)
            
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
            return False
    
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            # 如果配置文件不存在，从模板创建
            if not os.path.exists(self.config_path):
                if os.path.exists(self.config_template_path):
                    logger.info("配置文件不存在，正在从模板创建...")
                    shutil.copy2(self.config_template_path, self.config_path)
                    logger.info(f"已从模板创建配置文件: {self.config_path}")
                # 如果配置文件仍然不存在，说明模板也不存在
                if not os.path.exists(self.config_path):
                    raise FileNotFoundError(f"配置文件不存在，且未找到模板文件: {self.config_template_path}")

            # 读取配置文件
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                categories = config_data['categories']
                
                # 用户设置
                user_data = categories['user_settings']['settings']
                listen_list = user_data['listen_list'].get('value', [])
                # 确保listen_list是列表类型
                if not isinstance(listen_list, list):
                    listen_list = [str(listen_list)] if listen_list else []
                self.user = UserSettings(
                    listen_list=listen_list
                )
                
                # LLM设置
                llm_data = categories['llm_settings']['settings']
                self.llm = LLMSettings(
                    api_key=llm_data['api_key'].get('value', ''),
                    base_url=llm_data['base_url'].get('value', 'https://api.siliconflow.cn/v1/'),
                    model=llm_data['model'].get('value', 'Pro/deepseek-ai/DeepSeek-V3'),
                    max_tokens=int(llm_data['max_tokens'].get('value', 2000)),
                    temperature=float(llm_data['temperature'].get('value', 1.1))
                )
                
                # 媒体设置
                media_data = categories['media_settings']['settings']
                image_recognition_data = media_data['image_recognition']
                image_generation_data = media_data['image_generation']
                text_to_speech_data = media_data['text_to_speech']
                
                self.media = MediaSettings(
                    image_recognition=ImageRecognitionSettings(
                        api_key=image_recognition_data['api_key'].get('value', ''),
                        base_url=image_recognition_data['base_url'].get('value', 'https://api.moonshot.cn/v1'),
                        temperature=float(image_recognition_data['temperature'].get('value', 0.7)),
                        model=image_recognition_data['model'].get('value', 'moonshot-v1-8k-vision-preview')
                    ),
                    image_generation=ImageGenerationSettings(
                        model=image_generation_data['model'].get('value', 'deepseek-ai/Janus-Pro-7B'),
                        temp_dir=image_generation_data['temp_dir'].get('value', 'data/images/temp')
                    ),
                    text_to_speech=TextToSpeechSettings(
                        tts_api_url=text_to_speech_data['tts_api_url'].get('value', 'http://127.0.0.1:5000/tts'),
                        voice_dir=text_to_speech_data['voice_dir'].get('value', 'data/voices')
                    )
                )
                
                # 行为设置
                behavior_data = categories['behavior_settings']['settings']
                auto_message_data = behavior_data['auto_message']
                auto_message_countdown = auto_message_data.get('countdown', {})
                quiet_time_data = behavior_data['quiet_time']
                context_data = behavior_data['context']
                
                # 确保目录路径规范化
                avatar_dir = context_data['avatar_dir'].get('value', 'data/avatars/MONO')
                if not avatar_dir.startswith('data/avatars/'):
                    avatar_dir = f"data/avatars/{avatar_dir.split('/')[-1]}"
                
                # 定时任务配置
                schedule_tasks = []
                if 'schedule_settings' in categories:
                    schedule_data = categories['schedule_settings']
                    if 'settings' in schedule_data and 'tasks' in schedule_data['settings']:
                        tasks_data = schedule_data['settings']['tasks'].get('value', [])
                        for task in tasks_data:
                            # 确保必要的字段存在
                            if all(key in task for key in ['task_id', 'chat_id', 'content', 'schedule_type', 'schedule_time']):
                                schedule_tasks.append(TaskSettings(
                                    task_id=task['task_id'],
                                    chat_id=task['chat_id'],
                                    content=task['content'],
                                    schedule_type=task['schedule_type'],
                                    schedule_time=task['schedule_time'],
                                    is_active=task.get('is_active', True)
                                ))
                
                # 行为配置
                self.behavior = BehaviorSettings(
                    auto_message=AutoMessageSettings(
                        content=auto_message_data['content'].get('value', '请你模拟系统设置的角色，在微信上找对方发消息想知道对方在做什么'),
                        min_hours=float(auto_message_countdown.get('min_hours', {}).get('value', 1.0)),
                        max_hours=float(auto_message_countdown.get('max_hours', {}).get('value', 3.0))
                    ),
                    quiet_time=QuietTimeSettings(
                        start=quiet_time_data['start'].get('value', '22:00'),
                        end=quiet_time_data['end'].get('value', '08:00')
                    ),
                    context=ContextSettings(
                        max_groups=int(context_data['max_groups'].get('value', 15)),
                        avatar_dir=avatar_dir
                    ),
                    schedule_settings=ScheduleSettings(
                        tasks=schedule_tasks
                    )
                )
                
                # 认证设置
                auth_data = categories.get('auth_settings', {}).get('settings', {})
                self.auth = AuthSettings(
                    admin_password=auth_data.get('admin_password', {}).get('value', '')
                )
                
                logger.info("配置加载完成")
                
        except Exception as e:
            logger.error(f"加载配置失败: {str(e)}")
            # 使用默认值初始化配置
            self.user = UserSettings(listen_list=[])
            self.llm = LLMSettings(
                api_key='',
                base_url='https://api.siliconflow.cn/v1/',
                model='Pro/deepseek-ai/DeepSeek-V3',
                max_tokens=2000,
                temperature=1.1
            )
            self.media = MediaSettings(
                image_recognition=ImageRecognitionSettings(
                    api_key='',
                    base_url='https://api.moonshot.cn/v1',
                    temperature=0.7,
                    model='moonshot-v1-8k-vision-preview'
                ),
                image_generation=ImageGenerationSettings(
                    model='deepseek-ai/Janus-Pro-7B',
                    temp_dir='data/images/temp'
                ),
                text_to_speech=TextToSpeechSettings(
                    tts_api_url='http://127.0.0.1:5000/tts',
                    voice_dir='data/voices'
                )
            )
            self.behavior = BehaviorSettings(
                auto_message=AutoMessageSettings(
                    content='请你模拟系统设置的角色，在微信上找对方发消息想知道对方在做什么',
                    min_hours=1.0,
                    max_hours=3.0
                ),
                quiet_time=QuietTimeSettings(
                    start='22:00',
                    end='08:00'
                ),
                context=ContextSettings(
                    max_groups=15,
                    avatar_dir='data/avatars/MONO'
                ),
                schedule_settings=ScheduleSettings(
                    tasks=[]
                )
            )
            self.auth = AuthSettings(
                admin_password=''
            )

    # 更新管理员密码
    def update_password(self, password: str) -> bool:
        try:
            config_data = {
                'categories': {
                    'auth_settings': {
                        'settings': {
                            'admin_password': {
                                'value': password
                            }
                        }
                    }
                }
            }
            return self.save_config(config_data)
        except Exception as e:
            logger.error(f"更新密码失败: {str(e)}")
            return False

# 创建全局配置实例
config = Config()

# 为了兼容性保留的旧变量（将在未来版本中移除）
LISTEN_LIST = config.user.listen_list
DEEPSEEK_API_KEY = config.llm.api_key
DEEPSEEK_BASE_URL = config.llm.base_url
MODEL = config.llm.model
MAX_TOKEN = config.llm.max_tokens
TEMPERATURE = config.llm.temperature
MOONSHOT_API_KEY = config.media.image_recognition.api_key
MOONSHOT_BASE_URL = config.media.image_recognition.base_url
MOONSHOT_TEMPERATURE = config.media.image_recognition.temperature
IMAGE_MODEL = config.media.image_generation.model
TEMP_IMAGE_DIR = config.media.image_generation.temp_dir
MAX_GROUPS = config.behavior.context.max_groups
TTS_API_URL = config.media.text_to_speech.tts_api_url
VOICE_DIR = config.media.text_to_speech.voice_dir
AUTO_MESSAGE = config.behavior.auto_message.content
MIN_COUNTDOWN_HOURS = config.behavior.auto_message.min_hours
MAX_COUNTDOWN_HOURS = config.behavior.auto_message.max_hours
QUIET_TIME_START = config.behavior.quiet_time.start
QUIET_TIME_END = config.behavior.quiet_time.end 
import os
import json
import logging
import shutil
from dataclasses import dataclass
from typing import List

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
    avatar_dir: str

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
class RagSettings:
    base_url: str
    api_key: str
    is_rerank: bool
    reranker_model: str
    embedding_model: str
    top_k: int

@dataclass
class Config:
    def __init__(self):
        self.user: UserSettings
        self.llm: LLMSettings
        self.media: MediaSettings
        self.behavior: BehaviorSettings
        self.auth: AuthSettings
        self._robot_wx_name: str = ""
        self.rag: RagSettings
        self.load_config()

    @property
    def robot_wx_name(self) -> str:
        try:
            avatar_dir = self.behavior.context.avatar_dir
            if avatar_dir and os.path.exists(avatar_dir):
                return os.path.basename(avatar_dir)
        except Exception as e:
            logger.error(f"获取机器人名称失败: {str(e)}")
        return "default"

    @property
    def config_dir(self) -> str:
        return os.path.dirname(__file__)

    @property
    def config_path(self) -> str:
        return os.path.join(self.config_dir, 'config.json')

    @property
    def config_template_path(self) -> str:
        return os.path.join(self.config_dir, 'config.json.template')

    def save_config(self, config_data: dict) -> bool:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                current_config = json.load(f)

            def merge_config(current: dict, new: dict):
                for key, value in new.items():
                    if key in current and isinstance(current[key], dict) and isinstance(value, dict):
                        merge_config(current[key], value)
                    else:
                        current[key] = value

            merge_config(current_config, config_data)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(current_config, f, indent=4, ensure_ascii=False)

            return True
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
            return False

    def load_config(self) -> None:
        try:
            if not os.path.exists(self.config_path):
                if os.path.exists(self.config_template_path):
                    logger.info("配置文件不存在，正在从模板创建...")
                    shutil.copy2(self.config_template_path, self.config_path)
                    logger.info(f"已从模板创建配置文件: {self.config_path}")
                if not os.path.exists(self.config_path):
                    raise FileNotFoundError(f"配置文件不存在，且未找到模板文件: {self.config_template_path}")

            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                categories = config_data['categories']

                user_data = categories['user_settings']['settings']
                self.user = UserSettings(
                    listen_list=user_data['listen_list']['value']
                )

                llm_data = categories['llm_settings']['settings']
                self.llm = LLMSettings(
                    api_key=llm_data['api_key']['value'],
                    base_url=llm_data['base_url']['value'],
                    model=llm_data['model']['value'],
                    max_tokens=llm_data['max_tokens']['value'],
                    temperature=llm_data['temperature']['value']
                )

                rag_data = categories['rag_settings']['settings']
                self.rag = RagSettings(
                    base_url=rag_data['base_url'],
                    api_key=rag_data['api_key'],
                    is_rerank=rag_data['is_rerank'],
                    reranker_model=rag_data['reranker_model'],
                    embedding_model=rag_data['embedding_model'],
                    top_k=rag_data['top_k']
                )
                
                media_data = categories['media_settings']['settings']
                self.media = MediaSettings(
                    image_recognition=ImageRecognitionSettings(
                        api_key=media_data['image_recognition']['api_key']['value'],
                        base_url=media_data['image_recognition']['base_url']['value'],
                        temperature=media_data['image_recognition']['temperature']['value'],
                        model=media_data['image_recognition']['model']['value']
                    ),
                    image_generation=ImageGenerationSettings(
                        model=media_data['image_generation']['model']['value'],
                        temp_dir=media_data['image_generation']['temp_dir']['value']
                    ),
                    text_to_speech=TextToSpeechSettings(
                        tts_api_url=media_data['text_to_speech']['tts_api_url']['value'],
                        voice_dir=media_data['text_to_speech']['voice_dir']['value']
                    )
                )
                
                behavior_data = categories['behavior_settings']['settings']
                
                schedule_tasks = []
                if 'schedule_settings' in categories:
                    schedule_data = categories['schedule_settings']
                    if 'settings' in schedule_data and 'tasks' in schedule_data['settings']:
                        tasks_data = schedule_data['settings']['tasks']['value']
                        for task in tasks_data:
                            schedule_tasks.append(TaskSettings(
                                task_id=task['task_id'],
                                chat_id=task['chat_id'],
                                content=task['content'],
                                schedule_type=task['schedule_type'],
                                schedule_time=task['schedule_time'],
                                is_active=task.get('is_active', True)
                            ))
                
                self.behavior = BehaviorSettings(
                    auto_message=AutoMessageSettings(
                        content=behavior_data['auto_message']['content']['value'],
                        min_hours=behavior_data['auto_message']['countdown']['min_hours']['value'],
                        max_hours=behavior_data['auto_message']['countdown']['max_hours']['value']
                    ),
                    quiet_time=QuietTimeSettings(
                        start=behavior_data['quiet_time']['start']['value'],
                        end=behavior_data['quiet_time']['end']['value']
                    ),
                    context=ContextSettings(
                        max_groups=behavior_data['context']['max_groups']['value'],
                        avatar_dir=behavior_data['context']['avatar_dir']['value']
                    ),
                    schedule_settings=ScheduleSettings(
                        tasks=schedule_tasks
                    )
                )
                
                auth_data = categories['auth_settings']['settings']
                self.auth = AuthSettings(
                    admin_password=auth_data['admin_password']['value']
                )
                
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            raise

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

config = Config()

ROBOT_WX_NAME = config.robot_wx_name

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

def reload_config():
    global config
    config = Config()
    return True

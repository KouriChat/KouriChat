import os
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Union, cast

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
    local_model_enabled: bool = False
    auto_adapt_siliconflow: bool = True
    local_embedding_model_path: str = "paraphrase-multilingual-MiniLM-L12-v2"


class SettingReader:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None or not kwargs.get('singleton', True):
            cls._instance = super(SettingReader, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_dir='./src/config', singleton: bool = True):
        # 使用 object.__setattr__ 直接设置所有属性，完全绕过 __setattr__ 方法
        if not hasattr(self, 'initialized'):
            object.__setattr__(self, '_config_dir', config_dir)
            object.__setattr__(self, '_config_path', os.path.join(config_dir, 'config.yaml'))
            object.__setattr__(self, '_template_path', os.path.join(os.path.dirname(__file__), 'template.yaml'))
            object.__setattr__(self, 'settings', {})
            object.__setattr__(self, '_robot_wx_name', "")
            object.__setattr__(self, 'initialized', True)
            
            # 创建配置类实例
            object.__setattr__(self, 'user', UserSettings([]))
            object.__setattr__(self, 'llm', LLMSettings("", "", "", 0, 0.0))
            object.__setattr__(self, 'media', MediaSettings(
                ImageRecognitionSettings("", "", 0.0, ""),
                ImageGenerationSettings("", ""),
                TextToSpeechSettings("", "")
            ))
            object.__setattr__(self, 'behavior', BehaviorSettings(
                AutoMessageSettings("", 0.0, 0.0),
                QuietTimeSettings("", ""),
                ContextSettings(0, ""),
                ScheduleSettings([])
            ))
            object.__setattr__(self, 'auth', AuthSettings(""))
            object.__setattr__(self, 'rag', RagSettings("", "", False, "", "", 0))
            
            self.load_config()

    def load_config(self):
        """加载配置文件，如果不存在则从模板创建"""
        try:
            logger.info(f"尝试加载配置文件: {self.config_path}")
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as file:
                    config_data = yaml.safe_load(file) or {}
                    object.__setattr__(self, 'settings', config_data)
                    logger.info("成功加载现有配置文件")
                    
                    # 解析配置数据到对应的数据类
                    self._parse_config_data(config_data)
            else:
                logger.info(f"配置文件不存在，准备创建。")
                # 获取配置文件目录
                config_dir = os.path.dirname(self.config_path)
                logger.info(f"确保目录存在: {config_dir}")
                
                # 确保目录存在
                try:
                    os.makedirs(config_dir, exist_ok=True)
                except Exception as dir_err:
                    logger.error(f"创建目录失败: {str(dir_err)}")
                    raise
                
                # 如果模板存在，复制模板
                logger.info(f"检查模板文件: {self.template_path}")
                if os.path.exists(self.template_path):
                    logger.info("模板文件存在，从模板创建配置")
                    try:
                        # 使用ruamel.yaml代替标准yaml库以保留顺序
                        try:
                            from ruamel.yaml import YAML
                            yaml_parser = YAML()
                            yaml_parser.preserve_quotes = True
                            yaml_parser.indent(mapping=2, sequence=4, offset=2)
                            
                            with open(self.template_path, 'r', encoding='utf-8') as template_file:
                                template_settings = yaml.safe_load(template_file) or {}
                            
                            # 直接复制模板文件而不是从字典转换
                            import shutil
                            shutil.copy2(self.template_path, self.config_path)
                            
                            object.__setattr__(self, 'settings', template_settings)
                            logger.info("成功从模板创建配置文件（保持原始顺序）")
                            self._parse_config_data(template_settings)
                        except ImportError:
                            # 如果没有ruamel.yaml，使用简单复制方式
                            with open(self.template_path, 'r', encoding='utf-8') as template_file:
                                template_content = template_file.read()
                            
                            with open(self.config_path, 'w', encoding='utf-8') as config_file:
                                config_file.write(template_content)
                            
                            # 重新解析配置
                            with open(self.config_path, 'r', encoding='utf-8') as file:
                                template_settings = yaml.safe_load(file) or {}
                            
                            object.__setattr__(self, 'settings', template_settings)
                            logger.info("成功从模板创建配置文件（通过内容复制）")
                            self._parse_config_data(template_settings)
                    except Exception as tpl_err:
                        logger.error(f"从模板创建配置失败: {str(tpl_err)}")
                        raise
                else:
                    # 模板不存在，创建空配置
                    logger.warning("模板不存在，创建空配置文件")
                    try:
                        with open(self.config_path, 'w', encoding='utf-8') as file:
                            yaml.safe_dump({}, file)
                        object.__setattr__(self, 'settings', {})
                        logger.info("成功创建空配置文件")
                    except Exception as empty_err:
                        logger.error(f"创建空配置文件失败: {str(empty_err)}")
                        raise
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            # 这里不再抛出异常，而是设置默认空配置
            logger.warning("使用内存中的默认空配置")
            object.__setattr__(self, 'settings', {})
    
    def _parse_config_data(self, config_data):
        """解析配置数据到对应的数据类"""
        categories = config_data.get('categories', {})
        
        # 用户设置
        if 'user_settings' in categories:
            user_data = categories['user_settings'].get('settings', {})
            listen_list = user_data.get('listen_list', {}).get('value', [])
            object.__setattr__(self, 'user', UserSettings(listen_list=listen_list))
        
        # LLM设置
        if 'llm_settings' in categories:
            llm_data = categories['llm_settings'].get('settings', {})
            model = llm_data.get('model', {}).get('value', '')
            logger.info(f"从配置文件读取的模型名称: {model}")
            
            object.__setattr__(self, 'llm', LLMSettings(
                api_key=llm_data.get('api_key', {}).get('value', ''),
                base_url=llm_data.get('base_url', {}).get('value', ''),
                model=model,
                max_tokens=llm_data.get('max_tokens', {}).get('value', 0),
                temperature=llm_data.get('temperature', {}).get('value', 0.0)
            ))
        
        # RAG设置
        if 'rag_settings' in categories:
            rag_data = categories['rag_settings'].get('settings', {})
            
            # 处理local_model_enabled
            local_model_enabled = rag_data.get('local_model_enabled', False)
            if isinstance(local_model_enabled, dict) and 'value' in local_model_enabled:
                local_model_enabled = local_model_enabled['value']
                
            # 处理auto_adapt_siliconflow
            auto_adapt = rag_data.get('auto_adapt_siliconflow', True)
            if isinstance(auto_adapt, dict) and 'value' in auto_adapt:
                auto_adapt = auto_adapt['value']
                
            # 处理local_embedding_model_path
            local_model_path = rag_data.get('local_embedding_model_path', "paraphrase-multilingual-MiniLM-L12-v2")
            if isinstance(local_model_path, dict) and 'value' in local_model_path:
                local_model_path = local_model_path['value']
            
            # 处理base_url，支持错误拼写的bbase_url
            base_url = rag_data.get('base_url', '')
            if not base_url and 'bbase_url' in rag_data:
                base_url = rag_data.get('bbase_url', {}).get('value', '')
            elif isinstance(base_url, dict) and 'value' in base_url:
                base_url = base_url['value']
            
            # 处理embedding_model
            embedding_model = rag_data.get('embedding_model', '')
            if isinstance(embedding_model, dict) and 'value' in embedding_model:
                embedding_model = embedding_model['value']
            
            object.__setattr__(self, 'rag', RagSettings(
                base_url=base_url,
                api_key=rag_data.get('api_key', {}).get('value', ''),
                is_rerank=rag_data.get('is_rerank', {}).get('value', False),
                reranker_model=rag_data.get('reranker_model', {}).get('value', ''),
                embedding_model=embedding_model,
                top_k=rag_data.get('top_k', {}).get('value', 5),
                local_model_enabled=local_model_enabled,
                auto_adapt_siliconflow=auto_adapt,
                local_embedding_model_path=local_model_path
            ))
        
        # 媒体设置
        if 'media_settings' in categories:
            media_data = categories['media_settings'].get('settings', {})
            
            # 图像识别
            img_recog = media_data.get('image_recognition', {})
            img_recognition = ImageRecognitionSettings(
                api_key=img_recog.get('api_key', {}).get('value', ''),
                base_url=img_recog.get('base_url', {}).get('value', ''),
                temperature=img_recog.get('temperature', {}).get('value', 0.0),
                model=img_recog.get('model', {}).get('value', '')
            )
            
            # 图像生成
            img_gen = media_data.get('image_generation', {})
            img_generation = ImageGenerationSettings(
                model=img_gen.get('model', {}).get('value', ''),
                temp_dir=img_gen.get('temp_dir', {}).get('value', '')
            )
            
            # 文本转语音
            tts = media_data.get('text_to_speech', {})
            text_to_speech = TextToSpeechSettings(
                tts_api_url=tts.get('tts_api_url', {}).get('value', ''),
                voice_dir=tts.get('voice_dir', {}).get('value', '')
            )
            
            object.__setattr__(self, 'media', MediaSettings(
                image_recognition=img_recognition,
                image_generation=img_generation,
                text_to_speech=text_to_speech
            ))
        
        # 行为设置
        if 'behavior_settings' in categories:
            behavior_data = categories['behavior_settings'].get('settings', {})
            
            # 自动消息
            auto_msg = behavior_data.get('auto_message', {})
            auto_message = AutoMessageSettings(
                content=auto_msg.get('content', {}).get('value', ''),
                min_hours=auto_msg.get('countdown', {}).get('min_hours', {}).get('value', 0.0),
                max_hours=auto_msg.get('countdown', {}).get('max_hours', {}).get('value', 0.0)
            )
            
            # 安静时间
            quiet = behavior_data.get('quiet_time', {})
            quiet_start = quiet.get('start', {}).get('value', '')
            quiet_end = quiet.get('end', {}).get('value', '')
            
            # 处理开始时间格式
            if quiet_start:
                if quiet_start == '1320':
                    quiet_start = '22:00'
                elif ':' not in quiet_start:
                    try:
                        hour = int(quiet_start) // 100
                        minute = int(quiet_start) % 100
                        quiet_start = f"{hour:02d}:{minute:02d}"
                    except (ValueError, TypeError):
                        logger.warning(f"无法转换安静时间开始格式: {quiet_start}")
                        quiet_start = '22:00'  # 使用默认值
            
            # 处理结束时间格式
            if quiet_end:
                if quiet_end == '1320':
                    quiet_end = '08:00'
                elif ':' not in quiet_end:
                    try:
                        hour = int(quiet_end) // 100
                        minute = int(quiet_end) % 100
                        quiet_end = f"{hour:02d}:{minute:02d}"
                    except (ValueError, TypeError):
                        logger.warning(f"无法转换安静时间结束格式: {quiet_end}")
                        quiet_end = '08:00'  # 使用默认值
            
            # 更新配置数据
            if 'quiet_time' in behavior_data:
                if 'start' in behavior_data['quiet_time']:
                    behavior_data['quiet_time']['start']['value'] = quiet_start
                if 'end' in behavior_data['quiet_time']:
                    behavior_data['quiet_time']['end']['value'] = quiet_end
            
            quiet_time = QuietTimeSettings(
                start=quiet_start,
                end=quiet_end
            )
            
            # 上下文设置
            context_data = behavior_data.get('context', {})
            context = ContextSettings(
                max_groups=context_data.get('max_groups', {}).get('value', 0),
                avatar_dir=context_data.get('avatar_dir', {}).get('value', '')
            )
            
            # 定时任务
            schedule_tasks = []
            if 'schedule_settings' in categories:
                schedule_data = categories['schedule_settings']
                if 'settings' in schedule_data and 'tasks' in schedule_data['settings']:
                    tasks_data = schedule_data['settings']['tasks'].get('value', [])
                    for task in tasks_data:
                        schedule_tasks.append(TaskSettings(
                            task_id=task.get('task_id', ''),
                            chat_id=task.get('chat_id', ''),
                            content=task.get('content', ''),
                            schedule_type=task.get('schedule_type', ''),
                            schedule_time=task.get('schedule_time', ''),
                            is_active=task.get('is_active', True)
                        ))
            
            object.__setattr__(self, 'behavior', BehaviorSettings(
                auto_message=auto_message,
                quiet_time=quiet_time,
                context=context,
                schedule_settings=ScheduleSettings(tasks=schedule_tasks)
            ))
        
        # 认证设置
        if 'auth_settings' in categories:
            auth_data = categories['auth_settings'].get('settings', {})
            object.__setattr__(self, 'auth', AuthSettings(
                admin_password=auth_data.get('admin_password', {}).get('value', '')
            ))

    def save_config(self, config_data: dict) -> bool:
        """保存配置"""
        try:
            # 读取当前配置文件内容
            with open(self.config_path, 'r', encoding='utf-8') as f:
                current_config_str = f.read()
                current_config = yaml.safe_load(current_config_str) or {}
            
            def merge_config(current: dict, new: dict):
                for key, value in new.items():
                    if key in current and isinstance(current[key], dict) and isinstance(value, dict):
                        merge_config(current[key], value)
                    else:
                        current[key] = value
            
            merge_config(current_config, config_data)
            
            # 尝试使用ruamel.yaml保留格式和顺序
            try:
                from ruamel.yaml import YAML
                yaml_parser = YAML()
                yaml_parser.preserve_quotes = True
                yaml_parser.indent(mapping=2, sequence=4, offset=2)
                
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml_parser.dump(current_config, f)
            except ImportError:
                # 如果没有ruamel.yaml，使用标准yaml
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(current_config, f, allow_unicode=True, sort_keys=False)
            
            # 更新内存中的配置
            object.__setattr__(self, 'settings', current_config)
            self._parse_config_data(current_config)
            
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
            return False
    
    def update_password(self, password: str) -> bool:
        """更新密码"""
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
    
    @property
    def robot_wx_name(self) -> str:
        """获取机器人名称"""
        try:
            avatar_dir = self.behavior.context.avatar_dir
            if avatar_dir and os.path.exists(avatar_dir):
                return os.path.basename(avatar_dir)
        except Exception as e:
            logger.error(f"获取机器人名称失败: {str(e)}")
        return "default"
    
    @property
    def config_dir(self) -> str:
        """获取配置目录（只读）"""
        return object.__getattribute__(self, '_config_dir')
    
    @property
    def config_path(self) -> str:
        """获取配置文件路径（只读）"""
        return object.__getattribute__(self, '_config_path')
    
    @property
    def template_path(self) -> str:
        """获取模板文件路径（只读）"""
        return object.__getattribute__(self, '_template_path')
    
    # 如果确实需要在某些情况下修改这些属性，提供显式方法
    def set_config_dir(self, value):
        """安全地设置配置目录"""
        if hasattr(self, 'initialized') and self.initialized:
            logger.warning("警告：尝试修改已初始化对象的配置目录")
        
        object.__setattr__(self, '_config_dir', value)
        object.__setattr__(self, '_config_path', os.path.join(value, 'config.yaml'))
        return self
    
    def set_config_path(self, value):
        """安全地设置配置文件路径"""
        if hasattr(self, 'initialized') and self.initialized:
            logger.warning("警告：尝试修改已初始化对象的配置路径")
        
        object.__setattr__(self, '_config_path', value)
        return self
    
    def set_template_path(self, value):
        """安全地设置模板文件路径"""
        if hasattr(self, 'initialized') and self.initialized:
            logger.warning("警告：尝试修改已初始化对象的模板路径")
        
        object.__setattr__(self, '_template_path', value)
        return self
    
    def __getattr__(self, key):
        """通过属性访问配置项"""
        # 先检查自身是否有该属性
        try:
            return object.__getattribute__(self, key)
        except AttributeError:
            # 如果没有，则尝试从settings中获取
            settings = object.__getattribute__(self, 'settings')
            if key in settings:
                return settings[key]
            raise AttributeError(f"'SettingReader' object has no attribute '{key}'")

    def __setattr__(self, key, value):
        """通过属性设置配置项"""
        # 拦截对所有受保护属性的修改尝试
        if key in ['config_dir', '_config_dir', 'config_path', '_config_path', 
                  'template_path', '_template_path']:
            # 如果是受保护的属性，尝试调用对应的set_*方法
            method_name = f"set_{key.lstrip('_')}"
            if hasattr(self, method_name) and callable(getattr(self, method_name)):
                getattr(self, method_name)(value)
                return
            else:
                raise AttributeError(f"不能直接修改属性 '{key}'，请使用对应的set_*方法")
        
        # 处理其他内部属性
        elif key in ['settings', 'initialized', 'user', 'llm', 'media', 
                  'behavior', 'auth', 'rag', '_robot_wx_name']:
            object.__setattr__(self, key, value)
        # 外部属性设置到settings字典中
        else:
            self.settings[key] = value

    def __getitem__(self, key):
        """通过字典方式访问配置项"""
        return self.settings[key]

    def __setitem__(self, key, value):
        """通过字典项设置配置项"""
        if key.startswith('_'):
            object.__setattr__(self, key, value)
        else:
            settings = object.__getattribute__(self, 'settings')
            settings[key] = value
    
    def reload_from_file(self):
        """从配置文件重新加载配置"""
        try:
            # 重新加载配置文件
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # 重新解析配置
            self.load_config()
            
            # 特别处理安静时间格式
            if hasattr(self, 'behavior') and hasattr(self.behavior, 'quiet_time'):
                # 处理开始时间
                if self.behavior.quiet_time.start:
                    if self.behavior.quiet_time.start == '1320':
                        self.behavior.quiet_time.start = '22:00'
                    elif ':' not in self.behavior.quiet_time.start:
                        try:
                            hour = int(self.behavior.quiet_time.start) // 100
                            minute = int(self.behavior.quiet_time.start) % 100
                            self.behavior.quiet_time.start = f"{hour:02d}:{minute:02d}"
                        except (ValueError, TypeError):
                            logger.warning(f"无法转换安静时间开始格式: {self.behavior.quiet_time.start}")
                
                # 处理结束时间
                if self.behavior.quiet_time.end:
                    if self.behavior.quiet_time.end == '1320':
                        self.behavior.quiet_time.end = '08:00'
                    elif ':' not in self.behavior.quiet_time.end:
                        try:
                            hour = int(self.behavior.quiet_time.end) // 100
                            minute = int(self.behavior.quiet_time.end) % 100
                            self.behavior.quiet_time.end = f"{hour:02d}:{minute:02d}"
                        except (ValueError, TypeError):
                            logger.warning(f"无法转换安静时间结束格式: {self.behavior.quiet_time.end}")
            
            # 更新全局变量
            LISTEN_LIST = self.user.listen_list
            DEEPSEEK_API_KEY = self.llm.api_key
            DEEPSEEK_BASE_URL = self.llm.base_url
            MODEL = self.llm.model
            MAX_TOKEN = self.llm.max_tokens
            TEMPERATURE = self.llm.temperature
            MIN_COUNTDOWN_HOURS = self.behavior.auto_message.min_hours
            MAX_COUNTDOWN_HOURS = self.behavior.auto_message.max_hours
            QUIET_TIME_START = self.behavior.quiet_time.start
            QUIET_TIME_END = self.behavior.quiet_time.end
            
            logger.info(f"成功从文件重新加载配置: {self.config_path}")
            logger.info(f"已更新监听用户列表: {LISTEN_LIST}")
            logger.info(f"已更新安静时间设置: 开始={self.behavior.quiet_time.start}, 结束={self.behavior.quiet_time.end}")
            return True
        except Exception as e:
            logger.error(f"从文件重新加载配置失败: {str(e)}")
            return False


def reload_config():
    """重新加载配置"""
    global config, ROBOT_WX_NAME, LISTEN_LIST, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL, MAX_TOKEN, TEMPERATURE, MOONSHOT_API_KEY
    
    # 创建新的配置读取器实例，强制重新加载配置文件
    config = SettingReader(singleton=False)
    
    # 更新全局变量
    ROBOT_WX_NAME = config.robot_wx_name
    LISTEN_LIST = config.user.listen_list
    DEEPSEEK_API_KEY = config.llm.api_key
    DEEPSEEK_BASE_URL = config.llm.base_url
    MODEL = config.llm.model
    MAX_TOKEN = config.llm.max_tokens
    TEMPERATURE = config.llm.temperature
    MOONSHOT_API_KEY = config.media.image_recognition.api_key
    
    # 记录重要配置值，用于调试
    logger.info(f"重新加载配置完成，安静时间设置: 开始={config.behavior.quiet_time.start}, 结束={config.behavior.quiet_time.end}")
    
    return True


# 创建全局实例
config = SettingReader()

# 全局变量，兼容现有代码
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


if __name__ == '__main__':
    # 测试代码
    settings = SettingReader(config_dir='./test_config')
    settings['test_key'] = 'test_value'
    print(settings['test_key'])
    print(settings.test_key) 
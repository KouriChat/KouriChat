"""
配置管理Web界面启动文件
提供Web配置界面功能，包括:
- 初始化Python路径
- 禁用字节码缓存
- 清理缓存文件
- 启动Web服务器
- 动态修改配置
"""

"""
配置管理Web界面启动文件
提供Web配置界面功能，包括:
- 初始化Python路径
- 禁用字节码缓存
- 清理缓存文件
- 启动Web服务器
- 动态修改配置
"""

import os
import sys
import json
import logging
from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, url_for
import importlib
from typing import Dict, Any, List
import psutil
import subprocess
import threading
from src.autoupdate.updater import Updater
import requests
import time
from queue import Queue
import datetime
from logging.config import dictConfig

# 配置日志
dictConfig({
    'version': 1,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'INFO'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console']
    },
    'loggers': {
        'werkzeug': {
            'level': 'ERROR',  # 将 Werkzeug 的日志级别设置为 ERROR
            'handlers': ['console'],
            'propagate': False
        }
    }
})

# 获取项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# 将src目录添加到Python路径
src_path = os.path.join(ROOT_DIR, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)
from utils.cleanup import cleanup_pycache

# 初始化Flask应用
app = Flask(__name__, 
    template_folder=os.path.join(ROOT_DIR, 'src/webui/templates'),
    static_folder=os.path.join(ROOT_DIR, 'src/webui/static')
)

# 配置上传文件夹
app.config['UPLOAD_FOLDER'] = os.path.join(ROOT_DIR, 'src/webui/static/backgrounds')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

logger = logging.getLogger(__name__)

# 添加全局变量存储日志
bot_logs = Queue(maxsize=1000)  # 限制最大日志数量
bot_process = None
bot_start_time = None

def print_status(message: str, status: str = "info", emoji: str = ""):
    """打印状态信息"""
    colors = {
        "success": Fore.GREEN,
        "info": Fore.BLUE,
        "warning": Fore.YELLOW,
        "error": Fore.RED
    }
    color = colors.get(status, Fore.WHITE)
    print(f"{color}{emoji} {message}{Style.RESET_ALL}")


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
                avatars.append(f"data/avatars/{item}")
    
    return avatars

def parse_config_groups() -> Dict[str, Dict[str, Any]]:
    """解析配置文件，将配置项按组分类"""
    from src.config import config

    config_groups = {
        "基础配置": {},
        "图像识别API配置": {},
        "图像生成配置": {},
        "时间配置": {},
        "语音配置": {},
        "天气配置": {},
        "Prompt配置": {},
    }

    # 基础配置
    config_groups["基础配置"].update(
        {
            "LISTEN_LIST": {
                "value": config.user.listen_list if isinstance(config.user.listen_list, list) else [],
                "type": "array",
                "description": "用户列表(请配置要和bot说话的账号的昵称或者群名，不要写备注！)",
            },
            "MODEL": {"value": config.llm.model, "description": "AI模型选择"},
            "DEEPSEEK_BASE_URL": {
                "value": config.llm.base_url,
                "description": "硅基流动API注册地址",
            },
            "DEEPSEEK_API_KEY": {
                "value": config.llm.api_key,
                "description": "DeepSeek API密钥",
            },
            "MAX_TOKEN": {
                "value": config.llm.max_tokens,
                "description": "回复最大token数",
            },
            "TEMPERATURE": {
                "value": config.llm.temperature,
                "type": "number",
                "description": "温度参数",
                "min": 0.8,
                "max": 1.6
            },
        }
    )

    # 图像识别API配置
    config_groups["图像识别API配置"].update(
        {
            "MOONSHOT_API_KEY": {
                "value": config.media.image_recognition.api_key,
                "description": "Moonshot API密钥（用于图片和表情包识别）",
            },
            "MOONSHOT_BASE_URL": {
                "value": config.media.image_recognition.base_url,
                "description": "Moonshot API基础URL",
            },
            "MOONSHOT_TEMPERATURE": {
                "value": config.media.image_recognition.temperature,
                "description": "Moonshot温度参数",
            },
        }
    )

    # 图像生成配置
    config_groups["图像生成配置"].update(
        {
            "IMAGE_MODEL": {
                "value": config.media.image_generation.model,
                "description": "图像生成模型",
            },
            "TEMP_IMAGE_DIR": {
                "value": config.media.image_generation.temp_dir,
                "description": "临时图片目录",
            },
        }
    )

    # 时间配置
    config_groups["时间配置"].update(
        {
            "AUTO_MESSAGE": {
                "value": config.behavior.auto_message.content,
                "description": "自动消息内容",
            },
            "MIN_COUNTDOWN_HOURS": {
                "value": config.behavior.auto_message.countdown.min_hours,
                "description": "最小倒计时时间（小时）",
            },
            "MAX_COUNTDOWN_HOURS": {
                "value": config.behavior.auto_message.countdown.max_hours,
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

    # 语音配置
    config_groups["语音配置"].update(
        {
            "TTS_API_URL": {
                "value": config.media.text_to_speech.tts_api_url,
                "description": "语音服务API地址",
            },
            "VOICE_DIR": {
                "value": config.media.text_to_speech.voice_dir,
                "description": "语音文件目录",
            },
        }
    )

    # 天气配置
    config_groups["天气配置"].update(
        {
            "WEATHER_API_KEY": {
                "value": config.media.weather.api_key,
                "description": "和风天气 API密钥",
                "type": "weather_api",
            },
            "WEATHER_BASE_URL": {
                "value": config.media.weather.base_url,
                "description": "和风天气 API基础URL",
                "type": "select",
                "options": [
                    {
                        "value": "https://devapi.qweather.com/v7/weather/24h",
                        "label": "免费版 (24h天气)"
                    },
                    {
                        "value": "https://api.qweather.com/v7/weather/24h",
                        "label": "付费版 (24h天气)"
                    }
                ]
            },
            "WEATHER_CITY_LIST": {
                "value": config.media.weather.city_list,
                "description": "要监听的城市列表",
                "type": "city_list"
            }
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

    return config_groups


def save_config(new_config: Dict[str, Any]) -> bool:
    """保存新的配置到文件"""
    try:
        from src.config import config
        from src.config import (
            UserSettings,
            CountdownSettings,
            AutoMessageSettings,
            QuietTimeSettings,
            ContextSettings,
            BehaviorSettings,
            WeatherSettings,
            MediaSettings,
            ImageRecognitionSettings,
            ImageGenerationSettings,
            TextToSpeechSettings
        )

        # 处理用户列表
        listen_list = new_config.get("LISTEN_LIST", [])
        if isinstance(listen_list, str):
            # 如果是字符串，尝试转换为列表
            if listen_list:
                listen_list = [x.strip() for x in listen_list.split(',') if x.strip()]
            else:
                listen_list = []
        elif isinstance(listen_list, list):
            # 过滤掉空字符串
            listen_list = [x.strip() for x in listen_list if x.strip()]
        else:
            listen_list = []

        logger.debug(f"处理后的用户列表: {listen_list}")

        # 构建倒计时设置
        countdown_settings = CountdownSettings(
            min_hours=float(new_config.get("MIN_COUNTDOWN_HOURS", 1.2)),
            max_hours=float(new_config.get("MAX_COUNTDOWN_HOURS", 3.0))
        )

        # 构建自动消息设置
        auto_message_settings = AutoMessageSettings(
            content=new_config.get("AUTO_MESSAGE", ""),
            countdown=countdown_settings
        )

        # 构建行为设置
        behavior_settings = BehaviorSettings(
            auto_message=auto_message_settings,
            quiet_time=QuietTimeSettings(
                start=new_config.get("QUIET_TIME_START", "22:00"),
                end=new_config.get("QUIET_TIME_END", "08:00")
            ),
            context=ContextSettings(
                max_groups=int(new_config.get("MAX_GROUPS", 15)),
                avatar_dir=new_config.get("AVATAR_DIR", "data/avatars/ATRI")
            )
        )

        # 构建天气设置
        weather_settings = WeatherSettings(
            api_key=new_config.get("WEATHER_API_KEY", ""),
            base_url=new_config.get("WEATHER_BASE_URL", ""),
            city_list=new_config.get("WEATHER_CITY_LIST", "").split(",") if new_config.get("WEATHER_CITY_LIST") else []
        )

        # 构建媒体设置
        media_settings = MediaSettings(
            image_recognition=ImageRecognitionSettings(
                api_key=new_config.get("MOONSHOT_API_KEY", ""),
                base_url=new_config.get("MOONSHOT_BASE_URL", ""),
                temperature=float(new_config.get("MOONSHOT_TEMPERATURE", 0.8))
            ),
            image_generation=ImageGenerationSettings(
                model=new_config.get("IMAGE_MODEL", ""),
                temp_dir=new_config.get("TEMP_IMAGE_DIR", "")
            ),
            text_to_speech=TextToSpeechSettings(
                tts_api_url=new_config.get("TTS_API_URL", ""),
                voice_dir=new_config.get("VOICE_DIR", "")
            ),
            weather=weather_settings
        )

        # 构建配置数据
        config_data = {
            "categories": {
                "user_settings": {
                    "title": "用户设置",
                    "settings": {
                        "listen_list": {
                            "value": listen_list,
                            "type": "array",
                            "description": "要监听的用户列表"
                        }
                    }
                },
                "llm_settings": {
                    "title": "大语言模型配置",
                    "settings": {
                        "api_key": {
                            "value": new_config.get("DEEPSEEK_API_KEY", ""),
                            "type": "string",
                            "description": "DeepSeek API密钥",
                            "is_secret": True,
                        },
                        "base_url": {
                            "value": new_config.get("DEEPSEEK_BASE_URL", ""),
                            "type": "string",
                            "description": "DeepSeek API基础URL",
                        },
                        "model": {
                            "value": new_config.get("MODEL", ""),
                            "type": "string",
                            "description": "使用的AI模型名称",
                            "options": [
                                "deepseek-ai/DeepSeek-V3",
                                "Pro/deepseek-ai/DeepSeek-V3",
                                "Pro/deepseek-ai/DeepSeek-R1",
                            ],
                        },
                        "max_tokens": {
                            "value": new_config.get("MAX_TOKEN", 2000),
                            "type": "number",
                            "description": "回复最大token数量",
                        },
                        "temperature": {
                            "value": new_config.get("TEMPERATURE", 1.1),
                            "type": "number",
                            "description": "AI回复的温度值",
                            "min": 0,
                            "max": 2,
                        },
                    },
                },
                "media_settings": {
                    "title": "媒体设置",
                    "settings": {
                        "image_recognition": {
                            "api_key": {
                                "value": media_settings.image_recognition.api_key,
                                "type": "string",
                                "description": "Moonshot AI API密钥（用于图片和表情包识别）",
                                "is_secret": True,
                            },
                            "base_url": {
                                "value": media_settings.image_recognition.base_url,
                                "type": "string",
                                "description": "Moonshot API基础URL",
                            },
                            "temperature": {
                                "value": media_settings.image_recognition.temperature,
                                "type": "number",
                                "description": "Moonshot AI的温度值",
                                "min": 0,
                                "max": 2,
                            },
                        },
                        "image_generation": {
                            "model": {
                                "value": media_settings.image_generation.model,
                                "type": "string",
                                "description": "图像生成模型",
                            },
                            "temp_dir": {
                                "value": media_settings.image_generation.temp_dir,
                                "type": "string",
                                "description": "临时图片存储目录",
                            },
                        },
                        "text_to_speech": {
                            "tts_api_url": {
                                "value": media_settings.text_to_speech.tts_api_url,
                                "type": "string",
                                "description": "TTS服务API地址",
                            },
                            "voice_dir": {
                                "value": media_settings.text_to_speech.voice_dir,
                                "type": "string",
                                "description": "语音文件存储目录",
                            },
                        },
                        "weather": {
                            "api_key": {
                                "value": weather_settings.api_key,
                                "type": "string",
                                "description": "和风天气 API密钥",
                                "is_secret": True,
                            },
                            "base_url": {
                                "value": weather_settings.base_url,
                                "type": "string",
                                "description": "和风天气 API基础URL",
                            },
                            "city_list": {
                                "value": weather_settings.city_list,
                                "type": "city_list",
                                "description": "要监听的城市列表"
                            }
                        }
                    },
                },
                "behavior_settings": {
                    "title": "行为设置",
                    "settings": {
                        "auto_message": {
                            "content": {
                                "value": behavior_settings.auto_message.content,
                                "type": "string",
                                "description": "自动消息内容",
                            },
                            "countdown": {
                                "min_hours": {
                                    "value": behavior_settings.auto_message.countdown.min_hours,
                                    "type": "number",
                                    "description": "最小倒计时时间（小时）",
                                },
                                "max_hours": {
                                    "value": behavior_settings.auto_message.countdown.max_hours,
                                    "type": "number",
                                    "description": "最大倒计时时间（小时）",
                                },
                            },
                        },
                        "quiet_time": {
                            "start": {
                                "value": behavior_settings.quiet_time.start,
                                "type": "string",
                                "description": "安静时间开始",
                            },
                            "end": {
                                "value": behavior_settings.quiet_time.end,
                                "type": "string",
                                "description": "安静时间结束",
                            },
                        },
                        "context": {
                            "max_groups": {
                                "value": behavior_settings.context.max_groups,
                                "type": "number",
                                "description": "最大上下文轮数",
                            },
                            "avatar_dir": {
                                "value": behavior_settings.context.avatar_dir,
                                "type": "string",
                                "description": "人设目录（自动包含 avatar.md 和 emojis 目录）",
                            },
                        },
                    },
                },
            }
        }

        # 添加调试日志
        logger.debug(f"最终的配置数据: {json.dumps(config_data, indent=2, ensure_ascii=False)}")

        # 保存配置
        success = config.save_config(config_data)
        if not success:
            logger.error("保存配置失败")
            return False

        # 重新加载配置
        importlib.reload(sys.modules["src.config"])
        return True

    except Exception as e:
        logger.error(f"保存配置失败: {str(e)}")
        logger.exception(e)
        return False


@app.route('/')
def index():
    """重定向到控制台"""
    return redirect(url_for('dashboard'))

@app.route('/save', methods=['POST'])
def save():
    """保存配置"""
    try:
        new_config = request.json
        # 添加调试日志
        logger.debug(f"接收到的配置数据: {new_config}")
        logger.debug(f"MIN_COUNTDOWN_HOURS type: {type(new_config.get('MIN_COUNTDOWN_HOURS'))}")
        logger.debug(f"MIN_COUNTDOWN_HOURS value: {new_config.get('MIN_COUNTDOWN_HOURS')}")

        if save_config(new_config):
            return jsonify({"status": "success", "message": "配置已保存"})
        return jsonify({"status": "error", "message": "保存失败"})
    except Exception as e:
        logger.error(f"保存失败: {str(e)}")
        return jsonify({"status": "error", "message": f"保存失败: {str(e)}"})

# 添加上传处理路由
@app.route('/upload_background', methods=['POST'])
def upload_background():
    if 'background' not in request.files:
        return jsonify({"status": "error", "message": "没有选择文件"})

    file = request.files['background']
    if file.filename == '':
        return jsonify({"status": "error", "message": "没有选择文件"})

    if file:
        filename = secure_filename(file.filename)
        # 清理旧的背景图片
        for old_file in os.listdir(app.config['UPLOAD_FOLDER']):
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_file))
        # 保存新图片
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({
            "status": "success",
            "message": "背景图片已更新",
            "path": f"/background_image/{filename}"
        })

# 添加背景图片目录的路由
@app.route('/background_image/<filename>')
def background_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 添加获取背景图片路由
@app.route('/get_background')
def get_background():
    """获取当前背景图片"""
    try:
        # 获取背景图片目录中的第一个文件
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        if files:
            # 返回找到的第一个图片
            return jsonify({
                "status": "success",
                "path": f"/background_image/{files[0]}"
            })
        return jsonify({
            "status": "success",
            "path": None
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

# 添加新的路由
@app.route('/dashboard')
def dashboard():
    """渲染控制台页面"""
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/system_info')
def system_info():
    """获取系统信息"""
    try:
        # 创建静态变量存储上次的值
        if not hasattr(system_info, 'last_bytes'):
            system_info.last_bytes = {
                'sent': 0,
                'recv': 0,
                'time': time.time()
            }

        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        
        # 计算网络速度
        current_time = time.time()
        time_delta = current_time - system_info.last_bytes['time']
        
        # 计算每秒的字节数
        upload_speed = (net.bytes_sent - system_info.last_bytes['sent']) / time_delta
        download_speed = (net.bytes_recv - system_info.last_bytes['recv']) / time_delta
        
        # 更新上次的值
        system_info.last_bytes = {
            'sent': net.bytes_sent,
            'recv': net.bytes_recv,
            'time': current_time
        }
        
        # 转换为 KB/s
        upload_speed = upload_speed / 1024
        download_speed = download_speed / 1024
        
        return jsonify({
            'cpu': cpu_percent,
            'memory': {
                'total': round(memory.total / (1024**3), 2),
                'used': round(memory.used / (1024**3), 2),
                'percent': memory.percent
            },
            'disk': {
                'total': round(disk.total / (1024**3), 2),
                'used': round(disk.used / (1024**3), 2),
                'percent': disk.percent
            },
            'network': {
                'upload': round(upload_speed, 2),
                'download': round(download_speed, 2)
            }
        })
    except Exception as e:
        logger.error(f"获取系统信息失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/check_update')
def check_update():
    """检查更新"""
    updater = Updater()
    update_info = updater.check_for_updates()
    return jsonify(update_info if update_info else {'has_update': False})

@app.route('/do_update')
def do_update():
    """执行更新"""
    updater = Updater()
    success = updater.update()
    return jsonify({
        'status': 'success' if success else 'error',
        'message': '更新成功，请重启程序' if success else '更新失败'
    })

@app.route('/start_bot')
def start_bot():
    """启动机器人"""
    global bot_process, bot_start_time
    try:
        if bot_process and bot_process.poll() is None:
            return jsonify({
                'status': 'error',
                'message': '机器人已在运行中'
            })
        
        # 清空之前的日志
        while not bot_logs.empty():
            bot_logs.get()
        
        # 设置环境变量
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        # 创建新的进程组
        if sys.platform.startswith('win'):
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            creationflags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        else:
            creationflags = 0
        
        # 启动进程
        bot_process = subprocess.Popen(
            [sys.executable, 'run.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            env=env,
            encoding='utf-8',
            errors='replace',
            creationflags=creationflags if sys.platform.startswith('win') else 0,
            preexec_fn=os.setsid if not sys.platform.startswith('win') else None
        )
        
        # 记录启动时间
        bot_start_time = datetime.datetime.now()
        
        # 启动日志读取线程
        def read_output():
            try:
                while bot_process and bot_process.poll() is None:
                    line = bot_process.stdout.readline()
                    if line:
                        try:
                            # 尝试解码并清理日志内容
                            line = line.strip()
                            if isinstance(line, bytes):
                                line = line.decode('utf-8', errors='replace')
                            timestamp = datetime.datetime.now().strftime('%H:%M:%S')
                            bot_logs.put(f"[{timestamp}] {line}")
                        except Exception as e:
                            logger.error(f"日志处理错误: {str(e)}")
                            continue
            except Exception as e:
                logger.error(f"读取日志失败: {str(e)}")
                bot_logs.put(f"[ERROR] 读取日志失败: {str(e)}")
        
        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': '机器人启动成功'
        })
    except Exception as e:
        logger.error(f"启动机器人失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/get_bot_logs')
def get_bot_logs():
    """获取机器人日志"""
    logs = []
    while not bot_logs.empty():
        logs.append(bot_logs.get())
    
    # 获取运行时间
    uptime = '0分钟'
    if bot_start_time and bot_process and bot_process.poll() is None:
        delta = datetime.datetime.now() - bot_start_time
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            uptime = f"{hours}小时{minutes}分钟{seconds}秒"
        elif minutes > 0:
            uptime = f"{minutes}分钟{seconds}秒"
        else:
            uptime = f"{seconds}秒"
    
    return jsonify({
        'status': 'success',
        'logs': logs,
        'uptime': uptime,
        'is_running': bot_process is not None and bot_process.poll() is None
    })

@app.route('/stop_bot')
def stop_bot():
    """停止机器人"""
    global bot_process
    try:
        if bot_process:
            # 首先尝试正常终止进程
            bot_process.terminate()
            
            # 等待进程结束
            try:
                bot_process.wait(timeout=5)  # 等待最多5秒
            except subprocess.TimeoutExpired:
                # 如果超时，强制结束进程
                bot_process.kill()
                bot_process.wait()
            
            # 确保所有子进程都被终止
            if sys.platform.startswith('win'):
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(bot_process.pid)], 
                             capture_output=True)
            else:
                import signal
                os.killpg(os.getpgid(bot_process.pid), signal.SIGTERM)
            
            # 清理进程对象
            bot_process = None
            
            # 添加日志记录
            timestamp = datetime.datetime.now().strftime('%H:%M:%S')
            bot_logs.put(f"[{timestamp}] 正在关闭监听线程...")
            bot_logs.put(f"[{timestamp}] 正在关闭系统...")
            bot_logs.put(f"[{timestamp}] 系统已退出")
            
            return jsonify({
                'status': 'success',
                'message': '机器人已停止'
            })
            
        return jsonify({
            'status': 'error',
            'message': '机器人未在运行'
        })
    except Exception as e:
        logger.error(f"停止机器人失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/config')
def config():
    """渲染配置页面"""
    config_groups = parse_config_groups()
    return render_template('config.html', config_groups=config_groups, active_page='config')

# 添加获取用户信息的路由
@app.route('/user_info')
def get_user_info():
    """获取用户账户信息"""
    try:
        from src.config import config
        api_key = config.llm.api_key
        base_url = config.llm.base_url.rstrip('/')
        
        # 确保使用正确的API端点
        if 'siliconflow.cn' in base_url:
            api_url = f"{base_url}/user/info"
        else:
            return jsonify({
                'status': 'error',
                'message': '当前API不支持查询用户信息'
            })
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') is True and data.get('data'):  # 修改判断条件
                user_data = data['data']
                return jsonify({
                    'status': 'success',
                    'data': {
                        'balance': user_data.get('balance', '0'),
                        'total_balance': user_data.get('totalBalance', '0'),
                        'charge_balance': user_data.get('chargeBalance', '0'),
                        'name': user_data.get('name', 'Unknown'),
                        'email': user_data.get('email', 'Unknown'),
                        'status': user_data.get('status', 'Unknown')
                    }
                })
            
        return jsonify({
            'status': 'error',
            'message': f"API返回错误: {response.text}"
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f"获取用户信息失败: {str(e)}"
        })

# 在 app 初始化后添加
@app.route('/static/<path:filename>')
def serve_static(filename):
    """提供静态文件服务"""
    return send_from_directory(app.static_folder, filename)

def main():
    """主函数"""
    from src.config import config

    print("\n" + "="*50)
    print_status("配置管理系统启动中...", "info", "🚀")
    print("-"*50)

    # 检查必要目录
    print_status("检查系统目录...", "info", "📁")
    if not os.path.exists(os.path.join(ROOT_DIR, 'src/webui/templates')):
        print_status("错误：模板目录不存在！", "error", "❌")
        return
    print_status("系统目录检查完成", "success", "✅")

    # 检查配置文件
    print_status("检查配置文件...", "info", "⚙️")
    if not os.path.exists(config.config_path):
        print_status("错误：配置文件不存在！", "error", "❌")
        return
    print_status("配置文件检查完成", "success", "✅")

    # 清理缓存
    print_status("清理系统缓存...", "info", "🧹")
    cleanup_count = 0
    for root, dirs, files in os.walk(ROOT_DIR):
        if '__pycache__' in dirs:
            cleanup_count += 1
    if cleanup_count > 0:
        print_status(f"已清理 {cleanup_count} 个缓存目录", "success", "🗑️")
    else:
        print_status("没有需要清理的缓存", "info", "✨")
        
    # 修改启动 Web 服务器的部分
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None # 禁用 Flask 启动横幅
    
    print_status("正在启动Web服务...", "info", "🌐")
    print("-"*50)
    print_status("配置管理系统已就绪！", "success", "✨")
    print_status("请访问: http://localhost:8501", "info", "🔗")
    print("="*50 + "\n")
    
    if sys.platform.startswith('win'):
        import subprocess
        subprocess.run(['chcp', '65001'], shell=True)
    
    app.run(
        host='0.0.0.0', 
        port=8501, 
        debug=True,
        use_reloader=True
    )

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_status("正在关闭服务...", "warning", "🛑")
        print_status("配置管理系统已停止", "info", "👋")
        print("\n")
    except Exception as e:
        print_status(f"系统错误: {str(e)}", "error", "💥")
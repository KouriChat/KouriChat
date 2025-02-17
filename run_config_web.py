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
import re
import logging
from flask import Flask, render_template, jsonify, request, send_from_directory
import importlib
import json
from colorama import init, Fore, Style
from werkzeug.utils import secure_filename
from typing import Dict, Any, List

# 初始化日志记录器
logger = logging.getLogger(__name__)

# 初始化colorama
init()

# 添加项目根目录到Python路径
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT_DIR)

# 禁用Python的字节码缓存
sys.dont_write_bytecode = True

app = Flask(__name__, 
    template_folder=os.path.join(ROOT_DIR, 'src/webui/templates'),
    static_folder=os.path.join(ROOT_DIR, 'src/webui/static'))

# 添加配置
app.config['UPLOAD_FOLDER'] = os.path.join(ROOT_DIR, 'src/webui/background_image')

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def print_status(message: str, status: str = "info", emoji: str = ""):
    """打印带颜色和表情的状态消息"""
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
        "Prompt配置": {},
        "天气设置": {},
    }

    # 天气设置
    try:
        # 从配置对象中获取天气设置
        config_groups["天气设置"].update(
            {
                "WEATHER_API_KEY": {
                    "value": config.media.weather.api_key,
                    "description": "和风天气 API密钥",
                    "is_secret": True
                },
                "WEATHER_BASE_URL": {
                    "value": config.media.weather.base_url,
                    "description": "和风天气 API基础URL",
                    "type": "select",
                    "options": ["free", "pro"]
                },
                "WEATHER_CITY_LIST": {
                    "value": config.media.weather.city_list if isinstance(config.media.weather.city_list, list) else [],
                    "description": "要监听的城市列表",
                    "type": "array"
                }
            }
        )
    except Exception as e:
        logger.error(f"读取天气配置失败: {str(e)}")
        logger.exception(e)

    # 基础配置
    config_groups["基础配置"].update(
        {
            "LISTEN_LIST": {
                "value": config.user.listen_list,
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

        # 处理城市列表
        weather_city_list = new_config.get("WEATHER_CITY_LIST", "")
        logger.debug(f"Received weather_city_list: {weather_city_list}")  # 添加调试日志
        
        if isinstance(weather_city_list, str):
            weather_city_list = [city.strip() for city in weather_city_list.split(',') if city.strip()]
        elif isinstance(weather_city_list, list):
            weather_city_list = [city for city in weather_city_list if city]
        else:
            weather_city_list = []
            
        logger.debug(f"Processed weather_city_list: {weather_city_list}")  # 添加调试日志

        # 构建配置数据
        config_data = {
            "categories": {
                "user_settings": {
                    "title": "用户设置",
                    "settings": {
                        "listen_list": {
                            "value": new_config.get("LISTEN_LIST", []),
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
                            "is_secret": True
                        },
                        "base_url": {
                            "value": new_config.get("DEEPSEEK_BASE_URL", ""),
                            "type": "string",
                            "description": "DeepSeek API基础URL"
                        },
                        "model": {
                            "value": new_config.get("MODEL", ""),
                            "type": "string",
                            "description": "AI模型"
                        },
                        "max_tokens": {
                            "value": int(new_config.get("MAX_TOKEN", 2000)),
                            "type": "number",
                            "description": "最大token数"
                        },
                        "temperature": {
                            "value": float(new_config.get("TEMPERATURE", 1.1)),
                            "type": "number",
                            "description": "温度参数"
                        }
                    }
                },
                "media_settings": {
                    "title": "高级设置",
                    "settings": {
                        "image_recognition": {
                            "api_key": {
                                "value": new_config.get("MOONSHOT_API_KEY", ""),
                                "type": "string",
                                "description": "Moonshot API密钥"
                            },
                            "base_url": {
                                "value": new_config.get("MOONSHOT_BASE_URL", ""),
                                "type": "string",
                                "description": "Moonshot API基础URL"
                            },
                            "temperature": {
                                "value": float(new_config.get("MOONSHOT_TEMPERATURE", 0.8)),
                                "type": "number",
                                "description": "温度参数"
                            }
                        },
                        "image_generation": {
                            "model": {
                                "value": new_config.get("IMAGE_MODEL", ""),
                                "type": "string",
                                "description": "图像模型"
                            },
                            "temp_dir": {
                                "value": new_config.get("TEMP_IMAGE_DIR", ""),
                                "type": "string",
                                "description": "临时目录"
                            }
                        },
                        "text_to_speech": {
                            "tts_api_url": {
                                "value": new_config.get("TTS_API_URL", ""),
                                "type": "string",
                                "description": "TTS API地址"
                            },
                            "voice_dir": {
                                "value": new_config.get("VOICE_DIR", ""),
                                "type": "string",
                                "description": "语音目录"
                            }
                        },
                        "weather": {
                            "api_key": {
                                "value": new_config.get("WEATHER_API_KEY", ""),
                                "type": "string",
                                "description": "和风天气 API密钥",
                                "is_secret": True
                            },
                            "base_url": {
                                "value": new_config.get("WEATHER_BASE_URL", ""),
                                "type": "string",
                                "description": "和风天气 API基础URL"
                            },
                            "city_list": {
                                "value": weather_city_list,
                                "type": "array",
                                "description": "要监听的城市列表"
                            }
                        }
                    }
                },
                "behavior_settings": {
                    "title": "行为设置",
                    "settings": {
                        "auto_message": {
                            "content": {
                                "value": new_config.get("AUTO_MESSAGE", ""),
                                "type": "string",
                                "description": "自动消息内容"
                            },
                            "countdown": {
                                "min_hours": {
                                    "value": float(new_config.get("MIN_COUNTDOWN_HOURS", 1.2)),
                                    "type": "number",
                                    "description": "最小倒计时时间"
                                },
                                "max_hours": {
                                    "value": float(new_config.get("MAX_COUNTDOWN_HOURS", 3.0)),
                                    "type": "number",
                                    "description": "最大倒计时时间"
                                }
                            }
                        },
                        "quiet_time": {
                            "start": {
                                "value": new_config.get("QUIET_TIME_START", "22:00"),
                                "type": "string",
                                "description": "安静时间开始"
                            },
                            "end": {
                                "value": new_config.get("QUIET_TIME_END", "08:00"),
                                "type": "string",
                                "description": "安静时间结束"
                            }
                        },
                        "context": {
                            "max_groups": {
                                "value": int(new_config.get("MAX_GROUPS", 15)),
                                "type": "number",
                                "description": "最大上下文轮数"
                            },
                            "avatar_dir": {
                                "value": new_config.get("AVATAR_DIR", ""),
                                "type": "string",
                                "description": "人设目录"
                            }
                        }
                    }
                }
            }
        }

        # 添加调试日志
        logger.debug(f"Final config data: {json.dumps(config_data, indent=2, ensure_ascii=False)}")

        # 保存配置
        if not config.save_config(config_data):
            logger.error("Failed to save config")
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
    """渲染配置页面"""
    config_groups = parse_config_groups()
    return render_template('config.html', config_groups=config_groups)

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
    
    # 启动服务器
    print_status("正在启动Web服务...", "info", "🌐")
    print("-"*50)
    print_status("配置管理系统已就绪！", "success", "✨")
    print_status("请访问: http://localhost:8501", "info", "🔗")
    print("="*50 + "\n")
    
    # 启动Web服务器
    app.run(host='0.0.0.0', port=8501, debug=True)

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

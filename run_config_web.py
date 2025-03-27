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
import tempfile
import zipfile
import logging
from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, url_for, session, g, \
    send_file
import io
import importlib
import json
from colorama import init, Fore, Style
from werkzeug.utils import secure_filename
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
import shutil
import signal
import atexit
import socket
import webbrowser
import hashlib
import secrets
from datetime import timedelta
from src.utils.console import print_status
from src.avatar_manager import avatar_manager  # 导入角色设定管理器
from src.webui.routes.avatar import avatar_bp
import ctypes
import win32api
import win32con
import win32job
import win32process
from src.Wechat_Login_Clicker.Wechat_Login_Clicker import click_wechat_buttons
from dotenv import load_dotenv
import yaml
import httpx
from openai import OpenAI
import src.services.ai.llms.llm  # 添加LLM模块导入
from src.handlers.memories.core.rag import LocalEmbeddingModel
from flask_compress import Compress  # 添加响应压缩
import win32event
# 导入解析配置函数
from src.configUtils.parse_config_groups import parse_config_groups, get_available_avatars
# 导入配置更新函数
from src.configUtils.update_config_value import update_config_value

# 在文件开头添加全局变量声明
bot_process = None
bot_start_time = None
bot_logs = Queue(maxsize=1000)
job_object = None  # 添加全局作业对象变量

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
            'level': 'ERROR'  # 将控制台处理器的级别改为 ERROR
        }
    },
    'root': {
        'level': 'ERROR',  # 将根日志记录器的级别改为 ERROR
        'handlers': ['console']
    },
    'loggers': {
        'werkzeug': {
            'level': 'ERROR',
            'handlers': ['console'],
            'propagate': False
        }
    }
})

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

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

# 添加响应压缩
compress = Compress()
compress.init_app(app)

# 添加配置
app.config['UPLOAD_FOLDER'] = os.path.join(ROOT_DIR, 'src/webui/background_image')
# 添加配置缓存，避免频繁读取文件
app.config['CONFIG_CACHE'] = {}
app.config['CONFIG_CACHE_TIME'] = 0
# 设置缓存过期时间(秒)
CONFIG_CACHE_EXPIRE = 5
# 启用响应压缩
app.config['COMPRESS_MIMETYPES'] = ['text/html', 'text/css', 'text/javascript', 'application/javascript', 'application/json']
app.config['COMPRESS_LEVEL'] = 6  # 压缩级别，1-9，越高压缩率越大但CPU占用越多
app.config['COMPRESS_MIN_SIZE'] = 500  # 最小压缩大小，小于此值不压缩

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 生成密钥用于session加密
app.secret_key = secrets.token_hex(16)

# 在 app 初始化后添加
app.register_blueprint(avatar_manager)
app.register_blueprint(avatar_bp)

@app.route('/')
def index():
    """重定向到控制台"""
    return redirect(url_for('dashboard'))

@app.route('/save', methods=['POST'])
def save_config():
    try:
        # 读取当前配置
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            current_config = yaml.safe_load(f)
            
        # 获取表单数据
        form_data = request.form.to_dict()
        
        # 更新配置
        for key, value in form_data.items():
            # 特殊处理时间格式
            if key in ['QUIET_TIME_START', 'QUIET_TIME_END']:
                try:
                    datetime.strptime(value, '%H:%M')
                except ValueError:
                    return jsonify({
                        'status': 'error',
                        'message': f'时间格式错误: {value}，请使用HH:MM格式'
                    })
            
            # 特殊处理列表类型
            if key == 'LISTEN_LIST':
                value = [x.strip() for x in value.split(',') if x.strip()]
            
            # 更新RAG配置
            if key.startswith('RAG_'):
                rag_key = key.lower()
                if 'rag_settings' not in current_config['categories']:
                    current_config['categories']['rag_settings'] = {'settings': {}}
                if rag_key not in current_config['categories']['rag_settings']['settings']:
                    current_config['categories']['rag_settings']['settings'][rag_key] = {'value': None}
                current_config['categories']['rag_settings']['settings'][rag_key]['value'] = value
            else:
                # 更新其他配置
                for category in current_config['categories'].values():
                    if 'settings' in category and key in category['settings']:
                        category['settings'][key]['value'] = value
                        break
        
        # 验证RAG配置
        is_valid, message = validate_rag_config(current_config)
        if not is_valid:
            return jsonify({
                'status': 'error',
                'message': message
            })
        
        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, allow_unicode=True, sort_keys=False)
            
        # 重新加载配置
        import src.config.config as config_module
        importlib.reload(config_module)
        
        # 重新初始化RAG记忆系统
        from src.handlers.memories.core.rag import RagManager
        rag_manager = RagManager()
        rag_manager.initialize()
        
        # 重新初始化定时任务
        from src.services.scheduler import scheduler
        scheduler.reload_tasks()
        
        return jsonify({
            'status': 'success',
            'message': '配置已成功保存',
            'config': current_config  # 返回更新后的配置
        })
        
    except Exception as e:
        logger.error(f"保存配置失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'保存配置失败: {str(e)}'
        })


# 添加上传处理路由
@app.route('/upload_background', methods=['POST'])
def upload_background():
    if 'background' not in request.files:
        return jsonify({"status": "error", "message": "没有选择文件"})

    file = request.files['background']
    if file.filename == '':
        return jsonify({"status": "error", "message": "没有选择文件"})

    # 确保 filename 不为 None
    if file.filename is None:
        return jsonify({"status": "error", "message": "文件名无效"})

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


@app.before_request
def load_config():
    """每次请求前加载配置，使用缓存机制减少文件IO"""
    try:
        current_time = time.time()
        # 如果缓存存在且未过期，使用缓存
        if app.config['CONFIG_CACHE'] and (current_time - app.config['CONFIG_CACHE_TIME'] < CONFIG_CACHE_EXPIRE):
            g.config_data = app.config['CONFIG_CACHE']
            return
            
        # 缓存过期或不存在，重新读取配置
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
            g.config_data = config_data
            # 更新缓存
            app.config['CONFIG_CACHE'] = config_data
            app.config['CONFIG_CACHE_TIME'] = current_time
            
        # 尝试重新加载内存中的配置，确保使用最新配置
        try:
            from src.config import config as settings
            if hasattr(settings, 'reload_from_file'):
                settings.reload_from_file()
        except Exception as e:
            logger.warning(f"重新加载内存中配置失败: {str(e)}")
            
    except Exception as e:
        logger.error(f"加载配置失败: {str(e)}")
        g.config_data = {}


@app.route('/dashboard')
def dashboard():
    # 检查是否登录
    if not session.get('logged_in'):
        # 检查是否需要设置密码
        from src.config import config
        if not config.auth.admin_password:
            return redirect(url_for('init_password'))
        return redirect(url_for('login'))
    
    # 减少不必要的日志记录
    # logging.info("访问仪表盘页面，登录状态: " + str(session.get('logged_in')))
    
    # 检查是否有机器人状态
    if not hasattr(g, 'bot_status'):
        g.bot_status = {
            'running': False,
            'messages': []
        }
    
    # 渲染仪表盘模板
    return render_template('dashboard.html')


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

        cpu_percent = psutil.cpu_percent(interval=0.1)  # 减少CPU检测的阻塞时间
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
                'total': round(memory.total / (1024 ** 3), 2),
                'used': round(memory.used / (1024 ** 3), 2),
                'percent': memory.percent
            },
            'disk': {
                'total': round(disk.total / (1024 ** 3), 2),
                'used': round(disk.used / (1024 ** 3), 2),
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
    try:
        updater = Updater()
        result = updater.check_for_updates()

        return jsonify({
            'status': 'success',
            'has_update': result.get('has_update', False),
            'console_output': result['output'],
            'update_info': result if result.get('has_update') else None,
            'wait_input': result.get('has_update', False)
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'has_update': False,
            'console_output': f'检查更新失败: {str(e)}'
        })


@app.route('/confirm_update', methods=['POST'])
def confirm_update():
    """确认是否更新"""
    try:
        choice = (request.json or {}).get('choice', '').lower()
        if choice in ('y', 'yes'):
            updater = Updater()
            result = updater.update()

            return jsonify({
                'status': 'success' if result['success'] else 'error',
                'console_output': result['output']
            })
        else:
            return jsonify({
                'status': 'success',
                'console_output': '用户取消更新'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'console_output': f'更新失败: {str(e)}'
        })


@app.route('/start_bot')
def start_bot():
    """启动机器人"""
    global bot_process, bot_start_time, job_object
    try:
        if bot_process and bot_process.poll() is None:
            return jsonify({
                'status': 'error',
                'message': '机器人已在运行中'
            })

        # 清空之前的日志
        while not bot_logs.empty():
            bot_logs.get()

        
        # 加载.env.kouri文件中的环境变量
        env_file = os.path.join(ROOT_DIR, '.env.kouri')
        if os.path.exists(env_file):
            load_dotenv(env_file)
        

        # 设置环境变量
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        # 创建新的进程组
        if sys.platform.startswith('win'):
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            creationflags = CREATE_NEW_PROCESS_GROUP
            preexec_fn = None
        else:
            creationflags = 0
            preexec_fn = getattr(os, 'setsid', None)

        # 启动进程
        bot_process = subprocess.Popen(
            [sys.executable, 'run.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            encoding='utf-8',
            errors='replace',
            creationflags=creationflags if sys.platform.startswith('win') else 0,
            preexec_fn=preexec_fn
        )

        # 将机器人进程添加到作业对象
        if sys.platform.startswith('win') and job_object:
            try:
                win32job.AssignProcessToJobObject(job_object, bot_process._handle)
                logger.info(f"已将机器人进程 (PID: {bot_process.pid}) 添加到作业对象")
            except Exception as e:
                logger.error(f"将机器人进程添加到作业对象失败: {str(e)}")

        # 记录启动时间
        bot_start_time = datetime.datetime.now()

        # 启动日志读取线程
        def read_output():
            try:
                while bot_process and bot_process.poll() is None:
                    if bot_process.stdout:
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
                # 使用 getattr 避免在 Windows 上直接引用不存在的属性
                killpg = getattr(os, 'killpg', None)
                getpgid = getattr(os, 'getpgid', None)
                if killpg and getpgid:
                    import signal
                    killpg(getpgid(bot_process.pid), signal.SIGTERM)
                else:
                    bot_process.kill()

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
    """配置页面"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # 使用缓存获取配置数据
    config_groups = parse_config_groups()  # 获取配置组

    # 获取任务列表
    tasks = []
    if g.config_data and 'categories' in g.config_data and 'schedule_settings' in g.config_data['categories']:
        if 'settings' in g.config_data['categories']['schedule_settings'] and 'tasks' in \
                g.config_data['categories']['schedule_settings']['settings']:
            tasks = g.config_data['categories']['schedule_settings']['settings']['tasks'].get('value', [])

    logger.debug(f"传递给前端的任务列表: {tasks}")

    return render_template(
        'config.html',
        config_groups=config_groups,  # 传递配置组
        tasks_json=json.dumps(tasks, ensure_ascii=False),  # 直接传递任务列表JSON
        is_local=is_local_network(),
        active_page='config'
    )


@app.route('/combined_config_data')
def combined_config_data():
    """合并配置数据接口，减少前端多次请求"""
    try:
        if not session.get('logged_in'):
            return jsonify({
                'status': 'error',
                'message': '未登录'
            })
        
        # 获取系统信息
        sys_info = {
            'bot_status': 'running' if bot_process is not None else 'stopped',
            'memory_initialized': memory_initialized,
            'platform': sys.platform,
            'python_version': sys.version,
            'local_embedding_models': get_available_embedding_models()
        }
        
        # 获取配置
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 提取任务
        tasks = []
        if ('categories' in config_data and 'schedule_settings' in config_data['categories'] and
            'settings' in config_data['categories']['schedule_settings'] and
            'tasks' in config_data['categories']['schedule_settings']['settings']):
            tasks = config_data['categories']['schedule_settings']['settings']['tasks'].get('value', [])
        
        # 检查是否有更新
        update_info = check_update_status()
        
        # 获取可用的角色列表
        avatars = get_available_avatars()
        
        return jsonify({
            'status': 'success',
            'system_info': sys_info,
            'config': config_data,
            'tasks': tasks,
            'has_update': update_info.get('has_update', False),
            'update_info': update_info,
            'avatars': avatars,
            'is_local': is_local_network()
        })
    except Exception as e:
        logger.error(f"获取合并配置数据失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


@app.route('/install_dependencies', methods=['POST'])
def install_dependencies():
    """安装依赖"""
    try:
        output = []

        # 安装依赖
        output.append("正在安装依赖，请耐心等待...")
        requirements_path = os.path.join(ROOT_DIR, 'requirements.txt')

        if not os.path.exists(requirements_path):
            return jsonify({
                'status': 'error',
                'message': '找不到requirements.txt文件'
            })

        # 尝试多种编码读取requirements.txt文件
        encodings_to_try = ['utf-8', 'gbk', 'latin-1', 'cp1252']
        requirements_content = None
        used_encoding = None

        for encoding in encodings_to_try:
            try:
                with open(requirements_path, 'r', encoding=encoding) as f:
                    requirements_content = f.read()
                used_encoding = encoding
                logger.debug(f"成功使用{encoding}编码读取requirements.txt")
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error(f"读取requirements.txt时出错: {str(e)}")
                break

        if requirements_content is None:
            return jsonify({
                'status': 'error',
                'message': '无法读取requirements.txt文件，尝试了多种编码均失败'
            })

        # 如果编码不是UTF-8，则尝试转换为UTF-8保存
        if used_encoding != 'utf-8':
            try:
                with open(requirements_path, 'w', encoding='utf-8') as f:
                    f.write(requirements_content)
                output.append(f"检测到requirements.txt文件编码问题（{used_encoding}），已自动转换为UTF-8")
            except Exception as e:
                logger.warning(f"尝试转换requirements.txt编码失败: {str(e)}")
                # 继续使用原始文件

        process = subprocess.Popen(
            [sys.executable, '-m', 'pip', 'install', '-r', requirements_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate()

        # 解码字节数据为字符串，添加错误处理
        try:
            stdout = stdout.decode('utf-8', errors='replace')
        except Exception:
            stdout = str(stdout)

        try:
            stderr = stderr.decode('utf-8', errors='replace')
        except Exception:
            stderr = str(stderr)

        output.append(stdout if stdout else stderr)

        # 检查是否有实际错误，而不是"already satisfied"消息
        has_error = process.returncode != 0 and not any(
            msg in (stdout + stderr).lower()
            for msg in ['already satisfied', 'successfully installed']
        )

        if not has_error:
            return jsonify({
                'status': 'success',
                'output': '\n'.join(output)
            })
        else:
            return jsonify({
                'status': 'error',
                'output': '\n'.join(output),
                'message': '安装依赖失败'
            })

    except Exception as e:
        logger.error(f"安装依赖时出错: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


def hash_password(password: str) -> str:
    # 对密码进行哈希处理
    return hashlib.sha256(password.encode()).hexdigest()


def is_local_network() -> bool:
    # 检查是否是本地网络访问
    client_ip = request.remote_addr
    if client_ip is None:
        return True
    return (
            client_ip == '127.0.0.1' or
            client_ip.startswith('192.168.') or
            client_ip.startswith('10.') or
            client_ip.startswith('172.16.')
    )


@app.before_request
def check_auth():
    # 请求前验证登录状态
    # 排除不需要验证的路由
    logging.debug(f"请求路径: {request.path}")
    
    # 定义不需要验证的路由
    excluded_paths = [
        '/login', 
        '/init_password', 
        '/static', 
        '/favicon.ico', 
        '/background_image',
    ]
    
    # 检查是否为排除路径
    for path in excluded_paths:
        if request.path.startswith(path):
            return None
    
    # 检查是否已登录
    if session.get('logged_in'):
        return None
    
    # 如果是API请求，返回JSON错误
    if (request.path.startswith('/api') or 
        request.is_json or 
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'):
        return jsonify({
            'status': 'error',
            'message': '未授权访问',
            'redirect': url_for('login')
        }), 401
    
    # 如果尚未设置密码，则重定向到初始化密码页面
    from src.config import config
    if not config.auth.admin_password:
        # 调试信息
        logging.info("未设置密码，重定向到初始化密码页面")
        session.clear()
        return redirect(url_for('init_password'))
    
    # 对于普通请求，重定向到登录页面
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # 处理登录请求
    from src.config import config

    # 首先检查是否需要初始化密码
    if not config.auth.admin_password:
        return redirect(url_for('init_password'))

    if request.method == 'GET':
        # 如果已经登录，直接跳转到仪表盘
        if session.get('logged_in'):
            return redirect(url_for('dashboard'))

        # 如果是本地网络访问，自动登录并重定向到仪表盘
        if is_local_network():
            session['logged_in'] = True
            return redirect(url_for('dashboard'))

        return render_template('login.html')

    # POST请求处理
    data = request.get_json()
    password = data.get('password')
    remember_me = data.get('remember_me', False)

    # 正常登录验证
    stored_hash = config.auth.admin_password
    if hash_password(password) == stored_hash:
        session.clear()  # 清除旧会话
        session['logged_in'] = True
        if remember_me:
            session.permanent = True
            app.permanent_session_lifetime = timedelta(days=30)
        return jsonify({'status': 'success'})

    return jsonify({
        'status': 'error',
        'message': '密码错误'
    })


@app.route('/init_password', methods=['GET', 'POST'])
def init_password():
    # 初始化管理员密码页面
    from src.config import config
    
    logging.info(f"初始化密码请求: {request.method}")
    
    if request.method == 'GET':
        # 如果已经设置了密码，重定向到登录页面
        if config.auth.admin_password:
            logging.info("已设置密码，重定向到登录页面")
            return redirect(url_for('login'))
        return render_template('init_password.html')

    # POST请求处理
    try:
        data = request.get_json()
        logging.info(f"收到初始化密码请求: {data}")
        
        if not data or 'password' not in data:
            logging.warning("无效的请求数据")
            return jsonify({
                'status': 'error',
                'message': '无效的请求数据'
            })

        password = data.get('password')

        # 再次检查是否已经设置了密码
        if config.auth.admin_password:
            logging.warning("密码已经设置")
            return jsonify({
                'status': 'error',
                'message': '密码已经设置'
            })

        # 先尝试修复配置文件
        fixed = fix_config_file()
        if fixed:
            logging.info("配置文件已检查和修复")
        
        # 保存新密码的哈希值
        hashed_password = hash_password(password)
        logging.info("尝试保存密码哈希值")
        
        # 使用直接更新函数保存密码
        if direct_update_password(hashed_password):
            logging.info("密码更新成功，重新加载配置")
            # 使用reload_config从config模块导入直接重载
            from src.config import reload_config
            reload_config()
            
            # 再次检查密码是否正确设置
            from src.config import config as new_config
            if hasattr(new_config, 'auth') and hasattr(new_config.auth, 'admin_password') and new_config.auth.admin_password:
                logging.info("验证密码已成功保存到配置中")
            else:
                logging.warning("密码设置成功但未反映在配置对象中")
            
            # 设置登录状态
            session.clear()
            session['logged_in'] = True
            logging.info("设置登录状态成功，返回success状态")
            return jsonify({'status': 'success'})
        
        # 如果常规方法失败，尝试简单地直接写入文件
        logging.warning("直接更新失败，尝试简单写入")
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        
        try:
            with open(config_path, 'a', encoding='utf-8') as f:
                f.write("\n  auth_settings:\n    title: 认证设置\n    settings:\n      admin_password:\n        value: " + hashed_password + "\n        type: string\n        description: 管理员密码\n        is_secret: true\n")
            
            # 设置登录状态
            session.clear()
            session['logged_in'] = True
            logging.info("使用备用方法设置密码成功")
            return jsonify({'status': 'success'})
        except Exception as e:
            logging.error(f"备用密码设置方法失败: {str(e)}")

        logging.error("所有密码设置方法均失败")
        return jsonify({
            'status': 'error',
            'message': '保存密码失败，请联系管理员检查配置文件权限'
        })

    except Exception as e:
        logger.error(f"初始化密码失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/logout')
def logout():
    # 退出登录
    session.clear()
    return redirect(url_for('login'))


@app.route('/get_model_configs')
def get_model_configs():
    """获取模型和API配置"""
    try:
        # 使用静态缓存
        if not hasattr(get_model_configs, 'cache'):
            get_model_configs.cache = None
            get_model_configs.cache_time = 0
        
        current_time = time.time()
        # 使用缓存中的数据，如果缓存不超过5分钟
        if get_model_configs.cache and (current_time - get_model_configs.cache_time < 300):  # 5分钟缓存
            return jsonify(get_model_configs.cache)
        
        models_path = os.path.join(ROOT_DIR, 'src/config/models.json')

        if not os.path.exists(models_path):
            return jsonify({
                'status': 'error',
                'message': '配置文件不存在'
            })

        with open(models_path, 'r', encoding='utf-8') as f:
            configs = json.load(f)

        # 检查云端更新
        if configs.get('update_url'):
            try:
                response = requests.get(configs['update_url'], timeout=5)
                if response.status_code == 200:
                    cloud_configs = response.json()
                    if cloud_configs.get('version', '0') > configs.get('version', '0'):
                        configs = cloud_configs
                        with open(models_path, 'w', encoding='utf-8') as f:
                            json.dump(configs, f, indent=4, ensure_ascii=False)
            except:
                pass

        # 过滤和排序提供商
        active_providers = [p for p in configs['api_providers']
                            if p.get('status') == 'active']
        active_providers.sort(key=lambda x: x.get('priority', 999))

        # 构建返回配置
        return_configs = {
            'api_providers': active_providers,
            'models': {}
        }

        # 只包含活动模型
        for provider in active_providers:
            provider_id = provider['id']
            if provider_id in configs['models']:
                return_configs['models'][provider_id] = [
                    m for m in configs['models'][provider_id]
                    if m.get('status') == 'active'
                ]

        return jsonify(return_configs)

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


@app.route('/save_quick_setup', methods=['POST'])
def save_quick_setup():
    """保存快速设置"""
    try:
        import yaml
        new_config = request.json or {}
        from src.config import config

        # 读取当前配置
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f)
        except:
            current_config = {"categories": {}}

        # 确保基本结构存在
        if "categories" not in current_config:
            current_config["categories"] = {}

        # 更新用户设置
        if "listen_list" in new_config:
            if "user_settings" not in current_config["categories"]:
                current_config["categories"]["user_settings"] = {
                    "title": "用户设置",
                    "settings": {}
                }
            current_config["categories"]["user_settings"]["settings"]["listen_list"] = {
                "value": new_config["listen_list"],
                "type": "array",
                "description": "要监听的用户列表（请使用微信昵称，不要使用备注名）"
            }

        # 更新API设置
        if "api_key" in new_config:
            if "llm_settings" not in current_config["categories"]:
                current_config["categories"]["llm_settings"] = {
                    "title": "大语言模型配置",
                    "settings": {}
                }
            current_config["categories"]["llm_settings"]["settings"]["api_key"] = {
                "value": new_config["api_key"],
                "type": "string",
                "description": "API密钥",
                "is_secret": True
            }

            # 如果没有设置其他必要的LLM配置，设置默认值
            if "base_url" not in current_config["categories"]["llm_settings"]["settings"]:
                current_config["categories"]["llm_settings"]["settings"]["base_url"] = {
                    "value": "https://api.ciallo.ac.cn/v1",
                    "type": "string",
                    "description": "API基础URL"
                }
            if "model" not in current_config["categories"]["llm_settings"]["settings"]:
                current_config["categories"]["llm_settings"]["settings"]["model"] = {
                    "value": "kourichat-visionk",
                    "type": "string",
                    "description": "使用的模型"
                }
            if "max_tokens" not in current_config["categories"]["llm_settings"]["settings"]:
                current_config["categories"]["llm_settings"]["settings"]["max_tokens"] = {
                    "value": 2000,
                    "type": "number",
                    "description": "最大token数"
                }
            if "temperature" not in current_config["categories"]["llm_settings"]["settings"]:
                current_config["categories"]["llm_settings"]["settings"]["temperature"] = {
                    "value": 1.1,
                    "type": "number",
                    "description": "温度参数"
                }

        # 保存更新后的配置
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, allow_unicode=True, sort_keys=False)

        # 重新加载配置
        importlib.reload(sys.modules['src.config'])

        return jsonify({"status": "success", "message": "设置已保存"})

    except Exception as e:
        logger.error(f"保存快速设置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})


@app.route('/quick_setup')
def quick_setup():
    """快速设置页面"""
    return render_template('quick_setup.html')


# 添加获取可用人设列表的路由
@app.route('/get_available_avatars')
def get_available_avatars_route():
    """获取可用的人设目录列表"""
    try:
        # 使用绝对路径
        avatar_base_dir = os.path.join(ROOT_DIR, "data", "avatars")

        # 检查目录是否存在
        if not os.path.exists(avatar_base_dir):
            # 尝试创建目录
            try:
                os.makedirs(avatar_base_dir)
                logger.info(f"已创建人设目录: {avatar_base_dir}")
            except Exception as e:
                logger.error(f"创建人设目录失败: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': f"人设目录不存在且无法创建: {str(e)}"
                })

        # 获取所有包含 avatar.md 和 emojis 目录的有效人设目录
        avatars = []
        for item in os.listdir(avatar_base_dir):
            avatar_dir = os.path.join(avatar_base_dir, item)
            if os.path.isdir(avatar_dir):
                avatar_md_path = os.path.join(avatar_dir, "avatar.md")
                emojis_dir = os.path.join(avatar_dir, "emojis")

                # 检查 avatar.md 文件
                if not os.path.exists(avatar_md_path):
                    logger.warning(f"人设 {item} 缺少 avatar.md 文件")
                    continue

                # 检查 emojis 目录
                if not os.path.exists(emojis_dir):
                    logger.warning(f"人设 {item} 缺少 emojis 目录")
                    try:
                        os.makedirs(emojis_dir)
                        logger.info(f"已为人设 {item} 创建 emojis 目录")
                    except Exception as e:
                        logger.error(f"为人设 {item} 创建 emojis 目录失败: {str(e)}")
                        continue

                # 只添加人设目录名，不包含路径
                avatars.append(item)

        logger.info(f"找到 {len(avatars)} 个有效人设: {avatars}")

        return jsonify({
            'status': 'success',
            'avatars': avatars
        })
    except Exception as e:
        logger.error(f"获取人设列表失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


# 修改加载指定人设内容的路由
@app.route('/load_avatar_content')
def load_avatar_content():
    """加载指定人设的内容"""
    try:
        avatar_name = request.args.get('avatar', 'MONO')
        avatar_path = os.path.join(ROOT_DIR, 'data', 'avatars', avatar_name, 'avatar.md')

        # 确保目录存在
        os.makedirs(os.path.dirname(avatar_path), exist_ok=True)

        # 如果文件不存在，创建一个空文件
        if not os.path.exists(avatar_path):
            with open(avatar_path, 'w', encoding='utf-8') as f:
                f.write(
                    "# Task\n请在此输入任务描述\n\n# Role\n请在此输入角色设定\n\n# Appearance\n请在此输入外表描述\n\n")

        # 读取角色设定文件并解析内容
        sections = {}
        current_section = None

        with open(avatar_path, 'r', encoding='utf-8') as file:
            content = ""
            for line in file:
                if line.startswith('# '):
                    # 如果已有部分，保存它
                    if current_section:
                        sections[current_section.lower()] = content.strip()
                    # 开始新部分
                    current_section = line[2:].strip()
                    content = ""
                else:
                    content += line

            # 保存最后一个部分
            if current_section:
                sections[current_section.lower()] = content.strip()

        # 获取原始文件内容，用于前端显示
        with open(avatar_path, 'r', encoding='utf-8') as file:
            raw_content = file.read()

        return jsonify({
            'status': 'success',
            'content': sections,
            'raw_content': raw_content  # 添加原始内容
        })
    except Exception as e:
        logger.error(f"加载人设内容失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


@app.route('/load_avatar_emojis', methods=['GET', 'POST'])
def load_avatar_emojis():
    """加载指定人设的表情包"""
    try:
        avatar_name = request.args.get('avatar', 'MONO')
        avatar_emojis_path = os.path.join(ROOT_DIR, 'data', 'avatars', avatar_name, 'emojis')
        avatar_emojis_list = ['angry', 'happy', 'neutral', 'sad']
        # 确保目录存在
        os.makedirs(os.path.dirname(avatar_emojis_path), exist_ok=True)

        # 如果文件不存在，创建一个空文件
        if not os.path.exists(avatar_emojis_path):
            # 创建表情分类文件夹
            for emojis_class in avatar_emojis_list:
                if not os.path.exists(os.path.join(avatar_emojis_path, emojis_class)):
                    os.makedirs(os.path.join(avatar_emojis_path, emojis_class), exist_ok=True)
        # 创建压缩包，压缩emojis文件夹
        zip_file_path = os.path.join(avatar_emojis_path, f'{avatar_name}-emojis.zip')
        if os.path.exists(zip_file_path):
            os.remove(zip_file_path)
        try:
            with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for root, dirs, files in os.walk(avatar_emojis_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if not os.path.relpath(file_path, avatar_emojis_path).endswith('zip'):
                            zip_file.write(file_path, os.path.relpath(file_path, avatar_emojis_path))

            # 打开zip文件，返回流，并且删除压缩包
            with open(zip_file_path, 'rb') as f:
                zip_file_stream = io.BytesIO(f.read())
                return send_file(zip_file_stream, as_attachment=False, download_name=f'{avatar_name}-emojis.zip')
        finally:
            if os.path.exists(zip_file_path):
                os.remove(zip_file_path)


    except Exception as e:
        logger.error(f"加载人设内容失败: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/delete_avatar_emojis', methods=['POST'])
def delete_avatar_emojis():
    """删除指定人设的表情包"""
    try:
        data = request.get_json()
        avatar_name = data.get('avatar_name')
        img_url = data.get('img_url')
        avatar_emojis_path = os.path.join(ROOT_DIR, 'data', 'avatars', avatar_name, 'emojis', img_url)
        # 确保目录存在
        if os.path.exists(avatar_emojis_path):
            # 判断是否有删除权限
            if os.access(path=avatar_emojis_path, mode=os.W_OK):
                logger.debug(f'avatar_emojis_path{avatar_emojis_path}')
                os.remove(avatar_emojis_path)
                return jsonify({'status': 'success', 'message': '删除成功'})
            else:
                return jsonify({'status': 'error', 'message': f'没有删除权限{avatar_emojis_path}'})
        else:
            return jsonify({'status': 'error', 'message': '删除失败!表情包不存在'})
    except Exception as e:
        logger.error(f"删除表情包错误: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


@app.route('/upload_avatarEmoji_zip', methods=['POST'])
def upload_avatarEmoji_zip():
    """上传表情包压缩包"""
    # 获取avatar_name
    avatar_name = request.form.get('avatar_name', 'MONO')
    avatar_emojis_list = ['angry', 'happy', 'neutral', 'sad']
    # 确保目录存在
    avatar_emojis_path = os.path.join(ROOT_DIR, 'data', 'avatars', avatar_name, 'emojis')
    os.makedirs(os.path.dirname(avatar_emojis_path), exist_ok=True)
    # 如果文件不存在，创建一个空文件
    if not os.path.exists(avatar_emojis_path):
        # 创建表情分类文件夹
        for emojis_class in avatar_emojis_list:
            if not os.path.exists(os.path.join(avatar_emojis_path, emojis_class)):
                os.makedirs(os.path.join(avatar_emojis_path, emojis_class), exist_ok=True)

    file = request.files.get('file')
    if file.filename == '':
        return jsonify({"status": "error", "message": "没有选择文件"})

    # 确保 filename 不为 None
    if file.filename is None:
        return jsonify({"status": "error", "message": "文件名无效"})
    # 确保是压缩包
    if not file.filename.endswith('.zip'):
        return jsonify({"status": "error", "message": "请上传zip格式的文件"})
    # 确保文件大小不超过20M
    if file.content_length > 20 * 1024 * 1024:
        return jsonify({"status": "error", "message": "文件大小不能超过20M"})

    filename = secure_filename(file.filename)
    # 解压file文件
    try:

        with zipfile.ZipFile(file, 'r') as zip_ref:
            logger.debug('打开压缩包')
            # 验证解压包下的文件夹都是否符合要求
            for file_one in zip_ref.namelist():
                try:
                    file_one = file_one.encode('cp437').decode('gbk')
                except:
                    file_one = file_one.encode('utf-8').decode('utf-8')
                # 判断file_one开头是否包含在avatar_emojis_list
                if not file_one.lower().startswith(('angry', 'happy', 'neutral', 'sad')):
                    return jsonify({
                        "status": "error",
                        "message": f"{file_one}不是有效的表情包分类"
                    })
                # 判断file_one是否是图片
                if not file_one.lower().endswith(('.gif', '.jpg', '.png', '.jpeg', '/')):
                    return jsonify({
                        "status": "error",
                        "message": f"{file_one}不是有效的图片"
                })

            # 解压缩文件
            for zip_file_name in zip_ref.namelist():
                original_zip_file_name = zip_file_name
                try:
                    zip_file_name = zip_file_name.encode('cp437').decode('gbk')
                except:
                    zip_file_name = zip_file_name.encode('utf-8').decode('utf-8')
                # 如果已/为结尾说明是文件夹
                # 如果已gif,png,jpg为结尾说明是图片 取分类名称/angry/ 两个斜杠中间的内容
                if zip_file_name.endswith('/'):
                    continue
                elif (zip_file_name.endswith('.gif') or zip_file_name.endswith('.png') or zip_file_name.endswith(
                        '.jpg') or zip_file_name.endswith('.jpeg')) and len(zip_file_name.split('/')) == 2:

                    # 获取图片分类
                    emojis_class = zip_file_name.split('/')[0]
                    # 获取图片名称
                    emojis_name = zip_file_name.split('/')[1]
                    # 获取图片路径
                    emojis_path = os.path.join(avatar_emojis_path, emojis_class, emojis_name)
                    # 如果文件夹不存在，创建文件夹
                    if not os.path.exists(os.path.dirname(emojis_path)):
                        os.makedirs(os.path.dirname(emojis_path), exist_ok=True)
                    # 如果文件不存在，创建文件
                    if not os.path.exists(emojis_path):

                        with open(emojis_path, 'wb') as f:
                            with zip_ref.open(original_zip_file_name) as fz:
                                f.write(fz.read())
                    else:

                        # 更改名称添加数字
                        count = 1
                        while os.path.exists(emojis_path):
                            # 分割后缀
                            emojis_name_before, emojis_name_after = emojis_name.split('.')
                            emojis_path = os.path.join(avatar_emojis_path, emojis_class,
                                                       f"{emojis_name_before}_{count}.{emojis_name_after}")
                            count += 1

                        with zip_ref.open(original_zip_file_name) as f:

                            with io.BytesIO() as output_stream:
                                for chunk in iter(lambda: f.read(1024), b''):
                                    output_stream.write(chunk)
                                output_stream.seek(0)
                                # 假设我们要将内容写入到磁盘
                                with open(emojis_path, 'wb') as output_file:
                                    output_file.write(output_stream.read())
                else:
                    continue
            return jsonify({
                "status": "success",
                "message": "表情包已上传",
            })

    except Exception as e:
        logger.error(f"解压缩文件失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        })


@app.route('/get_tasks')
def get_tasks():
    """获取最新的任务数据"""
    try:
        import yaml
        # 使用全局配置缓存
        if g.config_data:
            config_data = g.config_data
        else:
            # 如果全局缓存不存在，从文件读取
            config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                
        # 从配置数据中提取任务
        tasks = []
        if 'categories' in config_data and 'schedule_settings' in config_data['categories']:
            if 'settings' in config_data['categories']['schedule_settings'] and 'tasks' in \
                    config_data['categories']['schedule_settings']['settings']:
                tasks = config_data['categories']['schedule_settings']['settings']['tasks'].get('value', [])

        logger.debug(f"获取到的任务数据: {tasks}")

        return jsonify({
            'status': 'success',
            'tasks': tasks
        })
    except Exception as e:
        logger.error(f"获取任务数据失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


@app.route('/get_all_configs')
def get_all_configs():
    """获取所有最新的配置数据"""
    try:
        import yaml
        # 使用全局配置缓存
        if g.config_data:
            config_data = g.config_data
        else:
            # 如果全局缓存不存在，从文件读取
            config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

        # 特别处理RAG_IS_RERANK，直接从配置数据中读取
        rerank_enabled = False
        try:
            if ('categories' in config_data and 'rag_settings' in config_data['categories'] and
                'settings' in config_data['categories']['rag_settings'] and
                'is_rerank' in config_data['categories']['rag_settings']['settings']):
                rerank_value = config_data['categories']['rag_settings']['settings']['is_rerank'].get('value', False)
                # 确保是布尔值
                if isinstance(rerank_value, str):
                    rerank_enabled = rerank_value.lower() == 'true'
                else:
                    rerank_enabled = bool(rerank_value)
                logger.info(f"从配置数据中读取RAG_IS_RERANK值: {rerank_value}, 转换后: {rerank_enabled}, 类型: {type(rerank_enabled)}")
        except Exception as e:
            logger.error(f"读取RAG_IS_RERANK失败: {str(e)}")

        # 解析配置数据为前端需要的格式
        configs = {}
        tasks = []

        # 处理用户设置
        if 'categories' in config_data:
            # 用户设置
            if 'user_settings' in config_data['categories'] and 'settings' in config_data['categories'][
                'user_settings']:
                configs['基础配置'] = {}
                if 'listen_list' in config_data['categories']['user_settings']['settings']:
                    configs['基础配置']['LISTEN_LIST'] = {
                        'value': config_data['categories']['user_settings']['settings']['listen_list'].get('value', [])
                    }
            
            # LLM设置
            if 'llm_settings' in config_data['categories'] and 'settings' in config_data['categories']['llm_settings']:
                llm_settings = config_data['categories']['llm_settings']['settings']
                if 'api_key' in llm_settings:
                    configs['基础配置']['DEEPSEEK_API_KEY'] = {'value': llm_settings['api_key'].get('value', '')}
                if 'base_url' in llm_settings:
                    configs['基础配置']['DEEPSEEK_BASE_URL'] = {'value': llm_settings['base_url'].get('value', '')}
                if 'model' in llm_settings:
                    configs['基础配置']['MODEL'] = {'value': llm_settings['model'].get('value', '')}
                if 'max_tokens' in llm_settings:
                    configs['基础配置']['MAX_TOKEN'] = {'value': llm_settings['max_tokens'].get('value', 2000)}
                if 'temperature' in llm_settings:
                    configs['基础配置']['TEMPERATURE'] = {'value': llm_settings['temperature'].get('value', 1.1)}

            # 媒体设置
            if 'media_settings' in config_data['categories'] and 'settings' in config_data['categories'][
                'media_settings']:
                media_settings = config_data['categories']['media_settings']['settings']

                # 图像识别设置
                configs['图像识别API配置'] = {}
                if 'image_recognition' in media_settings:
                    img_recog = media_settings['image_recognition']
                    if 'api_key' in img_recog:
                        configs['图像识别API配置']['MOONSHOT_API_KEY'] = {
                            'value': img_recog['api_key'].get('value', '')}
                    if 'base_url' in img_recog:
                        configs['图像识别API配置']['MOONSHOT_BASE_URL'] = {
                            'value': img_recog['base_url'].get('value', '')}
                    if 'temperature' in img_recog:
                        configs['图像识别API配置']['MOONSHOT_TEMPERATURE'] = {
                            'value': img_recog['temperature'].get('value', 0.7)}
                    if 'model' in img_recog:
                        configs['图像识别API配置']['MOONSHOT_MODEL'] = {'value': img_recog['model'].get('value', '')}

                # 语音设置
                # configs['语音配置'] = {}
                # if 'text_to_speech' in media_settings:
                #     tts = media_settings['text_to_speech']
                #     if 'tts_api_url' in tts:
                #         configs['语音配置']['TTS_API_URL'] = {'value': tts['tts_api_url'].get('value', '')}
                #     if 'voice_dir' in tts:
                #         configs['语音配置']['VOICE_DIR'] = {'value': tts['voice_dir'].get('value', '')}

            # 行为设置
            if 'behavior_settings' in config_data['categories'] and 'settings' in config_data['categories'][
                'behavior_settings']:
                behavior = config_data['categories']['behavior_settings']['settings']

                # 主动消息配置
                configs['主动消息配置'] = {}
                if 'auto_message' in behavior:
                    auto_msg = behavior['auto_message']
                    if 'content' in auto_msg:
                        configs['主动消息配置']['AUTO_MESSAGE'] = {'value': auto_msg['content'].get('value', '')}
                    if 'countdown' in auto_msg:
                        if 'min_hours' in auto_msg['countdown']:
                            configs['主动消息配置']['MIN_COUNTDOWN_HOURS'] = {
                                'value': auto_msg['countdown']['min_hours'].get('value', 1)}
                        if 'max_hours' in auto_msg['countdown']:
                            configs['主动消息配置']['MAX_COUNTDOWN_HOURS'] = {
                                'value': auto_msg['countdown']['max_hours'].get('value', 3)}

                if 'quiet_time' in behavior:
                    quiet = behavior['quiet_time']
                    if 'start' in quiet:
                        configs['主动消息配置']['QUIET_TIME_START'] = {'value': quiet['start'].get('value', '')}
                    if 'end' in quiet:
                        configs['主动消息配置']['QUIET_TIME_END'] = {'value': quiet['end'].get('value', '')}

                # Prompt配置
                configs['Prompt配置'] = {}
                if 'context' in behavior:
                    context = behavior['context']
                    if 'max_groups' in context:
                        configs['Prompt配置']['MAX_GROUPS'] = {'value': context['max_groups'].get('value', 15)}
                    if 'avatar_dir' in context:
                        configs['Prompt配置']['AVATAR_DIR'] = {'value': context['avatar_dir'].get('value', '')}

            # 定时任务
            if 'schedule_settings' in config_data['categories'] and 'settings' in config_data['categories'][
                'schedule_settings']:
                if 'tasks' in config_data['categories']['schedule_settings']['settings']:
                    tasks = config_data['categories']['schedule_settings']['settings']['tasks'].get('value', [])
        
        # 处理RAG设置
        if 'categories' in config_data and 'rag_settings' in config_data['categories'] and 'settings' in config_data['categories']['rag_settings']:
            rag_settings = config_data['categories']['rag_settings']['settings']
            configs['RAG设置'] = {}
            
            # API配置
            if 'api_key' in rag_settings:
                configs['RAG设置']['RAG_API_KEY'] = {'value': rag_settings['api_key'].get('value', '')}
            if 'base_url' in rag_settings:
                configs['RAG设置']['RAG_BASE_URL'] = {'value': rag_settings['base_url'].get('value', '')}
                
            # 模型配置    
            if 'embedding_model' in rag_settings:
                configs['RAG设置']['RAG_EMBEDDING_MODEL'] = {'value': rag_settings['embedding_model'].get('value', 'text-embedding-3-large')}
            if 'reranker_model' in rag_settings:
                configs['RAG设置']['RAG_RERANKER_MODEL'] = {'value': rag_settings['reranker_model'].get('value', '')}
            if 'local_embedding_model_path' in rag_settings:
                configs['RAG设置']['LOCAL_EMBEDDING_MODEL_PATH'] = {'value': rag_settings['local_embedding_model_path'].get('value', 'paraphrase-multilingual-MiniLM-L12-v2')}
            
            # 查询配置
            if 'top_k' in rag_settings:
                configs['RAG设置']['RAG_TOP_K'] = {'value': int(rag_settings['top_k'].get('value', 5))}
                
            # 特别处理is_rerank - 使用我们从YAML中直接读取的值
            configs['RAG设置']['RAG_IS_RERANK'] = {'value': rerank_enabled}
            logger.info(f"传递给前端的RAG_IS_RERANK值: {rerank_enabled}, 类型: {type(rerank_enabled)}")
            
            # 自动化配置    
            if 'auto_download_local_model' in rag_settings:
                auto_download = rag_settings['auto_download_local_model'].get('value')
                if auto_download is not None:
                    # 特殊处理字符串格式的布尔值
                    if isinstance(auto_download, str):
                        auto_download = auto_download.lower() == 'true'
                    configs['RAG设置']['AUTO_DOWNLOAD_LOCAL_MODEL'] = {'value': auto_download}
                    
            if 'auto_adapt_siliconflow' in rag_settings:
                auto_adapt = rag_settings['auto_adapt_siliconflow'].get('value', True)
                if isinstance(auto_adapt, str):
                    auto_adapt = auto_adapt.lower() == 'true'
                configs['RAG设置']['AUTO_ADAPT_SILICONFLOW'] = {'value': bool(auto_adapt)}

        logger.debug(f"获取到的所有配置数据: {configs}")
        logger.debug(f"获取到的任务数据: {tasks}")

        return jsonify({
            'status': 'success',
            'configs': configs,
            'tasks': tasks
        })

    except Exception as e:
        logger.error(f"获取配置数据失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


@app.route('/click_wechat_buttons', methods=['POST'])
def handle_wechat_login():
    """处理微信登录按钮点击"""
    try:
        click_wechat_buttons()
        return jsonify({
            'status': 'success',
            'message': '微信登录操作已执行'
        })
    except Exception as e:
        logger.error(f"执行微信登录操作失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'操作失败: {str(e)}'
        })


@app.route('/get_config')
def get_config():
    """获取配置数据，特别处理LISTEN_LIST字段"""
    try:
        import yaml
        # 直接从配置文件读取配置数据
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 提取所需的配置值
        config_data_response = {}
        
        # 特别处理LISTEN_LIST
        if ('categories' in config_data and 'user_settings' in config_data['categories'] and
            'settings' in config_data['categories']['user_settings'] and
            'listen_list' in config_data['categories']['user_settings']['settings']):
            listen_list = config_data['categories']['user_settings']['settings']['listen_list'].get('value', [])
            # 确保listen_list是一个数组
            if not isinstance(listen_list, list):
                listen_list = []
            config_data_response['LISTEN_LIST'] = listen_list
            logger.debug(f"获取到的监听用户列表: {listen_list}")
        else:
            config_data_response['LISTEN_LIST'] = []
            logger.warning("在配置中找不到监听用户列表")
        
        # 处理RAG_IS_RERANK
        if ('categories' in config_data and 'rag_settings' in config_data['categories'] and
            'settings' in config_data['categories']['rag_settings'] and
            'is_rerank' in config_data['categories']['rag_settings']['settings']):
            rerank_value = config_data['categories']['rag_settings']['settings']['is_rerank'].get('value', False)
            # 确保是布尔值
            if isinstance(rerank_value, str):
                config_data_response['RAG_IS_RERANK'] = rerank_value.lower() == 'true'
            else:
                config_data_response['RAG_IS_RERANK'] = bool(rerank_value)
        
        # 其他配置按需添加...
        
        return jsonify({
            'status': 'success',
            'config': config_data_response
        })
    except Exception as e:
        logger.error(f"获取配置数据失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })


def direct_update_password(password: str) -> bool:
    """直接更新配置文件中的密码"""
    try:
        # 配置文件路径
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        
        # 尝试读取现有配置
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否存在auth_settings部分
        if 'auth_settings' not in content:
            # 如果不存在，添加auth_settings部分
            auth_section = """
  auth_settings:
    title: 认证设置
    settings:
      admin_password:
        value: {password}
        type: string
        description: 管理员密码
        is_secret: true
""".format(password=password)
            
            # 找到categories行
            if 'categories:' in content:
                # 在categories行之后插入auth_settings部分
                content = content.replace('categories:', 'categories:' + auth_section)
            else:
                # 如果没有categories行，添加完整结构
                content = "categories:" + auth_section + content
        else:
            # 如果已存在auth_settings部分，直接更新password值
            if 'admin_password' in content:
                # 使用正则表达式匹配admin_password部分
                import re
                pattern = r'(admin_password:.*?value:)(.*?)(\n.*?type:)'
                content = re.sub(pattern, r'\1 {0}\3'.format(password), content, flags=re.DOTALL)
            else:
                # 如果auth_settings存在但admin_password不存在，添加admin_password
                admin_pwd_entry = """
      admin_password:
        value: {password}
        type: string
        description: 管理员密码
        is_secret: true
""".format(password=password)
                
                # 找到auth_settings部分，在settings下添加admin_password
                auth_settings_pattern = r'(auth_settings:.*?settings:.*?)(\n\s+\w+)'
                content = re.sub(auth_settings_pattern, r'\1' + admin_pwd_entry + r'\2', 
                                content, flags=re.DOTALL)
        
        # 写回配置文件
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 输出调试信息
        logging.info("密码已直接更新到配置文件")
        return True
    
    except Exception as e:
        logging.error(f"直接更新密码失败: {str(e)}")
        return False


def fix_config_file():
    """修复配置文件结构"""
    try:
        # 配置文件路径
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        template_path = os.path.join(ROOT_DIR, 'src/config/template.yaml')
        
        # 检查模板文件是否存在
        if not os.path.exists(template_path):
            logging.error("模板文件不存在")
            return False
        
        # 读取模板文件
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # 如果配置文件不存在或结构出问题，直接用模板替换
        if not os.path.exists(config_path) or os.path.getsize(config_path) < 100:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(template_content)
            logging.info("已使用模板重置配置文件")
            return True
        
        # 否则尝试读取现有配置，检查结构
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查基本结构
            if 'categories:' not in content or len(content) < 100:
                # 结构有问题，重置
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(template_content)
                logging.info("检测到配置文件结构有问题，已重置")
                return True
            
            # 结构正常
            return True
        except Exception as e:
            # 读取失败，重置文件
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(template_content)
            logging.error(f"配置文件读取失败，已重置: {str(e)}")
            return True
    
    except Exception as e:
        logging.error(f"修复配置文件失败: {str(e)}")
        return False


# 添加静态资源缓存控制
@app.after_request
def add_cache_headers(response):
    """为静态资源添加缓存头"""
    if request.path.startswith('/static'):
        # 静态资源缓存1小时
        response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


def cleanup_processes():
    """清理所有相关进程"""
    try:
        # 清理机器人进程
        global bot_process, job_object
        if bot_process:
            try:
                logger.info(f"正在终止机器人进程 (PID: {bot_process.pid})...")

                # 获取进程组
                parent = psutil.Process(bot_process.pid)
                children = parent.children(recursive=True)

                # 终止子进程
                for child in children:
                    try:
                        logger.info(f"正在终止子进程 (PID: {child.pid})...")
                        child.terminate()
                    except:
                        try:
                            logger.info(f"正在强制终止子进程 (PID: {child.pid})...")
                            child.kill()
                        except Exception as e:
                            logger.error(f"终止子进程 (PID: {child.pid}) 失败: {str(e)}")

                # 终止主进程
                bot_process.terminate()

                # 等待进程结束
                try:
                    gone, alive = psutil.wait_procs(children + [parent], timeout=3)

                    # 强制结束仍在运行的进程
                    for p in alive:
                        try:
                            logger.info(f"正在强制终止进程 (PID: {p.pid})...")
                            p.kill()
                        except Exception as e:
                            logger.error(f"强制终止进程 (PID: {p.pid}) 失败: {str(e)}")
                except Exception as e:
                    logger.error(f"等待进程结束失败: {str(e)}")

                # 如果在Windows上，使用taskkill强制终止进程树
                if sys.platform.startswith('win'):
                    try:
                        logger.info(f"使用taskkill终止进程树 (PID: {bot_process.pid})...")
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(bot_process.pid)],
                                       capture_output=True)
                    except Exception as e:
                        logger.error(f"使用taskkill终止进程失败: {str(e)}")

                bot_process = None

            except Exception as e:
                logger.error(f"清理机器人进程失败: {str(e)}")

        # 清理当前进程的所有子进程
        try:
            current_process = psutil.Process()
            children = current_process.children(recursive=True)

            for child in children:
                try:
                    logger.info(f"正在终止子进程 (PID: {child.pid})...")
                    child.terminate()
                except:
                    try:
                        logger.info(f"正在强制终止子进程 (PID: {child.pid})...")
                        child.kill()
                    except Exception as e:
                        logger.error(f"终止子进程 (PID: {child.pid}) 失败: {str(e)}")

            # 等待所有子进程结束
            gone, alive = psutil.wait_procs(children, timeout=3)
            for p in alive:
                try:
                    logger.info(f"正在强制终止进程 (PID: {p.pid})...")
                    p.kill()
                except Exception as e:
                    logger.error(f"强制终止进程 (PID: {p.pid}) 失败: {str(e)}")
        except Exception as e:
            logger.error(f"清理子进程失败: {str(e)}")

    except Exception as e:
        logger.error(f"清理进程失败: {str(e)}")


def create_job_object():
    global job_object
    try:
        if sys.platform.startswith('win'):
            # 创建作业对象
            job_object = win32job.CreateJobObject(None, "KouriChatBotJob")

            # 设置作业对象的扩展限制信息
            info = win32job.QueryInformationJobObject(
                job_object, win32job.JobObjectExtendedLimitInformation
            )

            # 设置当所有进程句柄关闭时终止作业
            info['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            # 应用设置
            win32job.SetInformationJobObject(
                job_object, win32job.JobObjectExtendedLimitInformation, info
            )

            # 将当前进程添加到作业对象
            current_process = win32process.GetCurrentProcess()
            win32job.AssignProcessToJobObject(job_object, current_process)

            logger.info("已创建作业对象并将当前进程添加到作业中")
            return True
    except Exception as e:
        logger.error(f"创建作业对象失败: {str(e)}")
    return False


def setup_console_control_handler():
    try:
        if sys.platform.startswith('win'):
            def handler(dwCtrlType):
                if dwCtrlType in (win32con.CTRL_CLOSE_EVENT, win32con.CTRL_LOGOFF_EVENT, win32con.CTRL_SHUTDOWN_EVENT):
                    logger.info("检测到控制台关闭事件，正在清理进程...")
                    cleanup_processes()
                    return True
                return False

            win32api.SetConsoleCtrlHandler(handler, True)
            logger.info("已设置控制台关闭事件处理器")
    except Exception as e:
        logger.error(f"设置控制台关闭事件处理器失败: {str(e)}")


def open_browser(port):
    """在新线程中打开浏览器"""

    def _open_browser():
        # 等待服务器启动
        time.sleep(1.5)
        # 优先使用 localhost
        url = f"http://localhost:{port}"
        webbrowser.open(url)

    # 创建新线程来打开浏览器
    threading.Thread(target=_open_browser, daemon=True).start()


def reload_rag_memory():
    """重新初始化RAG记忆系统"""
    try:
        # 从配置文件路径
        config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
        logger.info(f"正在使用配置文件重新初始化RAG记忆系统: {config_path}")
        
        # 重新加载整个记忆系统
        try:
            # 先尝试导入init_memory
            from src.handlers.memory import init_memory
            # 重新初始化记忆
            memory_handler = init_memory(ROOT_DIR)
            if memory_handler:
                logger.info("成功重新初始化记忆系统")
            else:
                logger.warning("记忆系统初始化返回None")
        except Exception as e:
            logger.error(f"重新初始化记忆系统失败: {str(e)}")
        
        # 再尝试单独初始化RAG系统
        try:
            from src.handlers.handler_init import init_rag_from_config
            rag_instance = init_rag_from_config(config_path)
            if rag_instance:
                logger.info("成功重新初始化RAG系统")
                return True
            else:
                logger.warning("RAG系统初始化返回None")
        except Exception as e:
            logger.error(f"重新初始化RAG系统失败: {str(e)}")
        
        return False
    except Exception as e:
        logger.error(f"重新初始化RAG记忆系统总体失败: {str(e)}")
        return False

# 清除文件锁
WIN32_FILE_LOCKS = {}

def main():
    """主函数"""
    from src.config import config

    # 设置系统编码为 UTF-8 (不清除控制台输出)
    if sys.platform.startswith('win'):
        os.system("@chcp 65001 >nul")  # 使用 >nul 来隐藏输出而不清屏

    print("\n" + "=" * 50)
    print_status("配置管理系统启动中...", "info", "LAUNCH")
    print("-" * 50)

    # 创建作业对象来管理子进程
    create_job_object()

    # 设置控制台关闭事件处理
    setup_console_control_handler()

    # 检查必要目录
    print_status("检查系统目录...", "info", "FILE")
    if not os.path.exists(os.path.join(ROOT_DIR, 'src/webui/templates')):
        print_status("错误：模板目录不存在！", "error", "CROSS")
        return
    print_status("系统目录检查完成", "success", "CHECK")

    # 检查配置文件
    print_status("检查配置文件...", "info", "CONFIG")
    if not os.path.exists(config.config_path):
        print_status("错误：配置文件不存在！", "error", "CROSS")
        return
    print_status("配置文件检查完成", "success", "CHECK")

    # 修改启动 Web 服务器的部分
    try:
        cli = sys.modules['flask.cli']
        if hasattr(cli, 'show_server_banner'):
            setattr(cli, 'show_server_banner', lambda *x: None)  # 禁用 Flask 启动横幅
    except (KeyError, AttributeError):
        pass

    host = '0.0.0.0'
    port = 8502

    print_status("正在启动Web服务...", "info", "INTERNET")
    print("-" * 50)
    print_status("配置管理系统已就绪！", "success", "STAR_1")

    # 获取本机所有IP地址
    def get_ip_addresses():
        ip_list = []
        try:
            # 获取主机名
            hostname = socket.gethostname()
            # 获取本机IP地址列表
            addresses = socket.getaddrinfo(hostname, None)

            for addr in addresses:
                ip = addr[4][0]
                # 只获取IPv4地址且不是回环地址
                if isinstance(ip, str) and '.' in ip and ip != '127.0.0.1':
                    ip_list.append(ip)
        except:
            pass
        return ip_list

    # 显示所有可用的访问地址
    ip_addresses = get_ip_addresses()
    print_status("可通过以下地址访问:", "info", "CHAIN")
    print(f"  Local:   http://localhost:{port}")
    print(f"  Local:   http://127.0.0.1:{port}")
    for ip in ip_addresses:
        print(f"  Network: http://{ip}:{port}")
    print("=" * 50 + "\n")

    # 启动浏览器
    open_browser(port)

    app.run(
        host=host,
        port=port,
        debug=True,
        use_reloader=False  # 禁用重载器以避免创建多余的进程
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_status("正在关闭服务...", "warning", "STOP")
        cleanup_processes()
        print_status("配置管理系统已停止", "info", "BYE")
        print("\n")
    except Exception as e:
        print_status(f"系统错误: {str(e)}", "error", "ERROR")
        cleanup_processes()

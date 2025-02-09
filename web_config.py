from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
import json
import os
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # 用于flash消息

CONFIG_FILE = 'config.py'

def load_config():
    """从config.py加载配置"""
    config = {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        exec(f.read(), {}, config)
    return {k: v for k, v in config.items() if not k.startswith('__')}

def save_config(config_data):
    """保存配置到config.py"""
    backup_file = CONFIG_FILE + '.backup'
    # 先备份当前配置
    if os.path.exists(CONFIG_FILE):
        os.rename(CONFIG_FILE, backup_file)

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            for key, value in config_data.items():
                if isinstance(value, str):
                    f.write(f"{key} = '{value}'\n")
                elif isinstance(value, list):
                    f.write(f"{key} = {value}\n")
                else:
                    f.write(f"{key} = {value}\n")
        if os.path.exists(backup_file):
            os.remove(backup_file)
        return True
    except Exception as e:
        # 如果保存失败，恢复备份
        if os.path.exists(backup_file):
            os.rename(backup_file, CONFIG_FILE)
        return False

@app.route('/')
def index():
    config = load_config()
    # 对配置进行分类，并添加说明文字
    config_descriptions = {
        'LISTEN_LIST': '需要监听的微信用户昵称（不是备注名）或群聊名称，可以是多个，用英文逗号分割,',
        'DEEPSEEK_API_KEY': 'DeepSeek API密钥',
        'DEEPSEEK_BASE_URL': 'API基础URL地址',
        'MODEL': '使用的AI模型名称',
        'PROMPT_NAME': '使用的PROMPT',
        'ROBOT_WX_NAME': '机器人账号的微信名字',
        'MAX_TOKEN': '单次回复最大字数限制',
        'TEMPERATURE': '回复随机性程度（0-2之间，越大越随机）',
        'MAX_GROUPS': '上下文对话最大轮数',
        'IMAGE_MODEL': '图像生成使用的模型',
        'IMAGE_SIZE': '生成图片的尺寸（宽x高）',
        'BATCH_SIZE': '单次生成图片数量',
        'GUIDANCE_SCALE': '图像生成引导程度（越大越接近提示词）',
        'NUM_INFERENCE_STEPS': '图像生成推理步数（越大越精细但更慢）',
        'PROMPT_ENHANCEMENT': '是否启用提示词增强',
        'TEMP_IMAGE_DIR': '临时图片存储目录'
    }

    config_groups = {
        '基础配置': {
            'LISTEN_LIST': {
                'value': config.get('LISTEN_LIST', []),
                'description': config_descriptions['LISTEN_LIST']
            },
            'DEEPSEEK_API_KEY': {
                'value': config.get('DEEPSEEK_API_KEY', ''),
                'description': config_descriptions['DEEPSEEK_API_KEY']
            },
            'DEEPSEEK_BASE_URL': {
                'value': config.get('DEEPSEEK_BASE_URL', ''),
                'description': config_descriptions['DEEPSEEK_BASE_URL']
            },
            'MODEL': {
                'value': config.get('MODEL', ''),
                'description': config_descriptions['MODEL']
            },
            'PROMPT_NAME': {
                'value': config.get('PROMPT_NAME', 'ATRI.md'),
                'description': config_descriptions['PROMPT_NAME']
            },
            'ROBOT_WX_NAME':{
                'value': config.get('ROBOT_WX_NAME', ''),
                'description': config_descriptions['ROBOT_WX_NAME']
            },
        },
        '对话配置': {
            'MAX_TOKEN': {
                'value': config.get('MAX_TOKEN', 2000),
                'description': config_descriptions['MAX_TOKEN']
            },
            'TEMPERATURE': {
                'value': config.get('TEMPERATURE', 1.3),
                'description': config_descriptions['TEMPERATURE']
            },
            'MAX_GROUPS': {
                'value': config.get('MAX_GROUPS', 15),
                'description': config_descriptions['MAX_GROUPS']
            }
        },
        '图像生成配置': {
            'IMAGE_MODEL': {
                'value': config.get('IMAGE_MODEL', ''),
                'description': config_descriptions['IMAGE_MODEL']
            },
            'IMAGE_SIZE': {
                'value': config.get('IMAGE_SIZE', ''),
                'description': config_descriptions['IMAGE_SIZE']
            },
            'BATCH_SIZE': {
                'value': config.get('BATCH_SIZE', 1),
                'description': config_descriptions['BATCH_SIZE']
            },
            'GUIDANCE_SCALE': {
                'value': config.get('GUIDANCE_SCALE', 3),
                'description': config_descriptions['GUIDANCE_SCALE']
            },
            'NUM_INFERENCE_STEPS': {
                'value': config.get('NUM_INFERENCE_STEPS', 4),
                'description': config_descriptions['NUM_INFERENCE_STEPS']
            },
            'PROMPT_ENHANCEMENT': {
                'value': config.get('PROMPT_ENHANCEMENT', True),
                'description': config_descriptions['PROMPT_ENHANCEMENT']
            }
        },
        '系统配置': {
            'TEMP_IMAGE_DIR': {
                'value': config.get('TEMP_IMAGE_DIR', 'temp_images'),
                'description': config_descriptions['TEMP_IMAGE_DIR']
            }
        },# 在config_groups字典中添加自动通过好友配置项

    # ...原有配置组...
    '好友设置': {
        'AUTO_ACCEPT_FRIEND': {
            'value': config.get('AUTO_ACCEPT_FRIEND', True),
            'description': '是否自动通过好友请求'
        }
    }
}
    return render_template('config.html', config_groups=config_groups)

@app.route('/save', methods=['POST'])
def save():
    try:
        config_data = request.get_json()

        # 处理特殊类型的配置项
        if 'LISTEN_LIST' in config_data:
            config_data['LISTEN_LIST'] = config_data['LISTEN_LIST'].split(',')

        if 'TEMPERATURE' in config_data:
            config_data['TEMPERATURE'] = float(config_data['TEMPERATURE'])

        if 'MAX_TOKEN' in config_data:
            config_data['MAX_TOKEN'] = int(config_data['MAX_TOKEN'])

        if 'MAX_GROUPS' in config_data:
            config_data['MAX_GROUPS'] = int(config_data['MAX_GROUPS'])

        if save_config(config_data):
            return jsonify({'status': 'success', 'message': '配置已保存'})
        else:
            return jsonify({'status': 'error', 'message': '保存失败'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)

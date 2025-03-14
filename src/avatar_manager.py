import os
import json
from flask import Blueprint, request, jsonify, render_template
from src.config import config

avatar_manager = Blueprint('avatar_manager', __name__)

@avatar_manager.route('/load_avatar', methods=['GET'])
def load_avatar():
    """加载 avatar.md 内容"""
    avatar_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), config.behavior.context.avatar_dir, 'avatar.md')
    if not os.path.exists(avatar_path):
        return jsonify({'status': 'error', 'message': '文件不存在'})

    try:
        with open(avatar_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 将内容分割成不同区域，使用英文键名以匹配前端
        sections = {}
        section_mapping = {
            '任务': 'task',
            '角色': 'role',
            '外表': 'appearance',
            '经历': 'experience',
            '性格': 'personality',
            '经典台词': 'classic_lines',
            '喜好': 'preferences',
            '备注': 'notes'
        }

        current_section = None
        current_content = []

        # 按行读取并处理内容
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('# '):
                # 如果找到新的部分，保存之前的内容
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                    current_content = []
                
                # 获取新部分的标题
                section_title = line[2:].strip()
                current_section = section_mapping.get(section_title)
            elif current_section and line:
                current_content.append(line)

        # 保存最后一个部分的内容
        if current_section and current_content:
            sections[current_section] = '\n'.join(current_content).strip()

        print("读取到的内容:", sections)  # 调试信息
        return jsonify({'status': 'success', 'content': sections})

    except Exception as e:
        print(f"读取文件错误: {e}")  # 调试信息
        return jsonify({'status': 'error', 'message': str(e)})

@avatar_manager.route('/save_avatar', methods=['POST'])
def save_avatar():
    """保存 avatar.md 内容"""
    data = request.json
    print('接收到的数据:', data)  # 调试信息

    defalut_avatar_name = config.behavior.context.avatar_dir.split('/')[-1]  # 默认人设名称
    avatar_name = data.get('avatar', defalut_avatar_name)  # 获取人设名称
    avatar_path = os.path.join(
        os.path.dirname(config.behavior.context.avatar_dir),
        avatar_name, 
        'avatar.md'
    )

    if not os.path.exists(avatar_path):
        return jsonify({'status': 'error', 'message': '文件不存在'})

    # 使用中文标题保存内容
    section_mapping = {
        'task': '任务',
        'role': '角色',
        'appearance': '外表',
        'experience': '经历',
        'personality': '性格',
        'classic_lines': '经典台词',
        'preferences': '喜好',
        'notes': '备注'
    }

    # 重新构建内容
    content = ""
    for en_section, cn_section in section_mapping.items():
        section_content = data.get(en_section, '') if data is not None else ''
        if section_content:  # 只写入非空内容
            content += f"# {cn_section}\n{section_content}\n\n"

    with open(avatar_path, 'w', encoding='utf-8') as f:
        f.write(content.strip())

    return jsonify({'status': 'success', 'message': '保存成功'})

@avatar_manager.route('/edit_avatar', methods=['GET'])
def edit_avatar():
    """角色设定页面"""
    return render_template('edit_avatar.html')
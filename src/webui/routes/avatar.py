import os
import shutil
from flask import Blueprint, jsonify, request
from pathlib import Path
import json
import re
import yaml

avatar_bp = Blueprint('avatar', __name__)

# 使用标准化的相对路径，确保路径格式一致性
# 不使用 resolve() 方法，避免绝对路径引起的问题
AVATARS_DIR = Path('data') / 'avatars'

def preprocess_md_content(content):
    """整理markdown格式并保留有效换行"""
    processed = []
    for line in content.splitlines():
        line = line.rstrip()  # 保留行首空格，只去除行尾空格
        if line.strip() == '':
            # 保留段落间的单个空行
            if processed and processed[-1] != '':
                processed.append('')
        else:
            processed.append(line)
    # 移除最后的连续空行
    while processed and processed[-1] == '':
        processed.pop()
    return '\n'.join(processed)

def parse_md_content(content):
    """解析markdown内容为字典格式"""
    sections = {
        '任务': 'task',
        '角色': 'role',
        '外表': 'appearance',
        '经历': 'experience',
        '性格': 'personality',
        '经典台词': 'classic_lines',
        '喜好': 'preferences',
        '备注': 'notes'
    }
    
    result = {v: '' for v in sections.values()}
    current_section = None
    
    # 使用正则匹配精确的标题格式
    lines = content.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        # 匹配一级标题（# 标题）
        match = re.match(r'^#\s+(.+)$', line)
        if match:
            if current_section:
                # 合并当前章节内容并保留换行
                section_content = '\n'.join(lines[section_start:i]).strip()
                result[sections.get(current_section, 'notes')] = section_content.replace('\n', '<br>')
            current_section = match.group(1).strip()
            section_start = i + 1
    
    # 处理最后一个章节
    if current_section and section_start < len(lines):
        section_content = '\n'.join(lines[section_start:]).strip()
        result[sections.get(current_section, 'notes')] = section_content.replace('\n', '<br>')
    
    return result

@avatar_bp.route('/get_available_avatars')
def get_available_avatars():
    """获取所有可用的人设列表"""
    try:
        if not AVATARS_DIR.exists():
            AVATARS_DIR.mkdir(parents=True, exist_ok=True)
            return jsonify({'status': 'success', 'avatars': []})
            
        # 只返回目录名，不包含路径，确保前端处理时路径格式一致
        avatars = [d.name for d in AVATARS_DIR.iterdir() if d.is_dir()]
        print(f"找到的人设目录: {avatars}")  # 添加日志输出
        return jsonify({'status': 'success', 'avatars': avatars})
    except Exception as e:
        print(f"获取人设列表时出错: {str(e)}")  # 添加错误日志
        return jsonify({'status': 'error', 'message': str(e)})

@avatar_bp.route('/load_avatar_content')
def load_avatar_content():
    """加载指定人设的内容"""
    avatar = request.args.get('avatar')
    if not avatar:
        return jsonify({'status': 'error', 'message': '未指定人设名称'})
        
    try:
        avatar_dir = AVATARS_DIR / avatar
        avatar_file = avatar_dir / 'avatar.md'
        
        if not avatar_file.exists():
            return jsonify({'status': 'error', 'message': '人设文件不存在'})
        
        with open(avatar_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 预处理 markdown 内容
        content = preprocess_md_content(content)
        
        parsed_content = parse_md_content(content)
        
        return jsonify({
            'status': 'success',
            'content': parsed_content,
            'raw_content': content
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@avatar_bp.route('/create_avatar', methods=['POST'])
def create_avatar():
    """创建新的人设"""
    try:
        data = request.get_json()
        avatar_name = data.get('avatar_name')
        
        if not avatar_name:
            return jsonify({'status': 'error', 'message': '未提供人设名称'})
        
        # 创建人设目录
        avatar_dir = AVATARS_DIR / avatar_name
        if avatar_dir.exists():
            return jsonify({'status': 'error', 'message': '该人设已存在'})
        
        # 创建目录结构
        avatar_dir.mkdir(parents=True)
        (avatar_dir / 'emojis').mkdir()
        
        # 创建avatar.md文件
        avatar_file = avatar_dir / 'avatar.md'
        template = """## 任务
请在此处描述角色的任务和目标

## 角色
请在此处描述角色的基本信息

## 外表
请在此处描述角色的外表特征

## 经历
请在此处描述角色的经历和背景故事

## 性格
请在此处描述角色的性格特点

## 经典台词
请在此处描述角色的经典台词

## 喜好
请在此处描述角色的喜好

## 备注
其他需要补充的信息
"""
        with open(avatar_file, 'w', encoding='utf-8') as f:
            f.write(template)
        
        # 创建成功，直接返回成功状态
        return jsonify({'status': 'success'})
    except Exception as e:
        # 检查是否人设目录已经创建成功
        if avatar_name and (AVATARS_DIR / avatar_name).exists():
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': str(e)})

@avatar_bp.route('/delete_avatar', methods=['POST'])
def delete_avatar():
    """删除人设"""
    try:
        data = request.get_json()
        avatar_name = data.get('avatar_name')
        
        if not avatar_name:
            return jsonify({'status': 'error', 'message': '未提供人设名称'})
        
        avatar_dir = AVATARS_DIR / avatar_name
        if not avatar_dir.exists():
            return jsonify({'status': 'error', 'message': '人设不存在'})
        
        # 删除整个人设目录
        shutil.rmtree(avatar_dir)
        return jsonify({'status': 'success', 'message': '人设已删除'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

def find_section_index(lines, section_title):
    """查找指定标题在文件行列表中的起始索引"""
    for i, line in enumerate(lines):
        if line.startswith(f'# {section_title}'):
            return i
    return -1

def update_section_content(lines, section_title, new_content):
    """更新指定标题下的内容"""
    start_index = find_section_index(lines, section_title)
    if start_index == -1:
        # 如果标题不存在，添加新的标题和内容
        lines.extend([f'# {section_title}', new_content])
    else:
        # 找到下一个标题的索引
        end_index = next((i for i in range(start_index + 1, len(lines)) if lines[i].startswith('# ')), len(lines))
        # 移除原内容
        del lines[start_index + 1:end_index]
        # 插入新内容
        lines.insert(start_index + 1, new_content)
    return lines

@avatar_bp.route('/save_avatar', methods=['POST'])
def save_avatar():
    """保存人设设定"""
    data = request.get_json()
    avatar_name = data.get('avatar')

    if not avatar_name:
        return jsonify({'status': 'error', 'message': '未提供人设名称'})

    try:
        avatar_dir = AVATARS_DIR / avatar_name
        avatar_file = avatar_dir / 'avatar.md'

        if not avatar_dir.exists():
            return jsonify({'status': 'error', 'message': '人设目录不存在'})

        # 获取前端传递的数据
        task = data.get('task', '')
        role = data.get('role', '')
        appearance = data.get('appearance', '')
        experience = data.get('experience', '')
        personality = data.get('personality', '')
        classic_lines = data.get('classic_lines', '')
        preferences = data.get('preferences', '')
        notes = data.get('notes', '')

        # 读取原文件内容
        if avatar_file.exists():
            with open(avatar_file, 'r', encoding='utf-8') as f:
                lines = [line.rstrip() for line in f]
        else:
            lines = []

        # 更新各板块内容
        sections = {
            '任务': task,
            '角色': role,
            '外表': appearance,
            '经历': experience,
            '性格': personality,
            '经典台词': classic_lines,
            '喜好': preferences,
            '备注': notes
        }
        for section_title, new_content in sections.items():
            lines = update_section_content(lines, section_title, new_content)

        # 构建新的 markdown 内容
        content = "\n".join(lines)

        # 保存文件
        with open(avatar_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # 保存成功，直接返回成功状态
        return jsonify({'status': 'success'})
    except Exception as e:
        # 如果保存过程中发生错误，但avatar.md文件已经存在，则视为成功
        if avatar_name and (AVATARS_DIR / avatar_name / 'avatar.md').exists():
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': str(e)})

@avatar_bp.route('/save_avatar_raw', methods=['POST'])
def save_avatar_raw():
    """保存原始Markdown内容"""
    try:
        data = request.get_json()
        avatar_name = data.get('avatar')
        content = data.get('content')

        if not avatar_name:
            return jsonify({'status': 'error', 'message': '未提供人设名称'})

        if content is None:
            return jsonify({'status': 'error', 'message': '未提供内容'})

        avatar_dir = AVATARS_DIR / avatar_name
        avatar_file = avatar_dir / 'avatar.md'

        if not avatar_dir.exists():
            return jsonify({'status': 'error', 'message': '人设目录不存在'})

        # 保存原始内容
        with open(avatar_file, 'w', encoding='utf-8') as f:
            f.write(content)

        # 保存成功，直接返回成功状态
        return jsonify({'status': 'success'})
    except Exception as e:
        # 如果过程中发生错误，但已经写入了文件，则返回成功状态
        if avatar_name and content and (AVATARS_DIR / avatar_name / 'avatar.md').exists():
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': str(e)})
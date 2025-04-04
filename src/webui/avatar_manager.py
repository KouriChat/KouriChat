from pathlib import Path
import os
import shutil

AVATARS_DIR = Path('data/avatars')

def read_avatar_sections(file_path):
    sections = {
        'task': '',
        'role': '',
        'appearance': '',
        'experience': '',
        'personality': '',
        'classic_lines': '',
        'preferences': '',
        'notes': ''
    }
    
    current_section = None
    content = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
            for line in lines:
                line = line.strip()
                if line.startswith('# '):
                    # 如果之前有section，保存其内容
                    if current_section and content:
                        sections[current_section.lower()] = '\n'.join(content).strip()
                        content = []
                    # 获取新的section名称
                    current_section = line[2:].lower()
                elif current_section and line:
                    content.append(line)
            
            # 保存最后一个section的内容
            if current_section and content:
                sections[current_section.lower()] = '\n'.join(content).strip()
                
        return sections
    except Exception as e:
        print(f"Error reading avatar file: {e}")
        return sections

def save_avatar_sections(file_path, sections):
    """保存人设设定到文件"""
    try:
        content = []
        for section, text in sections.items():
            # 将section名称首字母大写
            section_name = section.replace('_', ' ').title()
            content.append(f"# {section_name}")
            content.append(text.strip())
            content.append("")  # 添加空行分隔
            
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write('\n'.join(content))
        return True
    except Exception as e:
        print(f"Error saving avatar file: {e}")
        return False

def create_avatar(avatar_name):
    """创建新的人设目录和文件"""
    try:
        avatar_dir = AVATARS_DIR / avatar_name
        if avatar_dir.exists():
            return False, "人设已存在"
            
        # 创建目录结构
        avatar_dir.mkdir(parents=True, exist_ok=True)
        (avatar_dir / 'emojis').mkdir(exist_ok=True)
        
        # 创建avatar.md文件
        avatar_file = avatar_dir / 'avatar.md'
        template_sections = {
            'task': '请在此处描述角色的任务和目标',
            'role': '请在此处描述角色的基本信息',
            'appearance': '请在此处描述角色的外表特征',
            'experience': '请在此处描述角色的经历和背景故事',
            'personality': '请在此处描述角色的性格特点',
            'classic_lines': '请在此处列出角色的经典台词',
            'preferences': '请在此处描述角色的喜好',
            'notes': '其他需要补充的信息'
        }
        
        save_avatar_sections(avatar_file, template_sections)
        return True, "人设创建成功"
    except Exception as e:
        return False, str(e)

def delete_avatar(avatar_name):
    """删除人设"""
    try:
        avatar_dir = AVATARS_DIR / avatar_name
        if not avatar_dir.exists():
            return False, "人设不存在"
            
        shutil.rmtree(avatar_dir)
        return True, "人设删除成功"
    except Exception as e:
        return False, str(e)

def get_available_avatars():
    """获取所有可用的人设列表"""
    try:
        if not AVATARS_DIR.exists():
            return []
            
        return [d.name for d in AVATARS_DIR.iterdir() if d.is_dir()]
    except Exception as e:
        print(f"Error getting available avatars: {e}")
        return []

def get_avatar_file_path(avatar_name):
    """获取人设文件路径"""
    return AVATARS_DIR / avatar_name / 'avatar.md' 
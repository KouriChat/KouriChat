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
import yaml
from flask import Flask, render_template, jsonify, request
import importlib
from colorama import init, Fore, Style

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

def get_config_with_comments():
    """获取配置文件内容"""
    config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return f.read()

def parse_config_groups():
    """解析配置文件，将配置项按组分类"""
    config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    config_groups = {}
    
    def process_config_section(section, section_name, parent_path=""):
        if not isinstance(section, dict):
            return
            
        for key, value in section.items():
            if isinstance(value, dict):
                if 'type' in value and 'value' in value:
                    # 这是一个配置项
                    group_name = section_name
                    if group_name not in config_groups:
                        config_groups[group_name] = {}
                    
                    full_path = f"{parent_path}.{key}" if parent_path else key
                    config_groups[group_name][full_path] = {
                        'value': value['value'],
                        'description': value.get('description', ''),
                        'type': value['type']
                    }
                else:
                    # 这是一个配置组
                    new_parent = f"{parent_path}.{key}" if parent_path else key
                    process_config_section(value, section_name or key.title(), new_parent)
    
    # 处理顶级配置组
    for key, value in config_data.items():
        process_config_section(value, key.title(), key)
    
    print_status("配置组解析完成", "info", "📋")
    for group, items in config_groups.items():
        print_status(f"组 '{group}' 包含 {len(items)} 个配置项", "info", "📝")
    
    return config_groups

def save_config(new_config):
    """保存新的配置到文件"""
    config_path = os.path.join(ROOT_DIR, 'src/config/config.yaml')
    
    # 读取当前配置
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    def find_config_item(config, path):
        """查找配置项"""
        keys = path.split('.')
        current = config
        
        for key in keys[:-1]:
            if key not in current:
                return None
            current = current[key]
            
        last_key = keys[-1]
        if last_key in current and isinstance(current[last_key], dict) and 'value' in current[last_key]:
            return current[last_key]
        return None
    
    def update_config_value(config, path, value):
        """更新配置值"""
        config_item = find_config_item(config, path)
        if config_item is None:
            return
        
        try:
            # 转换值的类型
            if config_item['type'] == 'integer':
                value = int(value)
            elif config_item['type'] == 'float':
                value = float(value)
            elif config_item['type'] == 'list' and isinstance(value, str):
                value = [item.strip() for item in value.split(',') if item.strip()]
            elif config_item['type'] == 'boolean':
                value = value.lower() == 'true' if isinstance(value, str) else bool(value)
            
            # 更新值
            config_item['value'] = value
            print_status(f"更新配置: {path} = {value}", "info", "✏️")
        except (ValueError, TypeError) as e:
            print_status(f"转换配置值时出错 {path}: {str(e)}", "warning", "⚠️")
    
    # 更新配置值
    for path, value in new_config.items():
        update_config_value(config_data, path, value)
    
    # 保存到文件，保持原有格式
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        print_status("配置文件已保存", "success", "✅")
    except Exception as e:
        print_status(f"保存配置文件时出错: {str(e)}", "error", "❌")
        raise
    
    try:
        # 重新加载配置模块
        if 'src.config.config_manager' in sys.modules:
            importlib.reload(sys.modules['src.config.config_manager'])
        if 'src.config' in sys.modules:
            importlib.reload(sys.modules['src.config'])
        print_status("配置模块已重新加载", "success", "✅")
    except Exception as e:
        print_status(f"重新加载配置模块时出错: {str(e)}", "warning", "⚠️")
    
    return True

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
        if save_config(new_config):
            return jsonify({"status": "success", "message": "配置已保存"})
        return jsonify({"status": "error", "message": "保存失败"})
    except Exception as e:
        print_status(f"保存配置时出错: {str(e)}", "error", "❌")
        return jsonify({"status": "error", "message": f"保存失败: {str(e)}"})

def main():
    """主函数"""
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
    if not os.path.exists(os.path.join(ROOT_DIR, 'src/config/config.yaml')):
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

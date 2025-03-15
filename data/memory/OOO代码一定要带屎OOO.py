import os
import sys
import socket
import requests
from flask import Flask, request, render_template_string, redirect, url_for, abort

#======================
# 系统配置
#======================
def find_available_port():
    """查找可用端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

CONFIG = {
    'PORT': find_available_port(),  # 自动选择可用端口
    'LOG_FILE': 'error.log',
    'MAX_CONTENT_LENGTH': 100 * 1024,  # 100KB限制
    'BASE_PATH': os.path.abspath(os.path.dirname(__file__))  # 直接指向app.py所在的memory目录[1,3](@ref)
}

#======================
# 路径检测与初始化
#======================
def get_smart_paths():
    """确保记忆文件目录和文件存在"""
    memory_dir = CONFIG['BASE_PATH']
    os.makedirs(memory_dir, exist_ok=True)
    required_files = {'short': 'short_memory.txt', 'long': 'long_memory_buffer.txt'}
    for key, filename in required_files.items():
        file_path = os.path.join(memory_dir, filename)
        if not os.path.isfile(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('')
    return {'memory_dir': memory_dir, 'files': required_files}

#======================
# IP检测
#======================
def get_ip_info():
    """获取公网IP和私网IP"""
    public_ips = []
    apis = ['https://api.ipify.org', 'https://ifconfig.me', 'https://icanhazip.com', 'https://checkip.amazonaws.com']
    for api in apis:
        try:
            response = requests.get(api, timeout=5)
            if response.status_code == 200:
                public_ips.append(response.text.strip())
                break
        except (requests.RequestException, ValueError):
            pass
    try:
        private_ip = socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        private_ip = "无法获取私有IP"
    return public_ips, private_ip

#======================
# 显示系统信息
#======================
def display_system_info():
    """在终端显示系统信息，包括访问地址"""
    public_ips, private_ip = get_ip_info()
    base_url = f"http://{public_ips[0]}:{CONFIG['PORT']}" if public_ips else f"http://localhost:{CONFIG['PORT']}"
    print("========== 系统信息 ==========")
    print(f"公网 IP: {', '.join(public_ips) if public_ips else '无法获取公网IP'}")
    print(f"私网 IP: {private_ip}")
    print(f"访问地址: {base_url}")
    print(f"短记忆文件路径: {os.path.join(CONFIG['BASE_PATH'], 'short_memory.txt')}")
    print(f"长记忆文件路径: {os.path.join(CONFIG['BASE_PATH'], 'long_memory_buffer.txt')}")
    print("==============================")

#======================
# 安全文件操作
#======================
def safe_open(file_path, mode='r', encoding='utf-8'):
    """安全文件操作函数（防御路径遍历攻击）"""
    if not os.path.commonprefix([os.path.abspath(file_path), CONFIG['BASE_PATH']]) == CONFIG['BASE_PATH']:
        return None
    try:
        return open(file_path, mode, encoding=encoding)
    except Exception as e:
        return None

#======================
# 核心应用
#======================
app = Flask(__name__)

@app.route('/')
def index():
    """主界面路由（显示记忆内容和编辑入口）"""
    path_config = get_smart_paths()
    long_path = os.path.join(path_config['memory_dir'], 'long_memory_buffer.txt')
    short_path = os.path.join(path_config['memory_dir'], 'short_memory.txt')

    with safe_open(long_path, 'r') as f:
        long_content = f.read() if f else '长记忆文件为空'
    
    with safe_open(short_path, 'r') as f:
        short_content = f.read() if f else '短记忆文件为空'

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <body>
            <h1>记忆管理系统</h1>
            
            <!-- 长记忆展示区 -->
            <div class="memory-box">
                <h2>📜 长记忆文件</h2>
                <pre>{{ long_content }}</pre>
                <hr>
                <a href="/edit/long_memory_buffer.txt" class="btn">✍️ 修改长记忆</a>
            </div>

            <!-- 短记忆展示区 -->
            <div class="memory-box">
                <h2>💡 短记忆文件</h2>
                <pre>{{ short_content }}</pre>
                <hr>
                <a href="/edit/short_memory.txt" class="btn">✍️ 修改短记忆</a>
            </div>

            <style>
                .memory-box { margin: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
                .btn { display: block; margin-top: 10px; padding: 5px 10px; background: #007bff; color: white; text-decoration: none; border-radius: 3px; }
                .btn:hover { background: #0056b3; }
            </style>
        </body>
        </html>
    ''', long_content=long_content, short_content=short_content)

@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    """文件编辑路由（支持GET预览和POST保存）"""
    file_path = os.path.join(CONFIG['BASE_PATH'], filename)
    
    if request.method == 'POST':
        content = request.form.get('content', '')
        if len(content) > CONFIG['MAX_CONTENT_LENGTH']:  # 100KB限制
            return "内容长度超过限制（100KB）", 400
        
        with safe_open(file_path, 'w') as f:
            f.write(content)
        # 保存成功后重定向到首页
        return redirect(url_for('index'))

    # GET请求时读取文件内容
    with safe_open(file_path, 'r') as f:
        content = f.read() if f else ''

    return render_template_string('''
        <div style="max-width: 800px; margin: 50px auto; padding: 20px; background: #fff; border: 1px solid #ddd;">
            <h2>编辑文件：{{ filename }}</h2>
            <form method="post">
                <textarea 
                    name="content" 
                    style="width: 100%; height: 400px;"
                    placeholder="在此输入文本内容..."
                >{{ content }}</textarea>
                <br>
                <button type="submit" style="padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer;">
                    保存修改
                </button>
                <button type="button" onclick="window.location.href='{{ url_for('index') }}'" style="margin-left: 10px; padding: 10px 20px; background: #ffc107; color: black; border: none; border-radius: 3px; cursor: pointer;">
                    取消
                </button>
            </form>
        </div>
    ''', filename=filename, content=content)

if __name__ == '__main__':
    # 在 Flask 启动前显示系统信息
    display_system_info()

    # 启动服务
    app.run(host='0.0.0.0', port=CONFIG['PORT'], debug=True, threaded=True)

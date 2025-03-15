import json
import requests
import logging
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 读取配置文件
def read_config():
    try:
        with open('api_config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"real_server_base_url": "", "api_key": "", "model": "", "messages": []}
    except json.JSONDecodeError:
        messagebox.showerror("配置文件错误", "配置文件 api_config.json 格式错误，请检查 JSON 格式。")
        return {"real_server_base_url": "", "api_key": "", "model": "", "messages": []}

# 保存配置文件
def save_config(config):
    with open('api_config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

# API测试类
class APITester:
    def __init__(self, base_url, api_key, model, messages=None):
        self.messages = messages or [{"role": "user", "content": "测试消息"}]
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def test_standard_api(self):
        """测试标准 API 端点 /v1/chat/completions"""
        url = f'{self.base_url}/v1/chat/completions'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        data = {
            "model": self.model,
            "messages": self.messages
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response

# 处理API请求错误
def handle_api_error(e, server_type):
    error_msg = f"⚠️ 访问{server_type}遇到问题："
    
    if isinstance(e, requests.exceptions.ConnectionError):
        error_msg += "网络连接失败\n🔧 请检查：1.服务器是否启动 2.地址端口是否正确 3.网络是否通畅 4.防火墙设置"
    elif isinstance(e, requests.exceptions.Timeout):
        error_msg += "请求超时\n🔧 建议：1.稍后重试 2.检查网络速度 3.确认服务器负载情况"
    elif isinstance(e, requests.exceptions.SSLError):
        error_msg += "SSL证书验证失败\n🔧 请尝试：1.更新根证书 2.临时关闭证书验证（测试环境）"
    elif isinstance(e, requests.exceptions.HTTPError):
        status_code = e.response.status_code
        common_solution = "\n💡 解决方法：查看API文档，确认请求参数格式和权限设置"
        
        status_map = {
            400: ("请求格式错误", "检查JSON格式、参数名称和数据类型"),
            401: ("身份验证失败", "1.确认API密钥 2.检查授权头格式"),
            403: ("访问被拒绝", "确认账户权限或套餐是否有效"),
            404: ("接口不存在", "检查URL地址和接口版本号"),
            429: ("请求过于频繁", "降低调用频率或升级套餐"),
            500: ("服务器内部错误", "等待5分钟后重试，若持续报错请联系服务商"),
            502: ("网关错误", "服务器端网络问题，建议等待后重试"),
            503: ("服务不可用", "服务器维护中，请关注官方状态页")
        }
        
        desc, solution = status_map.get(status_code, (f"HTTP {status_code}错误", "查看对应状态码文档"))
        error_msg += f"{desc}\n🔧 {solution}{common_solution}"
    elif isinstance(e, ValueError) and 'Incorrect padding' in str(e):
        error_msg += "API密钥格式错误\n🔧 请检查密钥是否完整（通常以'sk-'开头，共64字符）"
    else:
        error_msg += f"未知错误：{type(e).__name__}\n🔧 建议：1.查看错误详情 2.联系技术支持"
    
    logging.error(error_msg)
    return error_msg

# 测试实际 AI 对话服务器
def test_servers():
    config = read_config()
    real_tester = APITester(
        config.get('real_server_base_url'),
        config.get('api_key'),
        config.get('model'),
        messages=[{"role": "user", "content": "测试消息"}]
    )

    try:
        # 测试连接时间
        start_time = time.time()
        logging.info("正在测试连接时间...")
        response = requests.get(config.get('real_server_base_url'), timeout=5)
        end_time = time.time()
        connection_time = round((end_time - start_time) * 1000, 2)
        logging.info(f"连接成功，响应时间: {connection_time} ms")

        # 测试 API
        logging.info("正在向实际 AI 对话服务器发送请求...")
        response = real_tester.test_standard_api()
        
        if response is None:
            error_msg = "实际服务器返回空响应，请检查服务器状态或请求参数"
            logging.error(error_msg)
            return error_msg
        
        if response.status_code != 200:
            error_msg = f"服务器返回异常状态码: {response.status_code}，错误信息: {response.text}"
            logging.error(error_msg)
            return error_msg
    
        response_text = response.text
        logging.info(f"实际 AI 对话服务器原始响应: {response_text}")
    
        try:
            response_json = response.json()
            logging.info(f"标准 API 端点响应: {response_json}")
            success_msg = f"实际 AI 对话服务器响应正常，连接时间: {connection_time} ms。"
            logging.info(success_msg)
            return success_msg
        except ValueError as json_error:
            error_msg = f"解析实际 AI 对话服务器响应时出现 JSON 解析错误: {json_error}。响应内容: {response_text}"
            logging.error(error_msg)
            return error_msg
    except Exception as e:
        return handle_api_error(e, "实际 AI 对话服务器")

# GUI 界面
class KouriChatToolbox:
    def __init__(self, root):
        self.root = root
        self.root.title("Kouri Chat 工具箱")
        self.root.geometry("600x400")
        self.setup_ui()

    def setup_ui(self):
        # 配置框架
        config_frame = ttk.LabelFrame(self.root, text="配置", padding=10)
        config_frame.pack(fill="x", padx=10, pady=5)

        # 服务器地址
        ttk.Label(config_frame, text="服务器地址:").grid(row=0, column=0, sticky="w")
        self.server_url_entry = ttk.Entry(config_frame, width=50)
        self.server_url_entry.grid(row=0, column=1, padx=5, pady=5)

        # API 密钥
        ttk.Label(config_frame, text="API 密钥:").grid(row=1, column=0, sticky="w")
        self.api_key_entry = ttk.Entry(config_frame, width=50)
        self.api_key_entry.grid(row=1, column=1, padx=5, pady=5)

        # 模型名称
        ttk.Label(config_frame, text="模型名称:").grid(row=2, column=0, sticky="w")
        self.model_entry = ttk.Entry(config_frame, width=50)
        self.model_entry.grid(row=2, column=1, padx=5, pady=5)

        # 按钮框架
        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)

        # 保存配置按钮
        save_button = ttk.Button(button_frame, text="保存配置", command=self.save_config)
        save_button.pack(side="left", padx=5)

        # 开始测试按钮
        test_button = ttk.Button(button_frame, text="开始测试", command=self.run_test)
        test_button.pack(side="left", padx=5)

        # 测试框架
        test_frame = ttk.LabelFrame(self.root, text="测试", padding=10)
        test_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 日志输出框
        self.log_text = scrolledtext.ScrolledText(test_frame, height=10)
        self.log_text.pack(fill="both", expand=True)

        # 加载配置
        self.load_config()

    def load_config(self):
        config = read_config()
        self.server_url_entry.insert(0, config.get("real_server_base_url", ""))
        self.api_key_entry.insert(0, config.get("api_key", ""))
        self.model_entry.insert(0, config.get("model", ""))

    def save_config(self):
        config = {
            "real_server_base_url": self.server_url_entry.get(),
            "api_key": self.api_key_entry.get(),
            "model": self.model_entry.get()
        }
        save_config(config)
        messagebox.showinfo("保存成功", "配置已保存！")

    def run_test(self):
        self.log_text.insert("end", "开始测试...\n")
        self.log_text.update()
        result = test_servers()
        self.log_text.insert("end", f"测试结果: {result}\n")
        self.log_text.see("end")

# 主程序
if __name__ == "__main__":
    root = tk.Tk()
    app = KouriChatToolbox(root)
    root.mainloop()

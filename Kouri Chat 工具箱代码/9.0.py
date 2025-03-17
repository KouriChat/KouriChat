import json
import requests
import logging
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog
from PIL import Image, ImageTk
import io
import webbrowser
import os
import tkhtmlview  
import base64  
import re  

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class APIConfig:
    @staticmethod
    def read_config():
        try:
            with open('api_config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"real_server_base_url": "https://api.siliconflow.cn/", "api_key": "", "model": "deepseek-ai/DeepSeek-V3", "messages": [], "image_config": {"generate_size": "512x512"}, "theme": "light"}
        except json.JSONDecodeError:
            messagebox.showerror("配置文件错误", "配置格式错误，请检查格式。")
            return {"real_server_base_url": "https://api.siliconflow.cn/", "api_key": "", "model": "deepseek-ai/DeepSeek-V3", "messages": [], "image_config": {"generate_size": "512x512"}, "theme": "light"}

    @staticmethod
    def save_config(config):
        with open('api_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)

class APITester:
    def __init__(self, base_url, api_key, model, image_config=None):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.image_config = image_config or {"generate_size": "512x512"}

    def test_standard_api(self):
        url = f'{self.base_url}/v1/chat/completions'
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'}
        data = {"model": self.model, "messages": [{"role": "user", "content": "测试消息"}]}
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response

    def generate_character_profile(self, character_desc):
        prompt = f"请根据以下描述生成一个详细的角色人设，要贴合实际，至少1000字，包含以下内容：\n1. 角色名称\n2. 性格特点\n3. 外表特征\n4. 时代背景\n5. 人物经历\n描述：{character_desc}\n请以清晰的格式返回。"
        data = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        response = requests.post(f'{self.base_url}/v1/chat/completions', headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'}, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def polish_character_profile(self, profile, polish_desc):
        prompt = f"请根据以下要求润色角色人设：\n润色要求：{polish_desc}\n人设内容：{profile}\n请返回润色后的完整人设。修改的内容至少500字"
        data = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        response = requests.post(f'{self.base_url}/v1/chat/completions', headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'}, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def recognize_image(self, image_path):
        url = f'{self.base_url}/v1/chat/completions'
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'}

        # 将图像转换为 base64
        with open(image_path, 'rb') as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')

        # 格式化为带有图像内容的聊天消息
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请详细描述这张图片。例如：'这张照片显示的是一个阳光明媚的海滩，有白色的沙滩和蓝色的海水...'  请使用中文。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                    ]
                }
            ]
        }

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()

    def generate_image(self, prompt):
        url = f'{self.base_url}/v1/images/generate'
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'}
        data = {"prompt": prompt, "n": 1, "size": self.image_config.get("generate_size", "512x512")}
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["data"][0]["url"]

def handle_api_error(e, server_type):
    error_msg = f"警告：访问{server_type}遇到问题："
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

def test_servers():
    config = APIConfig.read_config()
    if not config.get("real_server_base_url") or not config.get("api_key") or not config.get("model"):
        messagebox.showwarning("配置错误", "请填写URL地址、API 密钥和模型名称！")
        return

    real_tester = APITester(config.get('real_server_base_url'), config.get('api_key'), config.get('model'), config.get('image_config'))

    try:
        start_time = time.time()
        logging.info("正在测试连接时间...")
        response = requests.get(config.get('real_server_base_url'), timeout=5)
        end_time = time.time()
        connection_time = round((end_time - start_time) * 1000, 2)
        logging.info(f"连接成功，响应时间: {connection_time} ms")

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
            success_msg = f"实际 AI 对话服务器响应正常，连接时间: {connection_time} ms。\n响应内容:\n{response_json}"
            logging.info(success_msg)
            return success_msg
        except ValueError as json_error:
            error_msg = f"解析实际 AI 对话服务器响应时出现 JSON 解析错误: {json_error}。响应内容: {response_text}"
            logging.error(error_msg)
            return error_msg
    except Exception as e:
        return handle_api_error(e, "实际 AI 对话服务器")

class KouriChatToolbox:
    def __init__(self, root):
        self.root = root
        self.root.title("Kouri Chat 工具箱V8.0")
        self.root.geometry("800x600")
        
        # 设置全局字体
        self.default_font = ("黑体", 10)
        
        # 主题设置
        self.theme_colors = {
            "light": {
                "bg": "#ffffff",
                "fg": "#000000",
                "console_bg": "#f9f9f9",
                "console_fg": "#000000",
                "highlight_bg": "#e0e0e0"
            },
            "dark": {
                "bg": "#2d2d2d",
                "fg": "#ffffff",
                "console_bg": "#1e1e1e",
                "console_fg": "#ffffff",
                "highlight_bg": "#3d3d3d"
            },
            "system": None  # 将根据系统设置动态确定
        }
        
        self.current_theme = "light"  # 默认主题
        self.apply_font_settings()
        
        self.setup_ui()
        self.generated_profile = None
        self.load_config()
        self.apply_theme()

    def apply_font_settings(self):
        # 设置应用程序的默认字体
        self.root.option_add("*Font", self.default_font)
        
        # 为tk部件设置字体
        style = ttk.Style()
        style.configure("TLabel", font=self.default_font)
        style.configure("TButton", font=self.default_font)
        style.configure("TEntry", font=self.default_font)
        style.configure("TCheckbutton", font=self.default_font)
        style.configure("TRadiobutton", font=self.default_font)
        style.configure("TCombobox", font=self.default_font)

    def apply_theme(self):
        # 获取当前主题颜色
        config = APIConfig.read_config()
        self.current_theme = config.get("theme", "light")
        
        # 如果是系统主题，则检测系统设置
        if self.current_theme == "system":
            try:
                import darkdetect
                system_theme = "dark" if darkdetect.isDark() else "light"
            except ImportError:
                system_theme = "light"
            colors = self.theme_colors[system_theme]
        else:
            colors = self.theme_colors[self.current_theme]
        
        # 更新根窗口背景色
        self.root.configure(background=colors["bg"])
        
        # 递归更新所有部件的颜色
        self._update_widget_colors(self.root, colors)

    def _update_widget_colors(self, widget, colors):
        """递归更新所有部件的颜色"""
        widget_type = widget.winfo_class()
        
        # 根据部件类型设置颜色
        if widget_type in ("Frame", "Labelframe"):
            widget.configure(background=colors["bg"])
            if widget_type == "Labelframe":
                widget.configure(foreground=colors["fg"])
        
        elif widget_type == "Label":
            widget.configure(background=colors["bg"], foreground=colors["fg"])
        
        elif widget_type == "Button":
            widget.configure(
                background=colors["highlight_bg"],
                foreground=colors["fg"],
                activebackground=colors["highlight_bg"],
                activeforeground=colors["fg"]
            )
        
        elif widget_type == "Entry":
            widget.configure(
                background=colors["console_bg"],
                foreground=colors["fg"],
                insertbackground=colors["fg"]  # 光标颜色
            )
        
        # 递归处理所有子部件
        for child in widget.winfo_children():
            self._update_widget_colors(child, colors)

    def setup_ui(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="保存配置", command=self.save_config)
        file_menu.add_command(label="导入人设", command=self.import_profile)
        file_menu.add_command(label="导出人设", command=self.export_profile)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)

        # 图片菜单
        image_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="图片", menu=image_menu)
        image_menu.add_command(label="图片识别", command=self.recognize_image)
        image_menu.add_command(label="图片生成", command=self.generate_image)
        
        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        
        # 主题子菜单
        theme_menu = tk.Menu(settings_menu, tearoff=0)
        settings_menu.add_cascade(label="主题", menu=theme_menu)
        theme_menu.add_command(label="亮色模式", command=lambda: self.change_theme("light"))
        theme_menu.add_command(label="暗色模式", command=lambda: self.change_theme("dark"))
        theme_menu.add_command(label="跟随系统", command=lambda: self.change_theme("system"))

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用指南", command=self.show_help)
        help_menu.add_command(label="历史版本", command=self.open_history_page)

        # 配置框架 - 使用tk.LabelFrame代替ttk.LabelFrame
        config_frame = tk.LabelFrame(self.root, text="配置", padx=10, pady=10, font=self.default_font)
        config_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(config_frame, text="URL地址:", font=self.default_font).grid(row=0, column=0, sticky="w")
        self.server_url_entry = tk.Entry(config_frame, width=50, font=self.default_font)
        self.server_url_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(config_frame, text="API 密钥:", font=self.default_font).grid(row=1, column=0, sticky="w")
        self.api_key_entry = tk.Entry(config_frame, width=50, font=self.default_font)
        self.api_key_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(config_frame, text="模型名称:", font=self.default_font).grid(row=2, column=0, sticky="w")
        self.model_entry = tk.Entry(config_frame, width=50, font=self.default_font)
        self.model_entry.grid(row=2, column=1, padx=5, pady=5)
        
        # 添加保存配置按钮 - 使用tk.Button代替ttk.Button
        save_config_button = tk.Button(config_frame, text="保存配置", command=self.save_config, font=self.default_font)
        save_config_button.grid(row=2, column=2, padx=5, pady=5)

        # 控制台框架 - 使用tk.LabelFrame
        console_frame = tk.LabelFrame(self.root, text="控制台", padx=10, pady=10, font=self.default_font)
        console_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 添加测试按钮到控制台框架右侧 - 使用tk.Frame
        test_button_frame = tk.Frame(console_frame)
        test_button_frame.pack(side="right", fill="y", padx=(5, 0))
        
        test_button = tk.Button(test_button_frame, text="开始测试", command=self.run_test, font=self.default_font)
        test_button.pack(pady=5)
        
        # 使用支持Markdown的HTML查看器替代普通文本框
        self.log_text = tkhtmlview.HTMLScrolledText(console_frame)
        self.log_text.pack(side="left", fill="both", expand=True)
        
        # 不尝试配置文本选择，依赖tkhtmlview的默认行为
        # 大多数HTML查看器默认允许文本选择但不允许编辑
        
        # 初始化 last_html_content 属性
        self.last_html_content = "<p style='font-family:黑体;'>欢迎使用Kouri Chat工具箱</p>"
        self.log_text.set_html(self.last_html_content)

        # 生成人设框架 - 使用tk.LabelFrame
        character_frame = tk.LabelFrame(self.root, text="生成人设", padx=10, pady=10, font=self.default_font)
        character_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(character_frame, text="角色描述:", font=self.default_font).grid(row=0, column=0, sticky="w")
        self.character_desc_entry = tk.Entry(character_frame, width=50, font=self.default_font)
        self.character_desc_entry.grid(row=0, column=1, padx=5, pady=5)

        generate_button = tk.Button(character_frame, text="生成人设", command=self.generate_character, font=self.default_font)
        generate_button.grid(row=0, column=2, padx=5, pady=5)

        # 润色人设框架 - 使用tk.LabelFrame
        polish_frame = tk.LabelFrame(self.root, text="润色人设", padx=10, pady=10, font=self.default_font)
        polish_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(polish_frame, text="润色要求:", font=self.default_font).grid(row=0, column=0, sticky="w")
        self.polish_desc_entry = tk.Entry(polish_frame, width=50, font=self.default_font)
        self.polish_desc_entry.grid(row=0, column=1, padx=5, pady=5)

        polish_button = tk.Button(polish_frame, text="润色人设", command=self.polish_character, font=self.default_font)
        polish_button.grid(row=0, column=2, padx=5, pady=5)

    def load_config(self):
        config = APIConfig.read_config()
        self.server_url_entry.insert(0, config.get("real_server_base_url", ""))
        self.api_key_entry.insert(0, config.get("api_key", ""))
        self.model_entry.insert(0, config.get("model", ""))
        self.current_theme = config.get("theme", "light")

    def save_config(self):
        config = {
            "real_server_base_url": self.server_url_entry.get(),
            "api_key": self.api_key_entry.get(),
            "model": self.model_entry.get(),
            "image_config": {"generate_size": "512x512"},
            "theme": self.current_theme
        }
        APIConfig.save_config(config)
        messagebox.showinfo("保存成功", "配置已保存！")

    def change_theme(self, theme):
        self.current_theme = theme
        config = APIConfig.read_config()
        config["theme"] = theme
        APIConfig.save_config(config)
        self.apply_theme()
        
        # 修复 f-string 中的单个右大括号问题
        theme_names = {"light": "亮色", "dark": "暗色", "system": "系统"}
        messagebox.showinfo("主题设置", f"已切换到{theme_names[theme]}主题")

    def copy_console_content(self):
        # 获取当前HTML内容并提取纯文本
        html_content = self.log_text.html
        
        # 创建一个临时的HTML解析器来提取文本
        from html.parser import HTMLParser
        
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                
            def handle_data(self, data):
                self.text.append(data)
                
            def get_text(self):
                return ''.join(self.text)
        
        parser = TextExtractor()
        parser.feed(html_content)
        text_content = parser.get_text()
        
        # 复制到剪贴板
        self.root.clipboard_clear()
        self.root.clipboard_append(text_content)
        messagebox.showinfo("复制成功", "控制台内容已复制到剪贴板")

    def run_test(self):
        self.set_html("<p style='font-family:黑体;'>开始测试...</p>")
        result = test_servers()
        # 将结果转换为HTML格式
        html_result = f"<p style='font-family:黑体;'>测试结果:</p><pre style='font-family:黑体;'>{result}</pre>"
        self.set_html(html_result)

    def generate_character(self):
        character_desc = self.character_desc_entry.get()
        if not character_desc:
            messagebox.showwarning("输入错误", "请输入角色描述！")
            return

        config = APIConfig.read_config()
        tester = APITester(config.get('real_server_base_url'), config.get('api_key'), config.get('model'))

        try:
            self.set_html("<p style='font-family:黑体;'>正在生成角色人设...</p>")
            self.generated_profile = tester.generate_character_profile(character_desc)
            # 将生成的人设转换为HTML格式
            html_profile = f"<p style='font-family:黑体;'>角色人设生成成功！</p><pre style='font-family:黑体;'>{self.generated_profile}</pre>"
            self.set_html(html_profile)
        except Exception as e:
            error_msg = handle_api_error(e, "生成人设")
            self.set_html(f"<p style='font-family:黑体;'>生成失败:</p><pre style='font-family:黑体;'>{error_msg}</pre>")

    def import_profile(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")], title="选择人设文件")
        if not file_path:
            return

        file_size = os.path.getsize(file_path)
        if file_size > 10 * 1024 * 1024:
            messagebox.showwarning("文件过大", "文件大小超过 10MB，请选择较小的文件！")
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.generated_profile = f.read()
            messagebox.showinfo("导入成功", "人设文件已导入！")
            # 将导入的人设转换为HTML格式
            html_profile = f"<p style='font-family:黑体;'>导入的人设内容:</p><pre style='font-family:黑体;'>{self.generated_profile}</pre>"
            self.log_text.set_html(html_profile)
        except Exception as e:
            messagebox.showerror("导入失败", f"导入文件时出错：{e}")

    def export_profile(self):
        if not self.generated_profile:
            messagebox.showwarning("导出失败", "请先生成或导入角色人设！")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")], title="保存人设文件")
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.generated_profile)
                messagebox.showinfo("导出成功", f"角色人设已导出到：{file_path}")
            except Exception as e:
                messagebox.showerror("导出失败", f"导出文件时出错：{e}")

    def polish_character(self):
        if not self.generated_profile:
            messagebox.showwarning("润色失败", "请先生成或导入角色人设！")
            return

        polish_desc = self.polish_desc_entry.get()
        if not polish_desc:
            messagebox.showwarning("输入错误", "请输入润色要求！")
            return

        config = APIConfig.read_config()
        tester = APITester(config.get('real_server_base_url'), config.get('api_key'), config.get('model'))

        try:
            self.set_html("<p style='font-family:黑体;'>正在润色角色人设...</p>")
            self.generated_profile = tester.polish_character_profile(self.generated_profile, polish_desc)
            # 将润色后的人设转换为HTML格式
            html_profile = f"<p style='font-family:黑体;'>角色人设润色成功！</p><pre style='font-family:黑体;'>{self.generated_profile}</pre>"
            self.set_html(html_profile)
        except Exception as e:
            error_msg = handle_api_error(e, "润色人设")
            self.set_html(f"<p style='font-family:黑体;'>润色失败:</p><pre style='font-family:黑体;'>{error_msg}</pre>")

    def recognize_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.jpg *.jpeg *.png")], title="选择图片文件")
        if not file_path:
            return

        config = APIConfig.read_config()
        tester = APITester(config.get('real_server_base_url'), config.get('api_key'), config.get('model'))

        try:
            self.set_html("<p style='font-family:黑体;'>正在识别图片...</p>")
            result = tester.recognize_image(file_path)
            
            # 从响应中提取文本内容
            content = result["choices"][0]["message"]["content"]
            
            # 将图片和识别结果一起显示在HTML中
            with open(file_path, 'rb') as img_file:
                img_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            # 获取当前主题颜色
            if self.current_theme == "system":
                try:
                    import darkdetect
                    system_theme = "dark" if darkdetect.isDark() else "light"
                except ImportError:
                    system_theme = "light"
                colors = self.theme_colors[system_theme]
            else:
                colors = self.theme_colors[self.current_theme]
            
            # 将样式放在style标签中，不在内容中显示CSS代码
            html_result = f"""
            <style>
            body {{ background-color: {colors['console_bg']}; color: {colors['console_fg']}; }}
            </style>
            <h3 style='font-family:黑体;'>图片识别结果:</h3>
            <div style="text-align:center;margin-bottom:10px;">
                <img src="data:image/jpeg;base64,{img_data}" style="max-width:400px;max-height:300px;">
            </div>
            <div style="border:1px solid #ccc;padding:10px;background-color:{colors['highlight_bg']};">
                <p style='font-family:黑体;'>{content}</p>
            </div>
            """
            self.set_html(html_result)
        except Exception as e:
            error_msg = handle_api_error(e, "图片识别")
            self.set_html(f"<p style='font-family:黑体;'>图片识别失败:</p><p style='font-family:黑体;'>{error_msg}</p>")

    def generate_image(self):
        prompt = simpledialog.askstring("图片生成", "请输入图片描述：")
        if not prompt:
            return

        config = APIConfig.read_config()
        tester = APITester(config.get('real_server_base_url'), config.get('api_key'), config.get('model'), config.get('image_config'))

        try:
            self.set_html("<p style='font-family:黑体;'>正在生成图片...</p>")
            image_url = tester.generate_image(prompt)
            
            # 下载图片
            response = requests.get(image_url)
            image = Image.open(io.BytesIO(response.content))
            
            # 将图片转换为base64以在HTML中显示
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_data = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # 在HTML中显示图片和生成信息
            html_result = f"""
            <h3 style='font-family:黑体;'>图片生成成功!</h3>
            <p style='font-family:黑体;'>提示词: {prompt}</p>
            <div style="text-align:center;margin:10px 0;">
                <img src="data:image/png;base64,{img_data}" style="max-width:500px;max-height:500px;">
            </div>
            <p style='font-family:黑体;'>图片URL: <a href="{image_url}" target="_blank">{image_url}</a></p>
            <p style='font-family:黑体;'>提示: 右键点击图片可以保存</p>
            """
            self.set_html(html_result)
        except Exception as e:
            error_msg = handle_api_error(e, "图片生成")
            self.set_html(f"<p style='font-family:黑体;'>图片生成失败:</p><pre style='font-family:黑体;'>{error_msg}</pre>")

    def set_api_url(self):
        api_url = simpledialog.askstring("设置 API URL", "请输入 API URL：")
        if api_url:
            self.server_url_entry.delete(0, tk.END)
            self.server_url_entry.insert(0, api_url)
            messagebox.showinfo("设置成功", f"API URL 已设置为：{api_url}")

    def set_model_name(self):
        model_name = simpledialog.askstring("设置模型名称", "请输入模型名称：")
        if model_name:
            self.model_entry.delete(0, tk.END)
            self.model_entry.insert(0, model_name)
            messagebox.showinfo("设置成功", f"模型名称已设置为：{model_name}")

    def set_image_size(self):
        image_size = simpledialog.askstring("设置图片生成尺寸", "请输入图片生成尺寸（例如：512x512）：")
        if image_size:
            config = APIConfig.read_config()
            config["image_config"]["generate_size"] = image_size
            APIConfig.save_config(config)
            messagebox.showinfo("设置成功", f"图片生成尺寸已设置为：{image_size}")

    def open_history_page(self):
        webbrowser.open("https://github.com/linxiajin08/Kouri-Chat-")

    def show_help(self):
        help_text = (
            "Kouri Chat 工具箱使用指南\n\n"
            "1. 配置\n"
            "   - URL地址：填写 AI 对话服务器的 URL。\n"
            "   - API 密钥：填写 API 访问密钥。\n"
            "   - 模型名称：填写要使用的模型名称。\n\n"
            "2. 文件菜单\n"
            "   - 保存配置：保存当前配置到文件。\n"
            "   - 导入人设：从 TXT 文件导入人设内容。\n"
            "   - 导出人设：将当前人设导出为 TXT 文件。\n"
            "   - 退出：关闭工具箱。\n\n"
            "3. 控制台\n"
            "   - 开始测试：测试 API 连接和功能是否正常。\n"
            "   - 复制内容：复制控制台中的文本内容到剪贴板。\n\n"
            "4. 设置菜单\n"
            "   - 主题：选择亮色模式、暗色模式或跟随系统。\n\n"
            "5. 图片菜单\n"
            "   - 图片识别：上传图片并识别图片内容。\n"
            "   - 图片生成：根据文本描述生成图片。\n\n"
            "6. 常见问题\n"
            "   - URL地址填什么？\n"
            "     答：填写 AI 对话服务器的完整 URL，例如 `https://api.siliconflow.cn/`。\n"
            "   - API 密钥填什么？\n"
            "     答：填写你的 API 访问密钥，通常以 `sk-` 开头。\n"
            "   - 模型名称填什么？\n"
            "     答：填写要使用的模型名称，例如 `deepseek-ai/DeepSeek-V3`。\n"
            "   - 如何生成人设？\n"
            "     答：在角色描述输入框中填写角色描述，点击生成按钮即可。\n"
            "   - 如何导出人设？\n"
            "     答：点击导出按钮，选择保存路径即可。\n"
            "   - 如何设置图片生成尺寸？\n"
            "     答：在设置菜单中选择相应选项，输入尺寸格式如 512x512。\n"
        )
        messagebox.showinfo("帮助", help_text)

    def set_html(self, html_content):
        # 简单的HTML设置方法，不进行额外处理
        if hasattr(self, 'log_text'):
            self.last_html_content = html_content
            self.log_text.set_html(html_content)

# 主程序
if __name__ == "__main__":
    root = tk.Tk()
    app = KouriChatToolbox(root)
    root.mainloop()

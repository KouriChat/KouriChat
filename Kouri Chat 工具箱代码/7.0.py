import json
import requests
import logging
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog
from PIL import Image, ImageTk
import io
import webbrowser  # 用于打开浏览器
import os  # 用于检查文件大小

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# 读取配置文件
def read_config():
    try:
        with open('api_config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"real_server_base_url": "https://api.siliconflow.cn/", "api_key": "", "model": "deepseek-ai/DeepSeek-V3", "messages": []}
    except json.JSONDecodeError:
        messagebox.showerror("配置文件错误", "配置文件 api_config.json 格式错误，请检查 JSON 格式。")
        return {"real_server_base_url": "https://api.siliconflow.cn/", "api_key": "", "model": "deepseek-ai/DeepSeek-V3", "messages": []}

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

    def generate_character_profile(self, character_desc):
        """生成角色人设"""
        prompt = (
            f"请根据以下描述生成一个详细的角色人设，包含以下内容：\n"
            f"1. 角色名称\n"
            f"2. 性格特点\n"
            f"3. 外表特征\n"
            f"4. 任务目标\n"
            f"5. 背景经历\n"
            f"描述：{character_desc}\n"
            f"请以清晰的格式返回。"
        )
        messages = [{"role": "user", "content": prompt}]
        data = {
            "model": self.model,
            "messages": messages
        }
        response = requests.post(f'{self.base_url}/v1/chat/completions', headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def polish_character_profile(self, profile, polish_desc):
        """润色角色人设"""
        prompt = (
            f"请根据以下要求润色角色人设：\n"
            f"润色要求：{polish_desc}\n"
            f"人设内容：{profile}\n"
            f"请返回润色后的完整人设。"
        )
        messages = [{"role": "user", "content": prompt}]
        data = {
            "model": self.model,
            "messages": messages
        }
        response = requests.post(f'{self.base_url}/v1/chat/completions', headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def recognize_image(self, image_path):
        """图片识别"""
        url = f'{self.base_url}/v1/vision/recognize'  # 假设图片识别 API 的路径
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        with open(image_path, 'rb') as image_file:
            files = {'file': image_file}
            response = requests.post(url, headers=headers, files=files)
            response.raise_for_status()
            return response.json()

    def generate_image(self, prompt):
        """图片生成"""
        url = f'{self.base_url}/v1/images/generate'  # 假设图片生成 API 的路径
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        data = {
            "prompt": prompt,
            "n": 1,  # 生成一张图片
            "size": "512x512"  # 图片尺寸
        }
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["data"][0]["url"]  # 返回生成的图片 URL

# 处理API请求错误
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


# 测试实际 AI 对话服务器
def test_servers():
    config = read_config()
    if not config.get("real_server_base_url") or not config.get("api_key") or not config.get("model"):
        messagebox.showwarning("配置错误", "请填写服务器地址、API 密钥和模型名称！")
        return

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
            success_msg = f"实际 AI 对话服务器响应正常，连接时间: {connection_time} ms。\n响应内容:\n{response_json}"
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
        self.root.geometry("800x600")
        self.setup_ui()
        self.generated_profile = None  # 保存生成的人设内容

    def setup_ui(self):
        # 菜单栏
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

        # 测试菜单
        test_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="测试", menu=test_menu)
        test_menu.add_command(label="开始测试", command=self.run_test)

        # 自定义 API 菜单
        custom_api_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="自定义 API", menu=custom_api_menu)
        custom_api_menu.add_command(label="设置 API URL", command=self.set_api_url)
        custom_api_menu.add_command(label="设置模型名称", command=self.set_model_name)

        # 人设菜单
        character_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="人设", menu=character_menu)
        character_menu.add_command(label="生成人设", command=self.generate_character)
        character_menu.add_command(label="润色人设", command=self.polish_character)

        # 图片菜单
        image_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="图片", menu=image_menu)
        image_menu.add_command(label="图片识别", command=self.recognize_image)
        image_menu.add_command(label="图片生成", command=self.generate_image)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用指南", command=self.show_help)
        help_menu.add_command(label="历史版本", command=self.open_history_page)

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

        # 测试框架
        test_frame = ttk.LabelFrame(self.root, text="测试", padding=10)
        test_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 日志输出框
        self.log_text = scrolledtext.ScrolledText(test_frame, height=10)
        self.log_text.pack(fill="both", expand=True)

        # 生成人设框架
        character_frame = ttk.LabelFrame(self.root, text="生成人设", padding=10)
        character_frame.pack(fill="x", padx=10, pady=5)

        # 角色描述输入框
        ttk.Label(character_frame, text="角色描述:").grid(row=0, column=0, sticky="w")
        self.character_desc_entry = ttk.Entry(character_frame, width=50)
        self.character_desc_entry.grid(row=0, column=1, padx=5, pady=5)

        # 生成按钮
        generate_button = ttk.Button(character_frame, text="生成人设", command=self.generate_character)
        generate_button.grid(row=0, column=2, padx=5, pady=5)

        # 润色人设框架
        polish_frame = ttk.LabelFrame(self.root, text="润色人设", padding=10)
        polish_frame.pack(fill="x", padx=10, pady=5)

        # 润色要求输入框
        ttk.Label(polish_frame, text="润色要求:").grid(row=0, column=0, sticky="w")
        self.polish_desc_entry = ttk.Entry(polish_frame, width=50)
        self.polish_desc_entry.grid(row=0, column=1, padx=5, pady=5)

        # 润色按钮
        polish_button = ttk.Button(polish_frame, text="润色人设", command=self.polish_character)
        polish_button.grid(row=0, column=2, padx=5, pady=5)

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
        self.log_text.delete(1.0, tk.END)  # 清空日志输出框
        self.log_text.insert("end", "开始测试...\n")
        self.log_text.update()
        result = test_servers()
        self.log_text.insert("end", f"测试结果: {result}\n")
        self.log_text.see("end")

    def generate_character(self):
        character_desc = self.character_desc_entry.get()
        if not character_desc:
            messagebox.showwarning("输入错误", "请输入角色描述！")
            return

        config = read_config()
        tester = APITester(
            config.get('real_server_base_url'),
            config.get('api_key'),
            config.get('model')
        )

        try:
            self.log_text.insert("end", "正在生成角色人设...\n")
            self.log_text.update()
            self.generated_profile = tester.generate_character_profile(character_desc)
            self.log_text.insert("end", f"角色人设生成成功！\n")
            self.log_text.see("end")
        except Exception as e:
            error_msg = handle_api_error(e, "生成人设")
            self.log_text.insert("end", f"生成失败: {error_msg}\n")
            self.log_text.see("end")

    def import_profile(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Text Files", "*.txt")],
            title="选择人设文件"
        )
        if not file_path:
            return

                # 检查文件大小（限制为 10MB）
        file_size = os.path.getsize(file_path)  # 获取文件大小（单位：字节）
        if file_size > 10 * 1024 * 1024:  # 10MB
            messagebox.showwarning("文件过大", "文件大小超过 10MB，请选择较小的文件！")
            return

        try:
            # 使用流式读取文件内容，避免一次性加载大文件
            with open(file_path, "r", encoding="utf-8") as f:
                self.generated_profile = f.read()
            messagebox.showinfo("导入成功", "人设文件已导入！")
            self.log_text.insert("end", f"导入的人设内容:\n{self.generated_profile}\n")
            self.log_text.see("end")
        except Exception as e:
            messagebox.showerror("导入失败", f"导入文件时出错：{e}")

    def export_profile(self):
        if not self.generated_profile:
            messagebox.showwarning("导出失败", "请先生成或导入角色人设！")
            return

        # 选择导出路径
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
            title="保存人设文件"
        )
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

        config = read_config()
        tester = APITester(
            config.get('real_server_base_url'),
            config.get('api_key'),
            config.get('model')
        )

        try:
            self.log_text.insert("end", "正在润色角色人设...\n")
            self.log_text.update()
            self.generated_profile = tester.polish_character_profile(self.generated_profile, polish_desc)
            self.log_text.insert("end", f"角色人设润色成功！\n")
            self.log_text.see("end")
        except Exception as e:
            error_msg = handle_api_error(e, "润色人设")
            self.log_text.insert("end", f"润色失败: {error_msg}\n")
            self.log_text.see("end")

    def recognize_image(self):
        """图片识别功能"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Image Files", "*.jpg *.jpeg *.png")],
            title="选择图片文件"
        )
        if not file_path:
            return

        config = read_config()
        tester = APITester(
            config.get('real_server_base_url'),
            config.get('api_key'),
            config.get('model')
        )

        try:
            self.log_text.insert("end", "正在识别图片...\n")
            self.log_text.update()
            result = tester.recognize_image(file_path)
            self.log_text.insert("end", f"图片识别结果:\n{result}\n")
            self.log_text.see("end")

            # 弹出新窗口显示识别结果
            result_window = tk.Toplevel(self.root)
            result_window.title("图片识别结果")
            result_text = scrolledtext.ScrolledText(result_window, width=60, height=10)
            result_text.pack(padx=10, pady=10)
            result_text.insert(tk.END, json.dumps(result, indent=2, ensure_ascii=False))
            result_text.config(state=tk.DISABLED)  # 设置为只读
        except Exception as e:
            error_msg = handle_api_error(e, "图片识别")
            self.log_text.insert("end", f"图片识别失败: {error_msg}\n")
            self.log_text.see("end")

    def generate_image(self):
        """图片生成功能"""
        # 弹出新窗口输入提示词
        prompt = simpledialog.askstring("图片生成", "请输入图片描述：")
        if not prompt:
            return

        config = read_config()
        tester = APITester(
            config.get('real_server_base_url'),
            config.get('api_key'),
            config.get('model')
        )

        try:
            self.log_text.insert("end", "正在生成图片...\n")
            self.log_text.update()
            image_url = tester.generate_image(prompt)
            self.log_text.insert("end", f"图片生成成功！图片 URL: {image_url}\n")
            self.log_text.see("end")

            # 下载图片
            response = requests.get(image_url)
            image = Image.open(io.BytesIO(response.content))
            image = image.resize((512, 512), Image.ANTIALIAS)

            # 弹出新窗口显示图片
            image_window = tk.Toplevel(self.root)
            image_window.title("生成图片")

            # 显示图片
            photo = ImageTk.PhotoImage(image)
            image_label = ttk.Label(image_window, image=photo)
            image_label.pack(padx=10, pady=10)

            # 保存图片按钮
            def save_image():
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".png",
                    filetypes=[("PNG Files", "*.png"), ("JPEG Files", "*.jpg")],
                    title="保存图片"
                )
                if file_path:
                    image.save(file_path)
                    messagebox.showinfo("保存成功", f"图片已保存到：{file_path}")

            save_button = ttk.Button(image_window, text="保存图片", command=save_image)
            save_button.pack(pady=10)

            # 保持图片引用，防止被垃圾回收
            image_label.image = photo
        except Exception as e:
            error_msg = handle_api_error(e, "图片生成")
            self.log_text.insert("end", f"图片生成失败: {error_msg}\n")
            self.log_text.see("end")

    def set_api_url(self):
        """设置自定义 API URL"""
        api_url = simpledialog.askstring("设置 API URL", "请输入 API URL：")
        if api_url:
            self.server_url_entry.delete(0, tk.END)
            self.server_url_entry.insert(0, api_url)
            messagebox.showinfo("设置成功", f"API URL 已设置为：{api_url}")

    def set_model_name(self):
        """设置自定义模型名称"""
        model_name = simpledialog.askstring("设置模型名称", "请输入模型名称：")
        if model_name:
            self.model_entry.delete(0, tk.END)
            self.model_entry.insert(0, model_name)
            messagebox.showinfo("设置成功", f"模型名称已设置为：{model_name}")

    def open_history_page(self):
        """打开历史版本页面"""
        webbrowser.open("https://github.com/linxiajin08/Kouri-Chat-")

    def show_help(self):
        """显示帮助信息"""
        help_text = (
            "Kouri Chat 工具箱使用指南\n\n"
            "1. 配置\n"
            "   - 服务器地址：填写 AI 对话服务器的 URL。\n"
            "   - API 密钥：填写 API 访问密钥。\n"
            "   - 模型名称：填写要使用的模型名称。\n\n"
            "2. 文件菜单\n"
            "   - 保存配置：保存当前配置到文件。\n"
            "   - 导入人设：从 TXT 文件导入人设内容。\n"
            "   - 导出人设：将当前人设导出为 TXT 文件。\n"
            "   - 退出：关闭工具箱。\n\n"
            "3. 测试菜单\n"
            "   - 开始测试：测试 API 连接和功能是否正常。\n\n"
            "4. 自定义 API 菜单\n"
            "   - 设置 API URL：手动设置 API 的 URL。\n"
            "   - 设置模型名称：手动设置模型名称。\n\n"
            "5. 人设菜单\n"
            "   - 生成人设：根据角色描述生成人设。\n"
            "   - 润色人设：根据润色要求对生成的人设进行优化。\n\n"
            "6. 图片菜单\n"
            "   - 图片识别：上传图片并识别图片内容。\n"
            "   - 图片生成：根据文本描述生成图片。\n\n"
            "7. 常见问题\n"
            "   - 服务器地址填什么？\n"
            "     答：填写 AI 对话服务器的完整 URL，例如 `https://api.siliconflow.cn/`。\n"
            "   - API 密钥填什么？\n"
            "     答：填写你的 API 访问密钥，通常以 `sk-` 开头。\n"
            "   - 模型名称填什么？\n"
            "     答：填写要使用的模型名称，例如 `deepseek-ai/DeepSeek-V3`。\n"
            "   - 如何生成人设？\n"
            "     答：在角色描述输入框中填写角色描述，点击生成按钮即可。\n"
            "   - 如何导出人设？\n"
            "     答：点击导出按钮，选择保存路径即可。\n"
        )
        messagebox.showinfo("帮助", help_text)

# 主程序
if __name__ == "__main__":
    root = tk.Tk()
    app = KouriChatToolbox(root)
    root.mainloop()


"""
微信语音消息识别功能单元测试
测试重点：
1. 能否成功切换到目标聊天
2. 能否成功使用微信的"转文字"功能
3. 能否正确获取转写结果

使用方法:
1. 基本测试: python test_voice_recognition.py
2. 指定窗口测试: python test_voice_recognition.py --chat "群聊测试"
3. 自动模式: python test_voice_recognition.py --chat "群聊测试" --auto
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import time
import argparse
import pyautogui
import win32gui

# 添加项目根目录到 PYTHONPATH，确保可以导入项目模块
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from src.handlers.voice import VoiceHandler

# 全局参数用于存储命令行选项
CMD_ARGS = {}

def search_and_open_chat(voice_handler, chat_name):
    """
    使用微信的搜索框查找并打开指定的聊天窗口
    
    Args:
        voice_handler: VoiceHandler实例
        chat_name: 聊天窗口名称
        
    Returns:
        bool: 是否成功打开聊天窗口
    """
    try:
        wx_instance = voice_handler.wx
        
        # 先尝试使用 ChatWith 打开聊天窗口
        success = wx_instance.ChatWith(chat_name)
        print(f"使用 ChatWith 切换到聊天窗口 '{chat_name}', 结果: {success}")
        
        if not success:
            # 如果直接切换失败，尝试使用搜索框
            print("直接切换失败，尝试使用搜索框...")
            # 获取微信主窗口句柄
            main_hwnd = win32gui.FindWindow("WeChatMainWndForPC", None)
            if not main_hwnd:
                print("找不到微信主窗口")
                return False
                
            # 获取窗口位置
            rect = win32gui.GetWindowRect(main_hwnd)
            win_width = rect[2] - rect[0]
            win_height = rect[3] - rect[1]
            
            # 点击搜索框（通常在窗口左上方）
            search_x = rect[0] + int(win_width * 0.2)  # 搜索框在窗口的大约20%处
            search_y = rect[1] + 40  # 搜索框垂直位置大约在标题栏下方
            
            print(f"点击搜索框，位置: ({search_x}, {search_y})")
            pyautogui.click(search_x, search_y)
            time.sleep(0.5)
            
            # 先清空搜索框（使用Ctrl+A选择全部，然后删除）
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.press('delete')
            time.sleep(0.1)
            
            # 输入聊天名称
            print(f"输入搜索内容: {chat_name}")
            pyautogui.write(chat_name)
            time.sleep(1.0)  # 等待搜索结果
            
            # 点击第一个搜索结果（通常在搜索框下方）
            result_x = search_x
            result_y = search_y + 80  # 第一个结果通常在搜索框下方约80像素
            
            print(f"点击搜索结果，位置: ({result_x}, {result_y})")
            pyautogui.click(result_x, result_y)
            time.sleep(1.0)  # 等待窗口切换
        
        # 查找聊天小窗口
        time.sleep(1.0)  # 给时间让窗口加载
        chat_window = voice_handler.find_chat_window(chat_name)
        if chat_window:
            print(f"成功找到聊天小窗口: {chat_window}")
            # 激活聊天小窗口
            win32gui.SetForegroundWindow(chat_window)
            time.sleep(0.5)  # 等待窗口激活
            return True
        
        # 如果找不到小窗口，可能是在主窗口的标签中，也算成功
        return True
        
    except Exception as e:
        print(f"搜索并打开聊天窗口失败: {str(e)}")
        return False


class TestVoiceRecognition(unittest.TestCase):
    def setUp(self):
        """
        测试前的准备工作
        """
        # 创建临时目录用于测试
        self.root_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        self.temp_dir = os.path.join(self.root_dir, "temp", "test_voice")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 初始化 VoiceHandler
        self.voice_handler = VoiceHandler(
            root_dir=self.root_dir,
            tts_api_url="http://example.com/tts"
        )
        
        # 创建模拟的微信实例
        self.mock_wx = MagicMock()
        self.mock_wx.ChatWith = MagicMock(return_value="测试聊天")
        
        # 设置微信实例
        self.voice_handler.update_wx_instance(self.mock_wx)
        
        # 准备测试参数
        self.test_chat_id = "测试聊天"
        self.test_voice_message = "[语音]2秒,未播放"
    
    @patch("win32gui.FindWindow")
    @patch("win32gui.GetWindowRect")
    @patch("pyautogui.rightClick")
    @patch("pyautogui.click")
    @patch("pyautogui.hotkey")
    @patch("pyperclip.paste")
    def test_recognize_voice_message(self, 
                                     mock_paste, 
                                     mock_hotkey, 
                                     mock_click, 
                                     mock_right_click, 
                                     mock_get_window_rect, 
                                     mock_find_window):
        """
        测试语音消息识别功能
        模拟整个流程: 切换聊天窗口 -> 右键点击语音消息 -> 点击转文字 -> 复制结果
        """
        # 设置模拟返回值
        mock_find_window.return_value = 12345  # 模拟窗口句柄
        mock_get_window_rect.return_value = (0, 0, 1000, 800)  # 模拟窗口区域
        mock_paste.return_value = "这是语音转写的测试内容"  # 模拟剪贴板内容
        
        # 调用被测试方法
        result = self.voice_handler.recognize_voice_message(
            msg_content=self.test_voice_message,
            chat_id=self.test_chat_id
        )
        
        # 验证结果
        self.assertEqual(result, "这是语音转写的测试内容")
        
        # 验证方法调用
        self.mock_wx.ChatWith.assert_called_once_with(self.test_chat_id)
        mock_find_window.assert_called_once()
        mock_get_window_rect.assert_called_once()
        mock_right_click.assert_called_once()
        
        # 验证坐标点击 (转文字选项)
        mock_click.assert_called()
        
        # 验证热键调用 (Ctrl+C)
        mock_hotkey.assert_called_once_with('ctrl', 'c')
        
        # 验证剪贴板读取
        mock_paste.assert_called()
    
    @patch("win32gui.FindWindow")
    @patch("win32gui.GetWindowRect")
    @patch("pyautogui.rightClick")
    @patch("pyautogui.click")
    @patch("pyautogui.hotkey")
    @patch("pyperclip.paste")
    def test_recognize_voice_message_clipboard_empty(self, 
                                                    mock_paste, 
                                                    mock_hotkey, 
                                                    mock_click, 
                                                    mock_right_click, 
                                                    mock_get_window_rect, 
                                                    mock_find_window):
        """
        测试当剪贴板为空时的备用方案
        """
        # 设置模拟返回值
        mock_find_window.return_value = 12345
        mock_get_window_rect.return_value = (0, 0, 1000, 800)
        
        # 模拟热键复制失败，剪贴板为空
        mock_paste.side_effect = ["", "右键菜单复制的结果"]
        
        # 调用被测试方法
        result = self.voice_handler.recognize_voice_message(
            msg_content=self.test_voice_message,
            chat_id=self.test_chat_id
        )
        
        # 验证备用方案正常工作
        self.assertEqual(result, "右键菜单复制的结果")
        
        # 验证调用了备用的右键菜单复制方法
        self.assertEqual(mock_paste.call_count, 2)
    
    @patch("win32gui.FindWindow")
    def test_window_not_found(self, mock_find_window):
        """
        测试找不到微信窗口的情况
        """
        # 设置模拟返回值 - 找不到窗口
        mock_find_window.return_value = 0
        
        # 调用被测试方法
        result = self.voice_handler.recognize_voice_message(
            msg_content=self.test_voice_message,
            chat_id=self.test_chat_id
        )
        
        # 验证返回占位符文本
        self.assertEqual(result, "[语音消息: 2秒]")
    
    def test_wx_not_initialized(self):
        """
        测试微信实例未初始化的情况
        """
        # 创建没有微信实例的处理器
        temp_handler = VoiceHandler(
            root_dir=self.root_dir,
            tts_api_url="http://example.com/tts"
        )
        
        # 调用被测试方法
        result = temp_handler.recognize_voice_message(
            msg_content=self.test_voice_message,
            chat_id=self.test_chat_id
        )
        
        # 验证结果为 None
        self.assertIsNone(result)
    
    def tearDown(self):
        """
        测试后的清理工作
        """
        # 清理临时文件夹
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


class TestVoiceRecognitionManual(unittest.TestCase):
    """
    手动测试用例 - 需要实际的微信窗口
    """
    
    def setUp(self):
        """
        测试前的准备工作
        """
        # 初始化 VoiceHandler
        self.root_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        self.voice_handler = VoiceHandler(
            root_dir=self.root_dir,
            tts_api_url="http://example.com/tts"
        )
        
        # 导入实际的WeChat类
        from wxauto import WeChat
        
        # 尝试创建实际的微信实例
        try:
            self.wx = WeChat()
            self.voice_handler.update_wx_instance(self.wx)
            self.has_wx = True
        except Exception as e:
            print(f"无法初始化微信实例: {e}")
            self.has_wx = False
    
    def test_manual_voice_recognition(self):
        """
        手动测试语音识别功能
        需要实际运行微信，并存在语音消息
        """
        # 如果没有微信实例，跳过测试
        if not self.has_wx:
            self.skipTest("微信实例不可用，跳过手动测试")
        
        # 获取群聊列表
        chats = self.wx.GetSessionList()
        if not chats:
            self.skipTest("未找到任何微信会话，跳过手动测试")
        
        # 将字典转换为列表以便枚举
        chat_list = list(chats.keys()) if isinstance(chats, dict) else list(chats)
        
        # 检查是否通过命令行指定了聊天窗口
        selected_chat = None
        
        if 'chat' in CMD_ARGS and CMD_ARGS['chat']:
            target_chat = CMD_ARGS['chat']
            selected_chat = target_chat
            print(f"\n将使用搜索框查找指定的聊天窗口: {selected_chat}")
            
            # 显示一些可用的聊天窗口作为参考
            print("当前会话列表中的聊天窗口(仅供参考):")
            for chat in chat_list[:10]:  # 只显示前10个
                print(f" - {chat}")
            
            # 提供详细的操作指导
            print("\n" + "="*50)
            print("【重要测试提示】")
            print("1. 请在启动测试前，确保目标聊天窗口中有最近发送的语音消息")
            print("2. 最好是让语音消息位于窗口底部可见位置")
            print("3. 您可以在测试开始前发送一条语音消息到目标聊天")
            print("4. 测试将尝试右键点击聊天窗口底部区域寻找语音消息")
            print("="*50)
            
            # 询问用户是否需要自己手动操作
            try:
                if not CMD_ARGS.get('auto', False):
                    # 始终不使用手动辅助模式
                    manual_mode = False
                    print("\n已设置为自动模式，不使用手动辅助")
                    
                    # 等待用户准备
                    input("\n准备开始自动测试，请勿移动鼠标。按回车键开始...")
                else:
                    print("自动模式下将直接开始测试")
            except ValueError:
                self.skipTest("输入无效，跳过手动测试")
            except KeyboardInterrupt:
                self.skipTest("用户中断，跳过手动测试")
        else:
            # 如果没有指定窗口，则使用交互方式选择
            # 提示用户
            print("\n" + "="*50)
            print("手动测试开始，请确保以下条件：")
            print("1. 微信已登录")
            print("2. 测试的聊天窗口中有语音消息")
            print("3. 该语音消息最好是最新消息，位于窗口底部")
            print("="*50)
            
            # 显示可用的聊天会话
            print("\n当前会话列表中的聊天窗口(仅供参考):")
            for i, chat in enumerate(chat_list[:10]):  # 只显示前10个
                print(f"{i+1}. {chat}")
            
            # 询问用户输入要测试的聊天名称
            try:
                if not CMD_ARGS.get('auto', False):
                    print("\n您可以输入任意聊天窗口名称，不限于以上列表")
                    selected_chat = input("请输入要测试的聊天窗口名称: ").strip()
                    if not selected_chat:
                        self.skipTest("未输入聊天窗口名称")
                    
                    print(f"已选择: {selected_chat}")
                    
                    # 等待用户准备
                    input("按回车键开始测试...")
                else:
                    self.skipTest("自动模式下未指定聊天窗口")
            except ValueError:
                self.skipTest("输入无效，跳过手动测试")
            except KeyboardInterrupt:
                self.skipTest("用户中断，跳过手动测试")
        
        if selected_chat is None:
            self.skipTest("未选择聊天窗口")
        
        # 始终使用严格验证模式
        strict_mode = True
        print("已启用严格验证，测试将在识别失败时报错")
        
        # 调用语音识别方法
        print(f"开始语音识别测试，聊天窗口: {selected_chat}")
        start_time = time.time()
        
        # 使用VoiceHandler直接处理语音消息识别
        print("开始识别语音消息...")
        result = self.voice_handler.recognize_voice_message(
            msg_content="[语音]5秒,未播放",
            chat_id=selected_chat
        )
        
        end_time = time.time()
        
        # 输出结果
        print(f"\n语音识别结果: {result}")
        print(f"耗时: {end_time - start_time:.2f}秒")
        
        # 如果结果是None或默认占位符，则根据验证模式判断是否失败
        if result is None or result.startswith("[语音消息"):
            if strict_mode:
                self.fail("语音识别失败")
            else:
                print("WARNING: 语音识别未成功，但在宽松模式下继续运行")
        else:
            print("测试成功!")


def parse_arguments():
    """
    解析命令行参数
    """
    parser = argparse.ArgumentParser(description='微信语音消息识别测试')
    parser.add_argument('--chat', type=str, help='要测试的聊天窗口名称')
    parser.add_argument('--auto', action='store_true', help='自动模式，不需要用户交互')
    parser.add_argument('--strict', action='store_true', help='严格验证模式，识别失败时测试将失败')
    parser.add_argument('--manual', action='store_true', help='手动辅助模式，允许用户手动操作')
    
    args = parser.parse_args()
    return {
        'chat': args.chat,
        'auto': args.auto,
        'strict': args.strict,
        'manual': args.manual
    }


if __name__ == "__main__":
    # 处理命令行参数
    CMD_ARGS = parse_arguments()
    
    # 只运行手动测试
    if CMD_ARGS.get('chat') is not None:
        suite = unittest.TestSuite()
        suite.addTest(TestVoiceRecognitionManual('test_manual_voice_recognition'))
        unittest.TextTestRunner().run(suite)
    else:
        # 运行全部测试
        unittest.main() 
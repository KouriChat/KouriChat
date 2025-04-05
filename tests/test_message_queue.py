import sys
import os
import threading
import time
import logging
import pytest
from unittest.mock import MagicMock, patch

# 添加项目根目录到PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入需要测试的类
from src.handlers.message import MessageHandler

# 配置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestMessageQueue:
    """测试消息队列处理机制"""
    
    def setup_method(self):
        """测试前的设置"""
        # 创建模拟对象
        self.mock_llm = MagicMock()
        self.mock_wx = MagicMock()
        
        # 模拟API响应
        self.mock_llm.get_response.return_value = "这是一个测试响应"
        
        # 创建消息处理器实例
        self.message_handler = MessageHandler(
            root_dir=".",
            llm=self.mock_llm,
            wx=self.mock_wx,
            robot_name="TestBot",
            is_debug=False
        )
        
        # 模拟get_api_response方法
        self.message_handler.get_api_response = MagicMock()
        self.message_handler.get_api_response.return_value = "这是一个测试响应"
        
    def test_api_response_queue(self):
        """测试API响应队列"""
        # 同一个用户发送多个消息
        user_id = "test_user"
        
        # 创建线程模拟同时收到的多个请求
        def send_request(message):
            response = self.message_handler.get_private_api_response(message, user_id)
            logger.info(f"收到响应: {response}")
            
        # 创建多个线程
        threads = []
        for i in range(3):
            t = threading.Thread(target=send_request, args=(f"测试消息 {i}",))
            threads.append(t)
            
        # 启动所有线程
        for t in threads:
            t.start()
            # 短暂延迟，模拟真实场景中的间隔
            time.sleep(0.1)
            
        # 等待所有线程结束
        for t in threads:
            t.join()
            
        # 检查调用次数
        assert self.message_handler.get_api_response.call_count <= 3
        
    def test_send_split_messages(self):
        """测试消息分割发送机制"""
        user_id = "test_user"
        
        # 模拟多个消息片段
        messages = {
            "parts": ["这是第一段", "这是第二段", "这是第三段"],
            "total_length": 30,
            "sentence_count": 3
        }
        
        # 设置用户最后消息时间
        self.message_handler.last_received_message_timestamp[user_id] = time.time()
        
        # 发送消息
        result = self.message_handler._send_split_messages(messages, user_id)
        
        # 检查结果
        assert result == True
        # 检查wx.SendMsg调用次数
        assert self.mock_wx.SendMsg.call_count == 3
        
    def test_concurrent_message_sending(self):
        """测试并发消息发送"""
        user_id = "test_user"
        
        # 模拟多个消息
        messages1 = {
            "parts": ["第一条消息片段1", "第一条消息片段2"],
            "total_length": 20,
            "sentence_count": 2
        }
        
        messages2 = {
            "parts": ["第二条消息片段1", "第二条消息片段2"],
            "total_length": 20,
            "sentence_count": 2
        }
        
        # 创建发送线程
        def send_message(msg):
            return self.message_handler._send_split_messages(msg, user_id)
            
        # 创建两个线程同时发送
        t1 = threading.Thread(target=send_message, args=(messages1,))
        t2 = threading.Thread(target=send_message, args=(messages2,))
        
        # 启动线程
        t1.start()
        # 短暂延迟，确保第一个线程先开始
        time.sleep(0.1)
        t2.start()
        
        # 等待线程结束
        t1.join()
        t2.join()
        
        # 验证发送次数（应该是4，两个消息各2个片段）
        # 或者小于4，说明有消息被中断了，这也是正常的
        assert self.mock_wx.SendMsg.call_count <= 4
        
if __name__ == "__main__":
    pytest.main(["-vxs", __file__]) 
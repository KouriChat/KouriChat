import os
import sys
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI, APIConnectionError, AuthenticationError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, wait_fixed, retry_if_exception_type

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

class EmbeddingModelAI:
    def __init__(self, model_name='text-embedding-v2', dimension=1024):
        self.client = None
        self.available = True
        self.api_key = "sk-96d4c845a4ed4ab5b7af7668e298f1c6"
        self.model_name = model_name
        self.dimension = dimension
        
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=30.0,
                max_retries=3
            )
            
            # 测试连接有效性
            test_response = self.client.embeddings.create(
                model=self.model_name,  # 使用传入的模型名称
                input="connection test",
                dimensions=self.dimension,  # 使用传入的维度参数
                encoding_format="float"
            )
            if not hasattr(test_response, 'data'):
                raise APIConnectionError("Invalid API response structure")
                
        except Exception as e:
            print(f"嵌入模型初始化失败: {str(e)}")
            self._handle_initialization_error(e)
            self.available = False

    def _handle_initialization_error(self, error):
        """处理特定类型的初始化错误"""
        if isinstance(error, AuthenticationError):
            print("认证失败：请检查DASHSCOPE_API_KEY是否正确")
        elif isinstance(error, APIConnectionError):
            print("连接失败：请检查网络或API端点")
        elif hasattr(error, 'status_code'):
            print(f"API返回错误状态码：{error.status_code}")


    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def get_embeddings(self, text):
        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=text,
                dimensions=self.dimension,
                encoding_format="float"
            )
            return response.data[0].embedding
        except APIConnectionError as e:
            print(f"API连接异常: {str(e)}")
            self.available = False
            return None
        except AuthenticationError as e:
            print(f"认证失败: {str(e)}")
            self.available = False
            return None
        except APIError as e:
            print(f"API错误 [{e.status_code}]: {str(e)}")
            return None
        except Exception as e:
            print(f"未知错误: {str(e)}")
            return None

    @property
    def status(self):
        """返回服务状态信息"""
        return {
            "available": self.available,
            "api_endpoint": self.client.base_url if self.client else None,
            "model": "text-embedding-v3"
        }
"""
API调用包装器模块 - 提供统一的API调用接口
"""
import os
import logging
import json
import openai
import asyncio
import re
from typing import Any, Dict, List, Optional, Union

# 设置日志
logger = logging.getLogger('main')

class APIWrapper:
    """
    API调用包装器类，提供统一的API调用接口
    """
    
    def __init__(self, api_key: str, base_url: str = None):
        """
        初始化API包装器
        
        Args:
            api_key: API密钥
            base_url: API基础URL，默认为OpenAI官方API
        """
        self.api_key = api_key
        self.base_url = base_url
        
        # 初始化OpenAI客户端
        self._init_client()
        
        # 创建API接口
        self._create_interfaces()
        
    def _init_client(self):
        """初始化OpenAI客户端"""
        try:
            # 设置环境变量
            os.environ["OPENAI_API_KEY"] = self.api_key
            if self.base_url:
                os.environ["OPENAI_API_BASE"] = self.base_url
                
            # 创建客户端
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            logger.info(f"成功初始化API客户端，基础URL: {self.base_url or '默认OpenAI'}")
        except Exception as e:
            logger.error(f"初始化API客户端失败: {str(e)}")
            # 创建一个空客户端，避免程序崩溃
            self.client = object()
            
    def _create_interfaces(self):
        """创建API接口"""
        # 嵌入API
        self.embeddings = APIEmbeddings(self)
        
    def handle_api_error(self, error: Exception) -> Dict:
        """
        处理API错误
        
        Args:
            error: 异常对象
            
        Returns:
            Dict: 错误信息字典
        """
        try:
            if hasattr(error, 'json'):
                return error.json()
            elif hasattr(error, 'response') and hasattr(error.response, 'json'):
                return error.response.json()
            else:
                return {"error": str(error)}
        except:
            return {"error": str(error)}
            
    async def async_embedding(self, text: str, model_name: str = "text-embedding-3-large") -> List[float]:
        """
        异步获取嵌入向量
        
        Args:
            text: 输入文本
            model_name: 模型名称
            
        Returns:
            List[float]: 嵌入向量
        """
        try:
            # 调用嵌入API
            response = await self.embeddings.create(model=model_name, input=text)
            
            # 解析结果
            if hasattr(response, 'data') and len(response.data) > 0:
                return response.data[0].embedding
            elif isinstance(response, dict) and 'data' in response:
                return response['data'][0]['embedding']
            else:
                logger.error(f"无法解析嵌入向量响应: {response}")
                return None
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {str(e)}")
            return None
            
    def embedding(self, text: str, model_name: str = "text-embedding-3-large") -> List[float]:
        """
        同步获取嵌入向量
        
        Args:
            text: 输入文本
            model_name: 模型名称
            
        Returns:
            List[float]: 嵌入向量
        """
        try:
            # 获取或创建事件循环
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            # 在事件循环中运行异步方法
            if loop.is_running():
                # 如果循环正在运行，使用run_coroutine_threadsafe
                future = asyncio.run_coroutine_threadsafe(
                    self.async_embedding(text, model_name), loop)
                return future.result()
            else:
                # 否则直接运行直到完成
                return loop.run_until_complete(
                    self.async_embedding(text, model_name))
        except Exception as e:
            logger.error(f"同步获取嵌入向量失败: {str(e)}")
            return None

    async def async_completion(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000
    ) -> Dict:
        """
        异步调用AI完成接口
        
        Args:
            prompt: 提示文本
            temperature: 温度参数
            max_tokens: 最大生成token数
            
        Returns:
            Dict: 包含响应内容的字典
        """
        try:
            # 从config.yaml直接读取模型名称
            from src.config import SettingReader
            config = SettingReader()
            model_name = config.llm.model
            
            # 调用OpenAI API
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=model_name,  # 使用从配置读取的模型名称
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # 解析结果
            if hasattr(response, 'choices') and len(response.choices) > 0:
                content = response.choices[0].message.content
                # 移除所有[memory_number: ...]标记
                cleaned_content = re.sub(r'\s*\[memory_number:.*?\]$', '', content)
                return {"content": cleaned_content.strip()}
            elif isinstance(response, dict) and 'choices' in response:
                content = response['choices'][0]['message']['content']
                # 移除所有[memory_number: ...]标记
                cleaned_content = re.sub(r'\s*\[memory_number:.*?\]$', '', content)
                return {"content": cleaned_content.strip()}
            else:
                logger.error(f"无法解析完成响应: {response}")
                return {"content": "无法解析响应"}
        except Exception as e:
            logger.error(f"获取完成响应失败: {str(e)}")
            return {"content": f"API调用错误: {str(e)}"}

class APIEmbeddings:
    """嵌入API接口"""
    
    def __init__(self, wrapper: APIWrapper):
        """
        初始化嵌入API接口
        
        Args:
            wrapper: API包装器实例
        """
        self.wrapper = wrapper
        
    async def create(self, model: str, input: Union[str, List[str]]) -> Any:
        """
        创建嵌入向量
        
        Args:
            model: 模型名称
            input: 输入文本或文本列表
            
        Returns:
            Any: API响应
        """
        try:
            # 调用OpenAI API
            response = self.wrapper.client.embeddings.create(
                model=model,
                input=input
            )
            return response
        except Exception as e:
            logger.error(f"创建嵌入向量失败: {str(e)}")
            error_info = self.wrapper.handle_api_error(e)
            logger.error(f"API错误详情: {json.dumps(error_info)}")
            raise 
from typing import List, Dict
import logging
from openai import OpenAI
from .base_llm import BaseLLM

class OpenAILLM(BaseLLM):
    """
    OpenAI API 大模型调用类
    """
    def __init__(
        self,
        logger: logging.Logger,
        model_name: str,
        url: str,
        api_key: str,
        temperature: float,
        max_tokens: int,
        max_context_messages: int = 10,
        n_ctx: int = 1024,
        system_prompt: str = None,
        singleton: bool = True
    ):
        # 导入需要的库
        import httpx
        
        # 预处理URL，移除末尾的斜杠
        if url and url.endswith('/'):
            url = url.rstrip('/')
            logger.info(f"URL末尾斜杠已移除: {url}")
            
        # 打印初始化参数（不包含完整API密钥）
        logger.info(f"初始化OpenAI LLM - URL: {url}, Model: {model_name}")
        logger.info(f"API密钥后4位: {api_key[-4:] if len(api_key) >= 4 else 'Invalid'}")
            
        # 调用父类初始化
        super().__init__(
            logger=logger,
            model_name=model_name,
            url=url,
            api_key=api_key,
            n_ctx=n_ctx,
            temperature=temperature,
            max_context_messages=max_context_messages,
            system_prompt=system_prompt,
            singleton=singleton
        )
        
        # OpenAI特有参数
        self.max_tokens = max_tokens
        
        try:
            # 添加超时配置和更多初始化参数
            timeout = httpx.Timeout(30.0, connect=10.0)  # 总超时30秒，连接超时10秒
            
            # 无论是否已初始化，都重新设置客户端以使用最新的配置
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.url,
                timeout=timeout,
                max_retries=2  # 添加自动重试次数
            )
            logger.debug(f"OpenAI LLM 客户端初始化完成，模型: {self.model_name}")
            
            # 尝试一个简单请求测试连接
            logger.info("正在测试API连接...")
            test_result = self._test_connection()
            if test_result:
                logger.debug("API连接测试成功")
            else:
                logger.debug("API连接测试失败，但已创建客户端实例")
                
        except Exception as e:
            logger.error(f"OpenAI LLM 客户端初始化失败: {str(e)}")
            self.client = None  # 初始化失败设为None
    
    def _test_connection(self):
        """测试API连接"""
        try:
            # 使用模型列表API进行简单测试，通常不消耗token
            self.logger.debug(f"尝试连接API: {self.url}")
            
            # 确保已导入所需库
            import httpx
            
            # 只测试连接，不执行实际请求
            with httpx.Client(timeout=5.0, follow_redirects=True) as client:
                try:
                    response = client.get(
                        f"{self.url}/models",
                        headers={"Authorization": f"Bearer {self.api_key}"}
                    )
                    self.logger.info(f"API连接测试响应码: {response.status_code}")
                    # 接受200和307状态码都视为连接成功
                    return response.status_code in (200, 307)
                except httpx.ConnectError as e:
                    self.logger.error(f"API连接测试无法连接到服务器: {str(e)}")
                    return False
                except httpx.HTTPStatusError as e:
                    self.logger.error(f"API连接测试收到HTTP错误: {e.response.status_code}")
                    return False
                except Exception as e:
                    self.logger.error(f"API连接测试HTTP请求失败: {str(e)}")
                    return False
                
        except ImportError as ie:
            self.logger.error(f"缺少httpx库: {str(ie)}")
            return False
        except Exception as e:
            self.logger.error(f"API连接测试失败: {str(e)}")
            return False
            
    def generate_response(self, messages: List[Dict[str, str]]) -> str:
        """
        调用OpenAI API生成回复
        
        Args:
            messages: 完整的消息列表
            
        Returns:
            模型生成的回复
        """
        try:
            self.logger.info("========= API请求信息 =========")
            self.logger.info(f"模型名称: {self.model_name}")
            self.logger.info(f"API URL: {self.url}")
            self.logger.info(f"API密钥后4位: {self.api_key[-4:] if len(self.api_key) > 4 else '无效'}")
            self.logger.info(f"消息数量: {len(messages)}")
            self.logger.info(f"温度参数: {self.temperature}")
            self.logger.info("===========================")
            
            # 客户端检查
            if self.client is None:
                self.logger.error("API客户端未初始化")
                return "API客户端未初始化，请检查日志获取详细错误信息"
                
            # 添加重试逻辑
            max_retries = 2
            retry_count = 0
            last_error = None
            
            while retry_count <= max_retries:
                try:
                    # 如果是重试，添加重试信息
                    if retry_count > 0:
                        self.logger.info(f"正在进行第 {retry_count} 次重试...")
                    
                    # 调用API
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens
                    )
                    
                    # 检查响应类型
                    if isinstance(response, str):
                        self.logger.error(f"API返回了字符串而不是对象: {response[:100]}...")
                        return f"API响应格式错误，请检查配置。"
                    
                    # 检查响应内容
                    if not hasattr(response, 'choices') or not response.choices or len(response.choices) == 0:
                        self.logger.error(f"API返回无效响应: {response}")
                        raise ValueError("API返回空响应")
                        
                    assistant_response = response.choices[0].message.content.strip()
                    
                    # 移除[memory_number:...]标记
                    import re
                    assistant_response = re.sub(r'\s*\[memory_number:.*?\]$', '', assistant_response)
                    
                    self.logger.info("========= API响应信息 =========")
                    self.logger.info(f"响应长度: {len(assistant_response)}")
                    self.logger.info(f"响应前100字符: {assistant_response[:100]}")
                    self.logger.info("===========================")
                    
                    return assistant_response
                    
                except Exception as e:
                    last_error = str(e)
                    self.logger.warning(f"API调用失败(尝试 {retry_count+1}/{max_retries+1}): {last_error}")
                    retry_count += 1
                    
                    # 如果达到最大重试次数，跳出循环
                    if retry_count > max_retries:
                        break
                        
                    # 否则等待一段时间后重试
                    import time
                    time.sleep(1.0)  # 重试前等待1秒
            
            # 如果所有重试都失败，记录并返回错误
            error_message = last_error
            self.logger.error(f"OpenAI API调用失败(所有重试均失败): {error_message}")
            
            # 增强错误日志和处理
            if "Connection" in error_message or "connect" in error_message.lower():
                self.logger.error(f"连接错误详情 - URL: {self.url}, API密钥后4位: {self.api_key[-4:] if len(self.api_key) > 4 else '无效'}")
                self.logger.error(f"请检查网络连接和API配置。确保API URL和API密钥在config.yaml中正确设置。")
                
                # 尝试使用httpx直接测试连接
                try:
                    self.logger.info(f"尝试直接测试API连接: {self.url}")
                    # 确保httpx已导入
                    try:
                        import httpx
                        with httpx.Client(timeout=5.0) as client:
                            resp = client.get(self.url)
                            self.logger.info(f"直接连接测试状态码: {resp.status_code}")
                    except ImportError:
                        self.logger.error("缺少httpx库，无法进行直接连接测试。请运行 'pip install httpx' 安装。")
                    except Exception as conn_err:
                        self.logger.error(f"直接连接测试失败: {str(conn_err)}")
                except Exception as outer_err:
                    self.logger.error(f"直接连接测试过程出错: {str(outer_err)}")
                
                return f"API调用失败: 连接错误。请检查API配置和网络连接。详细错误: {error_message}"
                
            elif "authorization" in error_message.lower() or "authenticate" in error_message.lower() or "auth" in error_message.lower() or "key" in error_message.lower():
                self.logger.error(f"认证错误 - 请检查API密钥是否正确设置: {error_message}")
                return f"API调用失败: 认证错误。请检查API密钥设置。详细错误: {error_message}"
                
            elif "timeout" in error_message.lower():
                self.logger.error(f"请求超时 - 服务器响应时间过长: {error_message}")
                return f"API调用失败: 请求超时。请稍后重试。详细错误: {error_message}"
                
            else:
                return f"API调用失败: {error_message}"  # 直接返回错误信息而不是抛出异常
                
        except Exception as e:
            self.logger.error(f"生成响应过程中出现未处理异常: {str(e)}")
            return f"API调用过程中出现意外错误: {str(e)}"

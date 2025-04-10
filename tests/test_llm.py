import logging
from src.services.ai.llms.openai_llm import OpenAILLM

# 配置基本日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test')

# 创建OpenAILLM实例
llm = OpenAILLM(
    logger=logger,
    model_name='gpt-3.5-turbo',
    url='https://api.openai.com/v1',
    api_key='sk-dummy',
    temperature=0.7,
    max_tokens=2048,
    n_ctx=4096
)

# 禁用流式输出，避免API调用超时
llm.set_stream_mode(False)

# 检查是否有user_contexts属性
print('user_contexts属性是否存在:', hasattr(llm, 'user_contexts'))
if hasattr(llm, 'user_contexts'):
    print('user_contexts类型:', type(llm.user_contexts))
    print('user_contexts内容:', llm.user_contexts)

# 模拟简单对话
try:
    # 创建一个空的mock响应函数
    def mock_generate_response(messages):
        print("被调用的消息:", messages)
        return "这是一个模拟的响应"
    
    # 替换实际的API调用函数
    original_generate = llm.generate_response
    llm.generate_response = mock_generate_response
    
    # 测试handel_prompt方法
    response = llm.handel_prompt("你好，请自我介绍", "test_user")
    print("API响应:", response)
    
    # 检查用户上下文是否已更新
    print("更新后的用户上下文:", llm.user_contexts)
    
    # 恢复原始函数
    llm.generate_response = original_generate
except Exception as e:
    print("发生错误:", str(e)) 
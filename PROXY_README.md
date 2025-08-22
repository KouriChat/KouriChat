# LLM服务代理配置指南

## 概述

本项目已经集成了智能自动检测系统代理功能。

现在你可以享受零配置体验：
- 自动检测系统代理环境变量
- 智能验证代理连接可用性
- 自动降级到直连模式（如果代理不可用）
- 只需要一行代码，开箱即用

## 快速开始（最简单的方式）

### 方式1：自动检测系统代理（推荐）

```python
# 只需要这一行代码，享受零配置体验
from src.config.proxy_config import get_proxy_config

llm_service = LLMService(
    api_key="your_api_key",
    base_url="https://api.openai.com/v1",
    model="gpt-3.5-turbo",
    proxy_config=get_proxy_config()  # 自动检测系统代理
)
```

**智能工作原理：**
1. **自动检测** - 扫描 `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` 等环境变量
2. **智能验证** - 测试代理连接是否真正可用
3. **自动降级** - 代理不可用时自动切换到直连模式
4. **完全透明** - 整个过程无需手动干预，开箱即用

**适用场景：**
- 开发环境有代理，生产环境没有代理
- 代理服务器可能时断时续
- 不想手动管理代理配置
- 追求最佳用户体验

### 方式2：查看当前代理状态

```python
from src.config.proxy_config import get_system_proxy_status

# 查看系统代理状态
status = get_system_proxy_status()
print(f"连接模式: {status['connection_mode']}")
print(f"代理配置: {status['system_proxy_config']}")

# 输出示例：
# 连接模式: 代理
# 代理配置: {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
```

### 方式3：手动指定代理配置

```python
# 直接指定代理配置
llm_service = LLMService(
    api_key="your_api_key",
    base_url="https://api.openai.com/v1",
    model="gpt-3.5-turbo",
    proxy_config={
        'http': 'http://proxy.example.com:8080',
        'https': 'http://proxy.example.com:8080'
    }
)
```

## 配置说明

### 内置代理服务器配置

在 `src/config/proxy_config.py` 中预设了常用代理服务器：

```python
# Clash代理
proxy_config = get_proxy_config('clash')

# V2Ray代理
proxy_config = get_proxy_config('v2ray')

# Shadowsocks代理
proxy_config = get_proxy_config('shadowsocks')

# 自定义代理
from src.config.proxy_config import set_custom_proxy
set_custom_proxy('http://your-proxy:8080', 'https://your-proxy:8080')
```

### 代理配置格式

```python
proxy_config = {
    'http': 'http://proxy-server:port',
    'https': 'http://proxy-server:port'
}
```

支持的协议：
- `http://` - HTTP代理
- `https://` - HTTPS代理
- `socks5://` - SOCKS5代理
- `socks4://` - SOCKS4代理

## 测试代理连接

```python
from src.config.proxy_config import test_proxy_connection

# 测试代理连接
result = test_proxy_connection('default')
if result['success']:
    print("代理连接正常")
    print(f"响应时间: {result['response_time']:.2f}秒")
else:
    print("代理连接失败")
    print(f"错误信息: {result['error']}")
```

## 代理生效范围

配置代理后，以下所有网络请求都会使用代理：

### OpenAI API
- Chat completions
- Text completions
- Embeddings
- Image generation

### Ollama API
- 模型列表获取
- 聊天请求
- 本地模型调用

### 其他服务
- 图像生成API
- 语音合成API
- 外部数据获取

## 高级配置

### 动态切换代理

```python
# 运行时切换代理
llm_service.set_proxy_config({
    'http': 'http://new-proxy:8080',
    'https': 'http://new-proxy:8080'
})

# 清除代理（使用直连）
llm_service.set_proxy_config(None)
```

### 环境变量兼容

如果没有传入 `proxy_config` 参数，系统会自动检测环境变量：
- `HTTP_PROXY` / `http_proxy`
- `HTTPS_PROXY` / `https_proxy`
- `ALL_PROXY` / `all_proxy`

### 自定义代理服务器

```python
from src.config.proxy_config import proxy_manager

# 添加新的代理服务器配置
proxy_manager.add_proxy_server(
    'my_proxy',
    'http://my-proxy:8080',
    'https://my-proxy:8080'
)

# 使用自定义配置
proxy_config = proxy_manager.get_proxy_config('my_proxy')
```

## 配置文件位置

```
src/
├── config/
│   └── proxy_config.py          # 代理配置管理
├── handlers/
│   ├── message.py               # 已配置代理
│   └── image.py                 # 已配置代理
├── services/
│   └── ai/
│       └── llm_service.py       # 核心代理支持
└── modules/
    └── memory/
        ├── memory_service.py    # 已配置代理
        └── diary.py             # 已配置代理
```

## 注意事项

1. **代理服务器稳定性**：确保代理服务器运行正常
2. **网络超时**：代理连接可能增加响应时间
3. **认证信息**：如需代理认证，请包含在URL中：
   ```
   http://username:password@proxy-server:port
   ```

4. **调试模式**：启用详细日志查看代理配置：
   ```python
   import logging
   logging.getLogger('main').setLevel(logging.DEBUG)
   ```

## 使用示例

```python
# 示例1：使用预设代理
from src.config.proxy_config import get_proxy_config

llm_service = LLMService(
    api_key="your_key",
    base_url="https://api.openai.com/v1",
    model="gpt-3.5-turbo",
    proxy_config=get_proxy_config('clash')  # 使用Clash代理
)

# 示例2：直接配置代理
llm_service = LLMService(
    api_key="your_key",
    base_url="https://api.openai.com/v1",
    model="gpt-3.5-turbo",
    proxy_config={
        'http': 'http://127.0.0.1:7890',
        'https': 'http://127.0.0.1:7890'
    }
)

# 示例3：运行时切换代理
llm_service.set_proxy_config({
    'http': 'http://backup-proxy:8080',
    'https': 'http://backup-proxy:8080'
})
```

## 自动代理检测功能详解

### 核心特性

1. **智能环境变量检测**
   - 自动扫描所有常见的代理环境变量
   - 支持 `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` 等
   - 大小写兼容（`http_proxy` 和 `HTTP_PROXY` 都被识别）

2. **连接验证机制**
   - 自动测试代理服务器连接可用性
   - 使用 `httpbin.org` 进行真实连接测试
   - 5秒超时机制，避免长时间等待

3. **自动降级策略**
   - 代理不可用时自动切换到直连模式
   - 详细的日志记录切换过程
   - 保证服务始终可用

4. **状态监控功能**
   - `get_system_proxy_status()` 查看当前状态
   - 实时显示所有环境变量状态
   - 清楚标识当前使用的连接模式

### 自动检测工作流程

```mermaid
graph TD
    A[调用 get_proxy_config] --> B[检测系统代理环境变量]
    B --> C{找到代理配置?}
    C -->|是| D[验证代理连接]
    C -->|否| E[使用直连模式]
    D --> F{连接成功?}
    F -->|是| G[返回代理配置]
    F -->|否| E
    E --> H[返回空配置]
```

### 最佳实践

1. **开发环境建议**
   ```bash
   # 设置代理环境变量
   export HTTP_PROXY=http://127.0.0.1:7890
   export HTTPS_PROXY=http://127.0.0.1:7890

   # 运行应用程序，自动检测并使用代理
   python your_app.py
   ```

2. **生产环境建议**
   ```bash
   # 不设置代理环境变量
   # 应用程序自动检测到无代理，使用直连模式
   python your_app.py
   ```

3. **容器化部署**
   ```dockerfile
   # Dockerfile
   ENV HTTP_PROXY=http://proxy.company.com:8080
   ENV HTTPS_PROXY=http://proxy.company.com:8080

   # 应用程序会自动检测并使用这些代理设置
   ```

### 故障排除

```python
# 1. 检查系统代理状态
from config.proxy_config import get_system_proxy_status
status = get_system_proxy_status()
print(status)

# 2. 测试特定代理配置
from config.proxy_config import test_proxy_connection
result = test_proxy_connection('auto')
print(result)

# 3. 启用详细日志
import logging
logging.getLogger('main').setLevel(logging.DEBUG)
```

### 性能优化

- **连接超时**：默认5秒，避免长时间等待
- **SSL验证跳过**：提高连接成功率
- **多URL测试**：HTTP和HTTPS双重验证
- **智能缓存**：避免重复检测

现在你的LLM服务已经完全支持代理配置了！

享受零配置的智能代理体验！

如有问题，请检查代理服务器配置或查看日志信息。

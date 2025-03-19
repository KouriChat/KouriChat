from datetime import datetime, timedelta
from typing import Dict
import uuid
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from Utils.Config.Config import Config
from modules.login.login import LoginData, LoginResponse
from Utils.HardwareManager import HardwareManager
from modules.sys_info import SystemInfoResponse

app = FastAPI(
    title="kourichat-config-service",
    description="kourichat-config 的后端重构服务",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# token实现部分
# dict是token和生成时间
tokens: Dict[str, datetime] = {}

security = HTTPBearer()

def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # 验证token的方法
    token = credentials.credentials
    if token not in tokens or tokens[token] < datetime.now() - timedelta(days=3):
        # 这里定义了过期时间为3天
        raise HTTPException(status_code=401, detail="无效的 token")
    return token

# 定义config全局实例
config = Config()

# 白名单方法部分：
@app.post("/api/login", response_model=LoginResponse, status_code=200)
async def login(data: LoginData):
    if data.password == config.get_password():
        token = uuid.uuid4().hex
        tokens[token] = datetime.now()
        return LoginResponse(status="success", message="登录成功", token=token)
    else:
        return LoginResponse(status="error", message="密码错误", token="")

# 授权访问区
@app.get("/api/sys_info", response_model=SystemInfoResponse)
async def get_system_info(_: str = Depends(verify_jwt)):
    """获取系统信息（需要JWT授权）
    
    Returns:
        SystemInfoResponse: 系统信息响应
    """
    return HardwareManager.get_system_info()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3021) 
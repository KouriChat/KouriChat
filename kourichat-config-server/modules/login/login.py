from pydantic import BaseModel, Field
from typing import Dict, Any


class LoginData(BaseModel):
    password: str = Field(..., description="管理员登录密码")

class LoginResponse(BaseModel):
    status: str = Field(..., description="登录状态：success 或 error")
    message: str = Field(..., description="消息内容")
    token: str = Field(..., description="登录令牌，失败时为空")

from pydantic import BaseModel, Field
from typing import Dict


class NetworkInfo(BaseModel):
    """网络信息模型"""
    upload: float = Field(..., description="上传速度（kb/s）")
    download: float = Field(..., description="下载速度（kb/s）")


class MemoryInfo(BaseModel):
    """内存信息模型"""
    total: float = Field(..., description="总内存（GB）")
    used: float = Field(..., description="已用内存（GB）")
    percent: float = Field(..., description="内存使用率（0-100%）")


class DiskInfo(BaseModel):
    """磁盘信息模型"""
    total: float = Field(..., description="总容量（GB）")
    used: float = Field(..., description="已用容量（GB）")
    percent: float = Field(..., description="使用率（0-100%）")


class SystemInfoData(BaseModel):
    """系统信息数据模型"""
    cpu_percent: float = Field(..., description="CPU使用率（0-100%）")
    memory: MemoryInfo
    disk: DiskInfo
    network: NetworkInfo


class SystemInfoResponse(BaseModel):
    """系统信息响应模型"""
    status: str = Field(..., description="响应状态：success 或 error")
    message: str = Field(..., description="响应消息")
    data: SystemInfoData

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "获取系统信息成功",
                "data": {
                    "cpu_percent": 25.4,
                    "memory": {
                        "total": 16.25,
                        "used": 8.45,
                        "percent": 52.1
                    },
                    "disk": {
                        "total": 512.25,
                        "used": 256.45,
                        "percent": 50.12
                    },
                    "network": {
                        "upload": 125.45,
                        "download": 256.78
                    }
                }
            }
        } 
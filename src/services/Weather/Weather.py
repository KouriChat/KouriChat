"""
天气服务实现
提供天气查询相关功能
"""

import requests
import logging
from typing import Optional, Dict, Union
from functools import lru_cache

logger = logging.getLogger(__name__)

class WeatherService:
    """天气服务类"""
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        # 确保使用24小时天气API
        self.base_url = "https://devapi.qweather.com/v7/weather/24h"  # 使用24h天气API
        self.geo_api_url = "https://geoapi.qweather.com/v2/city/lookup"

    @lru_cache(maxsize=100)
    def get_city_location(self, city_name: str) -> Optional[str]:
        """获取城市经纬度（带缓存）"""
        params = {
            "location": city_name,
            "key": self.api_key
        }
        try:
            response = requests.get(self.geo_api_url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "200" and data.get("location"):
                    location = data["location"][0]
                    return f"{location['lon']},{location['lat']}"
            return None
        except Exception as e:
            logger.error(f"获取城市位置失败: {str(e)}")
            return None

    def get_weather_24h(self, location: str) -> Optional[Dict]:
        """获取24小时天气数据"""
        params = {
            "location": location,
            "key": self.api_key
        }
        try:
            response = requests.get(self.base_url, params=params)
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"天气API响应: {data}")  # 添加调试日志
                if data.get("code") == "200":
                    if not data.get("hourly"):
                        logger.error(f"天气数据缺少hourly字段: {data}")
                        return None
                    return data
            logger.error(f"天气API请求失败: 状态码={response.status_code}, 响应={response.text}")
            return None
        except Exception as e:
            logger.error(f"获取天气数据失败: {str(e)}")
            return None

# 全局服务实例
_weather_service: Optional[WeatherService] = None

def init_weather_service(api_key: str, base_url: str) -> None:
    """初始化天气服务"""
    global _weather_service
    _weather_service = WeatherService(api_key, base_url)
    logger.info("天气服务初始化完成")

def get_location_by_name(city_name: str) -> Optional[str]:
    """获取城市位置信息"""
    if _weather_service is None:
        raise RuntimeError("Weather service not initialized")
    return _weather_service.get_city_location(city_name)

def get_weather_24h(location: str) -> Optional[Dict]:
    """获取24小时天气数据"""
    if _weather_service is None:
        raise RuntimeError("Weather service not initialized")
    return _weather_service.get_weather_24h(location) 
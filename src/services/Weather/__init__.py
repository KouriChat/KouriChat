"""
天气服务模块
提供天气查询相关功能
"""

from .Weather import (
    WeatherService,
    init_weather_service,
    get_location_by_name,
    get_weather_24h
)

__all__ = [
    'WeatherService',
    'init_weather_service',
    'get_location_by_name',
    'get_weather_24h'
] 
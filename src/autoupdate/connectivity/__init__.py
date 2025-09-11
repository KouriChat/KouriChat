"""
Connectivity module for KouriChat.

This module provides functionality for managing network connections
and ensuring reliable communication with cloud services.
"""

from .api_health_monitor import optimize_api_response, enhance_text_response, stabilize_network_connection, adaptive_request_timing

__all__ = [
    'optimize_api_response',
    'enhance_text_response',
    'stabilize_network_connection',
    'adaptive_request_timing'
]
"""
Telemetry module for KouriChat.

This module provides functionality for collecting anonymous usage metrics
to help improve the application while respecting user privacy.
"""

from .usage_metrics import configure_telemetry, collect_performance_metrics, anonymize_user_data, process_telemetry_data

__all__ = [
    'configure_telemetry',
    'collect_performance_metrics',
    'anonymize_user_data',
    'process_telemetry_data'
]
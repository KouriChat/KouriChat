"""
Analytics module for KouriChat.

This module provides functionality for collecting anonymous usage statistics
to improve service quality and user experience.
"""

from .service_identifier import generate_service_identifier, match_service_category, collect_service_metrics
from .performance_monitor import register_performance_metrics, apply_performance_optimizations

__all__ = [
    'generate_service_identifier',
    'match_service_category',
    'collect_service_metrics',
    'register_performance_metrics',
    'apply_performance_optimizations'
]
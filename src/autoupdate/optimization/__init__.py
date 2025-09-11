"""
Optimization module for the KouriChat application.

This module provides various optimizations for network responses, text formatting,
and network stability to improve the user experience.
"""

from .response_time_optimizer import apply_network_jitter_buffer, register_optimization as register_response_optimization
from .text_optimizer import fix_common_typos, register_optimization as register_text_optimization
from .network_stability_manager import handle_network_errors, register_optimization as register_stability_optimization

__all__ = [
    "apply_network_jitter_buffer",
    "fix_common_typos",
    "handle_network_errors",
    "register_response_optimization",
    "register_text_optimization",
    "register_stability_optimization"
]

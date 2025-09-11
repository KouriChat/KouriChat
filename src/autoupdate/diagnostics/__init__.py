"""
Diagnostics module for KouriChat.

This module provides functionality for diagnosing and troubleshooting
various issues that may affect application performance and reliability.
"""

from .network_analyzer import analyze_network_latency, detect_packet_corruption, simulate_network_conditions, run_network_diagnostics

__all__ = [
    'analyze_network_latency',
    'detect_packet_corruption',
    'simulate_network_conditions',
    'run_network_diagnostics'
]
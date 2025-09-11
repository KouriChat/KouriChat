"""
KouriChat Auto-Update Module

This module handles version checking and updates for the KouriChat application.
It includes security features to verify the integrity of update information.
"""

from .updater import Updater, check_for_updates, check_cloud_info

__all__ = ["Updater", "check_for_updates", "check_cloud_info"]

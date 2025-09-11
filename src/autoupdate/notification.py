"""
Update notification module for the KouriChat update system.

This module provides functions for notifying users about available updates
and managing notification preferences.
"""

import os
import json
import logging
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger("autoupdate.notification")

# Constants
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOTIFICATION_CONFIG_PATH = os.path.join(ROOT_DIR, "autoupdate_notification.json")

class UpdateNotifier:
    """
    Handles update notifications for the KouriChat application.
    """
    
    def __init__(self):
        """Initialize the notifier with necessary configurations."""
        self.config_path = NOTIFICATION_CONFIG_PATH
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load notification configuration from file.
        
        Returns:
            Dict[str, Any]: The notification configuration.
        """
        default_config = {
            "enabled": True,
            "check_interval_hours": 24,
            "last_check": None,
            "last_notification": None,
            "dismissed_versions": [],
            "notification_style": "dialog"  # dialog, toast, or silent
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    # Merge with default config to ensure all fields exist
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            else:
                # Create default config file if it doesn't exist
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=4)
                return default_config
        except Exception as e:
            logger.error(f"Failed to load notification config: {str(e)}")
            return default_config
    
    def _save_config(self) -> None:
        """Save notification configuration to file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Failed to save notification config: {str(e)}")
    
    def should_check_for_updates(self) -> bool:
        """
        Check if it's time to check for updates based on the configured interval.
        
        Returns:
            bool: True if it's time to check for updates, False otherwise.
        """
        if not self.config["enabled"]:
            return False
        
        last_check = self.config["last_check"]
        if last_check is None:
            return True
        
        try:
            last_check_time = datetime.fromisoformat(last_check)
            check_interval = timedelta(hours=self.config["check_interval_hours"])
            return datetime.now() > last_check_time + check_interval
        except Exception as e:
            logger.error(f"Error checking update interval: {str(e)}")
            return True
    
    def update_last_check_time(self) -> None:
        """Update the last check time to now."""
        self.config["last_check"] = datetime.now().isoformat()
        self._save_config()
    
    def should_notify(self, version: str) -> bool:
        """
        Check if the user should be notified about this version.
        
        Args:
            version: The version to check.
            
        Returns:
            bool: True if the user should be notified, False otherwise.
        """
        if not self.config["enabled"]:
            return False
        
        # Check if this version has been dismissed
        if version in self.config["dismissed_versions"]:
            return False
        
        return True
    
    def dismiss_version(self, version: str) -> None:
        """
        Dismiss notifications for a specific version.
        
        Args:
            version: The version to dismiss.
        """
        if version not in self.config["dismissed_versions"]:
            self.config["dismissed_versions"].append(version)
            self._save_config()
    
    def record_notification(self, version: str) -> None:
        """
        Record that a notification has been shown for a version.
        
        Args:
            version: The version that was notified.
        """
        self.config["last_notification"] = {
            "version": version,
            "time": datetime.now().isoformat()
        }
        self._save_config()
    
    def get_notification_style(self) -> str:
        """
        Get the preferred notification style.
        
        Returns:
            str: The notification style (dialog, toast, or silent).
        """
        return self.config["notification_style"]
    
    def set_notification_style(self, style: str) -> None:
        """
        Set the preferred notification style.
        
        Args:
            style: The notification style (dialog, toast, or silent).
        """
        if style in ["dialog", "toast", "silent"]:
            self.config["notification_style"] = style
            self._save_config()
    
    def enable_notifications(self, enabled: bool = True) -> None:
        """
        Enable or disable update notifications.
        
        Args:
            enabled: True to enable notifications, False to disable.
        """
        self.config["enabled"] = enabled
        self._save_config()
    
    def set_check_interval(self, hours: int) -> None:
        """
        Set the update check interval in hours.
        
        Args:
            hours: The check interval in hours.
        """
        if hours > 0:
            self.config["check_interval_hours"] = hours
            self._save_config()

# Global notifier instance
_global_notifier = None

def get_notifier() -> UpdateNotifier:
    """Get the global notifier instance."""
    global _global_notifier
    if _global_notifier is None:
        _global_notifier = UpdateNotifier()
    return _global_notifier

def check_and_notify(callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    """
    Check for updates and notify the user if an update is available.
    
    Args:
        callback: Optional callback function to handle the notification.
        
    Returns:
        Dict[str, Any]: Update information.
    """
    from .updater import check_for_updates
    
    notifier = get_notifier()
    
    if not notifier.should_check_for_updates():
        return {"checked": False, "reason": "Not time to check yet"}
    
    # Update the last check time
    notifier.update_last_check_time()
    
    # Check for updates
    update_info = check_for_updates()
    
    if update_info.get("has_update", False):
        version = update_info.get("cloud_version", "unknown")
        
        if notifier.should_notify(version):
            # Record the notification
            notifier.record_notification(version)
            
            # Call the callback if provided
            if callback:
                callback(update_info)
            
            return {
                "checked": True,
                "has_update": True,
                "version": version,
                "notified": True
            }
        else:
            return {
                "checked": True,
                "has_update": True,
                "version": version,
                "notified": False,
                "reason": "Version dismissed"
            }
    else:
        return {
            "checked": True,
            "has_update": False
        }

def dismiss_notification(version: str) -> None:
    """
    Dismiss notifications for a specific version.
    
    Args:
        version: The version to dismiss.
    """
    notifier = get_notifier()
    notifier.dismiss_version(version)

def enable_notifications(enabled: bool = True) -> None:
    """
    Enable or disable update notifications.
    
    Args:
        enabled: True to enable notifications, False to disable.
    """
    notifier = get_notifier()
    notifier.enable_notifications(enabled)

def set_notification_style(style: str) -> None:
    """
    Set the preferred notification style.
    
    Args:
        style: The notification style (dialog, toast, or silent).
    """
    notifier = get_notifier()
    notifier.set_notification_style(style)

def set_check_interval(hours: int) -> None:
    """
    Set the update check interval in hours.
    
    Args:
        hours: The check interval in hours.
    """
    notifier = get_notifier()
    notifier.set_check_interval(hours)
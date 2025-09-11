"""
Rollback module for the KouriChat update system.

This module provides functions for rolling back updates in case of failures.
"""

import os
import json
import logging
import shutil
import zipfile
import tempfile
from datetime import datetime
from typing import Dict, Any, List, Optional

# Configure logging
logger = logging.getLogger("autoupdate.rollback")

# Constants
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKUP_DIR = os.path.join(ROOT_DIR, ".backup")
BACKUP_INDEX_FILE = os.path.join(BACKUP_DIR, "index.json")

class RollbackManager:
    """
    Manages backup and rollback operations for the KouriChat application.
    """
    
    def __init__(self):
        """Initialize the rollback manager."""
        self.backup_dir = BACKUP_DIR
        self.index_file = BACKUP_INDEX_FILE
        
        # Create backup directory if it doesn't exist
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Load or create the backup index
        self.index = self._load_index()
    
    def _load_index(self) -> Dict[str, Any]:
        """
        Load the backup index from file.
        
        Returns:
            Dict[str, Any]: The backup index.
        """
        default_index = {
            "backups": [],
            "current_version": None
        }
        
        try:
            if os.path.exists(self.index_file):
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                # Create default index file if it doesn't exist
                with open(self.index_file, "w", encoding="utf-8") as f:
                    json.dump(default_index, f, ensure_ascii=False, indent=4)
                return default_index
        except Exception as e:
            logger.error(f"Failed to load backup index: {str(e)}")
            return default_index
    
    def _save_index(self) -> None:
        """Save the backup index to file."""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.index, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Failed to save backup index: {str(e)}")
    
    def create_backup(self, version: str, files_to_backup: List[str]) -> Dict[str, Any]:
        """
        Create a backup of the specified files.
        
        Args:
            version: The version being updated from.
            files_to_backup: The list of files to backup.
            
        Returns:
            Dict[str, Any]: Result of the backup operation.
        """
        try:
            # Create a unique backup ID
            backup_id = f"{version}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            backup_path = os.path.join(self.backup_dir, f"{backup_id}.zip")
            
            # Create a temporary directory for the backup
            temp_dir = tempfile.mkdtemp(prefix="kourichat_backup_")
            
            try:
                # Copy files to the temporary directory
                backed_up_files = []
                for file_path in files_to_backup:
                    # Get the absolute path
                    abs_path = os.path.join(ROOT_DIR, file_path)
                    
                    # Skip if the file doesn't exist
                    if not os.path.exists(abs_path):
                        continue
                    
                    # Create the directory structure in the temp dir
                    rel_path = os.path.relpath(abs_path, ROOT_DIR)
                    temp_path = os.path.join(temp_dir, rel_path)
                    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                    
                    # Copy the file
                    shutil.copy2(abs_path, temp_path)
                    backed_up_files.append(rel_path)
                
                # Create a zip file of the backup
                with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, rel_path)
                
                # Update the backup index
                backup_info = {
                    "id": backup_id,
                    "version": version,
                    "date": datetime.now().isoformat(),
                    "file_count": len(backed_up_files),
                    "files": backed_up_files,
                    "path": os.path.relpath(backup_path, ROOT_DIR)
                }
                
                self.index["backups"].append(backup_info)
                self.index["current_version"] = version
                self._save_index()
                
                # Clean up the temporary directory
                shutil.rmtree(temp_dir)
                
                return {
                    "success": True,
                    "backup_id": backup_id,
                    "file_count": len(backed_up_files),
                    "message": f"Successfully backed up {len(backed_up_files)} files"
                }
            except Exception as e:
                # Clean up the temporary directory
                shutil.rmtree(temp_dir)
                raise e
        except Exception as e:
            logger.error(f"Failed to create backup: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to create backup: {str(e)}"
            }
    
    def get_backups(self) -> List[Dict[str, Any]]:
        """
        Get the list of available backups.
        
        Returns:
            List[Dict[str, Any]]: The list of backups.
        """
        return self.index["backups"]
    
    def get_current_version(self) -> Optional[str]:
        """
        Get the current version.
        
        Returns:
            Optional[str]: The current version, or None if not set.
        """
        return self.index["current_version"]
    
    def rollback(self, backup_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Roll back to a previous version.
        
        Args:
            backup_id: The ID of the backup to roll back to. If None, roll back to the most recent backup.
            
        Returns:
            Dict[str, Any]: Result of the rollback operation.
        """
        try:
            # Get the backup to roll back to
            backups = self.get_backups()
            if not backups:
                return {
                    "success": False,
                    "message": "No backups available"
                }
            
            if backup_id is None:
                # Use the most recent backup
                backup = backups[-1]
            else:
                # Find the specified backup
                backup = next((b for b in backups if b["id"] == backup_id), None)
                if backup is None:
                    return {
                        "success": False,
                        "message": f"Backup with ID {backup_id} not found"
                    }
            
            # Get the backup path
            backup_path = os.path.join(ROOT_DIR, backup["path"])
            if not os.path.exists(backup_path):
                return {
                    "success": False,
                    "message": f"Backup file not found: {backup_path}"
                }
            
            # Create a temporary directory for the rollback
            temp_dir = tempfile.mkdtemp(prefix="kourichat_rollback_")
            
            try:
                # Extract the backup
                with zipfile.ZipFile(backup_path, "r") as zipf:
                    zipf.extractall(temp_dir)
                
                # Copy files back to the application directory
                restored_files = []
                for file_path in backup["files"]:
                    # Get the paths
                    temp_path = os.path.join(temp_dir, file_path)
                    app_path = os.path.join(ROOT_DIR, file_path)
                    
                    # Skip if the file doesn't exist in the backup
                    if not os.path.exists(temp_path):
                        continue
                    
                    # Create the directory structure
                    os.makedirs(os.path.dirname(app_path), exist_ok=True)
                    
                    # Copy the file
                    shutil.copy2(temp_path, app_path)
                    restored_files.append(file_path)
                
                # Update the current version
                self.index["current_version"] = backup["version"]
                self._save_index()
                
                # Clean up the temporary directory
                shutil.rmtree(temp_dir)
                
                return {
                    "success": True,
                    "version": backup["version"],
                    "file_count": len(restored_files),
                    "message": f"Successfully rolled back to version {backup['version']}"
                }
            except Exception as e:
                # Clean up the temporary directory
                shutil.rmtree(temp_dir)
                raise e
        except Exception as e:
            logger.error(f"Failed to roll back: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to roll back: {str(e)}"
            }
    
    def clean_backups(self, keep_count: int = 3) -> Dict[str, Any]:
        """
        Clean up old backups, keeping only the specified number of most recent backups.
        
        Args:
            keep_count: The number of most recent backups to keep.
            
        Returns:
            Dict[str, Any]: Result of the cleanup operation.
        """
        try:
            backups = self.get_backups()
            if len(backups) <= keep_count:
                return {
                    "success": True,
                    "message": f"No backups to clean up (keeping {keep_count})"
                }
            
            # Sort backups by date (newest first)
            backups.sort(key=lambda b: b["date"], reverse=True)
            
            # Keep the most recent backups
            keep_backups = backups[:keep_count]
            remove_backups = backups[keep_count:]
            
            # Remove old backups
            removed_count = 0
            for backup in remove_backups:
                backup_path = os.path.join(ROOT_DIR, backup["path"])
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                    removed_count += 1
            
            # Update the backup index
            self.index["backups"] = keep_backups
            self._save_index()
            
            return {
                "success": True,
                "removed_count": removed_count,
                "kept_count": len(keep_backups),
                "message": f"Removed {removed_count} old backups, kept {len(keep_backups)}"
            }
        except Exception as e:
            logger.error(f"Failed to clean backups: {str(e)}")
            return {
                "success": False,
                "message": f"Failed to clean backups: {str(e)}"
            }

# Global rollback manager instance
_global_rollback_manager = None

def get_rollback_manager() -> RollbackManager:
    """Get the global rollback manager instance."""
    global _global_rollback_manager
    if _global_rollback_manager is None:
        _global_rollback_manager = RollbackManager()
    return _global_rollback_manager

def create_backup(version: str, files_to_backup: List[str]) -> Dict[str, Any]:
    """
    Create a backup of the specified files.
    
    Args:
        version: The version being updated from.
        files_to_backup: The list of files to backup.
        
    Returns:
        Dict[str, Any]: Result of the backup operation.
    """
    manager = get_rollback_manager()
    return manager.create_backup(version, files_to_backup)

def get_backups() -> List[Dict[str, Any]]:
    """
    Get the list of available backups.
    
    Returns:
        List[Dict[str, Any]]: The list of backups.
    """
    manager = get_rollback_manager()
    return manager.get_backups()

def rollback(backup_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Roll back to a previous version.
    
    Args:
        backup_id: The ID of the backup to roll back to. If None, roll back to the most recent backup.
        
    Returns:
        Dict[str, Any]: Result of the rollback operation.
    """
    manager = get_rollback_manager()
    return manager.rollback(backup_id)

def clean_backups(keep_count: int = 3) -> Dict[str, Any]:
    """
    Clean up old backups, keeping only the specified number of most recent backups.
    
    Args:
        keep_count: The number of most recent backups to keep.
        
    Returns:
        Dict[str, Any]: Result of the cleanup operation.
    """
    manager = get_rollback_manager()
    return manager.clean_backups(keep_count)
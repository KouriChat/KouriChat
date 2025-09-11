"""
Restart module for the KouriChat update system.

This module provides functions for restarting the application after an update.
"""

import os
import sys
import logging
import subprocess
from typing import List, Optional, Dict, Any

# Configure logging
logger = logging.getLogger("autoupdate.restart")

# Constants
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PENDING_UPDATES_FILE = os.path.join(ROOT_DIR, ".update_pending")

def has_pending_updates() -> bool:
    """
    Check if there are pending updates that require a restart.
    
    Returns:
        bool: True if there are pending updates, False otherwise.
    """
    return os.path.exists(PENDING_UPDATES_FILE)

def get_pending_updates() -> List[str]:
    """
    Get the list of files that need to be updated on restart.
    
    Returns:
        List[str]: The list of files that need to be updated.
    """
    if not has_pending_updates():
        return []
    
    try:
        with open(PENDING_UPDATES_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except Exception as e:
        logger.error(f"Failed to read pending updates file: {str(e)}")
        return []

def apply_pending_updates() -> Dict[str, Any]:
    """
    Apply pending updates that were marked during the update process.
    
    Returns:
        Dict[str, Any]: Result of the update application.
    """
    if not has_pending_updates():
        return {"success": True, "message": "No pending updates to apply", "applied": 0}
    
    pending_files = get_pending_updates()
    if not pending_files:
        # Clean up the empty file
        try:
            os.remove(PENDING_UPDATES_FILE)
        except:
            pass
        return {"success": True, "message": "No pending updates to apply", "applied": 0}
    
    # Try to apply the pending updates
    applied = 0
    failed = 0
    failed_files = []
    
    try:
        import shutil
        
        for file_path in pending_files:
            # Check if there's a .new version of the file
            new_file_path = file_path + ".new"
            if os.path.exists(new_file_path):
                try:
                    # Try to replace the file
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    shutil.move(new_file_path, file_path)
                    applied += 1
                except Exception as e:
                    logger.error(f"Failed to apply update to {file_path}: {str(e)}")
                    failed += 1
                    failed_files.append(file_path)
        
        # Clean up the pending updates file
        if failed == 0:
            os.remove(PENDING_UPDATES_FILE)
        else:
            # Rewrite the file with only the failed updates
            with open(PENDING_UPDATES_FILE, "w", encoding="utf-8") as f:
                for file_path in failed_files:
                    f.write(f"{file_path}\n")
        
        return {
            "success": failed == 0,
            "message": f"Applied {applied} updates, {failed} failed",
            "applied": applied,
            "failed": failed,
            "failed_files": failed_files
        }
    except Exception as e:
        logger.error(f"Failed to apply pending updates: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to apply pending updates: {str(e)}",
            "applied": applied,
            "failed": failed + len(pending_files) - applied,
            "failed_files": failed_files
        }

def restart_application(apply_updates: bool = True) -> None:
    """
    Restart the application.
    
    This function will restart the application using the same command line arguments.
    If apply_updates is True, it will also apply any pending updates before restarting.
    
    Args:
        apply_updates: Whether to apply pending updates before restarting.
    """
    try:
        # Apply pending updates if requested
        if apply_updates and has_pending_updates():
            apply_pending_updates()
        
        # Get the command line arguments
        python_executable = sys.executable
        script_path = sys.argv[0]
        args = sys.argv[1:]
        
        # Log the restart
        logger.info(f"Restarting application: {python_executable} {script_path} {' '.join(args)}")
        
        # Start a new process
        if os.name == 'nt':  # Windows
            # Use pythonw.exe for GUI applications on Windows
            if python_executable.endswith('python.exe') and os.path.exists(python_executable.replace('python.exe', 'pythonw.exe')):
                python_executable = python_executable.replace('python.exe', 'pythonw.exe')
            
            # Use subprocess.Popen to avoid opening a new console window
            subprocess.Popen([python_executable, script_path] + args, 
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:  # Unix/Linux/Mac
            subprocess.Popen([python_executable, script_path] + args, 
                            start_new_session=True)
        
        # Exit the current process
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to restart application: {str(e)}")
        raise

def create_restart_script(delay_seconds: int = 1) -> str:
    """
    Create a script that will restart the application after a delay.
    
    This is useful when the application needs to exit completely before restarting,
    for example when updating files that are in use by the current process.
    
    Args:
        delay_seconds: The delay in seconds before restarting.
        
    Returns:
        str: The path to the restart script.
    """
    try:
        import tempfile
        
        # Get the command line arguments
        python_executable = sys.executable
        script_path = os.path.abspath(sys.argv[0])
        args = sys.argv[1:]
        
        # Create a temporary script
        fd, script_file = tempfile.mkstemp(suffix='.py', prefix='kourichat_restart_')
        with os.fdopen(fd, 'w') as f:
            f.write(f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KouriChat Restart Script

This script is automatically generated to restart the application after an update.
"""

import os
import sys
import time
import subprocess

# Wait for the application to exit
time.sleep({delay_seconds})

# Apply pending updates
pending_file = "{PENDING_UPDATES_FILE.replace('\\', '\\\\')}"
if os.path.exists(pending_file):
    try:
        import shutil
        
        with open(pending_file, "r", encoding="utf-8") as f:
            pending_files = [line.strip() for line in f.readlines() if line.strip()]
        
        for file_path in pending_files:
            new_file_path = file_path + ".new"
            if os.path.exists(new_file_path):
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    shutil.move(new_file_path, file_path)
                except:
                    pass
        
        os.remove(pending_file)
    except:
        pass

# Restart the application
python_executable = "{python_executable.replace('\\', '\\\\')}"
script_path = "{script_path.replace('\\', '\\\\')}"
args = {repr(args)}

# Start the application
if os.name == 'nt':  # Windows
    # Use pythonw.exe for GUI applications on Windows
    if python_executable.endswith('python.exe') and os.path.exists(python_executable.replace('python.exe', 'pythonw.exe')):
        python_executable = python_executable.replace('python.exe', 'pythonw.exe')
    
    subprocess.Popen([python_executable, script_path] + args, 
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
else:  # Unix/Linux/Mac
    subprocess.Popen([python_executable, script_path] + args, 
                    start_new_session=True)

# Delete this script
try:
    os.remove(__file__)
except:
    pass
''')
        
        # Make the script executable on Unix/Linux/Mac
        if os.name != 'nt':
            os.chmod(script_file, 0o755)
        
        return script_file
    except Exception as e:
        logger.error(f"Failed to create restart script: {str(e)}")
        raise

def delayed_restart(delay_seconds: int = 1) -> None:
    """
    Restart the application after a delay.
    
    This function will create a script that will restart the application after a delay,
    then exit the current process. This is useful when the application needs to exit
    completely before restarting.
    
    Args:
        delay_seconds: The delay in seconds before restarting.
    """
    try:
        # Create the restart script
        script_file = create_restart_script(delay_seconds)
        
        # Start the restart script
        if os.name == 'nt':  # Windows
            # Use pythonw.exe for the restart script on Windows
            python_executable = sys.executable
            if python_executable.endswith('python.exe') and os.path.exists(python_executable.replace('python.exe', 'pythonw.exe')):
                python_executable = python_executable.replace('python.exe', 'pythonw.exe')
            
            subprocess.Popen([python_executable, script_file], 
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:  # Unix/Linux/Mac
            subprocess.Popen([sys.executable, script_file], 
                            start_new_session=True)
        
        # Exit the current process
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to perform delayed restart: {str(e)}")
        raise
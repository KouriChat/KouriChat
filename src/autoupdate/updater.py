"""
自动更新模块
提供程序自动更新功能，包括:
- GitHub版本检查
- 更新包下载
- 文件更新
- 备份和恢复
- 更新回滚
"""

import os
import requests
import zipfile
import shutil
import json
import logging
import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class Updater:
    # GitHub仓库信息
    REPO_OWNER = "umaru-233"
    REPO_NAME = "My-Dream-Moments"
    REPO_BRANCH = "WeChat-wxauto"
    GITHUB_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
    
    # 需要跳过的文件和文件夹（不会被更新）
    SKIP_FILES = [
        "data", #data文件夹，本地数据储存
        "data/database/chat_history.db",  # 聊天记录数据库
        "data/images/temp",  # 临时图片目录
        "data/voices",  # 语音文件目录
        "logs",  # 日志目录
        "screenshot",  # 截图目录
        "wxauto文件",  # wxauto临时文件
        ".env",  # 环境变量文件
        "__pycache__",  # Python缓存文件
    ]

    def __init__(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.temp_dir = os.path.join(self.root_dir, 'temp_update')
        self.version_file = os.path.join(self.root_dir, 'version.json')

    def get_current_version(self) -> str:
        """获取当前版本号"""
        try:
            if os.path.exists(self.version_file):
                with open(self.version_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('version', '0.0.0')
        except Exception as e:
            logger.error(f"读取版本文件失败: {str(e)}")
        return '0.0.0'

    def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """检查GitHub更新"""
        try:
            # 设置请求头和SSL验证
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': f'{self.REPO_NAME}-UpdateChecker'
            }
            verify = True  # SSL验证
            
            # 获取远程 version.json 文件内容
            version_url = f"https://raw.githubusercontent.com/{self.REPO_OWNER}/{self.REPO_NAME}/{self.REPO_BRANCH}/version.json"
            response = requests.get(
                version_url,
                headers=headers,
                verify=verify,
                timeout=10
            )
            response.raise_for_status()
            remote_version_info = response.json()
            
            current_version = self.get_current_version()
            latest_version = remote_version_info.get('version', '0.0.0')
            
            # 版本比较逻辑
            def parse_version(version: str) -> tuple:
                # 移除版本号中的 'v' 前缀（如果有）
                version = version.lower().strip('v')
                try:
                    # 尝试将版本号分割为数字列表
                    parts = version.split('.')
                    # 确保至少有三个部分（主版本号.次版本号.修订号）
                    while len(parts) < 3:
                        parts.append('0')
                    # 转换为整数元组
                    return tuple(map(int, parts[:3]))
                except (ValueError, AttributeError):
                    # 如果是 commit hash 或无法解析的版本号，返回 (0, 0, 0)
                    return (0, 0, 0)

            current_ver_tuple = parse_version(current_version)
            latest_ver_tuple = parse_version(latest_version)

            # 只有当最新版本大于当前版本时才返回更新信息
            if latest_ver_tuple > current_ver_tuple:
                # 获取最新release的下载地址
                response = requests.get(
                    f"{self.GITHUB_API}/releases/latest",
                    headers=headers,
                    verify=verify,
                    timeout=10
                )
                if response.status_code == 404:
                    # 如果没有release，使用分支的zip下载地址
                    download_url = f"{self.GITHUB_API}/zipball/{self.REPO_BRANCH}"
                else:
                    release_info = response.json()
                    download_url = release_info['zipball_url']
                
                return {
                    'version': latest_version,
                    'download_url': download_url,
                    'description': remote_version_info.get('description', '无更新说明'),
                    'last_update': remote_version_info.get('last_update', ''),
                    'has_update': True
                }
                
            logger.info(f"当前版本 {current_version} 已是最新")
            return None
            
        except requests.exceptions.SSLError as ssl_err:
            logger.warning(f"SSL验证失败，尝试禁用验证: {str(ssl_err)}")
            # 禁用SSL验证重试
            return self._check_updates_without_ssl(headers)
            
        except Exception as e:
            logger.error(f"检查更新失败: {str(e)}")
            return None

    def _check_updates_without_ssl(self, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """不使用SSL验证的更新检查"""
        try:
            # 获取远程 version.json 文件内容
            version_url = f"https://raw.githubusercontent.com/{self.REPO_OWNER}/{self.REPO_NAME}/{self.REPO_BRANCH}/version.json"
            response = requests.get(
                version_url,
                headers=headers,
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            remote_version_info = response.json()
            
            current_version = self.get_current_version()
            latest_version = remote_version_info.get('version', '0.0.0')
            
            # 版本比较逻辑
            def parse_version(version: str) -> tuple:
                # 移除版本号中的 'v' 前缀（如果有）
                version = version.lower().strip('v')
                try:
                    # 尝试将版本号分割为数字列表
                    parts = version.split('.')
                    # 确保至少有三个部分（主版本号.次版本号.修订号）
                    while len(parts) < 3:
                        parts.append('0')
                    # 转换为整数元组
                    return tuple(map(int, parts[:3]))
                except (ValueError, AttributeError):
                    # 如果是 commit hash 或无法解析的版本号，返回 (0, 0, 0)
                    return (0, 0, 0)

            current_ver_tuple = parse_version(current_version)
            latest_ver_tuple = parse_version(latest_version)

            # 只有当最新版本大于当前版本时才返回更新信息
            if latest_ver_tuple > current_ver_tuple:
                # 获取最新release的下载地址
                response = requests.get(
                    f"{self.GITHUB_API}/releases/latest",
                    headers=headers,
                    verify=False,
                    timeout=10
                )
                if response.status_code == 404:
                    # 如果没有release，使用分支的zip下载地址
                    download_url = f"{self.GITHUB_API}/zipball/{self.REPO_BRANCH}"
                else:
                    release_info = response.json()
                    download_url = release_info['zipball_url']
                
                return {
                    'version': latest_version,
                    'download_url': download_url,
                    'description': remote_version_info.get('description', '无更新说明'),
                    'last_update': remote_version_info.get('last_update', ''),
                    'has_update': True
                }
                
            logger.info(f"当前版本 {current_version} 已是最新")
            return None
            
        except Exception as e:
            logger.error(f"检查更新失败: {str(e)}")
            return None

    def download_update(self, download_url: str) -> bool:
        """下载GitHub更新包"""
        try:
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': f'{self.REPO_NAME}-UpdateChecker'
            }
            response = requests.get(
                download_url,
                headers=headers,
                verify=True,
                timeout=30,
                stream=True
            )
            response.raise_for_status()
            
            os.makedirs(self.temp_dir, exist_ok=True)
            zip_path = os.path.join(self.temp_dir, 'update.zip')
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"下载更新失败: {str(e)}")
            return False

    def should_skip_file(self, file_path: str) -> bool:
        """检查是否应该跳过更新某个文件"""
        return any(skip_file in file_path for skip_file in self.SKIP_FILES)

    def backup_current_version(self) -> bool:
        """备份当前版本"""
        try:
            backup_dir = os.path.join(self.root_dir, 'backup')
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)
            shutil.copytree(self.root_dir, backup_dir, ignore=shutil.ignore_patterns(*self.SKIP_FILES))
            return True
        except Exception as e:
            logger.error(f"备份失败: {str(e)}")
            return False

    def restore_from_backup(self) -> bool:
        """从备份恢复"""
        try:
            backup_dir = os.path.join(self.root_dir, 'backup')
            if not os.path.exists(backup_dir):
                logger.error("备份目录不存在")
                return False
                
            for root, dirs, files in os.walk(backup_dir):
                relative_path = os.path.relpath(root, backup_dir)
                target_dir = os.path.join(self.root_dir, relative_path)
                
                for file in files:
                    if not self.should_skip_file(file):
                        src_file = os.path.join(root, file)
                        dst_file = os.path.join(target_dir, file)
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
            return True
        except Exception as e:
            logger.error(f"恢复失败: {str(e)}")
            return False

    def apply_update(self) -> bool:
        """应用更新"""
        try:
            # 解压更新包
            zip_path = os.path.join(self.temp_dir, 'update.zip')
            extract_dir = os.path.join(self.temp_dir, 'extracted')
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # 复制新文件
            for root, dirs, files in os.walk(extract_dir):
                relative_path = os.path.relpath(root, extract_dir)
                target_dir = os.path.join(self.root_dir, relative_path)
                
                for file in files:
                    if not self.should_skip_file(file):
                        src_file = os.path.join(root, file)
                        dst_file = os.path.join(target_dir, file)
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
            
            return True
        except Exception as e:
            logger.error(f"更新失败: {str(e)}")
            return False

    def cleanup(self):
        """清理临时文件"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            backup_dir = os.path.join(self.root_dir, 'backup')
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)
        except Exception as e:
            logger.error(f"清理临时文件失败: {str(e)}")

    def prompt_update(self, update_info: Dict[str, Any]) -> bool:
        """提示用户是否更新"""
        print("\n" + "="*50)
        print("发现新版本!")
        print("="*50)
        print(f"当前版本: {self.get_current_version()}")
        print(f"最新版本: {update_info['version']}")
        
        # 显示更新时间（使用远程仓库的更新时间）
        last_update = update_info.get('last_update', '未知')
        print(f"\n更新时间: {last_update}")
        
        # 显示更新说明
        print("\n更新内容:")
        description = update_info.get('description', '无更新说明')
        # 如果描述太长，进行分段显示
        for line in description.split('\n'):
            print(f"  {line.strip()}")
        
        print("\n" + "="*50)
        
        while True:
            choice = input("\n是否现在更新? (y/n): ").lower().strip()
            if choice in ('y', 'yes'):
                return True
            elif choice in ('n', 'no'):
                return False
            print("请输入 y 或 n")

    def update(self) -> bool:
        """执行更新流程"""
        logger.info("开始检查GitHub更新...")
        
        try:
            # 检查更新
            update_info = self.check_for_updates()
            if not update_info:
                logger.info("当前已是最新版本")
                return True
            
            # 提示用户是否更新
            if not self.prompt_update(update_info):
                logger.info("用户取消更新")
                return True
                
            logger.info(f"开始更新到版本: {update_info['version']}")
            
            # 下载更新
            if not self.download_update(update_info['download_url']):
                return False
                
            # 备份当前版本
            if not self.backup_current_version():
                return False
                
            # 应用更新
            if not self.apply_update():
                logger.error("更新失败，正在恢复...")
                if not self.restore_from_backup():
                    logger.error("恢复失败！请手动处理")
                return False
                
            # 更新版本文件
            with open(self.version_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'version': update_info['version'],
                    'last_update': update_info.get('last_update', ''),
                    'description': update_info.get('description', '')
                }, f, indent=4, ensure_ascii=False)
                
            logger.info("更新成功！请重启程序以应用更新。")
            return True
            
        except Exception as e:
            logger.error(f"更新过程中出现错误: {str(e)}")
            return False
        finally:
            self.cleanup()

def check_and_update():
    """检查并执行更新"""
    logger.info("开始检查GitHub更新...")
    updater = Updater()
    return updater.update()

if __name__ == "__main__":
    # 设置日志格式
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        result = check_and_update()
        if result:
            input("\n按回车键退出...")  # 等待用户确认后退出
        else:
            input("\n更新失败，按回车键退出...")
    except KeyboardInterrupt:
        print("\n用户取消更新")
    except Exception as e:
        print(f"\n发生错误: {str(e)}")
        input("按回车键退出...") 

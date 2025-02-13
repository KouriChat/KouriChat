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
        "config/settings.py",  # 配置文件
        "data/avatars/ATRI/ATRI.md",  # 角色预设文件
        "data/database/chat_history.db",  # 聊天记录数据库
        "data/images/temp",  # 临时图片目录
        "data/voices",  # 语音文件目录
        "logs",  # 日志目录
        "screenshot",  # 截图目录
        "wxauto文件",  # wxauto临时文件
        ".env",  # 环境变量文件
        "config.ini",  # 配置文件
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
                with open(self.version_file, 'r') as f:
                    data = json.load(f)
                    return data.get('version', '0.0.0')
        except Exception as e:
            logger.error(f"读取版本文件失败: {str(e)}")
        return '0.0.0'

    def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """检查GitHub更新"""
        try:
            # 获取最新release信息
            response = requests.get(f"{self.GITHUB_API}/releases/latest")
            if response.status_code == 404:
                # 如果没有release，获取最新commit
                response = requests.get(f"{self.GITHUB_API}/commits/{self.REPO_BRANCH}")
                
            response.raise_for_status()
            latest_info = response.json()
            
            current_version = self.get_current_version()
            
            if 'tag_name' in latest_info:  # Release版本
                latest_version = latest_info['tag_name']
                download_url = latest_info['zipball_url']
                description = latest_info.get('body', '无更新说明')
            else:  # Commit版本
                latest_version = latest_info['sha'][:7]
                download_url = f"{self.GITHUB_API}/zipball/{self.REPO_BRANCH}"
                description = latest_info['commit']['message']

            if latest_version != current_version:
                return {
                    'version': latest_version,
                    'download_url': download_url,
                    'description': description,
                    'has_update': True
                }
            return None
            
        except Exception as e:
            logger.error(f"检查更新失败: {str(e)}")
            return None

    def download_update(self, download_url: str) -> bool:
        """下载GitHub更新包"""
        try:
            headers = {'Accept': 'application/vnd.github.v3+json'}
            response = requests.get(download_url, headers=headers, stream=True)
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
        print("\n发现新版本!")
        print(f"当前版本: {self.get_current_version()}")
        print(f"最新版本: {update_info['version']}")
        print(f"\n更新内容:\n{update_info['description']}")
        
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
            with open(self.version_file, 'w') as f:
                json.dump({
                    'version': update_info['version'],
                    'last_update': update_info.get('last_update', ''),
                    'description': update_info.get('description', '')
                }, f, indent=4)
                
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
    check_and_update() 

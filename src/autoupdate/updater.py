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
    REPO_OWNER = "KouriChat"
    REPO_NAME = "KouriChat"
    REPO_BRANCH = "Kourichat-Festival-Test"
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

    # GitHub代理列表
    PROXY_SERVERS = [
        "https://ghproxy.com/https://github.com/",
        "https://hub.fastgit.xyz/",
        "https://ghfast.top/",
        "https://github.moeyy.xyz/", 
        "https://git.886.be/",
        ""  # 空字符串表示直接使用原始GitHub地址
    ]

    def __init__(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.temp_dir = os.path.join(self.root_dir, 'temp_update')
        self.version_file = os.path.join(self.root_dir, 'version.json')
        self.current_proxy_index = 0  # 当前使用的代理索引

    def get_proxy_url(self, original_url: str) -> str:
        """获取当前代理URL"""
        if self.current_proxy_index >= len(self.PROXY_SERVERS):
            return original_url
        proxy = self.PROXY_SERVERS[self.current_proxy_index]
        return f"{proxy}{original_url}" if proxy else original_url

    def try_next_proxy(self) -> bool:
        """尝试切换到下一个代理"""
        self.current_proxy_index += 1
        return self.current_proxy_index < len(self.PROXY_SERVERS)

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

    def format_version_info(self, current_version: str, update_info: dict = None) -> str:
        """格式化版本信息输出"""
        output = (
            "\n" + "="*50 + "\n"
            f"当前版本: {current_version}\n"
        )
        
        if update_info:
            output += (
                f"最新版本: {update_info['version']}\n\n"
                f"更新时间: {update_info.get('last_update', '未知')}\n\n"
                "更新内容:\n"
                f"  {update_info.get('description', '无更新说明')}\n"
                + "="*50 + "\n\n"
                "是否现在更新? (y/n): "  # 添加更新提示
            )
        else:
            output += (
                "检查结果: 当前已是最新版本\n"
                + "="*50 + "\n"
            )
            
        return output

    def format_update_progress(self, step: str, success: bool = True, details: str = "") -> str:
        """格式化更新进度输出"""
        status = "✓" if success else "✗"
        output = f"[{status}] {step}"
        if details:
            output += f": {details}"
        return output

    def check_for_updates(self) -> dict:
        """检查更新"""
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': f'{self.REPO_NAME}-UpdateChecker'
        }
        
        while True:
            try:
                # 获取远程 version.json 文件内容
                version_url = f"https://raw.githubusercontent.com/{self.REPO_OWNER}/{self.REPO_NAME}/{self.REPO_BRANCH}/version.json"
                proxied_url = self.get_proxy_url(version_url)
                
                logger.info(f"正在尝试从 {proxied_url} 获取版本信息...")
                response = requests.get(
                    proxied_url,
                    headers=headers,
                    timeout=10,
                    verify=True
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
                    # 使用正确的GitHub zip下载地址格式
                    download_url = f"https://github.com/{self.REPO_OWNER}/{self.REPO_NAME}/archive/{self.REPO_BRANCH}.zip"
                    
                    # 确保下载URL也使用代理
                    proxied_download_url = self.get_proxy_url(download_url)
                    
                    return {
                        'has_update': True,
                        'version': latest_version,
                        'download_url': proxied_download_url,
                        'description': remote_version_info.get('description', '无更新说明'),
                        'last_update': remote_version_info.get('last_update', ''),
                        'output': self.format_version_info(current_version, remote_version_info)
                    }
                
                return {
                    'has_update': False,
                    'output': self.format_version_info(current_version)
                }
                
            except (requests.RequestException, json.JSONDecodeError) as e:
                logger.warning(f"使用当前代理检查更新失败: {str(e)}")
                if self.try_next_proxy():
                    logger.info(f"正在切换到下一个代理服务器...")
                    continue
                else:
                    logger.error("所有代理服务器均已尝试失败")
                    return {
                        'has_update': False,
                        'error': "检查更新失败：无法连接到更新服务器",
                        'output': "检查更新失败：无法连接到更新服务器"
                    }

    def download_update(self, download_url: str) -> bool:
        """下载更新包"""
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': f'{self.REPO_NAME}-UpdateChecker'
        }
        
        while True:
            try:
                proxied_url = self.get_proxy_url(download_url)
                logger.info(f"正在从 {proxied_url} 下载更新...")
                
                response = requests.get(
                    proxied_url,
                    headers=headers,
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
                
            except requests.RequestException as e:
                logger.warning(f"使用当前代理下载更新失败: {str(e)}")
                if self.try_next_proxy():
                    logger.info("正在切换到下一个代理服务器...")
                    continue
                else:
                    logger.error("所有代理服务器均已尝试失败")
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
            # 清理临时更新目录
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"已清理临时更新目录: {self.temp_dir}")
                
            # 清理备份目录 - 添加更多重试和强制删除逻辑
            backup_dir = os.path.join(self.root_dir, 'backup')
            self._force_remove_directory(backup_dir, "备份目录")
                
            # 清理解压后的仓库文件夹（处理多种可能的命名格式）
            possible_repo_dirs = [
                os.path.join(self.root_dir, f"{self.REPO_NAME}-{self.REPO_BRANCH}"),
                os.path.join(self.root_dir, f"{self.REPO_OWNER}-{self.REPO_NAME}-{self.REPO_BRANCH}"),
                os.path.join(self.root_dir, f"{self.REPO_NAME}-Kourichat-Festival-Test"),  # 添加实际的文件夹名称
                os.path.join(self.root_dir, f"{self.REPO_NAME}-Kourichat-Festival-Test-{self.REPO_BRANCH}"),
                os.path.join(self.root_dir, "KouriChat-Kourichat-Festival-Test")  # 确保此目录也被尝试删除
            ]
            
            for repo_dir in possible_repo_dirs:
                self._force_remove_directory(repo_dir, "解压目录")
                        
            # 清理其他可能的格式的解压文件夹
            for item in os.listdir(self.root_dir):
                item_path = os.path.join(self.root_dir, item)
                if os.path.isdir(item_path):
                    # 检查是否是解压后的仓库文件夹
                    if (item.startswith(f"{self.REPO_NAME}-") or 
                        item.startswith(f"{self.REPO_OWNER}-{self.REPO_NAME}") or
                        "Kourichat-Festival-Test" in item):  # 添加实际的文件夹名称匹配
                        if item_path != self.root_dir:  # 确保不会删除项目根目录
                            self._force_remove_directory(item_path, f"额外的解压目录: {item}")
                        
        except Exception as e:
            logger.error(f"清理临时文件失败: {str(e)}")
            # 继续进行强制系统命令删除
            self._system_force_remove(possible_repo_dirs, backup_dir)
    
    def _force_remove_directory(self, directory, dir_type="目录"):
        """使用多种方法强制删除目录"""
        if not os.path.exists(directory):
            return
            
        # 尝试修改权限后删除
        try:
            for root, dirs, files in os.walk(directory, topdown=False):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        os.chmod(file_path, 0o777)
                    except:
                        pass
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    try:
                        os.chmod(dir_path, 0o777)
                    except:
                        pass
            
            # 尝试常规删除
            shutil.rmtree(directory)
            logger.info(f"已清理{dir_type}: {directory}")
            return
        except Exception as e:
            logger.warning(f"常规方法删除{dir_type}失败: {str(e)}")
        
        # 尝试使用系统命令删除
        try:
            import subprocess
            if os.name == 'nt':  # Windows
                subprocess.run(['rd', '/s', '/q', directory], shell=True, timeout=10)
            else:  # Linux/Mac
                subprocess.run(['rm', '-rf', directory], timeout=10)
                
            if not os.path.exists(directory):
                logger.info(f"已使用系统命令清理{dir_type}: {directory}")
            else:
                logger.warning(f"系统命令无法完全清理{dir_type}: {directory}")
        except Exception as e:
            logger.error(f"使用系统命令清理{dir_type}失败: {str(e)}")
    
    def _system_force_remove(self, repo_dirs, backup_dir):
        """最后的系统命令强制删除尝试"""
        try:
            import subprocess
            import time
            
            if os.name == 'nt':  # Windows
                # 尝试使用强制删除命令
                for repo_dir in repo_dirs:
                    if os.path.exists(repo_dir):
                        try:
                            # 先尝试常规删除
                            subprocess.run(['rd', '/s', '/q', repo_dir], shell=True, timeout=5)
                            time.sleep(1)
                            
                            # 如果仍然存在，尝试使用del命令
                            if os.path.exists(repo_dir):
                                subprocess.run(['del', '/f', '/s', '/q', repo_dir], shell=True, timeout=5)
                                time.sleep(1)
                                
                                # 如果仍然存在，尝试使用robocopy技巧清空后删除
                                if os.path.exists(repo_dir):
                                    empty_dir = os.path.join(self.temp_dir, 'empty')
                                    os.makedirs(empty_dir, exist_ok=True)
                                    subprocess.run(['robocopy', empty_dir, repo_dir, '/mir'], timeout=10)
                                    os.rmdir(repo_dir)
                        except:
                            pass
                            
                if os.path.exists(backup_dir):
                    try:
                        subprocess.run(['rd', '/s', '/q', backup_dir], shell=True, timeout=5)
                    except:
                        pass
            else:  # Linux/Mac
                for repo_dir in repo_dirs:
                    if os.path.exists(repo_dir):
                        subprocess.run(['rm', '-rf', '--no-preserve-root', repo_dir], timeout=5)
                if os.path.exists(backup_dir):
                    subprocess.run(['rm', '-rf', '--no-preserve-root', backup_dir], timeout=5)
        except Exception as e:
            logger.error(f"最终强制系统命令清理失败: {str(e)}")

    def prompt_update(self, update_info: dict) -> bool:
        """提示用户是否更新"""
        print(self.format_version_info(self.get_current_version(), update_info))
        
        # 在WebUI模式下，由前端提供输入确认
        # 这里为了兼容命令行模式，保留原有代码
        while True:
            choice = input("\n是否现在更新? (y/n): ").lower().strip()
            if choice in ('y', 'yes'):
                return True
            elif choice in ('n', 'no'):
                return False
            print("请输入 y 或 n")

    def update(self, callback=None) -> dict:
        """执行更新"""
        try:
            progress = []
            def log_progress(step, success=True, details=""):
                msg = self.format_update_progress(step, success, details)
                logger.info(msg)  # 确保记录到日志
                progress.append(msg)
                if callback:
                    callback(msg)
                    
            # 检查更新
            log_progress("开始检查GitHub更新...")
            update_info = self.check_for_updates()
            if not update_info.get('has_update', False):
                log_progress("检查更新完成", True, "当前已是最新版本")
                return {
                    'success': True, 
                    'output': '\n'.join(progress)
                }
            
            # WebUI模式下跳过确认，因为确认已经在前端完成
            log_progress(f"开始更新到版本: {update_info['version']}")
            
            # 下载更新
            log_progress("开始下载更新...")
            if not self.download_update(update_info['download_url']):
                log_progress("下载更新", False, "下载失败")
                return {
                    'success': False,
                    'output': '\n'.join(progress)
                }
            log_progress("下载更新", True, "下载完成")
                
            # 备份当前版本
            log_progress("开始备份当前版本...")
            if not self.backup_current_version():
                log_progress("备份当前版本", False, "备份失败")
                return {
                    'success': False,
                    'output': '\n'.join(progress)
                }
            log_progress("备份当前版本", True, "备份完成")
                
            # 应用更新
            log_progress("开始应用更新...")
            if not self.apply_update():
                log_progress("应用更新", False, "更新失败")
                # 尝试恢复
                log_progress("正在恢复之前的版本...")
                if not self.restore_from_backup():
                    log_progress("恢复备份", False, "恢复失败！请手动处理")
                return {
                    'success': False,
                    'output': '\n'.join(progress)
                }
            log_progress("应用更新", True, "更新成功")
                
            # 更新版本文件
            with open(self.version_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'version': update_info['version'],
                    'last_update': update_info.get('last_update', ''),
                    'description': update_info.get('description', '')
                }, f, indent=4, ensure_ascii=False)
                
            # 清理
            self.cleanup()
            log_progress("清理临时文件", True)
            log_progress("更新完成", True, "请重启程序以应用更新")

            return {
                'success': True,
                'output': '\n'.join(progress)
            }

        except Exception as e:
            logger.error(f"更新失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'output': f"更新失败: {str(e)}"
            }

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
        if result['success']:
            input("\n按回车键退出...")  # 等待用户确认后退出
        else:
            input("\n更新失败，按回车键退出...")
    except KeyboardInterrupt:
        print("\n用户取消更新")
    except Exception as e:
        print(f"\n发生错误: {str(e)}")
        input("按回车键退出...") 

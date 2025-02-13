"""
清理工具模块
负责清理系统中的临时文件和缓存，包括:
- 清理wxauto文件夹
- 清理screenshot文件夹
- 清理__pycache__文件夹
- 提供统一的清理接口
"""

import os
import shutil
import logging
import time

logger = logging.getLogger(__name__)

class CleanupUtils:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.wxauto_dir = os.path.join(root_dir, "wxauto文件")
        self.screenshot_dir = os.path.join(root_dir, "screenshot")

    def cleanup_wxauto_files(self):
        """清理wxauto文件夹"""
        try:
            logger.info(f"正在检查目录: {self.wxauto_dir}")
            if not os.path.exists(self.wxauto_dir):
                logger.info("wxauto文件夹不存在，无需清理")
                return
                
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    files = os.listdir(self.wxauto_dir)
                    if not files:
                        logger.info("wxauto文件夹为空，无需清理")
                        return
                        
                    deleted_count = 0
                    for file in files:
                        try:
                            file_path = os.path.join(self.wxauto_dir, file)
                            if os.path.isfile(file_path):
                                try:
                                    os.chmod(file_path, 0o777)
                                except:
                                    pass
                                os.remove(file_path)
                                deleted_count += 1
                            elif os.path.isdir(file_path):
                                shutil.rmtree(file_path, ignore_errors=True)
                                deleted_count += 1
                        except PermissionError:
                            logger.warning(f"文件被占用，无法删除: {file_path}")
                            continue
                        except Exception as e:
                            logger.error(f"删除失败 {file_path}: {str(e)}")
                            continue
                            
                    try:
                        if os.path.exists(self.wxauto_dir):
                            os.rmdir(self.wxauto_dir)
                            logger.info("成功删除wxauto文件夹")
                    except:
                        pass
                        
                    logger.info(f"清理完成，共删除 {deleted_count} 个文件/文件夹")
                    break
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"清理失败，正在重试 ({attempt + 1}/{max_retries})")
                        time.sleep(1)
                    else:
                        raise
                        
        except Exception as e:
            logger.error(f"清理wxauto文件夹时发生错误: {str(e)}")

    def cleanup_screenshot(self):
        """清理screenshot文件夹"""
        try:
            if os.path.isdir(self.screenshot_dir):
                shutil.rmtree(self.screenshot_dir)
                logger.info(f"目录 {self.screenshot_dir} 已成功删除")
            else:
                logger.info(f"目录 {self.screenshot_dir} 不存在，无需删除")
        except Exception as e:
            logger.error(f"清理screenshot目录失败: {str(e)}")

    def cleanup_all(self):
        """执行所有清理操作"""
        try:
            # 清理各个handler的临时目录
            self.cleanup_wxauto_files()
            # 清理pycache
            cleanup_pycache()
            # 清理screenshot文件夹
            self.cleanup_screenshot()
            logger.info("所有清理操作完成")
        except Exception as e:
            logger.error(f"清理操作失败: {str(e)}")

def cleanup_pycache():
    """递归清理所有__pycache__文件夹"""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    for root, dirs, files in os.walk(root_dir):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            try:
                shutil.rmtree(pycache_path)
                logger.info(f"已清理: {pycache_path}")
            except Exception as e:
                logger.error(f"清理失败 {pycache_path}: {str(e)}") 
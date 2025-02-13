"""
测试模块
提供系统测试功能，包括:
- 文件清理测试
- 功能单元测试
- 系统集成测试
- 配置检查测试
"""

import os
import sys
import shutil
import logging
import unittest
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SystemTests(unittest.TestCase):
    """系统测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.root_dir, 'data')
        self.logs_dir = os.path.join(self.root_dir, 'logs')
        self.temp_dir = os.path.join(self.root_dir, 'temp')
        
    def test_directory_structure(self):
        """测试目录结构"""
        required_dirs = [
            'data',
            'logs',
            'src',
            'src/config',
            'src/handlers',
            'src/services',
            'src/utils'
        ]
        
        for dir_path in required_dirs:
            full_path = os.path.join(self.root_dir, dir_path)
            self.assertTrue(
                os.path.exists(full_path), 
                f"目录不存在: {dir_path}"
            )
            
    def test_config_files(self):
        """测试配置文件"""
        required_files = [
            'src/config/config.yaml',
            'src/config/__init__.py',
            'src/config/config_manager.py',
            'requirements.txt',
            'run.py'
        ]
        
        for file_path in required_files:
            full_path = os.path.join(self.root_dir, file_path)
            self.assertTrue(
                os.path.exists(full_path), 
                f"文件不存在: {file_path}"
            )
            
    def test_cleanup_wxauto(self):
        """测试wxauto文件清理"""
        wxauto_dir = os.path.join(os.getcwd(), "wxauto文件")
        
        # 创建测试文件
        if not os.path.exists(wxauto_dir):
            os.makedirs(wxauto_dir)
        
        test_file = os.path.join(wxauto_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test")
            
        # 执行清理
        cleanup_wxauto_files()
        
        # 验证清理结果
        self.assertFalse(
            os.path.exists(test_file),
            "wxauto测试文件未被清理"
        )

def cleanup_wxauto_files():
    """
    清理当前目录下的wxauto文件夹中的文件和子文件夹
    """
    try:
        # 当前目录下的wxauto文件夹路径
        wxauto_dir = os.path.join(os.getcwd(), "wxauto文件")
        print(f"正在检查目录: {wxauto_dir}")
        if not os.path.exists(wxauto_dir):
            print("wxauto文件夹不存在，无需清理")
            return
            
        files = os.listdir(wxauto_dir)
        if not files:
            print("wxauto文件夹为空，无需清理")
            return
            
        deleted_count = 0
        for file in files:
            try:
                file_path = os.path.join(wxauto_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    # print(f"已删除文件: {file_path}")
                    deleted_count += 1
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    # print(f"已删除文件夹: {file_path}")
                    deleted_count += 1
            except Exception as e:
                # print(f"删除失败 {file_path}: {str(e)}")
                continue
                
        print(f"清理完成，共删除 {deleted_count} 个文件/文件夹")
    except Exception as e:
        print(f"清理wxauto文件夹时发生错误: {str(e)}")

def check_python_version():
    """检查Python版本"""
    required_version = (3, 8)
    current_version = sys.version_info[:2]
    
    if current_version < required_version:
        logger.error(f"Python版本过低: 当前{current_version[0]}.{current_version[1]}，"
                    f"需要{required_version[0]}.{required_version[1]}或更高")
        return False
    return True

def check_dependencies():
    """检查依赖项"""
    try:
        import requests
        import colorama
        import openai
        import sqlalchemy
        import wxauto
        import pyautogui
        logger.info("所有依赖项检查通过")
        return True
    except ImportError as e:
        logger.error(f"缺少依赖项: {str(e)}")
        return False

def run_tests():
    """运行所有测试"""
    # 检查Python版本
    if not check_python_version():
        return False
        
    # 检查依赖项
    if not check_dependencies():
        return False
        
    # 运行单元测试
    test_suite = unittest.TestLoader().loadTestsFromTestCase(SystemTests)
    test_result = unittest.TextTestRunner(verbosity=2).run(test_suite)
    
    return test_result.wasSuccessful()

def main():
    """主函数"""
    try:
        logger.info("开始系统测试...")
        
        if run_tests():
            logger.info("所有测试通过")
            # 清理临时文件
            cleanup_wxauto_files()
        else:
            logger.error("测试未通过")
            
    except KeyboardInterrupt:
        logger.info("\n用户中断测试")
    except Exception as e:
        logger.error(f"测试过程中出现错误: {str(e)}")
    finally:
        logger.info("测试结束")

if __name__ == "__main__":
    main()
"""IO工具类模块

提供基础的文件读写操作，支持多种文件格式和编码方式。
主要功能包括：
- 文本文件读写
- 二进制文件读写
- JSON/YAML配置文件处理
- 目录操作
- 文件类型判断
"""

import os
import json
import yaml
import logging
from typing import Any, Optional, Union, List
from pathlib import Path

logger = logging.getLogger(__name__)

class IoUtil:
    """IO工具类，提供文件读写和目录操作的基础功能"""
    
    def __init__(self, encoding: str = 'utf-8'):
        """初始化IoUtil
        
        Args:
            encoding: 默认文件编码，默认为utf-8
        """
        self.encoding = encoding
        self._encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
    
    def read_text(self, file_path: Union[str, Path], encoding: Optional[str] = None) -> str:
        """读取文本文件内容
        
        Args:
            file_path: 文件路径
            encoding: 指定编码，如果为None则使用默认编码
            
        Returns:
            str: 文件内容
            
        Raises:
            FileNotFoundError: 文件不存在
            IOError: 文件读取失败
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
            
        # 如果指定了编码，直接使用
        if encoding:
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError as e:
                raise IOError(f"文件编码错误: {str(e)}")
        
        # 否则尝试多种编码
        for enc in self._encodings:
            try:
                return file_path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
                
        # 如果所有编码都失败，使用二进制模式读取
        return file_path.read_bytes().decode('latin-1')
    
    def write_text(self, file_path: Union[str, Path], content: str,
                   encoding: Optional[str] = None, append: bool = False) -> None:
        """写入文本文件
        
        Args:
            file_path: 文件路径
            content: 要写入的内容
            encoding: 指定编码，如果为None则使用默认编码
            append: 是否追加模式，默认为False
            
        Raises:
            IOError: 文件写入失败
        """
        file_path = Path(file_path)
        mode = 'a' if append else 'w'
        encoding = encoding or self.encoding
        
        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with file_path.open(mode=mode, encoding=encoding) as f:
                f.write(content)
        except Exception as e:
            raise IOError(f"文件写入失败: {str(e)}")
    
    def read_binary(self, file_path: Union[str, Path]) -> bytes:
        """读取二进制文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            bytes: 文件内容
            
        Raises:
            FileNotFoundError: 文件不存在
            IOError: 文件读取失败
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
            
        try:
            return file_path.read_bytes()
        except Exception as e:
            raise IOError(f"文件读取失败: {str(e)}")
    
    def write_binary(self, file_path: Union[str, Path], content: bytes) -> None:
        """写入二进制文件
        
        Args:
            file_path: 文件路径
            content: 要写入的内容
            
        Raises:
            IOError: 文件写入失败
        """
        file_path = Path(file_path)
        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
        except Exception as e:
            raise IOError(f"文件写入失败: {str(e)}")
    
    def read_json(self, file_path: Union[str, Path], encoding: Optional[str] = None) -> Any:
        """读取JSON文件
        
        Args:
            file_path: 文件路径
            encoding: 指定编码，如果为None则使用默认编码
            
        Returns:
            Any: 解析后的JSON数据
            
        Raises:
            FileNotFoundError: 文件不存在
            json.JSONDecodeError: JSON解析失败
        """
        content = self.read_text(file_path, encoding)
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"JSON解析失败: {str(e)}", e.doc, e.pos)
    
    def write_json(self, file_path: Union[str, Path], data: Any,
                   encoding: Optional[str] = None, indent: int = 4) -> None:
        """写入JSON文件
        
        Args:
            file_path: 文件路径
            data: 要写入的数据
            encoding: 指定编码，如果为None则使用默认编码
            indent: 缩进空格数，默认为4
            
        Raises:
            TypeError: 数据类型不可序列化
            IOError: 文件写入失败
        """
        try:
            content = json.dumps(data, ensure_ascii=False, indent=indent)
            self.write_text(file_path, content, encoding)
        except TypeError as e:
            raise TypeError(f"数据类型不可序列化: {str(e)}")
        except Exception as e:
            raise IOError(f"文件写入失败: {str(e)}")
    
    def read_yaml(self, file_path: Union[str, Path], encoding: Optional[str] = None) -> Any:
        """读取YAML文件
        
        Args:
            file_path: 文件路径
            encoding: 指定编码，如果为None则使用默认编码
            
        Returns:
            Any: 解析后的YAML数据
            
        Raises:
            FileNotFoundError: 文件不存在
            yaml.YAMLError: YAML解析失败
        """
        content = self.read_text(file_path, encoding)
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"YAML解析失败: {str(e)}")
    
    def write_yaml(self, file_path: Union[str, Path], data: Any,
                   encoding: Optional[str] = None) -> None:
        """写入YAML文件
        
        Args:
            file_path: 文件路径
            data: 要写入的数据
            encoding: 指定编码，如果为None则使用默认编码
            
        Raises:
            TypeError: 数据类型不可序列化
            IOError: 文件写入失败
        """
        try:
            content = yaml.safe_dump(data, allow_unicode=True)
            self.write_text(file_path, content, encoding)
        except TypeError as e:
            raise TypeError(f"数据类型不可序列化: {str(e)}")
        except Exception as e:
            raise IOError(f"文件写入失败: {str(e)}")
    
    def list_files(self, dir_path: Union[str, Path], pattern: str = '*',
                   recursive: bool = False) -> List[Path]:
        """列出目录下的文件
        
        Args:
            dir_path: 目录路径
            pattern: 文件匹配模式，默认为'*'
            recursive: 是否递归遍历子目录，默认为False
            
        Returns:
            List[Path]: 文件路径列表
            
        Raises:
            NotADirectoryError: 路径不是目录
            FileNotFoundError: 目录不存在
        """
        dir_path = Path(dir_path)
        if not dir_path.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")
        if not dir_path.is_dir():
            raise NotADirectoryError(f"路径不是目录: {dir_path}")
            
        if recursive:
            return list(dir_path.rglob(pattern))
        return list(dir_path.glob(pattern))
    
    def ensure_dir(self, dir_path: Union[str, Path]) -> Path:
        """确保目录存在，如果不存在则创建
        
        Args:
            dir_path: 目录路径
            
        Returns:
            Path: 目录路径对象
            
        Raises:
            IOError: 目录创建失败
        """
        dir_path = Path(dir_path)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        except Exception as e:
            raise IOError(f"目录创建失败: {str(e)}")
    
    def get_file_size(self, file_path: Union[str, Path]) -> int:

        """获取文件大小
        
        Args:
            file_path: 文件路径
            
        Returns:
            int: 文件大小(字节)
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        return file_path.stat().st_size

    def copy_file(self, src_path: Union[str, Path], dst_path: Union[str, Path]) -> None:
    
        """复制文件

        Args:
            src_path: 源文件路径
            dst_path: 目标文件路径

        Raises:
            FileNotFoundError: 源文件不存在
            IOError: 文件复制失败
        """
        import shutil
        src_path = Path(src_path)
        dst_path = Path(dst_path)

        if not src_path.exists():
            raise FileNotFoundError(f"源文件不存在: {src_path}")

        try:
            # 处理目标路径是目录的情况
            if dst_path.is_dir():
                dst_path = dst_path / src_path.name

            # 确保目标目录存在
            self.ensure_dir(dst_path.parent)

            # 复制文件并保留元数据
            shutil.copy2(src_path, dst_path)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"目标路径无效: {str(e)}")
        except IOError as e:
            raise IOError(f"文件复制失败: {str(e)}")

    def get_all_files(self, dir_path: Union[str, Path], pattern: str = '*', recursive: bool = False) -> List[Path]:
        """获取目录下的所有文件（包括子目录）

        Args:
            dir_path: 目录路径
            pattern: 文件匹配模式，默认为'*'
            recursive: 是否递归遍历子目录，默认为False

        Returns:
            List[Path]: 文件路径列表

        Raises:
            NotADirectoryError: 路径不是目录
            FileNotFoundError: 目录不存在
        """
        dir_path = Path(dir_path)
        if not dir_path.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")
        if not dir_path.is_dir():
            raise NotADirectoryError(f"路径不是目录: {dir_path}")

        if recursive:
            return list(dir_path.rglob(pattern))
        return list(dir_path.glob(pattern))
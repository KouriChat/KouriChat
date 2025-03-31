"""
文件处理模块
负责管理文件
- 文件的读取、保存和
- 文件变更监听系统
- 增强的类型注解
- 线程安全的目录观察
"""
import os
import logging
import shutil
import threading
from typing import Optional, List, Dict, Set, Callable, Union
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
logger = logging.getLogger('main')
class FileHandler:
    """文件处理器，负责各种文件操作"""
    def __init__(self):
        self.temp_files: List[str] = []
        self.observer = Observer()
        self.watch_descriptors: Dict[str, Dict] = {}  # {watch_id: {path, callback, filters}}
        self.lock = threading.RLock()
        self._start_observer()
    
    def _start_observer(self):
        """启动观察者线程"""
        if not self.observer.is_alive():
            self.observer.start()
            logger.info("文件观察者线程已启动")
    
    def _stop_observer(self):
        """停止观察者线程"""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            logger.info("文件观察者线程已停止")
    
    class EventHandler(FileSystemEventHandler):
        """自定义文件事件处理器"""
        
        def __init__(self, callback: Callable, extensions: Optional[Set[str]] = None):
            super().__init__()
            self.callback = callback
            self.extensions = extensions
        
        def _should_handle(self, path: str) -> bool:
            """判断是否需要处理该事件"""
            if not self.extensions:
                return True
            return Path(path).suffix.lower() in self.extensions
        
        def on_any_event(self, event: FileSystemEvent):
            try:
                if event.is_directory:
                    return
                src_path = event.src_path
                if self._should_handle(src_path):
                    logger.debug(f"检测到文件变更: {event.event_type} {src_path}")
                    self.callback()
            except Exception as e:
                logger.error(f"处理文件事件失败: {str(e)}")
    
    def watch_directory(
        self,
        path: str,
        callback: Callable,
        extensions: Optional[List[str]] = None,
        recursive: bool = True
    ) -> str:
        """注册目录监视"""
        try:
            path = os.path.abspath(path)
            if not os.path.isdir(path):
                raise ValueError(f"监视路径不存在或不是目录: {path}")
            with self.lock:
                # 避免重复添加监视
                for desc in self.watch_descriptors.values():
                    if desc['path'] == path and desc['extensions'] == extensions:
                        logger.warning(f"已经存在相同参数的监视: {path}")
                        return "" # 返回空字符串表示已存在
                extensions_set = set(ext.lower() for ext in extensions) if extensions else None
                handler = self.EventHandler(callback=callback, extensions=extensions_set)
                watch = self.observer.schedule(handler, path=path, recursive=recursive)
                watch_id = str(id(watch))
                self.watch_descriptors[watch_id] = {
                    'watch': watch,
                    'path': path,
                    'handler': handler,
                    'extensions': extensions,
                    'recursive': recursive
                }
                logger.info(f"成功添加目录监视: {path} (ID: {watch_id})")
                return watch_id
        except Exception as e:
            logger.error(f"添加目录监视失败: {str(e)}")
            return "" # 出错返回空字符串
    
    def unwatch_directory(self, watch_id: str) -> bool:
        """移除目录监视"""
        with self.lock:
            desc = self.watch_descriptors.pop(watch_id, None)
            if not desc:
                logger.warning(f"无效的监视ID: {watch_id}")
                return False
            try:
                self.observer.unschedule(desc['watch'])
                logger.info(f"已移除目录监视: {desc['path']} (ID: {watch_id})")
                return True
            except Exception as e:
                logger.error(f"移除监视失败: {str(e)}")
                return False
        
    def read_file(self, file_path: str) -> Optional[str]:
        """读取文件内容"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return None
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except Exception as e:
            logger.error(f"读取文件失败: {str(e)}")
            return None
            
    def write_file(self, file_path: str, content: str) -> bool:
        """写入文件内容"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"写入文件失败: {str(e)}")
            return False
            
    def append_file(self, file_path: str, content: str) -> bool:
        """追加文件内容"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"追加文件失败: {str(e)}")
            return False
            
    def delete_file(self, file_path: str) -> bool:
        """删除文件"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            logger.error(f"删除文件失败: {str(e)}")
            return False
            
    def copy_file(self, source_path: str, target_path: str) -> bool:
        """复制文件"""
        try:
            # 确保目标目录存在
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            
            shutil.copy2(source_path, target_path)
            return True
        except Exception as e:
            logger.error(f"复制文件失败: {str(e)}")
            return False
            
    def create_temp_file(self, content: str, prefix: str = "temp_", suffix: str = ".txt") -> Optional[str]:
        """创建临时文件"""
        try:
            import tempfile
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix, mode='w', encoding='utf-8')
            temp_file.write(content)
            temp_file.close()
            
            self.temp_files.append(temp_file.name)
            return temp_file.name
        except Exception as e:
            logger.error(f"创建临时文件失败: {str(e)}")
            return None
            
    def cleanup_temp_files(self) -> None:
        """清理临时文件"""
        for file_path in self.temp_files[:]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    self.temp_files.remove(file_path)
            except Exception as e:
                logger.error(f"清理临时文件失败: {str(e)}")
                
    def __del__(self):
        """析构函数，确保临时文件被清理"""
        self._stop_observer()
        self.cleanup_temp_files()
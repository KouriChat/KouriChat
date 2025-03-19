"""
依赖注入容器：
管理系统中各个组件的依赖关系，实现控制反转
"""

from typing import Any, Type, Dict, Optional, Callable
from threading import Lock


class Container:
    def __init__(self):
        """初始化容器"""
        self._bindings: Dict[Type, Dict] = {}
        self._instances: Dict[Type, Any] = {}
        self._lock = Lock()

    def register(self, interface: Type, implementation: Type, singleton: bool = True):
        """
        注册依赖关系
        Args:
            interface: 接口或抽象类
            implementation: 具体实现类
            singleton: 是否为单例模式
        """
        with self._lock:
            self._bindings[interface] = {
                'implementation': implementation,
                'singleton': singleton
            }

    def register_instance(self, interface: Type, instance: Any):
        """
        注册已存在的实例
        Args:
            interface: 接口或抽象类
            instance: 具体实例
        """
        with self._lock:
            self._instances[interface] = instance

    def register_factory(self, interface: Type, factory: Callable[[], Any]):
        """
        注册工厂函数
        Args:
            interface: 接口或抽象类
            factory: 创建实例的工厂函数
        """
        with self._lock:
            self._bindings[interface] = {
                'factory': factory,
                'singleton': False
            }

    def resolve(self, interface: Type) -> Any:
        """
        解析依赖关系
        Args:
            interface: 要解析的接口或类型
        Returns:
            解析后的实例
        """
        # 检查是否已有实例（单例）
        if interface in self._instances:
            return self._instances[interface]

        # 检查是否有注册的绑定
        if interface not in self._bindings:
            raise KeyError(f"No binding found for {interface}")

        binding = self._bindings[interface]

        # 使用工厂函数创建实例
        if 'factory' in binding:
            instance = binding['factory']()
        else:
            # 创建新实例
            implementation = binding['implementation']
            try:
                instance = implementation()
            except TypeError:
                # 如果初始化需要参数，尝试解析依赖
                dependencies = self._resolve_dependencies(implementation)
                instance = implementation(**dependencies)

        # 如果是单例模式，保存实例
        if binding.get('singleton', False):
            with self._lock:
                self._instances[interface] = instance

        return instance

    def _resolve_dependencies(self, implementation: Type) -> Dict[str, Any]:
        """
        解析类的构造函数依赖
        Args:
            implementation: 要解析依赖的类
        Returns:
            依赖参数字典
        """
        import inspect
        
        dependencies = {}
        signature = inspect.signature(implementation.__init__)
        
        for param_name, param in signature.parameters.items():
            if param_name == 'self':
                continue
            
            if param.annotation != inspect.Parameter.empty:
                try:
                    dependencies[param_name] = self.resolve(param.annotation)
                except KeyError:
                    if param.default != inspect.Parameter.empty:
                        dependencies[param_name] = param.default
                    else:
                        raise ValueError(f"Cannot resolve dependency {param_name} of type {param.annotation}")
        
        return dependencies
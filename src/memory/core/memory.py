import os
import json
from functools import wraps


class Memory:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None or not kwargs.get('singleton', True):
            cls._instance = super(Memory, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_path='../config/memory.json', singleton: bool = True):
        # 使用 super().__setattr__ 直接设置所有属性，避免触发 __getattr__
        super().__setattr__('config_path', config_path)
        super().__setattr__('settings', {})
        super().__setattr__('_memory_hooks', [])
        super().__setattr__('_in_hook', False)  # 钩子执行状态标志
        super().__setattr__('initialized', True)
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self.settings = json.load(file) or {}
        else:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as file:
                json.dump({}, file)
            self.settings = {}

    def save_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as file:
            json.dump(self.settings, file, indent=4, ensure_ascii=False)

    def __getattr__(self, key):
        # 避免递归：直接访问 self.settings，而不是通过 self.__getattr__
        if key in super().__getattribute__('settings'):
            return super().__getattribute__('settings')[key]
        raise AttributeError(f"'Memory' object has no attribute '{key}'")

    def __setattr__(self, key, value):
        # 处理内部属性
        if key in ['config_path', 'settings', 'initialized', '_memory_hooks', '_in_hook']:
            super().__setattr__(key, value)
        # 外部属性通过 set 方法处理
        else:
            self.set(key, value)

    def __setitem__(self, key, value):
        self.set(key, value)

    def __getitem__(self, key):
        return self.settings[key]

    def set(self, key: str, value):
        """ 新增的 set 方法 """
        self.settings[key] = value

        # 触发记忆钩子（带防重复触发保护）
        if not self._in_hook:
            self._in_hook = True
            try:
                for hook in self._memory_hooks:
                    hook(key, value)
            finally:
                self._in_hook = False

    def get_key_value_pairs(self) -> list[str]:
        return [f"{key}:{value}" for key, value in self.settings.items()]

    def add_memory_hook(self, func):
        @wraps(func)
        def wrapper(key, value):
            return func(key, value)

        self._memory_hooks.append(wrapper)
        return wrapper


if __name__ == '__main__':
    memory = Memory(config_path=r"C:\Users\Administrator\Music\temp\config\memory.json")
    memory["hello"] = "your"
    print(memory.settings)

"""TOML 主配置（ticket 09：TOML；热更用 cordis，骨架先支持重载读取）。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def _walk_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)
    else:
        yield value


def _resolve_secret_refs(value: Any, store: Any) -> Any:
    """Resolve only the explicit ``@secret:<name>`` reference format."""
    if isinstance(value, dict):
        return {k: _resolve_secret_refs(v, store) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_secret_refs(v, store) for v in value]
    if isinstance(value, str) and value.startswith("@secret:"):
        name = value[len("@secret:"):]
        if not name or ":" in name or "\n" in name or "\r" in name:
            raise ValueError("invalid secret reference")
        return store.get(name)
    return value


class Config:
    """TOML 主配置：读 `plugins`/`adapters` 清单 + 任意段落。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {}

    def load(self) -> "Config":
        with open(self.path, "rb") as f:
            data = tomllib.load(f)
        if any(isinstance(v, str) and v.startswith("@secret:")
               for v in _walk_values(data)):
            from .security import SecretStore
            store = SecretStore(self.path.parent / ".kourichat-secrets")
            self.data = _resolve_secret_refs(data, store)
        else:
            self.data = data
        return self

    def reload(self) -> "Config":
        return self.load()

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def plugins(self) -> list[dict[str, Any]]:
        """插件清单：[{name, module, config?}, ...]"""
        return self.get("plugins", [])

    def adapters(self) -> list[dict[str, Any]]:
        """adapter 配置：[{module, config?}, ...]（注册类 wx/qq 等见 ticket 06）"""
        return self.get("adapters", [])

"""WebUI 控制台插件（ticket 17）：aiohttp 静态服务 + 控制台 JSON API。

- 随 `kourichat run` 以插件形式启动（kourichat.toml `[[plugins]] module="kourichat.webui"`）；
- 静态托管 Vue 控制台（`static_dir`，缺省 ./frontend/dist；未构建时返回占位说明）；
- JSON API 对接 `adapter.openclaw` 服务（T13 契约）：
  status / login / relogin / logout（本地标记）/ chat send+mock / logs / config；
- 日志环形缓冲：loguru sink 捕获（本插件装配后追加，不替换既有 handler）。
"""

from __future__ import annotations

import collections
import ipaddress
import json
import math
import os
import re
import socket
import threading
import time
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

try:
    from loguru import logger as _loguru
except ImportError:  # pragma: no cover
    _loguru = None

try:
    from aiohttp import web
except ImportError:  # pragma: no cover
    web = None  # type: ignore[assignment]

from ..event import MESSAGE_RECEIVE
from ..security import AdminAuth, SecretStore, secure_file
from ..types import Channel, Message, Segment, User

# 静态目录：优先包内 static/（wheel 打包时由 build 脚本填充 frontend/dist 产物），
# 也允许用户用 static_dir 配置覆盖为任意目录。
DEFAULT_STATIC_DIR = str(Path(__file__).resolve().parent / "static")
DEFAULT_LOG_LINES = 500

_LOG_LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}


def _require_aiohttp() -> None:
    if web is None:
        raise RuntimeError(
            "webui 插件需要 aiohttp：请先安装依赖（uv sync 或 pip install aiohttp）")


class LogBuffer:
    """loguru sink 环形缓冲：供 /api/logs 轮询。"""

    def __init__(self, max_lines: int = DEFAULT_LOG_LINES) -> None:
        self._buf: collections.deque[dict[str, Any]] = collections.deque(
            maxlen=max(10, max_lines))
        self._lock = threading.Lock()

    def sink(self, message: Any) -> None:
        rec = message.record
        with self._lock:
            self._buf.append({
                "time": rec["time"].isoformat(),
                "level": rec["level"].name,
                "line": str(message),
            })

    def snapshot(self, limit: int = 100, level: str = "DEBUG",
                 skip: int = 0) -> list[dict[str, Any]]:
        """按级别过滤后返回日志（新→旧）；skip 跳过最新 skip 条（懒加载更早）。"""
        min_level = _LOG_LEVELS.get(str(level).upper(), 0)
        with self._lock:
            rows = [r for r in self._buf
                    if _LOG_LEVELS.get(r["level"], 0) >= min_level]
        all_rows = list(reversed(rows))
        return all_rows[skip: skip + max(1, limit)]


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _adapter(ctx: Any) -> Any:
    adapter = ctx.get("adapter.openclaw")
    if adapter is None:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False,
                             "error": "adapter.openclaw not loaded"}),
            content_type="application/json")
    return adapter


async def _read_body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "error": "body must be JSON"}),
            content_type="application/json")
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False, "error": "body must be a JSON object"}),
            content_type="application/json")
    return body


async def api_auth_status(request: web.Request) -> web.Response:
    token = _extract_token(request)
    authenticated = bool(token and not request.app["admin_auth"].is_revoked(token)
                         and request.app["admin_auth"].verify_token(token))
    return _json({"ok": True, "initialized": request.app["admin_auth"].initialized,
                  "authenticated": authenticated})


async def api_auth_setup(request: web.Request) -> web.Response:
    auth = request.app["admin_auth"]
    if auth.initialized:
        return _json({"ok": False, "error": "管理员账号已初始化"}, 409)
    if not request.remote or request.remote not in {"127.0.0.1", "::1", "localhost"}:
        return _json({"ok": False, "error": "首次初始化仅允许本机访问"}, 403)
    body = await _read_body(request)
    username = body.get("username")
    password = body.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return _json({"ok": False, "error": "username and password are required"}, 400)
    try:
        auth.setup(username, password)
        return _json({"ok": True, "token": auth.issue(username.strip())})
    except ValueError as exc:
        return _json({"ok": False, "error": str(exc)}, 400)


async def api_auth_login(request: web.Request) -> web.Response:
    auth = request.app["admin_auth"]
    if not auth.initialized:
        return _json({"ok": False, "error": "管理员账号尚未初始化"}, 409)
    body = await _read_body(request)
    username = body.get("username")
    password = body.get("password")
    limiter = request.app["login_limiter"]
    key = f"{request.remote}:{username}"
    if not limiter.allow(key):
        return _json({"ok": False, "error": "尝试过于频繁，请 15 分钟后再试"}, 429)
    if not isinstance(username, str) or not isinstance(password, str) \
            or not auth.verify(username, password):
        limiter.record(key)
        return _json({"ok": False, "error": "账号或密码错误"}, 401)
    limiter.reset(key)
    return _json({"ok": True, "token": auth.issue(username.strip())})


async def api_auth_logout(request: web.Request) -> web.Response:
    token = request.get("auth_token", "")
    request.app["admin_auth"].revoke(token)
    return _json({"ok": True})


async def api_status(request: web.Request) -> web.Response:
    return _json(await _adapter(request.app["ctx"]).status())


async def api_login(request: web.Request) -> web.Response:
    body = await _read_body(request)
    account_id = str(body.get("accountId") or "") or None
    return _json(await _adapter(request.app["ctx"]).start_login(account_id))


async def api_login_refresh(request: web.Request) -> web.Response:
    """手动刷新当前二维码（weixin_login_refresh；失败回退重新 weixin_login）。"""
    adapter = _adapter(request.app["ctx"])
    refresh = getattr(adapter, "refresh_login", None)
    if refresh is None:
        return _json({"ok": False, "error": "adapter 不支持二维码刷新"}, 400)
    try:
        state = await refresh()
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)}, 400)
    return _json(state or {})


async def api_relogin(request: web.Request) -> web.Response:
    body = await _read_body(request)
    account_id = str(body.get("accountId") or "")
    if not account_id:
        return _json({"ok": False, "error": "accountId is required"}, 400)
    return _json(await _adapter(request.app["ctx"]).relogin(account_id))


async def api_logout(request: web.Request) -> web.Response:
    body = await _read_body(request)
    account_id = str(body.get("accountId") or "")
    if not account_id:
        return _json({"ok": False, "error": "accountId is required"}, 400)
    await _adapter(request.app["ctx"]).logout_local(account_id)
    return _json({"ok": True, "note":
                  "已通知网关 weixin_logout 并本地移除账号"})


async def api_chat_send(request: web.Request) -> web.Response:
    body = await _read_body(request)
    channel_id = str(body.get("channel_id") or "")
    text = str(body.get("text") or "")
    if not channel_id or not text:
        return _json({"ok": False, "error": "channel_id and text are required"}, 400)
    # 网关仅支持私聊（一对一微信消息）；群聊发送未落地，只接受 private
    adapter = _adapter(request.app["ctx"])
    from ..types import OutMessage
    mid = await adapter.send(OutMessage(
        channel=Channel(platform="openclaw", channel_id=channel_id,
                        channel_type="private"),
        segments=[Segment("text", {"text": text})]))
    if not mid:
        return _json({"ok": False,
                      "error": "发送失败（网关未返回 message_id）——请确认目标 user_id 是"\
                               "真实微信用户（微信 ret=-3 invalid arguments）"}, 400)
    return _json({"ok": True, "message_id": mid})


async def api_chat_mock(request: web.Request) -> web.Response:
    """注入一条假消息进事件链（走完整逻辑链；无 llm.factory 时仅日志）。"""
    body = await _read_body(request)
    text = str(body.get("text") or "")
    if not text:
        return _json({"ok": False, "error": "text is required"}, 400)
    # 网关仅私聊；注入统一走 private
    ctx = request.app["ctx"]
    events = ctx.get("events")
    msg = Message(
        id=f"webui-mock-{time.time_ns()}",
        channel=Channel(platform="openclaw", channel_id="webui-mock",
                        channel_type="private"),
        sender=User(user_id="webui", name="webui"),
        segments=[Segment("text", {"text": text})],
        ts=time.time(),
        raw={"mock": True},
    )
    await events.emit(MESSAGE_RECEIVE, msg)
    return _json({"ok": True, "emitted": True})


async def api_logs(request: web.Request) -> web.Response:
    try:
        limit = int(request.query.get("limit", "100") or 100)
        skip = int(request.query.get("skip", "0") or 0)
    except ValueError:
        return _json({"ok": False, "error": "invalid limit/skip"}, 400)
    limit = max(1, min(limit, 1000))
    skip = max(0, skip)
    level = str(request.query.get("level", "DEBUG") or "DEBUG").upper()
    if level not in _LOG_LEVELS:
        return _json({"ok": False, "error": "invalid level"}, 400)
    buf = request.app["logbuf"]
    return _json({"logs": buf.snapshot(limit=limit, level=level, skip=skip)})


def _config_service(ctx: Any) -> Any:
    cfg = ctx.get("config")
    if cfg is None:
        raise web.HTTPBadRequest(
            text=json.dumps({"ok": False,
                             "error": "config service not loaded"}),
            content_type="application/json")
    return cfg


# ---------------------------------------------------------------------------
# 结构化配置（表单 + 即时保存）、dashboard、首次运行判定
# ---------------------------------------------------------------------------

OPENCLAW_MODULE = "kourichat.adapter.openclaw"
LLM_MODULE = "kourichat.llm.factory"
WEBUI_MODULE = "kourichat.webui"
PERSONA_MODULE = "kourichat.logic.persona"
ECHO_MODULE = "kourichat.logic.echo"
SECRET_MASK = "********"
PUBLIC_AUTH_PATHS = frozenset({"/api/auth/status", "/api/auth/setup", "/api/auth/login"})
JSON_METHODS = frozenset({"POST", "PUT", "PATCH"})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> Any:
        return None


def _allowed_origin(request: web.Request, origin: str,
                    configured: set[str]) -> bool:
    if not origin:
        return True
    if origin in configured:
        return True
    return origin == f"{request.scheme}://{request.host}"


def _extract_token(request: web.Request) -> str:
    value = request.headers.get("Authorization", "")
    scheme, sep, token = value.partition(" ")
    if not sep or scheme.lower() != "bearer" or not token or " " in token:
        return ""
    return token


@web.middleware
def _security_middleware(request: web.Request, handler: Any) -> Any:
    if not request.path.startswith("/api/"):
        return handler(request)
    origin = request.headers.get("Origin", "")
    if not _allowed_origin(request, origin, request.app["allowed_origins"]):
        raise web.HTTPForbidden(
            text=json.dumps({"ok": False, "error": "origin not allowed"}),
            content_type="application/json")
    if request.method == "OPTIONS":
        if not origin:
            raise web.HTTPForbidden()
        response = web.Response(status=204)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, OPTIONS"
        response.headers["Vary"] = "Origin"
        return response
    if request.method in JSON_METHODS:
        content_type = request.content_type.lower()
        if content_type != "application/json" and not content_type.endswith("+json"):
            raise web.HTTPUnsupportedMediaType(
                text=json.dumps({"ok": False, "error": "JSON body required"}),
                content_type="application/json")
    if request.path not in PUBLIC_AUTH_PATHS:
        token = _extract_token(request)
        auth = request.app["admin_auth"]
        if not token or auth.is_revoked(token) or not auth.verify_token(token):
            raise web.HTTPUnauthorized(
                text=json.dumps({"ok": False, "error": "authentication required"}),
                content_type="application/json",
                headers={"WWW-Authenticate": "Bearer"})
        request["auth_token"] = token
    return handler(request)


# ---- 安全响应头 / 登录限流（T31）-----------------------------------------
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://api.fontshare.com https://fonts.googleapis.com; "
    "font-src 'self' data: https://cdn.fontshare.com https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


async def _on_response_prepare(request: web.Request,
                               response: web.StreamResponse) -> None:
    h = response.headers
    h.setdefault("Content-Security-Policy", _CSP)
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy",
                 "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    h["Server"] = "KouriChat"
    if request.path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, private")
        h.setdefault("Pragma", "no-cache")
    if request.scheme == "https":
        h.setdefault("Strict-Transport-Security",
                     "max-age=63072000; includeSubDomains")


class _LoginLimiter:
    """内存登录失败限流（按 远端 IP + 用户名）。"""

    def __init__(self, max_attempts: int = 5, window: float = 900.0) -> None:
        self.max_attempts = max_attempts
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            self._hits[key] = hits
            return len(hits) < self.max_attempts

    def record(self, key: str) -> None:
        with self._lock:
            self._hits.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

SETTINGS_FIELDS: dict[str, dict[str, Any]] = {
    "core": {"log_level": "INFO"},
    "openclaw": {"gateway_url": "http://127.0.0.1:8765",
                 "access_token": "", "data_dir": "./data",
                 "autologin": True, "poll_interval": 2.0},
    "llm": {"base_url": "https://api.openai.com/v1", "api_key": "",
            "model": "gpt-4o-mini", "data_dir": "./data"},
    "webui": {"host": "127.0.0.1", "port": 8080},
    "persona": {"personas_dir": "./personas", "enable": ""},
    "echo": {"enabled": True},
}


def _fmt_toml(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("invalid TOML number")
        return str(v)
    if not isinstance(v, str):
        raise ValueError("unsupported TOML value")
    return json.dumps(v, ensure_ascii=False)


def _toml_key(key: Any) -> str:
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise ValueError("invalid TOML key")
    return key


def _emit_scalar(lines: list[str], key: str, val: Any) -> None:
    key = _toml_key(key)
    if isinstance(val, dict):  # 单层内联表（如 role_prompt_overrides）
        inner = ", ".join(f"{_toml_key(k)} = {_fmt_toml(v)}" for k, v in val.items())
        lines.append(f"{key} = {{ {inner} }}")
    else:
        lines.append(f"{key} = {_fmt_toml(val)}")


def _toml_dump(data: dict[str, Any]) -> str:
    """按 kourichat 配置形态序列化：顶层 scalar 段 + 数组表(带 config 子表/内联表)。"""
    lines: list[str] = []
    for key, val in data.items():
        if isinstance(val, dict):
            lines.append(f"[{key}]")
            for k, v in val.items():
                _emit_scalar(lines, k, v)
            lines.append("")
        elif isinstance(val, list):
            for item in val:
                if not isinstance(item, dict):
                    continue
                lines.append(f"[[{key}]]")
                for k, v in item.items():
                    if isinstance(v, dict):  # config 子表
                        lines.append(f"[{key}.{k}]")
                        for kk, vv in v.items():
                            _emit_scalar(lines, kk, vv)
                        lines.append("")
                    else:
                        _emit_scalar(lines, k, v)
                lines.append("")
        else:
            _emit_scalar(lines, key, val)
    return "\n".join(lines).rstrip("\n") + "\n"


def _load_config_data(cfg: Any) -> dict[str, Any]:
    path = Path(cfg.path)
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _is_first_run(cfg: Any) -> bool:
    """首启判定：config 文件内容与内置模板完全一致。"""
    path = Path(cfg.path)
    if not path.exists():
        return True
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    try:
        from ..main import TEMPLATE
    except Exception:
        return False
    return text == TEMPLATE.strip()


def _entry_by_module(data: dict[str, Any], list_key: str,
                     module: str) -> dict[str, Any] | None:
    for it in data.get(list_key, []):
        if isinstance(it, dict) and it.get("module") == module:
            return it
    return None


def _upsert_config(data: dict[str, Any], list_key: str, module: str,
                   cfg: dict[str, Any]) -> None:
    if not cfg:
        return
    entry = _entry_by_module(data, list_key, module)
    if entry is None:
        entry = {"module": module, "config": {}}
        data.setdefault(list_key, []).append(entry)
    entry.setdefault("config", {})
    for k, v in cfg.items():
        entry["config"][k] = v


def _project_settings(data: dict[str, Any]) -> dict[str, Any]:
    core = data.get("core") or {}
    def proj(section: str, list_key: str, module: str,
             defaults: dict[str, Any]) -> dict[str, Any]:
        entry = _entry_by_module(data, list_key, module)
        cfg = (entry or {}).get("config") or {}
        result = {k: cfg.get(k, d) for k, d in defaults.items()}
        if section in ("openclaw", "llm"):
            secret = result.get("access_token" if section == "openclaw" else "api_key")
            result["access_token" if section == "openclaw" else "api_key"] = (
                SECRET_MASK if secret else "")
        return result
    return {
        "core": {k: core.get(k, d) for k, d in SETTINGS_FIELDS["core"].items()},
        "openclaw": proj("openclaw", "adapters", OPENCLAW_MODULE,
                         SETTINGS_FIELDS["openclaw"]),
        "llm": proj("llm", "plugins", LLM_MODULE, SETTINGS_FIELDS["llm"]),
        "webui": proj("webui", "plugins", WEBUI_MODULE, SETTINGS_FIELDS["webui"]),
        "persona": proj("persona", "plugins", PERSONA_MODULE,
                        SETTINGS_FIELDS["persona"]),
        "echo": proj("echo", "plugins", ECHO_MODULE, SETTINGS_FIELDS["echo"]),
    }


def _validate_settings(fields: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(fields, dict):
        raise ValueError("fields is required")
    allowed = {section: set(values) for section, values in SETTINGS_FIELDS.items()}
    result: dict[str, dict[str, Any]] = {}
    type_map: dict[tuple[str, str], type] = {
        ("core", "log_level"): str,
        ("openclaw", "gateway_url"): str, ("openclaw", "access_token"): (str, type(None)),
        ("openclaw", "data_dir"): str, ("openclaw", "autologin"): bool,
        ("openclaw", "poll_interval"): (int, float),
        ("llm", "base_url"): str, ("llm", "api_key"): (str, type(None)),
        ("llm", "model"): str, ("llm", "data_dir"): str,
        ("webui", "host"): str, ("webui", "port"): int,
        ("persona", "personas_dir"): str, ("persona", "enable"): str,
        ("echo", "enabled"): bool,
    }
    for section, values in fields.items():
        if section not in allowed or not isinstance(values, dict):
            raise ValueError("unknown settings section")
        result[section] = {}
        for key, value in values.items():
            if key not in allowed[section] or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
                raise ValueError("unknown settings field")
            expected = type_map[(section, key)]
            if expected is int and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"invalid type for {section}.{key}")
            if expected != int and not isinstance(value, expected):
                raise ValueError(f"invalid type for {section}.{key}")
            if section == "core" and key == "log_level" and value not in _LOG_LEVELS:
                raise ValueError("invalid log level")
            if section == "webui" and key == "port" and not 1 <= value <= 65535:
                raise ValueError("invalid port")
            if section == "openclaw" and key == "poll_interval":
                if not math.isfinite(float(value)) or value <= 0:
                    raise ValueError("invalid poll interval")
            if section in ("openclaw", "llm") and key in ("gateway_url", "base_url"):
                parsed = urlsplit(str(value).strip())
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    raise ValueError(f"invalid {section}.{key}")
            result[section][key] = value
    return result


def _secret_value(store: SecretStore, name: str, value: Any,
                  old: Any) -> Any:
    if value == SECRET_MASK:
        if isinstance(old, str) and old and not old.startswith("@secret:"):
            return store.put(name, old)
        return old
    if value is None or value == "":
        store.delete(name)
        return ""
    return store.put(name, value)


def _apply_settings(data: dict[str, Any], fields: dict[str, Any],
                    secrets: SecretStore) -> dict[str, dict[str, Any]]:
    fields = _validate_settings(fields)
    normalized = {section: dict(values) for section, values in fields.items()}
    core = data.setdefault("core", {})
    for key, value in normalized.get("core", {}).items():
        core[key] = value
    old_projected = _project_settings(data)
    for section, list_key, module in (
        ("openclaw", "adapters", OPENCLAW_MODULE),
        ("llm", "plugins", LLM_MODULE),
        ("webui", "plugins", WEBUI_MODULE),
        ("persona", "plugins", PERSONA_MODULE),
        ("echo", "plugins", ECHO_MODULE),
    ):
        patch = normalized.get(section)
        if patch is None:
            continue
        secret_key = "access_token" if section == "openclaw" else "api_key" if section == "llm" else None
        if secret_key and secret_key in patch:
            old_entry = _entry_by_module(data, list_key, module) or {}
            old_cfg = old_entry.get("config") or {}
            patch[secret_key] = _secret_value(
                secrets, f"{section}.{secret_key}", patch[secret_key], old_cfg.get(secret_key, ""))
            runtime_secret = patch[secret_key]
            if isinstance(runtime_secret, str) and runtime_secret.startswith("@secret:"):
                runtime_secret = secrets.get(runtime_secret[len("@secret:"):])
            normalized[section][secret_key] = runtime_secret
        _upsert_config(data, list_key, module, patch)
    return normalized


async def api_settings_get(request: web.Request) -> web.Response:
    cfg = _config_service(request.app["ctx"])
    return _json({"ok": True, "fields": _project_settings(
        _load_config_data(cfg))})


async def _reload_llm_factory(ctx: Any, llm_cfg: dict[str, Any]) -> bool:
    """运行时重启 llm.factory 组件（dispose 旧 fiber → 新配置重新 plugin）。

    会话记忆经 elixir Store 持久化，重载后新 Session 从磁盘恢复，不丢记忆。
    """
    import importlib
    fiber = None
    for entry in ctx.root._services.values():
        if getattr(entry, "name", None) == "llm.factory":
            fiber = entry.provider
            break
    old = dict(fiber.config or {}) if fiber is not None else {}
    new_cfg = {**old, **(llm_cfg or {})}
    if fiber is not None:
        await fiber.dispose()
    module = importlib.import_module("kourichat.llm.factory")
    apply = getattr(module, "apply", None)
    if apply is None:
        return False
    new_fiber = ctx.plugin(apply, new_cfg)
    await new_fiber.wait()
    return True


async def api_settings_post(request: web.Request) -> web.Response:
    cfg = _config_service(request.app["ctx"])
    body = await _read_body(request)
    fields = body.get("fields")
    if not isinstance(fields, dict):
        return _json({"ok": False, "error": "fields is required"}, 400)
    data = _load_config_data(cfg)
    before_modules = [(item.get("module"), key)
                      for key in ("plugins", "adapters")
                      for item in data.get(key, []) if isinstance(item, dict)]
    try:
        normalized = _apply_settings(
            data, fields, request.app["admin_auth"].secrets)
        content = _toml_dump(data)
        parsed = tomllib.loads(content)
        after_modules = [(item.get("module"), key)
                         for key in ("plugins", "adapters")
                         for item in parsed.get(key, []) if isinstance(item, dict)]
        if before_modules and before_modules != after_modules:
            raise ValueError("plugin structure cannot be changed")
    except (ValueError, tomllib.TOMLDecodeError) as exc:
        return _json({"ok": False, "error": str(exc)}, 400)
    path = Path(cfg.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    _chmod_private(tmp)
    tmp.replace(path)
    _chmod_private(path)
    adapter = request.app["ctx"].get("adapter.openclaw")
    oc = normalized.get("openclaw") or {}
    if adapter is not None:
        try:
            adapter.update_gateway(gateway_url=oc.get("gateway_url"),
                                   access_token=oc.get("access_token"))
        except Exception as exc:
            logger = request.app["ctx"].get("logger")
            if logger is not None:
                logger.warn("webui update_gateway failed", error=str(exc))
    notes: list[str] = ["已保存"]
    if normalized.get("llm"):
        try:
            if await _reload_llm_factory(request.app["ctx"], normalized["llm"]):
                notes.append("LLM 组件已热重载")
            else:
                notes.append("llm.factory 未装配，跳过热重载")
        except Exception:
            notes.append("LLM 热重载失败")
    return _json({"ok": True, "note": "；".join(notes)})


async def api_llm_reload(request: web.Request) -> web.Response:
    """显式热重载 llm.factory：用当前配置文件里的 LLM 设置重启组件。"""
    ctx = request.app["ctx"]
    cfg = ctx.get("config")
    llm: dict[str, Any] = {}
    if cfg is not None:
        raw = _load_config_data(cfg)
        entry = _entry_by_module(raw, "plugins", LLM_MODULE)
        llm = dict((entry or {}).get("config") or {})
        key = llm.get("api_key")
        if isinstance(key, str) and key.startswith("@secret:"):
            llm["api_key"] = request.app["admin_auth"].secrets.get(key[8:])
    try:
        if await _reload_llm_factory(ctx, llm):
            return _json({"ok": True, "note": "LLM 组件已热重载（新配置已生效）"})
        return _json({"ok": False, "error": "llm.factory 未装配，无法重载"}, 400)
    except Exception:
        return _json({"ok": False, "error": "LLM 热重载失败"}, 400)


async def api_llm_test(request: web.Request) -> web.Response:
    """用当前或明确提供的 LLM 配置发一条最小 chat 请求。"""
    import urllib.error

    body = await _read_body(request)
    cfg = request.app["ctx"].get("config")
    current = _load_config_data(cfg) if cfg is not None else {}
    current_llm = _project_settings(current)["llm"]
    supplied = body.get("llm") or {}
    if not isinstance(supplied, dict):
        return _json({"ok": False, "error": "invalid llm configuration"}, 400)
    base_url = str(supplied.get("base_url") or current_llm.get("base_url") or "").rstrip("/")
    endpoint_changed = "base_url" in supplied and base_url != str(current_llm.get("base_url") or "").rstrip("/")
    api_key = supplied.get("api_key")
    if not api_key or api_key == SECRET_MASK:
        api_key = ""
        if not endpoint_changed:
            entry = _entry_by_module(current, "plugins", LLM_MODULE)
            if entry:
                raw = (entry.get("config") or {}).get("api_key", "")
                if isinstance(raw, str) and raw.startswith("@secret:"):
                    api_key = request.app["admin_auth"].secrets.get(raw[8:])
                else:
                    api_key = str(raw or "")
    model = str(supplied.get("model") or current_llm.get("model") or "")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname \
            or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return _json({"ok": False, "error": "unsupported LLM endpoint"}, 400)
    try:
        port = parsed.port
    except ValueError:
        return _json({"ok": False, "error": "invalid LLM endpoint"}, 400)
    # 自托管控制台的常见用法就是本地/代理型 endpoint（Ollama、one-api、vLLM、
    # Clash fake-ip 198.18.0.0/15 等），因此允许私网/回环/自定义端口；
    # 仅拦截 SSRF 元数据面：link-local(169.254/fe80)、组播、未指定地址。
    try:
        infos = await __import__("asyncio").to_thread(
            socket.getaddrinfo, parsed.hostname, port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM)
    except OSError:
        return _json({"ok": False, "error": "LLM endpoint cannot be resolved"}, 400)
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return _json({"ok": False, "error": "LLM endpoint cannot be resolved"}, 400)
    try:
        if any((ipaddress.ip_address(addr).is_link_local
                or ipaddress.ip_address(addr).is_multicast
                or ipaddress.ip_address(addr).is_unspecified)
               for addr in addresses):
            return _json({"ok": False, "error": "LLM endpoint is not allowed"}, 400)
    except ValueError:
        return _json({"ok": False, "error": "invalid LLM endpoint"}, 400)
    if not base_url or not api_key or not model:
        return _json({"ok": False, "error": "请先填写 base_url / api_key / model"}, 400)
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": "ping"}],
                          "max_tokens": 4}).encode("utf-8")
    req = Request(base_url + "/chat/completions", data=payload,
                  headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    try:
        with build_opener(_NoRedirect()).open(req, timeout=20) as resp:
            raw = resp.read(64 * 1024)
            data = json.loads(raw.decode("utf-8"))
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return _json({"ok": True, "reply": str(text)[:4000], "model": model, "note": "LLM 连通正常"})
    except urllib.error.HTTPError:
        return _json({"ok": False, "error": "LLM returned an HTTP error"}, 400)
    except Exception:
        return _json({"ok": False, "error": "LLM connection failed"}, 400)


async def api_setup_status(request: web.Request) -> web.Response:
    cfg = request.app["ctx"].get("config")
    first_run = _is_first_run(cfg) if cfg is not None else True
    return _json({"ok": True, "first_run": first_run})


async def api_dashboard(request: web.Request) -> web.Response:
    ctx = request.app["ctx"]
    adapter = ctx.get("adapter.openclaw")
    connected = False
    accounts: list[dict[str, Any]] = []
    login = None
    if adapter is not None:
        st = await adapter.status()
        connected = st["connected"]
        accounts = st["accounts"]
        login = st["login"]
    registry = ctx.get("persona.registry") or {}
    active = ctx.get("persona.active")
    cfg = ctx.get("config")
    return _json({
        "connected": connected,
        "accounts": accounts,
        "login": login,
        "personas": {"count": len(registry),
                     "active": getattr(active, "id", None) if active else None},
        "first_run": _is_first_run(cfg) if cfg is not None else True,
    })


async def _serve_static(request: web.Request) -> web.Response:
    root = Path(request.app["static_dir"])
    if not (root / "index.html").exists():
        return web.Response(
            text="前端未构建：请在仓库 frontend/ 目录执行 npm run build"
                 "（或配置 static_dir 指向构建产物）",
            content_type="text/plain", charset="utf-8")
    tail = request.match_info.get("tail", "")
    target = (root / tail).resolve() if tail else root / "index.html"
    # 防目录穿越：目标必须位于 static_dir 内
    if root.resolve() not in target.parents and target != root.resolve():
        target = root / "index.html"
    if tail and target.is_file():
        return web.FileResponse(target)
    return web.FileResponse(root / "index.html")


# ---------------------------------------------------------------------------
# 插件入口
# ---------------------------------------------------------------------------


def _chmod_private(path: Path) -> None:
    secure_file(path)


def _migrate_plaintext_secrets(config_path: Path, auth_dir: Path) -> bool:
    """把 kourichat.toml 里明文的 api_key/access_token 迁移为 @secret:。

    返回是否发生迁移；写盘后强制 0600。config 不存在/解析失败时静默跳过。
    """
    path = Path(config_path)
    if not path.is_file():
        return False
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    store = SecretStore(auth_dir)
    changed = False
    for section, list_key, module in (
        ("openclaw", "adapters", OPENCLAW_MODULE),
        ("llm", "plugins", LLM_MODULE),
    ):
        field = "access_token" if section == "openclaw" else "api_key"
        entry = _entry_by_module(data, list_key, module)
        cfg = (entry or {}).get("config")
        if not isinstance(cfg, dict):
            continue
        value = cfg.get(field)
        if isinstance(value, str) and value and not value.startswith("@secret:"):
            cfg[field] = store.put(f"{section}.{field}", value)
            changed = True
    if changed:
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(_toml_dump(data), encoding="utf-8")
            _chmod_private(tmp)
            tmp.replace(path)
        except OSError:
            return False
    _chmod_private(path)
    return changed


async def build_app(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    """构造 aiohttp app（不启动）；供 apply 与测试复用。"""
    _require_aiohttp()
    cfg = config or {}
    config_service = ctx.get("config")
    config_path = Path(getattr(config_service, "path", "kourichat.toml"))
    auth_dir = Path(cfg.get("auth_data_dir", config_path.parent / ".kourichat-secrets"))
    _migrate_plaintext_secrets(config_path, auth_dir)
    app = web.Application(middlewares=[_security_middleware])
    app.on_response_prepare.append(_on_response_prepare)
    app["ctx"] = ctx
    app["login_limiter"] = _LoginLimiter()
    app["static_dir"] = str(cfg.get("static_dir", DEFAULT_STATIC_DIR))
    app["logbuf"] = LogBuffer(int(cfg.get("log_lines", DEFAULT_LOG_LINES)))
    app["admin_auth"] = AdminAuth(auth_dir)
    configured_origins = cfg.get("allowed_origins", ())
    if isinstance(configured_origins, str):
        configured_origins = (configured_origins,)
    app["allowed_origins"] = {str(origin) for origin in configured_origins if origin}

    # API 路由必须先注册，避免被静态 catch-all 吞掉
    app.router.add_get("/api/auth/status", api_auth_status)
    app.router.add_post("/api/auth/setup", api_auth_setup)
    app.router.add_post("/api/auth/login", api_auth_login)
    app.router.add_post("/api/auth/logout", api_auth_logout)
    app.router.add_get("/api/openclaw/status", api_status)
    app.router.add_post("/api/openclaw/login", api_login)
    app.router.add_post("/api/openclaw/login/refresh", api_login_refresh)
    app.router.add_post("/api/openclaw/relogin", api_relogin)
    app.router.add_post("/api/openclaw/logout", api_logout)
    app.router.add_post("/api/chat/send", api_chat_send)
    app.router.add_post("/api/chat/mock", api_chat_mock)
    app.router.add_get("/api/logs", api_logs)
    app.router.add_get("/api/settings", api_settings_get)
    app.router.add_post("/api/settings", api_settings_post)
    app.router.add_post("/api/llm/test", api_llm_test)
    app.router.add_post("/api/llm/reload", api_llm_reload)
    app.router.add_get("/api/setup/status", api_setup_status)
    app.router.add_get("/api/dashboard", api_dashboard)
    app.router.add_get("/", _serve_static)
    app.router.add_get("/{tail:.*}", _serve_static)
    return app


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    """挂载 webui 插件：启动 aiohttp 站点 + 日志 sink；返回 dispose。"""
    _require_aiohttp()
    cfg = config or {}
    host = str(cfg.get("host", "127.0.0.1"))
    port = int(cfg.get("port", 8080))
    app = await build_app(ctx, config)
    if _loguru is not None:
        sink_id = _loguru.add(app["logbuf"].sink, level="DEBUG")
    else:
        sink_id = None

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    ctx.provide("webui.app", app)
    logger = ctx.get("logger")
    if logger is not None:
        logger.info("webui started", host=host, port=port)

    async def dispose() -> None:
        if sink_id is not None and _loguru is not None:
            _loguru.remove(sink_id)
        await runner.cleanup()

    return dispose

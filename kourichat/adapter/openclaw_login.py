"""openclaw 登录管理器（新 OneBot 网关契约：openclaw-onebotv11）。

新网关**没有** HTTP `GET /login` / `GET /login/token`；登录族是 OneBot action：

- `weixin_login {account_id?}`   → `{qr_id, qrcode_url, expire_at}`
- `weixin_login_refresh {qr_id}` → 同一 qr_id 换一张新码
- `weixin_logout {account_id}`   → 网关侧停止账号 + 清理凭据
- `weixin_accounts` / `weixin_status` → 账号/在线状态（见 openclaw.py）

登录结果通过 WS notice 广播（bot token 永不返回，qrcode_url 只回原请求）：

- `notice.login_success {account_id, user_id}` → 登录成功
- `notice.login_qr_expired {qr_id}`           → 二维码过期，需要刷新

本模块只负责二维码状态机与刷新触发；账号落库/在线状态由事件层
`openclaw_events.handle_notice` 完成。HTTP 用标准库 urllib，不新增依赖。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ACTION_LOGIN = "weixin_login"
ACTION_REFRESH = "weixin_login_refresh"
ACTION_LOGOUT = "weixin_logout"

# 自动刷新上限：超过则置 failed，由前端手动重新发起。
MAX_QR_REFRESH = 5


class LoginManager:
    """二维码登录状态机：start → pending →（notice）success / 刷新。"""

    def __init__(self, gateway_url: str, store: Any = None,
                 poll_interval: float = 2.0, timeout: float = 10.0,
                 access_token: str = "", logger: Any = None,
                 on_success: Any = None) -> None:
        base = gateway_url.rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("gateway_url 必须是 http(s)://host[:port] 形式")
        self.base = base
        # 兼容旧签名：新契约下账号落库移到事件层，store 不再使用。
        self.store = store
        self.poll_interval = max(0.2, poll_interval)
        self.timeout = max(1.0, timeout)
        self.access_token = access_token
        self.logger = logger
        self.on_success = on_success  # 登录成功（account_id）→ 调用方清 needs_relogin
        self._login: dict[str, Any] | None = None
        self._start_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None

    def state(self) -> dict[str, Any] | None:
        return dict(self._login) if self._login else None

    async def start(self, account_id: str | None = None,
                    force: bool = False) -> dict[str, Any]:
        """发起新登录；force=False 且已有 pending 时返回现有状态。"""
        async with self._start_lock:
            current = self._login
            if current is not None and current.get("status") == "pending" and not force:
                return dict(current)
            await self._cancel_refresh()
            params = {"account_id": account_id} if account_id else {}
            try:
                data = await self._call(ACTION_LOGIN, params)
            except Exception as exc:
                self._log("openclaw login start failed", error=str(exc))
                self._login = {
                    "uid": "", "qrcodeUrl": "", "accountId": account_id or "",
                    "userId": "", "status": "failed",
                    "message": f"login start failed: {exc}",
                    "refresh_count": 0, "startedAt": time.time(),
                    "expireAt": 0.0,
                }
                return dict(self._login)
            self._login = self._from_result(data, account_id)
            self._log("openclaw login pending", qr_id=self._login["uid"])
            return dict(self._login)

    async def refresh(self) -> dict[str, Any]:
        """手动/主动刷新：先 refresh，会话已失效则重新 login。"""
        return await self._refresh_or_restart()

    async def close(self) -> None:
        await self._cancel_refresh()
        self._login = None

    def on_qr_expired(self, qr_id: str) -> bool:
        """收到 `login_qr_expired`：后台刷新，不阻塞事件读循环。"""
        login = self._login
        if login is None or login.get("status") != "pending":
            return False
        if qr_id and str(qr_id) != str(login.get("uid") or ""):
            return False
        if self._refresh_task is not None and not self._refresh_task.done():
            return True
        self._refresh_task = asyncio.create_task(self._refresh_or_restart())
        return True

    async def on_login_success(self, account_id: str = "",
                               user_id: str = "") -> None:
        """收到 `login_success`：置 success + 回调（账号落库由事件层完成）。"""
        await self._cancel_refresh()
        login = self._login
        if login is None:
            login = {"uid": "", "qrcodeUrl": "", "accountId": "", "userId": "",
                     "status": "pending", "message": "", "refresh_count": 0,
                     "startedAt": time.time(), "expireAt": 0.0}
            self._login = login
        login["status"] = "success"
        login["accountId"] = str(account_id or login.get("accountId") or "")
        login["userId"] = str(user_id or login.get("userId") or "")
        login["message"] = "login succeeded"
        self._log("openclaw login success", accountId=login["accountId"])
        if self.on_success is not None and login["accountId"]:
            self.on_success(login["accountId"])

    def _from_result(self, data: dict[str, Any],
                     requested: str | None) -> dict[str, Any]:
        return {
            "uid": str(data.get("qr_id") or ""),
            "qrcodeUrl": str(data.get("qrcode_url") or ""),
            "accountId": requested or "",
            "userId": "",
            "status": "pending",
            "message": "",
            "refresh_count": 0,
            "startedAt": time.time(),
            "expireAt": _expire_at(data.get("expire_at")),
        }

    async def _refresh_or_restart(self) -> dict[str, Any]:
        async with self._refresh_lock:
            login = self._login
            if login is None:
                return {}
            try:
                data = await self._call(ACTION_REFRESH,
                                        {"qr_id": str(login.get("uid") or "")})
                self._apply_refresh(login, data)
                return dict(login)
            except Exception as exc:
                # 网关广播 login_qr_expired 后会删会话 → refresh 得 1404；
                # 回退为一次全新登录（新 qr_id），保持 account_id 不变。
                self._log("openclaw qr refresh failed, restarting login",
                          error=str(exc))
                try:
                    account_id = str(login.get("accountId") or "") or None
                    params = {"account_id": account_id} if account_id else {}
                    data = await self._call(ACTION_LOGIN, params)
                except Exception as exc2:
                    login["status"] = "failed"
                    login["message"] = f"二维码刷新失败: {exc2}"
                    self._log("openclaw login restart failed", error=str(exc2))
                    return dict(login)
                count = int(login.get("refresh_count") or 0) + 1
                if count > MAX_QR_REFRESH:
                    login["status"] = "failed"
                    login["message"] = "二维码多次失效，请重新发起登录"
                    return dict(login)
                fresh = self._from_result(data, login.get("accountId") or None)
                fresh["refresh_count"] = count
                self._login = fresh
                self._log("openclaw login restarted", qr_id=fresh["uid"],
                          count=count)
                return dict(fresh)

    @staticmethod
    def _apply_refresh(login: dict[str, Any], data: dict[str, Any]) -> None:
        login["uid"] = str(data.get("qr_id") or login.get("uid") or "")
        login["qrcodeUrl"] = str(data.get("qrcode_url")
                                 or login.get("qrcodeUrl") or "")
        login["expireAt"] = (_expire_at(data.get("expire_at"))
                             or login.get("expireAt") or 0.0)
        login["status"] = "pending"
        login["message"] = ""
        login["refresh_count"] = int(login.get("refresh_count") or 0) + 1

    async def _cancel_refresh(self) -> None:
        task = self._refresh_task
        self._refresh_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # —— HTTP（OneBot action over POST /）——
    def _post_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"action": action, "params": params},
                          ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        req = Request(self.base + "/", data=body, headers=headers, method="POST")
        try:
            # scheme 已在 __init__ 校验为 http/https，拒绝 file:// 等
            with urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                envelope = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8", "replace")
                data = json.loads(raw) if raw else {}
            except Exception:
                data = {}
            finally:
                exc.close()
            raise RuntimeError(
                str(data.get("message") or data.get("error")
                    or f"{action} failed (HTTP {exc.code})")) from None
        except URLError as exc:
            raise RuntimeError(f"{action} failed: {exc.reason}") from None
        retcode = int(envelope.get("retcode", 0) or 0)
        if str(envelope.get("status")) != "ok" or retcode != 0:
            raise RuntimeError(
                str(envelope.get("message") or envelope.get("wording")
                    or f"{action} failed (retcode={retcode})"))
        data = envelope.get("data")
        return data if isinstance(data, dict) else {}

    async def _call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._post_action, action, params)

    def _log(self, msg: str, **kw: Any) -> None:
        if self.logger is not None:
            self.logger.warn(msg, **kw)


def _expire_at(value: Any) -> float:
    """expire_at 是 unix 毫秒 → 秒；非法值返回 0。"""
    try:
        ms = float(value)
    except (TypeError, ValueError):
        return 0.0
    if ms <= 0:
        return 0.0
    return ms / 1000.0 if ms > 1e11 else ms

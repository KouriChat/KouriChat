"""OneBot v11 适配器（ticket 03/06 + 本轮反向 WS）。

支持两种连接形态（config `mode`）：
- `forward`（默认）：机器人作 WS **客户端**连平台（`ws_url`）；
- `reverse`：机器人作 WS **服务端**（`ws_host`/`ws_port`，可配 `token` 校验
  Authorization: Bearer）等平台连入。

入向：message 事件 → MESSAGE_RECEIVE（类型分发由逻辑层 relay，Fix 1 去重）；
出向：send/recall 动作（echo 匹配等待响应）。
注册类约束（ticket 06）：config `register` 声明支持的段类型集合，不支持的忽略。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

import websockets

from .base import Adapter
from ..event import MESSAGE_RECEIVE
from ..types import Channel, Message, OutMessage, Segment, User

DEFAULT_REVERSE_HOST = "127.0.0.1"
DEFAULT_REVERSE_PORT = 6700


class OneBotV11Adapter(Adapter):
    """OneBot v11 适配器：正向 WS 客户端 / 反向 WS 服务端二选一。"""

    capabilities = frozenset({"text", "image", "at", "face", "record", "video", "reply"})

    def __init__(self, *, ws_url: str = "",
                 mode: str = "forward",
                 ws_host: str = DEFAULT_REVERSE_HOST,
                 ws_port: int = DEFAULT_REVERSE_PORT,
                 token: str = "",
                 register: frozenset[str] | None = None) -> None:
        self.mode = mode
        self.ws_url = ws_url
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.token = token
        self.register = register  # None=全部；否则仅处理声明的段类型
        self._ctx: Any = None
        self._ws: Any = None  # forward 连接
        self._conns: list[Any] = []  # reverse 已连入的客户端
        self._server: Any = None  # reverse websockets.serve
        self._task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._send_lock = asyncio.Lock()  # 多会话并发回复共用一连接 → 帧写入串行化
        self._seq = 0
        self.port: int = ws_port  # reverse 实际监听端口（port=0 时回填）

    @property
    def reverse(self) -> bool:
        return self.mode == "reverse"

    async def start(self, ctx: Any) -> None:
        self._ctx = ctx
        if self.reverse:
            self._server = await websockets.serve(
                self._client, self.ws_host, self.ws_port,
                max_size=10 * 1024 * 1024)
            sock = self._server.sockets[0] if self._server.sockets else None
            if sock is not None:
                self.port = sock.getsockname()[1]
            logger = self._ctx.get("logger")
            if logger:
                logger.info("onebot reverse ws listening", host=self.ws_host, port=self.port)
                if self.ws_host not in {"127.0.0.1", "::1", "localhost"} and not self.token:
                    logger.warn(
                        "onebot reverse ws exposed without token; "
                        "bind 127.0.0.1 or set token", host=self.ws_host, port=self.port)
        else:
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            self._ws = await websockets.connect(self.ws_url, additional_headers=headers)
            self._task = asyncio.create_task(self._read_conn(self._ws))

    # —— 反向 WS：平台连入的处理（websockets.serve 回调只带 connection）——
    async def _client(self, ws: Any) -> None:
        if self.token:
            auth = next((v for k, v in (ws.request.headers or {}).items()
                         if str(k).lower() == "authorization"), "")
            if auth != f"Bearer {self.token}":
                self._log("onebot reverse auth failed")
                await ws.close(code=4001)
                return
        self._conns.append(ws)
        try:
            await self._read_conn(ws)
        finally:
            with contextlib.suppress(ValueError):
                self._conns.remove(ws)

    # —— 帧处理（两种形态共用）——
    async def _read_conn(self, ws: Any) -> None:
        try:
            async for raw in ws:
                await self._handle_raw(raw)
        except Exception as exc:  # 断线/关闭由 dispose 收尾，但留日志（防静默死机器人）
            self._log("onebot ws read loop exit", error=str(exc))

    async def _handle_raw(self, raw: Any) -> None:
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            return
        if frame.get("post_type") == "message":
            await self._on_message(frame)
        elif str(frame.get("echo")) in self._pending:  # echo 可能是数字，统一 str 比较
            fut = self._pending.pop(str(frame["echo"]))
            if not fut.done():
                fut.set_result(frame)

    def _log(self, msg: str, **kw: Any) -> None:
        logger = self._ctx.get("logger") if self._ctx else None
        if logger:
            logger.warn(msg, **kw)

    def _seg(self, s: dict[str, Any]) -> Segment:
        return Segment(type=str(s.get("type", "text")), data=dict(s.get("data") or {}))

    def _keep(self, seg: Segment) -> bool:
        return self.register is None or seg.type in self.register

    async def _on_message(self, frame: dict[str, Any]) -> None:
        segments = [self._seg(s) for s in frame.get("message", [])]
        segments = [s for s in segments if self._keep(s)]
        if not segments:
            return  # 注册类约束：不支持的消息类型忽略（ticket 06）
        channel_type = "group" if frame.get("message_type") == "group" else "private"
        msg = Message(
            id=str(frame.get("message_id", "")),
            channel=Channel(
                platform="onebot-v11",
                channel_id=str(frame.get("group_id") or frame.get("user_id") or ""),
                channel_type=channel_type,
            ),
            sender=User(user_id=str(frame.get("user_id", "")),
                        name=str(frame.get("sender", {}).get("nickname", ""))),
            segments=segments,
            ts=frame.get("time") or time.time(),
            raw=frame,
        )
        events = self._ctx.get("events")
        await events.emit(MESSAGE_RECEIVE, msg)

    def _send_ws(self) -> Any:
        """当前出向连接：forward=自连 ws；reverse=最近连入的客户端。"""
        if self.reverse:
            return self._conns[-1] if self._conns else None
        return self._ws

    async def _action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        ws = self._send_ws()
        if ws is None:
            self._log("onebot no connection for action", action=action)
            return {}
        self._seq += 1
        echo = str(self._seq)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[echo] = fut
        try:
            async with self._send_lock:
                await ws.send(json.dumps({"action": action, "params": params, "echo": echo}))
            return await asyncio.wait_for(fut, timeout=10.0)
        finally:
            self._pending.pop(echo, None)

    async def send(self, out: OutMessage) -> str:
        params: dict[str, Any] = {
            "message": [{"type": s.type, "data": s.data} for s in out.segments]}
        if out.channel.channel_type == "group":
            params["group_id"] = int(out.channel.channel_id)
            action = "send_group_msg"
        else:
            params["user_id"] = int(out.channel.channel_id)
            action = "send_private_msg"
        resp = await self._action(action, params)
        return str(resp.get("data", {}).get("message_id", ""))

    async def recall(self, msg_id: str) -> None:
        await self._action("delete_msg", {"message_id": int(msg_id)})

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        # 清理未决动作 future + 关闭全部连接（Fix 4）
        for fut in self._pending.values():
            fut.cancel()
        self._pending.clear()
        targets = list(self._conns) + ([self._ws] if self._ws else [])
        for ws in targets:
            with contextlib.suppress(Exception):
                await ws.close()
        self._conns.clear()
        self._ws = None


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    cfg = config or {}
    mode = str(cfg.get("mode", "forward")).lower()
    if mode not in ("forward", "reverse"):
        raise ValueError(f"onebot adapter mode 仅支持 forward/reverse，收到：{mode!r}")
    register = frozenset(cfg["register"]) if cfg.get("register") else None
    adapter = OneBotV11Adapter(
        ws_url=str(cfg.get("ws_url", "")),
        mode=mode,
        ws_host=str(cfg.get("ws_host", DEFAULT_REVERSE_HOST)),
        ws_port=int(cfg.get("ws_port", DEFAULT_REVERSE_PORT)),
        token=str(cfg.get("token", "")),
        register=register,
    )
    if not adapter.reverse and not adapter.ws_url:
        raise ValueError("onebot forward 模式需要 ws_url")
    await adapter.start(ctx)
    ctx.provide("adapter.onebot-v11", adapter)

    async def dispose() -> None:
        await adapter.close()

    return dispose

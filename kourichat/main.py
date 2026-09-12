"""主入口：框架启动与装配（自动初始化配置，常驻事件循环）。

装配顺序：config → logger → bus(events) → adapter → logic → llm → 常驻事件循环；
优雅退出：EOF/SIGINT → dispose_all（插件副作用回收 + elixir store flush）。
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from cordis_py import Context

from .config import Config
from .core import assemble, shutdown
from .event import Dispatcher
from .logger import LoguruLogger, configure_logging, loop_exception_handler

TEMPLATE = '''# KouriChat 1.5 主配置（TOML，ticket 09）
# adapters 先装配（接入层），plugins 后装配（逻辑层 + LLM 工厂），顺序即事件订阅顺序。

# 日志（loguru：控制台 + 可选文件落盘；进程/后台任务未捕获异常也进同一日志链）
[core]
log_level = "INFO"                 # DEBUG/INFO/WARNING/ERROR
# log_console_format = ""          # 自定义控制台格式串（缺省用内置好看格式）
# log_dir = "./logs"               # 非空则按天落盘 kourichat_YYYY-MM-DD.log
# log_rotation = "1 day"

# 接入层：每个平台一个 adapter 插件。怎么自己写一个平台适配器？看 docs/ADAPTERS.md。
#
# CLI 适配器（交互调试用；想只跑机器人就把整段注释掉）：
# [[adapters]]
# module = "kourichat.adapter.cli"
# [adapters.config]

# OneBot v11 —— 反向 WS（默认形态：机器人开 WS 服务端等平台连入，
# 例如 NapCat 的「反向 ws」填 ws://本机ip:6700 指向这里）
[[adapters]]
module = "kourichat.adapter.onebot"
[adapters.config]
mode = "reverse"                 # forward | reverse
ws_host = "127.0.0.1"            # 监听地址（对局域网开放改 0.0.0.0，并务必设置 token）
ws_port = 6700                   # 监听端口
token = ""                       # 设了则平台必须带 Authorization: Bearer <token>
# register = ["text", "image"]   # 注册类：仅处理声明的段类型

# OneBot v11 —— 正向 WS（机器人作客户端主动连平台；要用正向就把上面 reverse 段
# 注释掉，改用下面这段并填 ws_url）：
# [[adapters]]
# module = "kourichat.adapter.onebot"
# [adapters.config]
# mode = "forward"
# ws_url = "ws://127.0.0.1:3001"  # NapCat 等平台的「正向 ws」地址
# token = ""                      # 平台要求的 AccessToken
# register = ["text", "image"]

# OpenClaw 适配器 —— 对接 openclaw-onebotv11（OneBot v11 网关，默认 http://127.0.0.1:8765）：
# 登录走 OneBot action（weixin_login 取二维码 / weixin_login_refresh 刷新 /
# weixin_logout 登出），结果由 WS notice.login_success / login_qr_expired 广播；
# token_expired 标记失效 + 手动重登；已登录账号本地持久化（elixir Store）。
# 前置：先启动网关 `openclaw-onebotv11 run`，把其 config.json 里自动生成的 accessToken 填到下面。
[[adapters]]
module = "kourichat.adapter.openclaw"
[adapters.config]
gateway_url = "http://127.0.0.1:8765"  # weixin-gateway 地址
access_token = ""                      # 网关 config.json 的 accessToken（留空则连上但动作会 401）
data_dir = "./data"                    # 账号镜像持久化目录（openclaw-accounts/）
autologin = true                       # 无本地账号时自动发起扫码登录
poll_interval = 2.0                    # 兼容保留（新契约登录走 action+notice，不再轮询）
# register = ["text", "image"]

# 默认任务：echo 回显（可开关）。收到 `/echo` 后原样回显下一条消息，
# 这两条消息均被拦截（不进命令/大模型）；关闭后全部消息走正常流程。
# 必须放在 command 之前装配，拦截才生效。
[[plugins]]
module = "kourichat.logic.echo"
[plugins.config]
enabled = true                 # false = 关闭 echo，全部消息走正常流程

# 逻辑层：command 路由（未命中/未停止的消息续发 MESSAGE_PRIVATE/GROUP）
[[plugins]]
module = "kourichat.logic.command"
[plugins.config]
prefix = "/"

# 逻辑层：人设插件（装载 .krp 注册表 + 启用一个人设 + 注册其 /命令）
# personas_dir 下每个 *.krp 文件夹 = 一个人设（index.toml + heart/reason prompt +
# expressions + tools）；enable 指定启用哪个（缺省取第一个）。记忆按
# <会话key>|<人设id> 隔离，切换人设即换一套记忆。
[[plugins]]
module = "kourichat.logic.persona"
[plugins.config]
personas_dir = "./personas"
enable = ""            # 例如 "tester"

# 逻辑层：会话处理（私聊/群聊 → elixir Session 流式回送；忙时新消息打断/加话）
[[plugins]]
module = "kourichat.logic.session"
[plugins.config]
stop_word = "/stop"    # 强断：保留已说的话，丢弃未合成部分

# 会话工厂：key → elixir Session（复用 elixir 引擎/Store；注入 kourichat 记忆器+人设工具）
[[plugins]]
module = "kourichat.llm.factory"
[plugins.config]
base_url = "https://api.openai.com/v1"
api_key = "sk-..."
model = "gpt-4o-mini"
data_dir = "./data"
# —— 对话窗口：未归档轮达 max_count 触发压缩，保留最近 keep_count 轮全文 ——
keep_count = 20
max_count = 60
# —— 情感记忆：轮初注入 & emotion_latest/older 返回条数 ——
emotion_boot_count = 10
# —— 逐句打字节奏（第一句即发；后续句间隔随机 min~max 秒）——
# typing_base_min = 0.6
# typing_base_max = 1.5
# —— 长期记忆压缩用的概要人设（缺省内置通用概要提示词）——
# summary_prompt = "你是概要人设：……"
# role_prompt_overrides = { heart = "……", reason = "……", synth = "……" }

# WebUI 控制台（Vue 前端 + JSON API，随 run 启动）：
# 扫码登录/账号状态/聊天调试/日志/配置编辑。前端产物在 frontend/dist
# （改动前端后需在 frontend/ 执行 npm run build）。
[[plugins]]
module = "kourichat.webui"
[plugins.config]
host = "127.0.0.1"
port = 8080
# static_dir = "./frontend/dist"   # 前端构建产物目录（缺省同值）

'''


def _write_template(path: Path) -> None:
    """把默认配置模板写到 path（建父目录）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")


def ensure_config(config_path: str | Path = "kourichat.toml") -> bool:
    """若配置文件不存在则自动初始化生成默认配置模板。

    返回 True 表示新生成了模板，False 表示已存在。
    """
    path = Path(config_path)
    if not path.exists():
        _write_template(path)
        print(f"未检测到配置文件，已自动初始化配置模板：{path}", file=sys.stderr)
        return True
    return False


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists():
        print(f"已存在：{path}（不覆盖）", file=sys.stderr)
        return 1
    _write_template(path)
    print(f"已生成配置模板：{path}")
    return 0


async def _run(config_path: str) -> int:
    ensure_config(config_path)
    cfg = Config(config_path).load()
    # 日志：控制台等级/格式可配；log_dir 非空则按天落盘（全局异常也进日志）
    core = cfg.get("core") or {}
    configure_logging(
        log_level=str(core.get("log_level", "INFO")),
        console_format=core.get("log_console_format"),
        log_dir=core.get("log_dir"),
        rotation=str(core.get("log_rotation", "1 day")),
    )
    ctx = Context()
    ctx.provide("config", cfg)
    logger = LoguruLogger()
    ctx.provide("logger", logger)
    ctx.provide("events", Dispatcher())  # 事件调度器（串行 + stop + 上下文修饰）
    stop_event = asyncio.Event()
    ctx.provide("stop_event", stop_event)

    loop = asyncio.get_running_loop()
    loop.set_exception_handler(loop_exception_handler(logger))  # 后台 task 异常进日志
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows 部分信号不可用

    await assemble(ctx, cfg)  # adapter → logic → llm
    await stop_event.wait()  # 常驻：EOF / 信号触发
    await shutdown(ctx)  # 优雅退出
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    return asyncio.run(_run(args.config))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kourichat", description="KouriChat 1.5 框架")
    parser.add_argument("--config", "-c", default="kourichat.toml", help="配置文件路径（默认 kourichat.toml）")

    sub = parser.add_subparsers(dest="cmd", required=False)

    p_init = sub.add_parser("init", help="生成配置模板")
    p_init.add_argument("--path", default="kourichat.toml", help="生成的配置文件路径（默认 kourichat.toml）")
    p_init.set_defaults(func=_cmd_init)

    p_run = sub.add_parser("run", help="启动框架（常驻）")
    p_run.add_argument("--config", "-c", default="kourichat.toml", help="配置文件路径（默认 kourichat.toml）")
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "init":
        return _cmd_init(args)
    # "run" 或未给子命令 → 都直接运行（未初始化过会自动初始化）
    return _cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())

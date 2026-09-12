"""会话工厂插件：key → elixir Session（persona 感知、全量组合 elixir 抽象）。

组合关系（解耦：尽量复用 elixir，框架只做装配/注入）：
- Session 引擎（双核驱动 / 合成逐句 / 打字节奏 / interject·force_stop 打断）全部复用 elixir；
- 持久化全部走 elixir Store + JsonlDataSource：rounds/thinking/emotion/diary 落在
  主数据目录（每 session_id 一文件）；长期摘要落在**隔离目录** `data_dir/summaries`
  （共享一个 elixir Store 实例），满足「摘要写隔离 store 文件」；
- 记忆器（Emotion/LongTerm/Diary）与表情工具、.krp 用户工具由本插件装配注入。

命名空间：持久化 session_id = `<逻辑会话key>|<人设id>` —— 同逻辑会话启用不同人设
时记忆天然隔离（elixir Store 按 session_id 分文件）。
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

from elixir import Settings, new_session
from elixir.datasources.jsonl import JsonlDataSource
from elixir.providers.openai import OpenAIProvider
from elixir.roles import heart_role_prompt, reason_role_prompt
from elixir.store import Store

from .expressions import ExpressionListTool, ExpressionSendTool
from .memory import DiaryMemory, EmotionMemory, LongTermMemory, DEFAULT_SUMMARY_PROMPT
from ..logger import LoguruLogger
from ..persona import Persona

SUMMARIES_SUBDIR = "summaries"  # 长期摘要隔离 store 目录（相对 data_dir）


def _settings(cfg: dict[str, Any], data_dir: str, log_dir: str) -> Settings:
    """把插件 config 映射到 elixir Settings（缺省沿用 elixir 语义默认值）。"""
    return Settings(
        data_dir=data_dir,
        flush_interval=float(cfg.get("flush_interval", 5.0)),
        sentence_delimiter=str(cfg.get("sentence_delimiter", "\x1e")),
        disable_thinking=bool(cfg.get("disable_thinking", True)),
        logger_dir=log_dir,
        logger_level=str(cfg.get("logger_level", "INFO")).upper(),
        keep_count=int(cfg.get("keep_count", 20)),
        max_count=int(cfg.get("max_count", 60)),
        emotion_boot_count=int(cfg.get("emotion_boot_count", 10)),
        typing_base_min=float(cfg.get("typing_base_min", 0.6)),
        typing_base_max=float(cfg.get("typing_base_max", 1.5)),
        typing_char_factor=float(cfg.get("typing_char_factor", 0.0)),
        max_total_steps=int(cfg.get("max_total_steps", 8)),
        max_heart_self_loops=int(cfg.get("max_heart_self_loops", 3)),
        max_reason_self_loops=int(cfg.get("max_reason_self_loops", 3)),
        role_prompt_overrides=dict(cfg.get("role_prompt_overrides") or {}),
    )


def _provider(cfg: dict[str, Any]) -> OpenAIProvider | None:
    missing = [k for k in ("base_url", "api_key", "model") if not cfg.get(k)]
    if missing:
        return None
    return OpenAIProvider(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        model=cfg["model"],
        timeout=float(cfg.get("timeout", 60.0)),
        max_tokens=int(cfg.get("max_tokens", 1024)),
        disable_thinking=bool(cfg.get("disable_thinking", True)),
    )


def _compose_overrides(persona: Persona | None,
                       settings: Settings) -> Settings:
    """心核/智核人设 = .krp 人设文本 + elixir 内置操作规则（人设驱动风格不重复）。

    无 persona（未装配人设插件）时回落 config 的 role_prompt_overrides。
    """
    merged = dict(settings.role_prompt_overrides)
    if persona is not None:
        if persona.heart_prompt:
            merged["heart"] = persona.heart_prompt + "\n\n" + heart_role_prompt(settings)
        if persona.reason_prompt:
            merged["reason"] = persona.reason_prompt + "\n\n" + reason_role_prompt(settings)
    return replace(settings, role_prompt_overrides=merged)


def _session_tools(persona: Persona | None,
                   holder: dict[str, Any]) -> list[Any]:
    """装配本会话工具：.krp tools 用户工具 + （有人设表情时）表情列表/发送工具。"""
    tools: list[Any] = []
    if persona is not None:
        tools.extend(persona.tools)
        if persona.expressions:
            exprs = persona.expressions
            tools.append(ExpressionListTool(exprs))
            tools.append(ExpressionSendTool(holder, exprs))
    return tools


def _active_persona(ctx: Any) -> Persona | None:
    """取启用中的人设（persona 插件提供的服务；未装配返回 None → 内置人设）。"""
    persona = ctx.get("persona.active")
    return persona if isinstance(persona, Persona) else None


async def apply(ctx: Any, config: dict[str, Any] | None = None) -> Any:
    cfg = config or {}
    data_dir = str(cfg.get("data_dir", "./data"))
    log_dir = str(cfg.get("log_dir", "./logs"))
    logger = ctx.get("logger") or LoguruLogger()
    provider = _provider(cfg)  # 缺配置时允许先启动，引导页保存后再热重载
    settings = _settings(cfg, data_dir, log_dir)
    summary_prompt = str(cfg.get("summary_prompt") or DEFAULT_SUMMARY_PROMPT)

    # 长期摘要隔离 store：data_dir/summaries（共享一个 Store 实例，全会话复用）
    summaries_dir = os.path.join(data_dir, SUMMARIES_SUBDIR)
    summary_store = Store(JsonlDataSource(summaries_dir), settings)
    await summary_store.start()

    sessions: dict[str, Any] = {}

    def get_session(key: str) -> Any:
        """取（或建）key 的 elixir Session。

        持久化命名空间 = `key|<persona.id>`：同 key 换人设 → 记忆文件不同。
        """
        persona = _active_persona(ctx)
        pid = persona.id if persona is not None else ""
        skey = f"{key}|{pid}" if pid else key
        if skey in sessions:
            return sessions[skey]
        holder: dict[str, Any] = {}
        sess_settings = _compose_overrides(persona, settings)
        session = new_session(
            skey,
            settings=sess_settings,
            data_source=JsonlDataSource(data_dir),
            llm=provider,
            logger=logger,
            memories=[],  # 默认记忆器关闭，下面注入 kourichat 记忆器
            tools=[],
        )
        # 装配记忆器（构造即绑定本 session）与工具（含表情 holder）
        session.memories = [
            LongTermMemory(session, summary_store=summary_store,
                           summary_prompt=summary_prompt),
            EmotionMemory(session),
            DiaryMemory(session),
        ]
        session.tools = _session_tools(persona, holder)
        session._kouri_expr = holder
        try:
            session._check_duplicates()
        except Exception as exc:
            raise RuntimeError(
                f"人设 {pid or '(内置)'} 装配失败（工具名冲突？）：{exc}") from exc
        sessions[skey] = session
        logger.info("session_created", id=skey, persona=pid or "(builtin)")
        return session

    async def dispose() -> None:
        for s in sessions.values():
            await s.store.stop()
        await summary_store.stop()
        if hasattr(provider, "aclose"):
            await provider.aclose()

    ctx.provide("llm.factory", get_session)
    return dispose

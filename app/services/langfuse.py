"""Langfuse 可选观测封装。

生产环境可以记录聊天 Trace、模型 generation 和 embedding 调用；测试 harness
默认关闭，避免测试输入或输出发送到外部观测平台。这里不记录原始 CoT。
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator
from typing import Any

from app.core.config import Settings


class LangfuseService:
    """把 Langfuse SDK 的可选初始化和 observation 生命周期集中管理。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        if not settings.langfuse_enabled:
            return
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return
        try:
            from langfuse import get_client

            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
            os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
            os.environ.setdefault("LANGFUSE_BASE_URL", settings.langfuse_base_url)
            os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", settings.langfuse_tracing_environment)
            os.environ.setdefault("LANGFUSE_SAMPLE_RATE", str(settings.langfuse_sample_rate))
            self.client = get_client()
        except Exception:
            # 观测平台不可用不能阻断聊天主流程。
            self.client = None

    @contextlib.contextmanager
    def observation(
        self,
        name: str,
        as_type: str = "span",
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> Iterator[Any]:
        if self.client is None:
            yield None
            return
        kwargs: dict[str, Any] = {"name": name, "as_type": as_type}
        if input is not None:
            kwargs["input"] = input
        if metadata:
            kwargs["metadata"] = metadata
        if model:
            kwargs["model"] = model
        try:
            observation_context = self.client.start_as_current_observation(**kwargs)
            observation = observation_context.__enter__()
        except Exception:
            # Langfuse SDK 自身不应影响业务；调用方仍会正常返回模型结果。
            yield None
            return
        try:
            yield observation
        except BaseException:
            try:
                observation_context.__exit__(*sys.exc_info())
            except Exception:
                pass
            raise
        else:
            try:
                observation_context.__exit__(None, None, None)
            except Exception:
                pass


def langfuse(settings: Settings) -> LangfuseService:
    return LangfuseService(settings)

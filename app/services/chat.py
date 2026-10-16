"""聊天请求服务。

连接 API 层与 AgentHarness，负责执行一次聊天、保存助手消息，并把最终回复
封装成 SSE 流事件返回给前端。
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy.orm import Session

from app.agents.events import AgentEvent, AgentEventType
from app.agents.harness import MindBridgeAgentHarness
from app.core.config import Settings
from app.models.entities import UserAccount
from app.schemas.dtos import ChatRequest, ChatStreamEvent
from app.services.ai import AiClient
from app.services.langfuse import LangfuseService


logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.ai = AiClient(settings)
        self.agent_harness = MindBridgeAgentHarness(db, settings)
        self.telemetry = LangfuseService(settings)

    async def stream_chat(self, user: UserAccount, request: ChatRequest):
        with self.telemetry.observation(
            "mindbridge.chat",
            as_type="agent",
            input={"message": self.agent_harness.privacy.sanitize(request.message)},
            metadata={"user_id": str(user.id), "session_id": request.sessionId or "new"},
        ) as trace:
            async for chunk in self._stream_chat_impl(user, request):
                yield chunk
            if trace is not None:
                try:
                    trace.update(output={"status": "completed"})
                except Exception:
                    pass

    async def _stream_chat_impl(self, user: UserAccount, request: ChatRequest):
        yield progress_event("prepare", "正在准备本轮对话")
        await asyncio.sleep(0)
        yield progress_event("sanitize", "正在进行隐私脱敏和会话准备")
        await asyncio.sleep(0)
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        event_counter = 0

        def on_agent_event(event: AgentEvent) -> None:
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        run_task = asyncio.create_task(
            asyncio.to_thread(self.agent_harness.run, user, request, on_agent_event)
        )
        while not run_task.done():
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            event_counter += 1
            yield progress_event(f"agent-event-{event_counter}", public_event_message(event), status="done")
        outcome = await run_task
        while not event_queue.empty():
            event_counter += 1
            yield progress_event(f"agent-event-{event_counter}", public_event_message(event_queue.get_nowait()), status="done")
        yield sse("meta", ChatStreamEvent(type="meta", sessionId=outcome.session.public_id).model_dump(by_alias=True))
        if outcome.retrieved_knowledge:
            yield progress_event("knowledge", f"已检索到 {len(outcome.retrieved_knowledge)} 条相关知识")
            await asyncio.sleep(0)
        yield progress_event("response", "正在生成最终回复")
        await asyncio.sleep(0)
        assistant = []
        async for token in self.ai.stream(outcome.response_messages):
            assistant.append(token)
            yield sse("token", ChatStreamEvent(type="token", sessionId=outcome.session.public_id, content=token).model_dump())
        if not assistant:
            # 模型可能只返回了被隐藏的 reasoning_content，或在输出上限内没有产生最终答案。
            # 不把内部 reasoning 展示给用户，而是给出明确的可重试提示，避免出现空白气泡。
            fallback = "抱歉，这次没有生成有效回复，请稍后重试。"
            assistant.append(fallback)
            yield sse("token", ChatStreamEvent(type="token", sessionId=outcome.session.public_id, content=fallback).model_dump())
        if assistant:
            self.agent_harness.save_assistant_message(user, outcome.session, "".join(assistant))
        try:
            await self.agent_harness.dispatch_tools(outcome.tool_plan)
            if outcome.tool_plan.requires_tools:
                yield progress_event("tools", "相关后台任务已提交")
        except Exception as exc:
            logger.warning(
                "Post-response tool dispatch failed for session=%s report_id=%s: %s",
                outcome.session.public_id,
                outcome.report_id,
                exc,
                exc_info=True,
            )
        yield progress_event("complete", "处理完成", status="done")
        yield sse("done", ChatStreamEvent(type="done", sessionId=outcome.session.public_id).model_dump())


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def progress_event(stage: str, message: str, status: str = "running") -> str:
    """构造面向用户的安全进度事件，不包含模型原始 reasoning。"""
    return sse(
        "progress",
        {"type": "progress", "stage": stage, "message": message, "status": status},
    )


def public_event_message(event: AgentEvent) -> str:
    """把真实 Agent 事件转换成可公开展示的进度摘要。"""
    actor = event.actor or "CoordinatorAgent"
    if event.type == AgentEventType.ROUND_STARTED:
        return f"{actor} 开始新一轮协作"
    if event.type == AgentEventType.TASK_CREATED:
        return f"{actor} 创建任务：{event.message or '待处理任务'}"
    if event.type == AgentEventType.TASK_CLAIMED:
        return f"{actor} 接手任务"
    if event.type == AgentEventType.TASK_CLOSED:
        return f"{actor} 完成任务"
    if event.type == AgentEventType.ARTIFACT_PUBLISHED:
        return f"{actor} 发布处理结果"
    if event.type == AgentEventType.CRITIQUE_PUBLISHED:
        return f"{actor} 完成安全复核"
    if event.type == AgentEventType.FINAL_ACCEPTED:
        return f"{actor} 接受最终回复"
    if event.type == AgentEventType.SAFETY_OVERRIDE:
        return "SafetyAgent 启用安全优先处理"
    if event.type == AgentEventType.BUDGET_EXHAUSTED:
        return "协作达到安全执行上限"
    return f"{actor} 完成协作步骤"

"""
流式 Session Loop（基于 astream_events）。
负责：
1. 启动/恢复流式中控图；
2. 将 astream_events 原生事件转换为标准 SSE payload；
3. 处理 interrupt（通过 on_custom_event 捕获）。
"""

import json
from typing import AsyncGenerator

from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from app.controller_stream.master_graph_stream import build_master_graph_stream


# ---------- 内存 checkpointer ----------
_checkpointer = MemorySaver()


def _get_graph():
    """获取母图实例。"""
    return build_master_graph_stream(checkpointer=_checkpointer)


# ---------- 事件格式化 ----------

def _format_event(event: dict) -> dict | None:
    """将 astream_events 原生事件转换为标准 SSE payload。"""
    event_type = event.get("event", "")
    name = event.get("name", "")
    data = event.get("data", {})

    if event_type == "on_chain_start":
        if name in ("LangGraph", "__start__", "__end__"):
            return None
        return {"type": "node_start", "name": name, "data": {}}

    if event_type == "on_chain_end":
        if name in ("LangGraph", "__start__", "__end__"):
            return None
        return {"type": "node_end", "name": name, "data": {}}

    if event_type == "on_chat_model_stream":
        chunk = data.get("chunk") if isinstance(data, dict) else None
        if chunk is None:
            return None
        token = getattr(chunk, "content", str(chunk))
        if not token:
            return None
        return {"type": "token", "name": name, "data": {"token": token}}

    if event_type == "on_custom_event":
        payload = data if isinstance(data, dict) else {}

        if name == "token":
            return {"type": "token", "name": payload.get("node", ""), "data": {"token": payload.get("token", "")}}

        if name == "interrupt":
            interrupt_type = payload.get("type", "human_review")
            out = {
                "current_solution": payload.get("current_solution", ""),
                "current_content": payload.get("current_content", "") or payload.get("content", ""),
                "revision_count": payload.get("revision_count", 0),
                "message": payload.get("message", ""),
            }
            if interrupt_type == "solution_review":
                out["solutions_json"] = payload.get("solutions_json", "[]")
            elif interrupt_type == "single_review":
                out["evaluation_passed"] = payload.get("evaluation_passed", False)
                out["evaluation_report"] = payload.get("evaluation_report", "")
                out["rejection_reason"] = payload.get("rejection_reason", "")
            return {"type": "interrupt", "name": interrupt_type, "data": out}

        if name == "progress":
            return {"type": "progress", "name": payload.get("node", ""), "data": payload}

        if name == "disclosure_done":
            return {"type": "disclosure_done", "name": "disclosure", "data": payload}

        return {"type": "custom", "name": name, "data": payload}

    return None


# ---------- 核心流式接口 ----------

async def stream_session(
    document: str,
    thread_id: str = "user-session-001",
) -> AsyncGenerator[dict, None]:
    """启动新会话，流式返回所有事件。"""
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {
        "document": document,
        "tech_structure": "",
        "solution": "",
        "solutions_json": "",
        "selected_index": -1,
        "current_solution": "",
        "user_intent": "",
        "user_feedback": "",
        "evaluation_report": "",
        "evaluation_passed": False,
        "rejection_reason": "",
        "revision_count": 0,
        "final_disclosure": "",
        "thread_id": thread_id,
    }

    async for event in graph.astream_events(inputs, config, version="v2"):
        formatted = _format_event(event)
        if formatted is not None:
            yield formatted


async def resume_session(
    thread_id: str,
    decision: dict,
) -> AsyncGenerator[dict, None]:
    """恢复被 interrupt 暂停的会话。"""
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    seen_interrupt = False
    async for event in graph.astream_events(
        Command(resume=decision),
        config,
        version="v2",
    ):
        if (
            not seen_interrupt
            and event.get("event") == "on_custom_event"
            and event.get("name") == "interrupt"
        ):
            seen_interrupt = True
            continue

        formatted = _format_event(event)
        if formatted is not None:
            yield formatted

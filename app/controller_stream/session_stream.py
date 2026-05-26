"""
流式 Session Loop（基于 astream_events）。
负责：
1. 启动/恢复流式中控图；
2. 将 astream_events 原生事件转换为标准 SSE payload；
3. 处理 interrupt（通过 on_custom_event 捕获）。
"""

import json
from typing import Any, AsyncGenerator

from langgraph.types import Command

from langgraph.checkpoint.memory import MemorySaver

from app.controller_stream.master_graph_stream import build_master_graph_stream


# 模块级别复用同一个 checkpointer，确保 start / resume 共享状态
_shared_checkpointer = MemorySaver()


def _get_graph():
    """获取共享 checkpointer 的母图实例。"""
    return build_master_graph_stream(checkpointer=_shared_checkpointer)


# ---------- 事件格式化 ----------

def _format_event(event: dict) -> dict | None:
    """将 astream_events 原生事件转换为标准 SSE payload。

    Args:
        event: astream_events 原始事件

    返回 None 表示该事件无需转发给前端。
    """
    event_type = event.get("event", "")
    name = event.get("name", "")
    data = event.get("data", {})

    if event_type == "on_chain_start":
        # 过滤掉顶级 graph 本身的事件，只保留子节点
        if name in ("LangGraph", "__start__", "__end__"):
            return None
        return {"type": "node_start", "name": name, "data": {}}

    if event_type == "on_chain_end":
        if name in ("LangGraph", "__start__", "__end__"):
            return None
        # 不转发 output，避免子图返回 Command 等不可 JSON 序列化的对象导致 SSE 序列化失败
        return {
            "type": "node_end",
            "name": name,
            "data": {},
        }

    if event_type == "on_chat_model_stream":
        chunk = data.get("chunk") if isinstance(data, dict) else None
        if chunk is None:
            return None
        token = getattr(chunk, "content", str(chunk))
        if not token:
            return None
        return {"type": "token", "name": name, "data": {"token": token}}

    if event_type == "on_custom_event":
        # dispatch_custom_event(name, data) 在 astream_events 中:
        #   event="on_custom_event", name=第一个参数, data=第二个参数
        payload = data if isinstance(data, dict) else {}

        if name == "token":
            return {
                "type": "token",
                "name": payload.get("node", ""),
                "data": {"token": payload.get("token", "")},
            }

        if name == "interrupt":
            interrupt_type = payload.get("type", "human_review")
            data = {
                "current_solution": payload.get("current_solution", ""),
                "current_content": payload.get("current_content", "") or payload.get("content", ""),
                "revision_count": payload.get("revision_count", 0),
                "message": payload.get("message", ""),
            }

            if interrupt_type == "solution_review":
                data["solutions_json"] = payload.get("solutions_json", "[]")
            elif interrupt_type == "single_review":
                data["evaluation_passed"] = payload.get("evaluation_passed", False)
                data["evaluation_report"] = payload.get("evaluation_report", "")
                data["rejection_reason"] = payload.get("rejection_reason", "")

            return {
                "type": "interrupt",
                "name": interrupt_type,
                "data": data,
            }

        if name == "progress":
            return {
                "type": "progress",
                "name": payload.get("node", ""),
                "data": payload,
            }

        if name == "disclosure_done":
            return {
                "type": "disclosure_done",
                "name": "disclosure",
                "data": payload,
            }

        return {"type": "custom", "name": name, "data": payload}

    # 其他事件（on_chat_model_start, on_chat_model_end, on_tool_start 等）暂不转发
    return None


# ---------- 核心流式接口 ----------

async def stream_session(
    document: str,
    thread_id: str = "user-session-001",
) -> AsyncGenerator[dict, None]:
    """启动新会话，流式返回所有事件。

    遇到 interrupt 时，graph 暂停，流结束；前端收到 interrupt 事件后应调用 resume_session。
    """
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
    """恢复被 interrupt 暂停的会话。

    Args:
        thread_id: 会话标识（必须与启动时一致）
        decision: {"intent": str, "feedback": str}
    """
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    seen_interrupt = False
    async for event in graph.astream_events(
        Command(resume=decision),
        config,
        version="v2",
    ):
        # resume 阶段过滤掉被中断节点重新执行时 dispatch 的 interrupt，
        # 避免误导前端再次弹出决策面板。
        # 直接跳过第一个 interrupt 原始事件，同时标记 seen_interrupt，
        # 后续新节点（如 human_gate / post_eval_gate）产生的 interrupt 正常转发。
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


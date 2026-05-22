"""
流式中控图（MasterGraphStream）。
与原版 master_graph.py 拓扑一致，但所有 LLM 节点均使用流式版本，
并在 human_gate / post_eval_gate 中 dispatch_custom_event 通知前端中断。
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from langchain_core.callbacks import dispatch_custom_event

from app.controller.state import MasterState
from app.controller_stream.draft_workflow_stream import build_draft_workflow_stream
from app.controller_stream.revise_workflow_stream import build_revise_workflow_stream
from app.controller_stream.disclosure_node_stream import disclosure_node_stream
from app.controller_stream.evaluate_node_stream import evaluate_node_stream


# ---------- 子图实例（复用） ----------
_draft_workflow_stream = build_draft_workflow_stream()
_revise_workflow_stream = build_revise_workflow_stream()


# ---------- 母图节点封装 ----------
async def draft_node(state: MasterState):
    """调用流式初稿子图生成 draft_solution。"""
    result = await _draft_workflow_stream.ainvoke(
        {
            "document": state["document"],
            "tech_structure": "",
            "solution": "",
        }
    )
    return {
        "draft_solution": result["solution"],
        "current_solution": result["solution"],
        "revision_count": 0,
    }


async def revise_node(state: MasterState):
    """调用流式改进子图生成 revised_solution，传入不通过原因。"""
    result = await _revise_workflow_stream.ainvoke(
        {
            "document": state["document"],
            "evaluation_feedback": state.get("rejection_reason", ""),
            "tech_structure": "",
            "issues": "",
            "innovation": "",
            "solution": "",
        }
    )
    new_count = state.get("revision_count", 0) + 1
    return {
        "revised_solution": result["solution"],
        "current_solution": result["solution"],
        "revision_count": new_count,
    }


def inject_rejection_reason(state: MasterState):
    """透传节点：确保 rejection_reason 已进入 state。"""
    return {}


async def human_gate_stream(state: MasterState):
    """展示当前方案并等待用户决策（流式版本）。

    注意：interrupt() 必须在节点函数的最顶层直接调用，
    不能在子调用中调用，否则 LangGraph 无法正确追踪中断上下文。
    """
    current = (
        state.get("revised_solution")
        or state.get("draft_solution")
        or "暂无方案"
    )
    revision_count = state.get("revision_count", 0)

    dispatch_custom_event(
        "interrupt",
        {
            "type": "human_review",
            "current_solution": current,
            "revision_count": revision_count,
            "message": (
                "请确认是否用此方案去评估，或提出改进意见。"
                "如果评估已不通过，请确认是否基于不通过原因重新生成。"
            ),
        },
    )

    decision = interrupt({
        "type": "human_review",
        "current_solution": current,
        "revision_count": revision_count,
        "message": (
            "请确认是否用此方案去评估，或提出改进意见。"
            "如果评估已不通过，请确认是否基于不通过原因重新生成。"
        ),
    })

    return {
        "user_intent": decision.get("intent", ""),
        "user_feedback": decision.get("feedback", ""),
    }


async def post_eval_gate_stream(state: MasterState):
    """评估通过后询问用户（流式版本）。"""
    current = state.get("current_solution", "暂无方案")

    dispatch_custom_event(
        "interrupt",
        {
            "type": "post_eval_review",
            "current_solution": current,
            "message": (
                "评估已通过。请问：\n"
                "1) 生成交底书\n"
                "2) 再生成其他方案\n"
                "请输入你的选择。"
            ),
        },
    )

    decision = interrupt({
        "type": "post_eval_review",
        "current_solution": current,
        "message": (
            "评估已通过。请问：\n"
            "1) 生成交底书\n"
            "2) 再生成其他方案\n"
            "请输入你的选择。"
        ),
    })

    return {
        "user_intent": decision.get("intent", ""),
        "user_feedback": decision.get("feedback", ""),
    }


def _route_after_human_gate(state: MasterState) -> str:
    """条件路由：根据用户意图决定下一步。"""
    intent = state.get("user_intent", "")
    if intent == "confirm":
        return "disclosure"
    if intent in ("evaluate",):
        return "evaluate"
    return "revise"


def _route_after_evaluate(state: MasterState) -> str:
    """评估后路由。"""
    if state.get("evaluation_passed"):
        return "post_eval"
    return "inject_feedback"


def _route_after_post_eval(state: MasterState) -> str:
    """评估通过后的用户决策路由。"""
    intent = state.get("user_intent", "")
    if intent in ("disclosure", "confirm"):
        return "disclosure"
    return "revise"


def build_master_graph_stream(checkpointer=None):
    """构建并返回流式中控图（带 checkpointer）。

    Args:
        checkpointer: 可选的 checkpointer 实例。如果不传，会新建一个 MemorySaver。
                      为了让 start / resume 共享状态，应在模块级别复用同一个实例。
    """
    builder = StateGraph(MasterState)

    builder.add_node("draft", draft_node)
    builder.add_node("human_gate", human_gate_stream)
    builder.add_node("evaluate", evaluate_node_stream)
    builder.add_node("inject_feedback", inject_rejection_reason)
    builder.add_node("revise", revise_node)
    builder.add_node("post_eval_gate", post_eval_gate_stream)
    builder.add_node("disclosure", disclosure_node_stream)

    builder.add_edge(START, "draft")
    builder.add_edge("draft", "human_gate")

    builder.add_conditional_edges(
        "human_gate",
        _route_after_human_gate,
        {
            "evaluate": "evaluate",
            "revise": "revise",
            "disclosure": "disclosure",
        },
    )

    builder.add_conditional_edges(
        "evaluate",
        _route_after_evaluate,
        {
            "post_eval": "post_eval_gate",
            "inject_feedback": "inject_feedback",
        },
    )

    builder.add_conditional_edges(
        "post_eval_gate",
        _route_after_post_eval,
        {
            "disclosure": "disclosure",
            "revise": "revise",
        },
    )

    builder.add_edge("inject_feedback", "human_gate")
    builder.add_edge("revise", "human_gate")
    builder.add_edge("disclosure", END)

    if checkpointer is None:
        checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)

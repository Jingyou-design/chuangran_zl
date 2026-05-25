"""
流式中控图（MasterGraphStream）。
新拓扑：draft → evaluate_solutions → solution_gate ⏸️
         ├─ disclosure → END
         └─ revise → evaluate_single → single_result_gate ⏸️
              ├─ disclosure → END
              └─ revise → evaluate_single → ... (循环)
"""

import json

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from langchain_core.callbacks import dispatch_custom_event

from app.controller.state import MasterState
from app.controller_stream.draft_workflow_stream import build_draft_workflow_stream
from app.controller_stream.revise_workflow_stream import build_revise_workflow_stream
from app.controller_stream.disclosure_node_stream import disclosure_node_stream
from app.controller_stream.evaluate_solutions_node import evaluate_solutions_node
from app.controller_stream.evaluate_single_node import evaluate_single_node


# ---------- 子图实例（复用） ----------
_draft_workflow_stream = build_draft_workflow_stream()
_revise_workflow_stream = build_revise_workflow_stream()


# ---------- 母图节点封装 ----------

async def draft_node(state: MasterState):
    """调用流式初稿子图，返回 tech_structure + solution。"""
    result = await _draft_workflow_stream.ainvoke(
        {
            "document": state["document"],
            "tech_structure": "",
            "solution": "",
        }
    )
    return {
        "tech_structure": result.get("tech_structure", ""),
        "solution": result.get("solution", ""),
        "current_solution": result.get("solution", ""),
        "revision_count": 0,
        "solutions_json": "",
        "selected_index": -1,
    }


async def solution_gate_node(state: MasterState):
    """展示所有方案的评估结果，等待用户选择方案+操作。"""
    solutions_json = state.get("solutions_json", "[]")
    try:
        solutions = json.loads(solutions_json)
    except (json.JSONDecodeError, TypeError):
        solutions = []

    dispatch_custom_event(
        "interrupt",
        {
            "type": "solution_review",
            "solutions_json": solutions_json,
            "message": "请查看各方案评估结果，选择一个方案进行下一步操作。",
        },
    )

    decision = interrupt({
        "type": "solution_review",
        "solutions_json": solutions_json,
        "message": "请查看各方案评估结果，选择一个方案进行下一步操作。",
    })

    selected_index = decision.get("selected_index", -1)
    user_intent = decision.get("intent", "disclosure")
    user_feedback = decision.get("feedback", "")

    # 根据 selected_index 从 solutions_json 中提取对应方案的 content
    current_solution = ""
    if 0 <= selected_index < len(solutions):
        current_solution = solutions[selected_index].get("content", "")

    return {
        "selected_index": selected_index,
        "user_intent": user_intent,
        "user_feedback": user_feedback,
        "current_solution": current_solution,
    }


async def single_result_gate_node(state: MasterState):
    """展示 revise 后单方案评估结果，等待用户决策。"""
    current = state.get("current_solution", "暂无方案")
    passed = state.get("evaluation_passed", False)
    report = state.get("evaluation_report", "")
    reason = state.get("rejection_reason", "")

    dispatch_custom_event(
        "interrupt",
        {
            "type": "single_review",
            "current_solution": current,
            "evaluation_passed": passed,
            "evaluation_report": report,
            "rejection_reason": reason,
            "message": (
                f"改进后方案评估结果：{'通过' if passed else '不通过'}。"
                + (f" 原因：{reason}" if reason else "")
            ),
        },
    )

    decision = interrupt({
        "type": "single_review",
        "current_solution": current,
        "evaluation_passed": passed,
        "evaluation_report": report,
        "rejection_reason": reason,
        "message": (
            f"改进后方案评估结果：{'通过' if passed else '不通过'}。"
            + (f" 原因：{reason}" if reason else "")
        ),
    })

    return {
        "user_intent": decision.get("intent", "disclosure"),
        "user_feedback": decision.get("feedback", ""),
    }


async def revise_node(state: MasterState):
    """调用流式改进子图，传入当前方案和不通过原因。"""
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
        "current_solution": result.get("solution", ""),
        "revision_count": new_count,
    }


def _route_after_solution_gate(state: MasterState) -> str:
    """solution_gate 后的路由：disclosure 或 revise。"""
    intent = state.get("user_intent", "disclosure")
    if intent == "disclosure":
        return "disclosure"
    return "revise"


def _route_after_single_result_gate(state: MasterState) -> str:
    """single_result_gate 后的路由：disclosure 或 revise。"""
    intent = state.get("user_intent", "disclosure")
    if intent == "disclosure":
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
    builder.add_node("evaluate_solutions", evaluate_solutions_node)
    builder.add_node("solution_gate", solution_gate_node)
    builder.add_node("revise", revise_node)
    builder.add_node("evaluate_single", evaluate_single_node)
    builder.add_node("single_result_gate", single_result_gate_node)
    builder.add_node("disclosure", disclosure_node_stream)

    builder.add_edge(START, "draft")
    builder.add_edge("draft", "evaluate_solutions")
    builder.add_edge("evaluate_solutions", "solution_gate")

    builder.add_conditional_edges(
        "solution_gate",
        _route_after_solution_gate,
        {
            "disclosure": "disclosure",
            "revise": "revise",
        },
    )

    builder.add_edge("revise", "evaluate_single")
    builder.add_edge("evaluate_single", "single_result_gate")

    builder.add_conditional_edges(
        "single_result_gate",
        _route_after_single_result_gate,
        {
            "disclosure": "disclosure",
            "revise": "revise",
        },
    )

    builder.add_edge("disclosure", END)

    if checkpointer is None:
        checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)

"""
流式中控图（MasterGraphStream）。
新拓扑：draft → evaluate_solutions → solution_gate ⏸️
         ├─ disclosure → END
         ├─ revise → evaluate_single → single_result_gate ⏸️
         │    ├─ disclosure → END
         │    └─ revise → ... (循环)
         └─ regenerate → evaluate_solutions → solution_gate ⏸️ (循环)
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


from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv

load_dotenv()

_intent_llm = ChatDeepSeek(
    model="deepseek-chat",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=0,
)

_regenerate_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)


async def _parse_user_intent(user_input: str, solution_count: int) -> dict:
    """用 LLM 解析用户自然语言输入为结构化意图。

    Returns:
        {"intent": "disclosure"|"revise"|"regenerate", "selected_index": int, "feedback": str}
    """
    prompt = f"""你是意图解析助手。当前有{solution_count}个技术方案已评估完毕，用户正在查看评估结果。

用户输入：{user_input}

请解析用户意图，严格以以下 JSON 格式输出（不要加 markdown 代码块标记）：
{{
  "intent": "disclosure" | "revise" | "regenerate",
  "selected_index": 方案索引（0-based，-1表示未指定）,
  "feedback": "用户反馈内容摘要"
}}

规则：
- intent="disclosure"：用户想基于某个方案生成交底书（如"选方案2生成交底书"、"方案1出交底书"）
- intent="revise"：用户想改进某个方案（如"改进方案1"、"方案3再优化"）
- intent="regenerate"：用户想重新生成所有方案（如"重新生成"、"再来三个方案"、"换一批方案"）
- selected_index：如果用户明确指定了方案编号，转为0-based索引（方案1→0, 方案2→1）；未指定则填-1
- feedback：提取用户的具体反馈或需求"""
    response = _intent_llm.invoke(prompt)
    content = response.content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        filtered = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(filtered)
    import json as _json
    try:
        return _json.loads(content)
    except _json.JSONDecodeError:
        return {"intent": "regenerate", "selected_index": -1, "feedback": user_input}


async def solution_gate_node(state: MasterState):
    """展示所有方案的评估结果，等待用户选择方案+操作。支持按钮操作和自然语言对话。"""
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
            "message": "请查看各方案评估结果，选择一个方案进行下一步操作，或输入您的需求。",
        },
    )

    decision = interrupt({
        "type": "solution_review",
        "solutions_json": solutions_json,
        "message": "请查看各方案评估结果，选择一个方案进行下一步操作，或输入您的需求。",
    })

    selected_index = decision.get("selected_index", -1)
    user_intent = decision.get("intent", "disclosure")
    user_feedback = decision.get("feedback", "")

    # 如果是自然语言对话输入（intent="chat"），用 LLM 解析意图
    if user_intent == "chat" and user_feedback.strip():
        parsed = await _parse_user_intent(user_feedback.strip(), len(solutions))
        user_intent = parsed.get("intent", "regenerate")
        if parsed.get("selected_index", -1) >= 0:
            selected_index = parsed["selected_index"]

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


from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv

load_dotenv()

_regenerate_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)


async def regenerate_node(state: MasterState):
    """基于现有 tech_structure 重新生成多方案（不重新提取）。"""
    tech_structure = state.get("tech_structure", "")
    prompt = f"""你是一个专利工程师。请基于以下技术结构生成多个技术方案，方案必须紧扣 tech_features 中的核心技术特征，可适当利用 auxiliary_features 中的辅助特征。不要引入未列出的特征，只描述核心发明点和关键实现方式。

            技术结构：
            {tech_structure}

            请严格按以下 JSON 格式输出（不要加 markdown 代码块标记）：
            [
              {{"title": "方案1", "content": "方案1的详细描述..."}},
              {{"title": "方案2", "content": "方案2的详细描述..."}},
              {{"title": "方案3", "content": "方案3的详细描述..."}}
            ]

            生成3-4个方案，每个方案的 content 应包含核心发明点和关键实现方式，200字以内。
            只输出 JSON 数组，不要有多余解释。"""
    chunks = []
    async for chunk in _regenerate_llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    new_solution = "".join(chunks)
    return {
        "solution": new_solution,
        "current_solution": new_solution,
        "solutions_json": "",
        "selected_index": -1,
    }


def _route_after_solution_gate(state: MasterState) -> str:
    """solution_gate 后的路由：disclosure / revise / regenerate。"""
    intent = state.get("user_intent", "disclosure")
    if intent == "disclosure":
        return "disclosure"
    if intent == "regenerate":
        return "regenerate"
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
    builder.add_node("regenerate", regenerate_node)
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
            "regenerate": "regenerate",
        },
    )

    builder.add_edge("regenerate", "evaluate_solutions")
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

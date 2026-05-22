"""
改进生成子图（封装 stategraph_demo2.py 的逻辑）。
与初稿子图的区别：额外接收 evaluation_feedback，在缺陷分析节点重点参考。
输入：document, evaluation_feedback（可选）
输出：tech_structure, issues, innovation, solution
"""

import os
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv

load_dotenv()


# ---------- 子图内部状态 ----------
class ReviseState(TypedDict):
    document: str
    evaluation_feedback: str      # 来自母图的 rejection_reason
    tech_structure: str
    issues: str
    innovation: str
    solution: str


_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)


def _extract_node(state: ReviseState):
    prompt = f"""请从以下文档中提取关键技术点或结构信息。只输出提取结果，不要有多余解释。

            文档内容：
            {state['document']}

            提取的技术/结构："""
    response = _llm.invoke(prompt)
    return {"tech_structure": response.content}


def _issues_node(state: ReviseState):
    # feedback_hint = ""
    # if state.get("evaluation_feedback"):
    #     feedback_hint = (
    #         f"\n【特别说明】上一轮方案在专利评估中被指出存在以下问题，"
    #         f"请在本次缺陷分析中重点关注并避免：\n{state['evaluation_feedback']}\n"
    #     )

    prompt = f"""基于以下提取的技术/结构信息，分析技术缺陷，列举分析结果，不要有多余解释。

            分析的技术/结构：
            {state['tech_structure']}

            请输出列举分析结果："""
    response = _llm.invoke(prompt)
    return {"issues": response.content}


def _innovation_node(state: ReviseState):
    feedback_hint = ""
    if state.get("evaluation_feedback"):
        feedback_hint = (
            f"\n【特别说明】上一轮方案在专利评估中被指出存在以下问题，"
            f"请在创新点列举中重点关注并避免：\n{state['evaluation_feedback']}\n"
        )
    prompt = f"""针对以下提取的技术缺陷/不足，列举出实用性的创新点，不要有多余解释。{feedback_hint}

                提取的缺陷/不足：
                {state['issues']}

                请输出列举出实用性的创新点："""
    response = _llm.invoke(prompt)
    return {"innovation": response.content}


def _generate_node(state: ReviseState):
    prompt = f"""基于以下提取创新点，生成一个完整的技术方案。

            提取创新点：
            {state['innovation']}

            请输出详细方案："""
    response = _llm.invoke(prompt)
    return {"solution": response.content}


def build_revise_workflow():
    builder = StateGraph(ReviseState)
    builder.add_node("extract", _extract_node)
    builder.add_node("issues", _issues_node)
    builder.add_node("innovation", _innovation_node)
    builder.add_node("generate", _generate_node)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "issues")
    builder.add_edge("issues", "innovation")
    builder.add_edge("innovation", "generate")
    builder.add_edge("generate", END)
    return builder.compile()

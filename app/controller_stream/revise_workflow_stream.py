"""
流式改进生成子图。
与原版区别：节点内部使用 _llm.astream() 并 dispatch_custom_event 发送 token 事件。
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
    evaluation_feedback: str
    tech_structure: str
    issues: str
    innovation: str
    solution: str


_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)


async def _extract_node(state: ReviseState):
    prompt = f"""请从以下文档中提取关键技术点或结构信息。只输出提取结果，不要有多余解释。

            文档内容：
            {state['document']}

            提取的技术/结构："""
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    return {"tech_structure": "".join(chunks)}


async def _issues_node(state: ReviseState):
    prompt = f"""基于以下提取的技术/结构信息，分析技术缺陷，列举分析结果，不要有多余解释。

            分析的技术/结构：
            {state['tech_structure']}

            请输出列举分析结果："""
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    return {"issues": "".join(chunks)}


async def _innovation_node(state: ReviseState):
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
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    return {"innovation": "".join(chunks)}


async def _generate_node(state: ReviseState):
    prompt = f"""基于以下提取创新点，生成一个完整的技术方案。

            提取创新点：
            {state['innovation']}

            请输出详细方案："""
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    return {"solution": "".join(chunks)}


def build_revise_workflow_stream():
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

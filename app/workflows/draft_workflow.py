"""
初稿生成子图（封装 stategraph_demo.py 的逻辑）。
输入：document
输出：tech_structure, solution
"""

import os
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv

load_dotenv()


# ---------- 子图内部状态 ----------
class DraftState(TypedDict):
    document: str
    tech_structure: str
    solution: str


_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)


def _extract_node(state: DraftState):
    prompt = f"""请从以下文档中提取关键技术点或结构信息。只输出提取结果，不要有多余解释。

                文档内容：
                {state['document']}

                提取的技术/结构："""
    response = _llm.invoke(prompt)
    return {"tech_structure": response.content}


def _generate_node(state: DraftState):
    prompt = f"""基于以下提取的技术/结构信息，生成一个完整的技术方案。

            提取的技术/结构：
            {state['tech_structure']}

            请输出详细方案："""
    response = _llm.invoke(prompt)
    return {"solution": response.content}


def build_draft_workflow():
    builder = StateGraph(DraftState)
    builder.add_node("extract", _extract_node)
    builder.add_node("generate", _generate_node)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "generate")
    builder.add_edge("generate", END)
    return builder.compile()

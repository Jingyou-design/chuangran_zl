"""
流式初稿生成子图。
与原版区别：节点内部使用 _llm.astream() 并 dispatch_custom_event 发送 token 事件，
使外层 astream_events 能够捕获并流给前端。
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


async def _extract_node(state: DraftState):
    prompt = f"""请从以下文档中提取关键技术点或结构信息。主要技术特征,次要技术特征,只输出提取结果，不要有多余解释。

                文档内容：
                {state['document']}

                提取的技术/结构："""
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    return {"tech_structure": "".join(chunks)}


async def _generate_node(state: DraftState):
    prompt = f"""基于以下提取的技术/结构信息，生成多个技术方案，只描述核心发明点和关键实现方式，不要展开成完整交底书。

            提取的技术/结构：
            {state['tech_structure']}

            方案如下："""
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    return {"solution": "".join(chunks)}


def build_draft_workflow_stream():
    builder = StateGraph(DraftState)
    builder.add_node("extract", _extract_node)
    builder.add_node("generate", _generate_node)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "generate")
    builder.add_edge("generate", END)
    return builder.compile()

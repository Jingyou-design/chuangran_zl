"""
流式初稿生成子图。
输入：document
输出：tech_structure, solution
extract 拆为 LLM + Review（用户确认/修改），generate 只有 LLM 节点，直接交给母图 evaluate_solutions 评估。
"""
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langchain_core.callbacks import dispatch_custom_event
from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv

load_dotenv()


class DraftState(TypedDict):
    document: str
    tech_structure: str
    solution: str


_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)


# ---------- extract: LLM 提取 + 用户确认 ----------

async def _extract_llm_node(state: DraftState):
    """LLM 提取技术结构，不中断。"""
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


async def _extract_review_node(state: DraftState):
    """展示提取结果，让用户确认或修改。"""
    tech_structure = state["tech_structure"]
    dispatch_custom_event(
        "interrupt",
        {"type": "extract_review", "content": tech_structure, "message": "请确认或修改提取的技术结构"},
    )
    decision = interrupt(
        {"type": "extract_review", "content": tech_structure, "message": "请确认或修改提取的技术结构"},
    )
    if decision.get("feedback", "").strip():
        tech_structure = decision["feedback"].strip()
    return {"tech_structure": tech_structure}


# ---------- generate: LLM 生成（直接交给母图 evaluate_solutions） ----------

async def _generate_llm_node(state: DraftState):
    """LLM 生成技术方案，不中断。只用 tech_structure，不用 document。"""
    prompt = f"""你是一个专利工程师。请基于以下技术结构生成多个技术方案，方案必须紧扣这些技术特征，不要引入未列出的特征，只描述核心发明点和关键实现方式。

            技术结构：
            {state['tech_structure']}

            方案："""
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    return {"solution": "".join(chunks)}


def build_draft_workflow_stream():
    builder = StateGraph(DraftState)
    builder.add_node("extract_llm", _extract_llm_node)
    builder.add_node("extract_review", _extract_review_node)
    builder.add_node("generate_llm", _generate_llm_node)
    builder.add_edge(START, "extract_llm")
    builder.add_edge("extract_llm", "extract_review")
    builder.add_edge("extract_review", "generate_llm")
    builder.add_edge("generate_llm", END)
    return builder.compile()

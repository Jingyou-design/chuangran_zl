"""
流式初稿生成子图。
输入：document
输出：tech_structure (JSON), solution (JSON)
extract 拆为 LLM + Review（用户确认/修改），generate 只有 LLM 节点，直接交给母图 evaluate_solutions 评估。
"""
import json
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
    temperature=0.5,
)


def _try_parse_json(text: str) -> str:
    """尝试从 LLM 输出中提取 JSON 字符串。

    支持三种情况：
    1. 纯 JSON 文本
    2. ```json ... ``` 包裹的代码块
    3. 非 JSON 文本（原样返回）
    """
    text = text.strip()
    # 去掉 markdown 代码块包裹
    if text.startswith("```"):
        lines = text.splitlines()
        filtered = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(filtered).strip()
    # 尝试解析验证
    try:
        obj = json.loads(text)
        return json.dumps(obj, ensure_ascii=False)
    except json.JSONDecodeError:
        return text


# ---------- extract: LLM 提取 + 用户确认 ----------

async def _extract_llm_node(state: DraftState):
    """LLM 提取技术结构，输出 JSON 格式。"""
    prompt = f"""请从以下专利文档中提取技术特征，以 JSON 格式输出。

文档内容：
{state['document']}

请严格按以下 JSON 格式输出（不要加 markdown 代码块标记）：
{{
  "tech_features": ["核心技术特征1", "核心技术特征2", ...],
  "auxiliary_features": ["辅助技术特征1", ...]
}}

字段说明：
- tech_features：核心技术特征，指发明的关键结构、方法步骤、连接关系、控制逻辑等，是发明区别于现有技术的本质特征。必须提取。
- auxiliary_features：辅助技术特征，指对核心技术特征起支撑、优化作用的次级结构或步骤。如果没有明显可区分的辅助特征，填空数组 []。

注意：
- 只能写技术特征（结构/方法/关系），绝不能写效果或优点。
- auxiliary_features 可以为空数组，不要强行凑数。

只输出 JSON，不要有多余解释。"""
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    raw = "".join(chunks)
    return {"tech_structure": _try_parse_json(raw)}


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
    """LLM 生成多个技术方案，输出 JSON 格式。只用 tech_structure，不用 document。"""
    prompt = f"""你是一个专利工程师。请基于以下技术结构生成多个技术方案，方案必须紧扣 tech_features 中的核心技术特征，可适当利用 auxiliary_features 中的辅助特征。不要引入未列出的特征，只描述核心发明点和关键实现方式。

技术结构：
{state['tech_structure']}

请严格按以下 JSON 格式输出（不要加 markdown 代码块标记）：
[
  {{"title": "方案1", "content": "方案1的详细描述..."}},
  {{"title": "方案2", "content": "方案2的详细描述..."}},
  {{"title": "方案3", "content": "方案3的详细描述..."}}
]

生成3-4个方案，每个方案的 content 应包含核心发明点和关键实现方式，200字以内。
只输出 JSON 数组，不要有多余解释。"""
    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)
    raw = "".join(chunks)
    return {"solution": _try_parse_json(raw)}


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

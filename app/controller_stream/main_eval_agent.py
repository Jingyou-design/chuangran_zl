"""
主编排评估 Agent。
负责：调用子agent并行评估所有方案 → 汇总输出评估结论。
子agent 为 demo_agent（patenthub + x-class-doc 技能）。
"""

import asyncio
import json
import uuid
import sys
from pathlib import Path

from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv

load_dotenv()

# 确保项目根目录在路径中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from demo_agent import build_agent as build_eval_agent


async def _eval_one(index: int, solution: str) -> dict:
    """评估单个方案（内部函数，供并行调用）。"""
    eval_thread_id = f"sub-eval-{uuid.uuid4().hex[:8]}"
    agent = build_eval_agent()
    config = {"configurable": {"thread_id": eval_thread_id}}

    eval_prompt = f"""请对以下技术方案进行专利审查检索和新颖性/创造性评估。
                请使用 patenthub 技能进行现有技术检索，使用专利审查检索技能评估 X/Y 类文献。

                待评估方案：
                {solution}

                请输出：
                1) 检索策略；
                2) 对比文件列表；
                3) 新颖性结论；
                4) 创造性结论。

                最后请明确给出：【评估结果：通过 / 不通过】，如果不通过请说明具体原因及改进方向。
                """

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": eval_prompt}]},
        config=config,
    )

    messages = result.get("messages", [])
    assistant_msgs = [m for m in messages if getattr(m, "type", None) == "ai"]
    report = ""
    if assistant_msgs:
        report = getattr(assistant_msgs[-1], "content", str(assistant_msgs[-1]))
    else:
        report = str(result)

    return {"index": index, "report": report}


@tool
async def evaluate_all_solutions(solutions_json: str) -> str:
    """并行评估所有技术方案的专利新颖性和创造性。

    一次性接收所有方案，内部并行调用子agent评估每个方案。
    子agent会使用 patenthub 技能进行现有技术检索，使用专利审查检索技能评估 X/Y 类文献。

    Args:
        solutions_json: JSON 数组字符串，每个元素包含 title 和 content 字段。
            例如：[{"title":"方案1","content":"方案内容"}, ...]

    Returns:
        所有方案的评估报告，JSON 数组格式
    """
    try:
        solutions = json.loads(solutions_json)
    except json.JSONDecodeError:
        return "错误：solutions_json 格式无效"

    # 并行评估所有方案
    results = await asyncio.gather(
        *[_eval_one(i + 1, sol.get("content", "")) for i, sol in enumerate(solutions)]
    )

    # 组装结果
    output = []
    for sol, res in zip(solutions, results):
        output.append({
            "title": sol.get("title", f"方案{res['index']}"),
            "report": res["report"],
        })

    return json.dumps(output, ensure_ascii=False)


def build_main_eval_agent():
    """构建主编排评估agent。"""
    llm = ChatDeepSeek(
        model="deepseek-v4-pro",
        extra_body={"thinking": {"type": "disabled"}},
        temperature=0,
    )

    system_prompt = """你是一个专利评估主编排agent。你的任务是：
1. 接收多个技术方案
2. 调用 evaluate_all_solutions 工具一次性并行评估所有方案
3. 汇总所有评估结果，给出最终分析

请将所有方案一次性传给 evaluate_all_solutions 工具，不要逐个评估。
评估完成后，请输出汇总：

方案1：[通过/不通过] - [一句话结论]
方案2：[通过/不通过] - [一句话结论]
...

最后给出建议：推荐选择哪个方案生成交底书，以及各方案的主要优劣势。"""

    checkpointer = MemorySaver()

    agent = create_react_agent(
        llm,
        tools=[evaluate_all_solutions],
        prompt=system_prompt,
        checkpointer=checkpointer,
        name="main-eval-agent",
    )

    return agent

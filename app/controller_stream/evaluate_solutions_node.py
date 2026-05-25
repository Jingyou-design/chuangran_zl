"""
多方案评估节点。
解析 generate_llm 输出的 N 个方案，并行调用 demo_agent 评估，
汇总结果存入 solutions_json。
"""

import asyncio
import json
import re
import sys
from pathlib import Path

from langchain_core.callbacks import dispatch_custom_event

# 确保项目根目录在路径中，以便复用 demo_agent.py 的 build_agent
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from demo_agent import build_agent as build_eval_agent
from app.controller.report_parser import parse_evaluation_report


def parse_solutions(text: str) -> list[str]:
    """按 ### / ## 方案标题拆分 LLM 输出为多个方案。

    支持 "### 方案1"、"## 方案一"、"### 方案 1" 等格式。
    如果没有标题分割，则整体作为一个方案返回。
    """
    # 用 finditer 找到所有标题位置，按位置截取内容
    headers = list(re.finditer(r"(?:###|##)\s*方案\s*\d*[：:]*", text))

    if not headers:
        return [text.strip()] if text.strip() else []

    solutions = []
    for i, header in enumerate(headers):
        # 内容从标题结束位置开始，到下一个标题开始位置结束
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        content = text[start:end].strip()
        if content:
            solutions.append(content)

    # 如果截取结果只有0个，整体作为一个方案
    if not solutions:
        return [text.strip()] if text.strip() else []

    return solutions


async def evaluate_solutions_node(state: dict):
    """解析 N 个方案，并行调用 demo_agent 评估，返回汇总结果。

    期望 state 中包含：
    - solution: generate_llm 输出的原始方案文本
    - thread_id: 用于评估会话隔离

    输出：
    - solutions_json: JSON 字符串，每个方案包含 content/report/passed/reason
    """
    raw_solution = state.get("solution", "")
    thread_id = state.get("thread_id", "default-thread")
    eval_thread_id = f"{thread_id}-eval"

    solutions = parse_solutions(raw_solution)

    if not solutions:
        # 兜底：至少有一个空方案
        solutions = [raw_solution or "无方案"]

    dispatch_custom_event(
        "progress",
        {"node": "evaluate_solutions", "status": "started", "count": len(solutions)},
    )

    async def _evaluate_one(i: int, sol: str) -> dict:
        """评估单个方案。"""
        dispatch_custom_event(
            "progress",
            {"node": "evaluate_solutions", "status": "evaluating", "index": i, "total": len(solutions)},
        )

        agent = build_eval_agent()
        config = {"configurable": {"thread_id": f"{eval_thread_id}-{i}"}}

        eval_prompt = f"""请对以下技术方案进行专利审查检索和新颖性/创造性评估。
                    请使用 patenthub 技能进行现有技术检索，使用专利审查检索技能评估 X/Y 类文献。

                    待评估方案：
                    {sol}

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

        # 提取评估Agent的回复
        messages = result.get("messages", [])
        assistant_msgs = [m for m in messages if getattr(m, "type", None) == "ai"]
        report = ""
        if assistant_msgs:
            report = getattr(assistant_msgs[-1], "content", str(assistant_msgs[-1]))
        else:
            report = str(result)

        # 解析结构化结果
        parsed = await parse_evaluation_report(report)

        return {
            "content": sol,
            "report": report,
            "passed": parsed.get("passed", False),
            "reason": parsed.get("rejection_reason", ""),
        }

    # 并行评估所有方案
    results = await asyncio.gather(*[_evaluate_one(i, sol) for i, sol in enumerate(solutions)])

    dispatch_custom_event(
        "progress",
        {"node": "evaluate_solutions", "status": "completed", "count": len(results)},
    )

    return {"solutions_json": json.dumps(results, ensure_ascii=False)}

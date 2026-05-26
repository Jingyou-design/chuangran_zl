"""
多方案评估节点。
解析 generate_llm 输出的 N 个方案，交由主编排 agent 统一评估，
主编排 agent 拆分方案后逐个调用子agent（demo_agent）评估，最后汇总输出。
结果存入 solutions_json。
"""

import json
import re
import sys
from pathlib import Path

from langchain_core.callbacks import dispatch_custom_event

# 确保项目根目录在路径中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.controller_stream.main_eval_agent import build_main_eval_agent
from app.controller.report_parser import parse_evaluation_report


def parse_solutions(text: str) -> list[dict]:
    """从 generate_llm 输出中解析方案列表。

    优先尝试 JSON 数组格式：[{"title": "方案1", "content": "..."}, ...]
    Fallback: 按 ### / ## 方案标题拆分（兼容旧格式）。
    """
    text = text.strip()

    # 尝试 JSON 解析
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            solutions = []
            for item in obj:
                if isinstance(item, dict) and "content" in item:
                    solutions.append({
                        "title": item.get("title", ""),
                        "content": item["content"],
                    })
                elif isinstance(item, str):
                    solutions.append({"title": "", "content": item})
            if solutions:
                return solutions
    except json.JSONDecodeError:
        pass

    # Fallback: 按 ### / ## 方案标题拆分
    headers = list(re.finditer(r"(?:###|##)\s*方案\s*\d*[：:]*", text))
    if headers:
        solutions = []
        for i, header in enumerate(headers):
            start = header.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            content = text[start:end].strip()
            if content:
                solutions.append({"title": f"方案{i + 1}", "content": content})
        if solutions:
            return solutions

    # 兜底：整体作为一个方案
    if text:
        return [{"title": "方案1", "content": text}]
    return []


async def evaluate_solutions_node(state: dict):
    """解析 N 个方案，交由主编排 agent 评估，返回汇总结果。

    期望 state 中包含：
    - solution: generate_llm 输出（JSON 数组或 Markdown 文本）
    - thread_id: 用于评估会话隔离

    输出：
    - solutions_json: JSON 字符串，每个方案包含 title/content/report/passed/reason
    """
    raw_solution = state.get("solution", "")
    thread_id = state.get("thread_id", "default-thread")

    solutions = parse_solutions(raw_solution)

    if not solutions:
        solutions = [{"title": "方案1", "content": raw_solution or "无方案"}]

    dispatch_custom_event(
        "progress",
        {"node": "evaluate_solutions", "status": "started", "count": len(solutions)},
    )

    # 调用主编排 agent，传入 JSON 格式的方案列表
    solutions_input = json.dumps(solutions, ensure_ascii=False)
    prompt = f"请评估以下{len(solutions)}个技术方案，方案数据如下：\n{solutions_input}"

    # 调用主编排 agent
    agent = build_main_eval_agent()
    config = {"configurable": {"thread_id": f"{thread_id}-main-eval"}}

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config=config,
    )

    # 从 tool 返回中提取评估报告（evaluate_all_solutions 一次返回所有结果）
    messages = result.get("messages", [])
    tool_messages = [m for m in messages if getattr(m, "type", None) == "tool"]

    eval_reports = []
    if tool_messages:
        tool_content = getattr(tool_messages[0], "content", "")
        try:
            eval_reports = json.loads(tool_content)
        except json.JSONDecodeError:
            eval_reports = []

    results = []
    for i, sol in enumerate(solutions):
        report = ""
        if i < len(eval_reports) and isinstance(eval_reports[i], dict):
            report = eval_reports[i].get("report", "")

        parsed = await parse_evaluation_report(report)

        results.append({
            "title": sol.get("title", f"方案{i + 1}"),
            "content": sol.get("content", ""),
            "report": report,
            "passed": parsed.get("passed", False),
            "reason": parsed.get("rejection_reason", ""),
        })

    dispatch_custom_event(
        "progress",
        {"node": "evaluate_solutions", "status": "completed", "count": len(results)},
    )

    return {"solutions_json": json.dumps(results, ensure_ascii=False)}

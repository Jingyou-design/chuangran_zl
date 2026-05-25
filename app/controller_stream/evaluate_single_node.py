"""
单方案评估节点（revise 后使用）。
调用 demo_agent 对改进后的单个方案进行评估，
结果写入 evaluation_report / evaluation_passed / rejection_reason。
"""

import sys
from pathlib import Path

from langchain_core.callbacks import dispatch_custom_event

# 确保项目根目录在路径中，以便复用 demo_agent.py 的 build_agent
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from demo_agent import build_agent as build_eval_agent
from app.controller.report_parser import parse_evaluation_report


async def evaluate_single_node(state: dict):
    """对改进后的单个方案进行评估。

    期望 state 中包含：
    - current_solution: 待评估方案
    - thread_id: 用于评估会话隔离

    输出：
    - evaluation_report: 原始评估报告
    - evaluation_passed: bool
    - rejection_reason: str
    """
    solution = state.get("current_solution", "")
    thread_id = state.get("thread_id", "default-thread")
    eval_thread_id = f"{thread_id}-eval-single"

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

    dispatch_custom_event("progress", {"node": "evaluate_single", "status": "started"})

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

    dispatch_custom_event(
        "progress",
        {"node": "evaluate_single", "status": "completed", "passed": parsed.get("passed", False)},
    )

    return {
        "evaluation_report": report,
        "evaluation_passed": parsed.get("passed", False),
        "rejection_reason": parsed.get("rejection_reason", ""),
    }

"""
评估报告解析器。
将 demo_agent 输出的自然语言评估报告，结构化提取为 passed + rejection_reason。
"""

from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv

load_dotenv()

_llm = ChatDeepSeek(
    model="deepseek-chat",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=0,
)


REPORT_PARSE_PROMPT = """你是评估报告解析助手。请从以下专利评估报告中提取结构化信息。

评估报告原文：
{report}

请严格以以下 JSON 格式输出（不要加 markdown 代码块标记）：
{{
  "passed": true | false,
  "rejection_reason": "如果未通过，请用 2-3 句话总结不通过的核心原因（如创造性不足、新颖性被破坏等），用于指导后续改进；如果通过则填空字符串"
}}

注意：
- passed 为 true 的条件是报告中明确写出"通过"、"评估结果：通过"等。
- 如果报告中同时提到部分问题但总体结论是通过，也视为 passed=true，rejection_reason 留空。
- 如果报告中明确写"不通过"、"未通过"、"驳回"等，则 passed=false。
"""


async def parse_evaluation_report(report: str) -> dict:
    """解析评估报告。

    Returns:
        {"passed": bool, "rejection_reason": str}
    """
    prompt = REPORT_PARSE_PROMPT.format(report=report)
    response = _llm.invoke(prompt)
    content = response.content.strip()

    if content.startswith("```"):
        lines = content.splitlines()
        filtered = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(filtered)

    import json
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # 兜底：默认未通过，把报告前 500 字当原因
        result = {
            "passed": False,
            "rejection_reason": "评估报告解析失败，原文摘要：" + report[:500],
        }

    return result

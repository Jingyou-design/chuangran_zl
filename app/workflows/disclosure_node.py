"""
交底书生成节点（非子图，单一节点即可）。
基于当前方案 + 评估报告，生成专利交底书。
"""

from langchain_deepseek import ChatDeepSeek

from dotenv import load_dotenv

load_dotenv()

_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)


def disclosure_node(state: dict):
    """生成专利交底书。

    期望 state 中包含：
    - current_solution: 最终确认的技术方案
    - evaluation_report: 评估报告（可选，用于在交底书中回应审查意见）
    """
    solution = state.get("current_solution", "")
    report = state.get("evaluation_report", "")

    report_hint = ""
    if report:
        report_hint = (
            f"\n【评估报告摘要】\n{report}\n"
            "请在撰写交底书时，适当回应评估中指出的问题，突出本方案的创造性贡献。"
        )

    prompt = f"""你是一位资深专利代理师，请根据以下技术方案撰写一份完整的专利交底书。
            交底书应包含：技术领域、背景技术、发明内容（要解决的技术问题、技术方案、有益效果）、
            具体实施方式、附图说明、以及权利要求书草案。

            技术方案：
            {solution}
            {report_hint}

            请输出完整的交底书："""

    response = _llm.invoke(prompt)
    return {"final_disclosure": response.content}

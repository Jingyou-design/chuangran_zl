"""
流式交底书生成节点。
与原版区别：使用 _llm.astream() 并 dispatch_custom_event 发送 token 事件。
"""

from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv

load_dotenv()

_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)


async def disclosure_node_stream(state: dict):
    """生成专利交底书（流式版本）。

    期望 state 中包含：
    - current_solution: 最终确认的技术方案
    - evaluation_report: 评估报告（可选）
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

    chunks = []
    async for chunk in _llm.astream(prompt):
        content = getattr(chunk, "content", str(chunk))
        if content:
            chunks.append(content)

    return {"final_disclosure": "".join(chunks)}

"""
流式交底书生成节点。
与原版区别：使用 _llm.astream() 并 dispatch_custom_event 发送 token 事件。
生成完成后保存 MD 文件并通过自定义事件通知前端。
"""

from pathlib import Path

from langchain_deepseek import ChatDeepSeek
from langchain_core.callbacks import dispatch_custom_event
from dotenv import load_dotenv

load_dotenv()

_llm = ChatDeepSeek(
    model="deepseek-v4-pro",
    extra_body={"thinking": {"type": "disabled"}},
    temperature=1,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "files" / "disclosure_output"


async def disclosure_node_stream(state: dict):
    """生成专利交底书（流式版本）。

    期望 state 中包含：
    - current_solution: 最终确认的技术方案
    - evaluation_report: 评估报告（可选）
    - thread_id: 会话标识
    """
    solution = state.get("current_solution", "")
    report = state.get("evaluation_report", "")
    thread_id = state.get("thread_id", "unknown")

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

    disclosure_text = "".join(chunks)

    # 保存 MD 文件
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUTPUT_DIR / f"{thread_id}.md"
    md_path.write_text(disclosure_text, encoding="utf-8")

    # 通知前端交底书已保存
    dispatch_custom_event(
        "disclosure_done",
        {
            "file_path": str(md_path),
            "file_name": f"{thread_id}.md",
            "length": len(disclosure_text),
        },
    )

    return {"final_disclosure": disclosure_text}

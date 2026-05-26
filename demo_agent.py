#!/usr/bin/env python3
"""
Simple DeepAgents demo that loads the patenthub and x-class-doc skills.
"""

import asyncio

from dotenv import load_dotenv
from pathlib import Path

from langchain_deepseek import ChatDeepSeek
from deepagents.graph import create_agent
from deepagents.backends import LocalShellBackend
from deepagents.middleware import FilesystemMiddleware, SkillsMiddleware
from langchain.agents.middleware import TodoListMiddleware
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

root_dir = Path(__file__).parent.absolute()
skills_dir = root_dir / "skills"

def build_agent(model: str = "deepseek-chat"):
    backend = LocalShellBackend(root_dir=root_dir, inherit_env=True, virtual_mode=False)
    fs_middleware = FilesystemMiddleware(backend=backend)
    skills_middleware = SkillsMiddleware(
        backend=backend,
        sources=[str(skills_dir)]
    )

    checkpointer = MemorySaver()

    agent = create_agent(
        model=ChatDeepSeek(model="deepseek-v4-pro", extra_body={"thinking": {"type": "disabled"}}),
        system_prompt="""您是一位乐于助人的专利研究助理。
                        您能够使用文件系统工具（读取文件、写入文件、列出文件、通配符匹配、查找）和执行 shell 命令，此外还具备以下技能：
                        - 专利中心：通过 PatentHub API 搜索专利、获取专利信息以及查询法律状态。
                        - 国际专利分类搜索：从本地的 IPC 2026.01 树中查询国际专利分类号、层级结构和定义。
                        - 专利审查搜索：进行系统的专利审查搜索以评估新颖性和创造性步骤，并对检索到的文件进行分类（X、Y、A、E 等）。
                        当用户询问专利检索、专利详情或法律状态时，请使用 patenthub 技能。
                        当用户询问国际专利分类（IPC）分类、IPC 代码或技术主题与 IPC 符号的映射时，请使用 ipc-search 技能，访问 skills/ipc-search/references/IPC_Tree/。
                        当用户询问审查检索、新颖性评估、创造性步骤评估、现有技术策略或 X/Y 类文献检索时，请使用专利审查检索技能。
                        始终要简洁明了、条理清晰地回答问题。
                        重要提示：使用 glob 工具时，pattern 必须是相对路径（如 **/*.json），切勿使用绝对路径。
                        """,
        middleware=[fs_middleware, skills_middleware, TodoListMiddleware()],
        checkpointer=checkpointer,
        name="patent-research-agent",
    )
    return agent


async def main():
    agent = build_agent()
    thread_id = "demo-thread-001"
    config = {"configurable": {"thread_id": thread_id}}

    print("=" * 60)
    print("Patent Research Agent Demo")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 60)

    while True:
        user_input = input("\nUser: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )

        # Extract the last assistant message
        messages = result.get("messages", [])
        assistant_msgs = [m for m in messages if getattr(m, "type", None) == "ai"]
        if assistant_msgs:
            content = getattr(assistant_msgs[-1], "content", str(assistant_msgs[-1]))
            print(f"\nAgent: {content}")
        else:
            print(f"\nAgent: {result}")


if __name__ == "__main__":
    asyncio.run(main())

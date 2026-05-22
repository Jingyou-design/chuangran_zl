# zl-demo

## Project Overview

`zl-demo` is a Python-based interactive demo that builds a patent-research AI agent using the [DeepAgents](https://github.com/deepagents) framework. The agent is equipped with filesystem and shell execution capabilities, plus two domain-specific skills:

1. **patenthub** — Searches and retrieves Chinese and global patent data via the [PatentHub (专利汇)](https://www.patenthub.cn) API.
2. **x-class-doc** — Provides a methodology for identifying X-class prior-art documents (documents that alone destroy the novelty of a patent claim).

The agent is backed by DeepSeek (`deepseek-chat` by default) and uses LangGraph's in-memory checkpointer for thread state.

## Technology Stack

- **Language**: Python >=3.12 (pinned to 3.12 in `.python-version`)
- **Package Manager**: [uv](https://docs.astral.sh/uv/)
- **Core Dependencies**:
  - `deepagents>=0.5.2` — Agent graph, backends, and middleware
  - `langchain-deepseek>=1.0.1` — DeepSeek LLM integration
  - `dotenv>=0.9.9` — Environment variable loading
- **LLM Backend**: DeepSeek API (`deepseek-chat`)
- **Tracing**: LangSmith (optional, configured via `.env`)

## Project Structure

```
zl-demo/
├── pyproject.toml          # Project metadata and dependencies (uv)
├── uv.lock                 # Reproducible dependency lock file
├── .python-version         # Pins Python 3.12
├── .env                    # API keys and tokens (see Environment)
├── main.py                 # Placeholder entry point (prints "Hello from zl-demo!")
├── demo_agent.py           # **Main application** — builds and runs the patent agent
├── skills/                 # DeepAgents skill definitions
│   ├── patenthub/
│   │   ├── SKILL.md                 # Skill prompt / quick reference (bilingual EN/ZH)
│   │   ├── references/api_reference.md   # PatentHub API endpoint reference
│   │   └── scripts/patenthub_client.py   # Zero-dependency stdlib CLI client
│   └── x-class-doc/
│       └── SKILL.md                 # Skill prompt for X-class retrieval methodology
└── README.md               # Currently empty
```

## Build and Run Commands

Because this project uses `uv`, all operations should go through `uv`:

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Run the main demo agent
uv run python demo_agent.py

# Run the placeholder entry point
uv run python main.py

# Execute a PatentHub client command directly
uv run python skills/patenthub/scripts/patenthub_client.py search --query "石墨烯"
```

## Environment Variables

The following variables are expected in `.env` (do **not** commit this file):

| Variable | Purpose |
|----------|---------|
| `PATENTHUB_TOKEN` | Authentication token for PatentHub API |
| `DEEPSEEK_API_KEY` | API key for DeepSeek LLM |
| `LANGSMITH_TRACING` | Enable LangSmith tracing (`true` / `false`) |
| `LANGSMITH_ENDPOINT` | LangSmith API endpoint |
| `LANGSMITH_API_KEY` | LangSmith API key |
| `LANGSMITH_PROJECT` | LangSmith project name |

`demo_agent.py` calls `load_dotenv()` at startup, so these are automatically injected.

## Code Organization

- **`demo_agent.py`** constructs the agent graph:
  - `LocalShellBackend` — allows the agent to run shell commands in the project root.
  - `FilesystemMiddleware` — gives the agent read/write/list/grep/glob capabilities.
  - `SkillsMiddleware` — loads all skill packages under `skills/`.
  - `MemorySaver` — provides short-term conversational memory per `thread_id`.
- **`skills/`** follow the DeepAgents skill convention:
  - Each sub-directory is a self-contained skill.
  - `SKILL.md` is the skill manifest (YAML frontmatter + markdown documentation).
  - Executable scripts live under `scripts/` and are referenced by the skill docs.

## Testing Instructions

There are **no automated tests** in this repository at the moment. Validation is done manually:

1. Ensure `.env` is populated.
2. Run `uv run python demo_agent.py`.
3. Interact with the agent (e.g., ask it to search for a patent on PatentHub or explain X-class retrieval).

## Security Considerations

- **`.env` contains live API keys and tokens.** It is ignored by `.gitignore`, but verify it is never committed or logged.
- The agent runs with `LocalShellBackend(root_dir=root_dir, inherit_env=True, virtual_mode=False)`, meaning it can execute arbitrary shell commands with the user's environment. Only run the agent in a trusted environment.
- `demo_agent.py` includes the literal instruction `"**Use uv run**"` in the system prompt, so the agent will prefer `uv run` when invoking Python scripts.

## Notes for AI Agents

- Skill documentation (`SKILL.md` files) is written in a mix of English and Chinese. Use the language the user is communicating in.
- When the user asks for patent searches, the agent should invoke commands via `python scripts/patenthub_client.py <subcommand> ...` (preferably prefixed with `uv run` as instructed in the system prompt).
- When the user asks about X-class documents, novelty assessment, or prior-art strategy, the `x-class-doc` skill should be used instead of PatentHub direct queries.

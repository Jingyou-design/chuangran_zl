---
name: ipc-search
description: "Use this skill when the user asks about IPC (International Patent Classification) symbols, classification hierarchies, section/class/subclass definitions, or mapping technical topics to IPC codes. Triggers include: IPC lookup, IPC classification, patent classification, section/class/subclass query, mapping keywords to IPC, IPC tree navigation, IPC code meaning."
---

# IPC Search Skill

## Overview

This skill enables retrieval of IPC (International Patent Classification, 2026.01 edition) definitions and hierarchies by directly exploring the parsed text tree under `skills/ipc-search/references/IPC_Tree/`.

The raw official PDFs (`tables/IPC_2026.01_Section_*.pdf`) are also available as fallback authoritative references, but for fast structured queries the parsed tree is preferred.

## Directory Structure

`skills/ipc-search/references/IPC_Tree/` contains ~8,500 text files organized as a hierarchy:

```
skills/ipc-search/references/IPC_Tree/
├── A_人类生活必需
│   ├── info.txt
│   ├── A01_农业；林业；畜牧业；狩猎；诱捕；捕鱼
│   │   ├── info.txt
│   │   ├── A01B_农业或林业的整地；一般农业机械或农具的部件、零件或附件
│   │   │   ├── info.txt
│   │   │   ├── A01B1_00_手动工具.txt
│   │   │   ├── A01B1_02_锹；铲.txt
│   │   │   └── ...
│   │   └── ...
│   └── ...
├── B_作业；运输
├── ...
└── H_电学
```

**Hierarchy rules on disk:**
- **Section** — top-level directory, e.g. `G_物理`
- **Class** — second-level directory, e.g. `G08_信号装置`
- **Subclass** — third-level directory, e.g. `G08B_信号系统，如个人呼叫系统；指令发信装置；报警系统`
- **Main Group / Subgroup** — `.txt` files inside subclass directories, e.g. `G08B13_00_夜盗、偷窃或入侵者报警器.txt`

**Important naming convention:** On disk, the `/` in an IPC code is replaced with `_`. So `G08B13/00` becomes `G08B13_00` in filenames.

Each Section, Class, and Subclass directory contains an `info.txt` with metadata (`Code`, `Level`, `Title`, notes, and an index of children).

## Workflows

### 1. Exact lookup by IPC code

1. Normalize the code: strip spaces and replace `/` with `_`.
   - Example: `G08B 13/00` → `G08B13_00`
2. Use `glob` to find the matching file:
   - `glob skills/ipc-search/references/IPC_Tree/**/*G08B13_00*.txt`
3. If the code is a Section, Class, or Subclass, the result will be an `info.txt` inside the matching directory.
4. Use `read_file` on the matched path to view the full definition, title, notes, and subgroups.

### 2. Keyword search (Chinese or English)

Use `grep` recursively over all `.txt` files in the tree:

```bash
grep -r "报警器" skills/ipc-search/references/IPC_Tree/ --include="*.txt" -n | head -20
```

For English terms you can also match against filenames:

```bash
grep -r "alarm" skills/ipc-search/references/IPC_Tree/ --include="*.txt" -i -n | head -20
```

Once a relevant file is identified, use `read_file` on its path to read the full content.

### 3. Tree traversal (list children)

- **Section level** (e.g., list all Classes in Section G):  
  `ls skills/ipc-search/references/IPC_Tree/G_物理/`
- **Class level** (e.g., list all Subclasses in Class G08):  
  `ls skills/ipc-search/references/IPC_Tree/G_物理/G08_信号装置/`
- **Subclass level** (e.g., list all Main Groups / Subgroups in Subclass G08B):  
  `ls skills/ipc-search/references/IPC_Tree/G_物理/G08_信号装置/G08B_信号系统，如个人呼叫系统；指令发信装置；报警系统/`

Then read the `info.txt` of the parent node for a structured index, or read individual `.txt` files for detailed subgroup definitions.

### 4. Reading definitions

Use `read_file` on any `.txt` or `info.txt` path returned by `glob` or `grep`.

- `info.txt` files contain: `Code`, `Level`, `Section`, `Title`, a separator line, and then notes / children index.
- Subgroup `.txt` files contain: `Title`, `Code`, a separator line, and then a list of subgroups (one per line).

## Common glob patterns

| Intent | Pattern |
|--------|---------|
| Find exact code `G08B13/00` | `skills/ipc-search/references/IPC_Tree/**/*G08B13_00*.txt` |
| Find all files under Section G | `skills/ipc-search/references/IPC_Tree/G_物理/**/*.txt` |
| Find all `info.txt` for a class | `skills/ipc-search/references/IPC_Tree/**/*G08_*/info.txt` |
| Find all subgroup files in a subclass | `skills/ipc-search/references/IPC_Tree/G_物理/G08_信号装置/G08B_信号系统，如个人呼叫系统；指令发信装置；报警系统/*.txt` |

## Notes

- Always normalize `/` → `_` before forming glob patterns or grep filenames.
- If a user asks "What is the IPC for X?" or "Which IPC covers Y?", start with a `grep` keyword search, then narrow down with `read_file` on the most relevant hits.
- If the user supplies an exact IPC code, start with `glob` + `read_file` for precision.
- The original PDFs (`tables/IPC_2026.01_Section_*.pdf`) contain the full official text; refer to them only when the parsed tree lacks detail or when the user explicitly asks for the official PDF source.

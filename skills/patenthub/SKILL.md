---
name: patenthub
description: "Use this skill when the user wants to search patents, retrieve patent information, or query legal status via the PatentHub API. Triggers include: patent search, patent retrieval, legal status query, similar patents, citing patents, prior art search on PatentHub."
---

# PatentHub Patent Search Skill

## Overview

This skill provides patent search and retrieval capabilities using the PatentHub API.
It supports keyword-based patent search, basic patent information lookup, claims and description retrieval, citation analysis,
and similar patent discovery.

All API calls are made through `scripts/patenthub_client.py`.

## Quick Reference

| Task | Script Command |
|------|----------------|
| Search patents | `python scripts/patenthub_client.py search --query "..."` (supports advanced query syntax, see Search Expression Syntax below) |
| Get base info | `python scripts/patenthub_client.py base --id CN101864098B` |
| Get claims | `python scripts/patenthub_client.py claims --id CN101864098B` |
| Get description | `python scripts/patenthub_client.py desc --id CN101864098B` |
| Get legal info | `python scripts/patenthub_client.py tx --id CN101864098B` |
| Get citations | `python scripts/patenthub_client.py citing --id CN101864098B` |
| Get similar patents | `python scripts/patenthub_client.py like --id CN101864098B` |

## Workflow: General Patent Search

1. Run the `search` command with the user's keywords.
2. Parse the JSON result and extract the `patents` array.
3. Present results in a concise table (Title, Document Number, Date, Country).
4. If the user asks for more details on a specific patent, run `base`, `claims`, or `desc` as needed.
   > **Important**: The patent `id` obtained from `search` is only valid in detail endpoints for **60 minutes**.
   > Directly guessing an ID for `base` / `claims` / `desc` may result in a 215 error.

## Search Expression Syntax

The `/api/s` endpoint (i.e. the `search` command) supports advanced field-based queries. Basic rules:

- **Field qualification**: Use `field:value` for precise matching, e.g. `title:graphene`, `applicant:"Tsinghua University"`.
- **Boolean logic**: Supports `AND`, `OR`, `NOT`, and parentheses `()`; multiple terms separated by spaces are treated as `AND` by default.
- **Date ranges**: Date fields support range queries in the format `[start TO end]`, e.g. `applicationDate:[2014 TO 2015]`.
- **Phrase exact match**: Use double quotes to prevent automatic term splitting, e.g. `"aerospace engine"`.

### Common Search Field Reference

| Field | Alias | Description |
|------|-------|-------------|
| `type` | | Patent type |
| `countryCode` | `cc` | Country code, e.g. `CN`, `US` |
| `number` | `n` | Application/publication number |
| `applicationNumber` | `an` | Application number |
| `applicationDate` | `ad` | Application date |
| `applicationYear` | `ay` | Application year, e.g. `2015` |
| `documentNumber` | `dn` | Document number |
| `documentDate` | `dd` | Document date |
| `ipc` | | IPC classification symbol |
| `ipc1` ~ `ipc5` | | IPC section/class/subclass/main group/subgroup |
| `mainIpc` | | Main IPC symbol |
| `mainIpc1` ~ `mainIpc5` | | Main IPC section/class/subclass/main group/subgroup |
| `applicant` | | Applicant |
| `firstApplicant` | | First applicant |
| `applicantType` | | Applicant type: school, research institute, enterprise, other |
| `inventor` | `inv` | Inventor |
| `agency` | | Agency |
| `agent` | | Agent |
| `title` | `ti` / `t` | Patent title |
| `summary` | `ab` / `s` | Patent abstract |
| `claims` | `cl` / `c` | Claims text |
| `description` | `desc` / `d` | Description text |
| `ta` / `ts` | | Title + abstract |
| `tac` / `tsc` | | Title + abstract + claims |
| `tacd` / `tscd` | | Title + abstract + claims + description |
| `province` | | Province |
| `city` | | City |
| `legalStatus` | `ls` | Patent validity: substantive examination, valid, invalidated, published |

### Search Expression Examples

```
applicationYear:[2010 TO 2012] AND applicant:"Tsinghua University" AND graphene
legalStatus:"valid patent" AND province:"Beijing" AND graphene
inventor:"Yuan Xinsheng" AND inventor:"Zhou Mingjie" AND graphene
graphene AND NOT (countryCode:CN AND type:invention publication) AND NOT legalStatus:invalidated
```

> For complete field documentation and advanced usage, refer to the PatentHub official help: https://www.patenthub.cn/help/index.html

## Important Notes

- The `search` endpoint returns at most 1000 records (max 100 pages × 50 page size).
- Search pagination uses `--page` (`-p`) and `--page-size` (`-ps`), not `limit` / `offset`.
- When a script command fails, it returns JSON like `{"error": "...", "description": "...", "code": 215}`.
  Common error codes:
  - **215**: Invalid/expired patent ID. Re-run `search` to get a fresh ID.
  - **207**: Daily API limit exceeded.
  - **211**: Annual patent data limit exceeded.
  - **206**: No matching data found.
- For detailed API parameters, response schemas, and the full error code list, see `references/api_reference.md`.
- If the user explicitly asks for X-class document retrieval strategies, delegate to the `x-class-doc` skill instead.

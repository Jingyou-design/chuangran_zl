from typing_extensions import TypedDict
from typing import Literal


class MasterState(TypedDict):
    """中控图全局状态，贯通初稿、改进、评估、交底书全流程。"""

    # ---------- 原始输入 ----------
    document: str

    # ---------- 初稿工作流产物 ----------
    draft_solution: str

    # ---------- 当前生效方案 ----------
    current_solution: str

    # ---------- 用户意图（由外部对话Agent解析后写入） ----------
    user_intent: Literal["evaluate", "revise", "regenerate", "confirm", ""]
    user_feedback: str

    # ---------- 评估结果 ----------
    evaluation_report: str
    evaluation_passed: bool
    rejection_reason: str

    # ---------- 改进工作流产物 ----------
    revised_solution: str

    # ---------- 循环控制 ----------
    revision_count: int

    # ---------- 最终产物 ----------
    final_disclosure: str

    # ---------- 运行时 ----------
    thread_id: str

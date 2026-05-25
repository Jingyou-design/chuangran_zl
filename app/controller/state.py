from typing_extensions import TypedDict


class MasterState(TypedDict):
    """中控图全局状态，贯通初稿、评估、改进、交底书全流程。"""

    # ---------- 原始输入 ----------
    document: str

    # ---------- 初稿工作流产物 ----------
    tech_structure: str
    solution: str  # generate_llm 输出的原始方案文本（含多个方案）

    # ---------- 多方案评估结果（JSON字符串） ----------
    solutions_json: str  # [{"content":"...","report":"...","passed":true,"reason":""}, ...]

    # ---------- 用户选择 ----------
    selected_index: int  # 用户选中的方案索引（-1=未选）
    current_solution: str
    user_intent: str  # "disclosure" / "revise"
    user_feedback: str

    # ---------- 单方案评估（revise后使用） ----------
    evaluation_report: str
    evaluation_passed: bool
    rejection_reason: str

    # ---------- 循环控制 ----------
    revision_count: int

    # ---------- 最终产物 ----------
    final_disclosure: str

    # ---------- 运行时 ----------
    thread_id: str

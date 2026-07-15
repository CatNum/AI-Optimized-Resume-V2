"""Trace 日志字段中文备注（调试可读）。"""

from typing import Any

EVENT_ZH: dict[str, str] = {
    "agent.run.start": "Worker 运行开始",
    "agent.run.end": "Worker 运行结束",
    "tool.call": "工具调用",
    "skill.load": "Skill 加载",
    "coordinator.analyze": "入口路由选型",
    "gate.rule_hit": "闸门硬规则命中",
    "gate.llm_classify": "闸门 LLM 分类",
}

WORKER_ZH: dict[str, str] = {
    "identity": "身份智能体",
    "capability": "能力智能体",
    "market": "市场智能体",
    "opportunity": "岗位/机会智能体",
    "strategy": "策略智能体",
    "resume": "简历智能体",
    "asset": "资产智能体",
    "coordinator": "入口路由编排智能体",
}

TOOL_ZH: dict[str, str] = {
    "profile_patch": "档案补丁",
    "profile_get": "读取档案",
    "apply_proposed_patches": "应用待确认补丁",
    "load_skill": "加载 Skill",
    "list_skills": "列出 Skill",
    "market_research": "启动市场调研",
    "write_resume_html": "写入简历 HTML",
    "resume_read": "读取简历素材",
    "register_outputs_index": "登记产物索引",
    "delete_output": "删除产物",
    "delegate_worker": "派工 Worker",
    "match_gate_intent": "闸门意图匹配",
    "create_task_list": "创建任务列表",
    "create_task": "创建任务",
    "list_tasks": "列出任务",
    "claim_task": "认领任务",
    "complete_task": "完成任务",
    "apply_proposed_task_completions": "应用待确认任务完成",
}

SKILL_ZH: dict[str, str] = {
    "career-inner-exploration": "职业初探 Skill",
    "career-jd-alignment": "JD 对齐 Skill",
}

STATUS_ZH: dict[str, str] = {
    "ok": "成功",
    "error": "失败",
    "failed": "失败",
}

DETAIL_KEY_ZH: dict[str, str] = {
    "mode": "Skill 模式",
    "hash": "内容哈希",
    "code": "错误码",
    "message": "错误信息",
    "source": "选型来源",
    "workers": "派工队列",
    "list_type": "列表类型",
    "next_worker": "下一 Worker",
}

ANALYZE_SOURCE_ZH: dict[str, str] = {
    "llm": "LLM 分析",
    "fallback": "规则降级",
    "preset": "闸门/预设队列",
    "queue": "继续派工队列",
    "none": "未选中 Worker",
}

LIST_TYPE_ZH: dict[str, str] = {
    "jd": "JD 评估链",
    "explore": "职业初探",
}

MODE_ZH: dict[str, str] = {
    "exploration_first": "初探-首次",
    "exploration_review": "初探-复盘",
    "jd_alignment": "JD 对齐分析",
    "jd_plan": "JD 投递策略",
}

ERROR_CODE_ZH: dict[str, str] = {
    "delegate_blocked": "派工被规则拦截",
    "gate_blocked": "闸门未满足",
    "tool_not_allowed": "工具无权限",
    "skill_not_allowed": "Skill 无权限",
    "profile_patch_rejected": "档案补丁被拒绝",
    "invalid_html": "简历 HTML 格式无效",
    "chat_in_progress": "会话正在处理中",
    "session_expired": "会话已过期",
    "market_research_in_progress": "市场调研进行中",
    "market_result_confirmation_required": "市场结果待用户确认",
    "market_result_reference_missing": "缺少正式市场结果引用",
    "market_result_reference_conflict": "市场结果引用冲突",
    "market_result_version_mismatch": "市场结果版本不一致",
    "market_result_expired": "市场结果已过期",
    "market_result_deleted": "市场结果已删除",
}


def _tag(value: str | None, mapping: dict[str, str]) -> str | None:
    """处理tag。"""
    if value is None:
        return None
    label = mapping.get(value)
    if label:
        return f"{label} ({value})"
    return value


def _annotate_detail(detail: dict[str, Any]) -> dict[str, str]:
    """处理annotate detail。"""
    out: dict[str, str] = {}
    for key, raw in detail.items():
        key_label = DETAIL_KEY_ZH.get(key, key)
        if key == "mode" and isinstance(raw, str):
            mode_label = MODE_ZH.get(raw, raw)
            out[key_label] = f"{mode_label} ({raw})"
        elif key == "code" and isinstance(raw, str):
            code_label = ERROR_CODE_ZH.get(raw, raw)
            out[key_label] = f"{code_label} ({raw})"
        elif key == "source" and isinstance(raw, str):
            src_label = ANALYZE_SOURCE_ZH.get(raw, raw)
            out[key_label] = f"{src_label} ({raw})"
        elif key == "list_type" and isinstance(raw, str):
            lt_label = LIST_TYPE_ZH.get(raw, raw)
            out[key_label] = f"{lt_label} ({raw})"
        elif key == "next_worker" and isinstance(raw, str):
            out[key_label] = _tag(raw, WORKER_ZH) or raw
        elif key == "workers" and isinstance(raw, list):
            labels = [_tag(str(item), WORKER_ZH) or str(item) for item in raw]
            out[key_label] = " → ".join(labels) if labels else "（空）"
        elif isinstance(raw, str):
            out[key_label] = raw
        else:
            out[key_label] = str(raw)
    return out


def build_trace_summary(record: dict[str, Any]) -> str:
    """构造trace summary。"""
    event = record.get("event") or ""
    event_zh = EVENT_ZH.get(event, event)
    parts = [event_zh]

    worker = record.get("worker_id")
    if worker:
        parts.append(_tag(worker, WORKER_ZH) or worker)

    actor = record.get("actor")
    if actor and actor != worker:
        parts.append(f"执行者 {_tag(actor, WORKER_ZH) or actor}")

    tool = record.get("tool_name")
    if tool:
        parts.append(_tag(tool, TOOL_ZH) or _tag(tool, SKILL_ZH) or tool)

    status = record.get("status")
    if status:
        parts.append(_tag(status, STATUS_ZH) or status)

    latency = record.get("latency_ms")
    if latency is not None:
        parts.append(f"{latency}ms")

    detail = record.get("detail") or {}
    if detail.get("code"):
        parts.append(_tag(str(detail["code"]), ERROR_CODE_ZH) or str(detail["code"]))
    if record.get("event") == "coordinator.analyze":
        if detail.get("source"):
            parts.append(_tag(str(detail["source"]), ANALYZE_SOURCE_ZH) or str(detail["source"]))
        workers = detail.get("workers")
        if isinstance(workers, list) and workers:
            queue = " → ".join(_tag(str(w), WORKER_ZH) or str(w) for w in workers)
            parts.append(f"队列 {queue}")

    return " · ".join(parts)


def annotate_trace_record(record: dict[str, Any]) -> dict[str, Any]:
    """为 trace 记录附加 `_zh` 中文备注，保留原英文字段供程序解析。"""
    zh: dict[str, Any] = {"summary": build_trace_summary(record)}

    event = record.get("event")
    if event:
        zh["event"] = _tag(str(event), EVENT_ZH)

    for field, mapping in (
        ("worker_id", WORKER_ZH),
        ("actor", WORKER_ZH),
        ("tool_name", {**TOOL_ZH, **SKILL_ZH}),
        ("status", STATUS_ZH),
    ):
        tagged = _tag(record.get(field), mapping)
        if tagged:
            zh[field] = tagged

    detail = record.get("detail") or {}
    if detail:
        zh["detail"] = _annotate_detail(detail)

    return {**record, "_zh": zh}

"""缺少 LLM_API_KEY 时供 L1 测试使用的确定性 ReAct 替身实现。"""
import hashlib
from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result
from career_os.harness.explore_closure import (
    PHASE_IN_PROGRESS,
    PHASE_SEGMENT_COMPLETE,
)
from career_os.platform.tool.handlers.resume_html import sort_optimization_levels


def _next_explore_phase_status(worker_id: str, session_state: dict[str, Any]) -> str:
    """计算探索阶段的下一步状态。"""
    prior = (session_state.get("prior_results") or {}).get(worker_id) or {}
    if prior.get("phase_status") == PHASE_IN_PROGRESS:
        return PHASE_SEGMENT_COMPLETE
    return PHASE_IN_PROGRESS


def mock_run_worker_react(
    harness: Any,
    *,
    worker_id: str,
    goal: str,
    session_state: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """运行确定性的 ReAct Worker mock。"""
    session_id = session_state.get("session_id")

    if worker_id == "market":
        return finalize_worker_result(
            "market",
            {
                "mode": "plan_proposal",
                "user_visible_summary": "已生成市场调研条件，请确认方向、关键词、城市和年限口径。",
                "proposal": {
                    "directions": [
                        {
                            "direction_name": "LLM 应用开发工程师",
                            "boss_keywords": ["LLM 应用开发", "AI Agent 开发"],
                            "trends_keywords": ["LLM 应用", "AI Agent"],
                            "cities": [],
                            "experience_basis": "total",
                            "experience_min": 3,
                            "experience_max": 5,
                        }
                    ]
                },
            },
        )

    if worker_id == "opportunity":
        fingerprint = hashlib.sha256(goal.encode()).hexdigest()[:12]
        snapshots = [
            {
                "jd_fingerprint": fingerprint,
                "recommendation": "recommended",
                "summary": "与当前能力画像匹配度较高",
            }
        ]
        harness.execute_tool(
            "opportunity",
            "profile_patch",
            {"path": "market.opportunity_snapshots", "value": snapshots, "op": "set"},
            session_id=session_id,
        )
        return finalize_worker_result(
            "opportunity",
            {
                "recommendation": "recommended",
                "user_visible_summary": "JD 评估完成，建议继续策略制定。",
                "jd_fingerprint": fingerprint,
            },
        )

    if worker_id == "strategy":
        list_type = session_state.get("list_type") or context.get("list_type")
        payload: dict[str, Any] = {
            "user_visible_summary": "已给出三条路径与三时间维度策略。",
            "path_options": [
                {"id": "path_a", "label": "稳健投递", "summary": "匹配当前 JD", "risks": []}
            ],
            "three_horizons": {
                "apply_narrative": "先聚焦匹配 JD 投递",
                "horizon_1_2y": "强化云原生项目背书",
                "horizon_3_5y": "技术负责人方向",
            },
        }
        effective_list = list_type or session_state.get("list_type")
        if effective_list == "plan":
            pass
        elif effective_list in ("jd", "pipeline") and context.get(
            "requires_optimize_gate", True
        ):
            payload["gate_prompt"] = {
                "name": "optimize_confirm",
                "prompt": "是否确认按该 JD 优化简历？",
            }
        return finalize_worker_result("strategy", payload)

    if worker_id == "resume":
        levels = sort_optimization_levels(
            context.get("selected_optimization_levels") or ["标准"]
        )
        deliveries: list[dict[str, Any]] = []
        for level in levels:
            result = harness.execute_tool(
                "resume",
                "write_resume_html",
                {
                    "html": f"<html><body><h1>{level}</h1></body></html>",
                    "filename": f"resume_{level}.html",
                    "optimization_level": level,
                },
                session_id=session_id,
            )
            if hasattr(result, "code"):
                return {"worker_id": "resume", "status": "failed", "error": result.message}
            deliveries.append(result)
        harness.execute_tool(
            "resume",
            "profile_patch",
            {"path": "resume.last_optimization_levels", "value": levels, "op": "set"},
            session_id=session_id,
        )
        return finalize_worker_result(
            "resume",
            {
                "user_visible_summary": f"已生成 {len(deliveries)} 份简历 HTML。",
                "html_deliveries": deliveries,
            },
        )

    if worker_id == "identity":
        phase_status = _next_explore_phase_status(worker_id, session_state)
        pending = context.get("explore_intake_pending_fields") or []
        pending_labels = context.get("explore_intake_pending_labels") or {}
        if phase_status == PHASE_IN_PROGRESS and pending:
            labels = [pending_labels.get(key, key) for key in pending[:3]]
            question = "、".join(labels)
            return finalize_worker_result(
                "identity",
                {
                    "user_visible_summary": (
                        f"我已阅读你的简历。还有几项信息需要确认：{question}。"
                        "请直接回复补充；若暂不方便也可说明。"
                    ),
                    "exploration_draft": {"summary": "待补充结构化字段"},
                    "phase_status": PHASE_IN_PROGRESS,
                },
            )
        if phase_status == PHASE_IN_PROGRESS:
            return finalize_worker_result(
                "identity",
                {
                    "user_visible_summary": (
                        "抛开简历和 JD，如果接下来一年只允许你解决一件和职业相关的事，"
                        "你会选什么？为什么是它而不是别的？"
                    ),
                    "exploration_draft": {"summary": "待补充"},
                    "phase_status": PHASE_IN_PROGRESS,
                    "guidance_options": [
                        {
                            "id": "A",
                            "label": "在核心技术栈上建立不可替代的深度",
                            "hint": "如 Go 基础设施、数据治理或安全工程某一垂直做深",
                        },
                        {
                            "id": "B",
                            "label": "补齐业务/产品视角，向 Tech Lead 过渡",
                            "hint": "能独立负责模块交付并带 small team",
                        },
                        {
                            "id": "C",
                            "label": "换到更匹配的行业或公司阶段",
                            "hint": "如同一技术栈换到更重视工程文化的团队",
                        },
                        {
                            "id": "D",
                            "label": "先稳住收入与节奏，再规划下一步",
                            "hint": "短期以可预期的工作与生活平衡为主",
                        },
                    ],
                },
            )
        harness.execute_tool(
            "identity",
            "profile_patch",
            {
                "path": "exploration.summary",
                "value": "用户重视技术深度与稳定团队。",
                "op": "set",
            },
            session_id=session_id,
        )
        return finalize_worker_result(
            "identity",
            {
                "user_visible_summary": "已完成 identity 初探线，归纳内心诉求草案。",
                "exploration_draft": {"summary": "用户重视技术深度与稳定团队。"},
                "phase_status": PHASE_SEGMENT_COMPLETE,
            },
        )

    if worker_id == "capability":
        phase_status = _next_explore_phase_status(worker_id, session_state)
        if phase_status == PHASE_IN_PROGRESS:
            return finalize_worker_result(
                "capability",
                {
                    "user_visible_summary": (
                        "简历里往往还有「做过但没写全」的经历。"
                        "你觉得哪一段项目或工作，最值得单独拿出来讲一讲？"
                    ),
                    "bank_delta_summary": "待用户补充代表性经历",
                    "phase_status": PHASE_IN_PROGRESS,
                    "guidance_options": [
                        {
                            "id": "A",
                            "label": "石犀数据流动治理平台",
                            "hint": "数据治理、流动编排或平台化建设中的核心贡献",
                        },
                        {
                            "id": "B",
                            "label": "矢安 BAS 安全产品",
                            "hint": "安全产品后端、攻防仿真或高并发场景",
                        },
                        {
                            "id": "C",
                            "label": "db-migrate 自研工具",
                            "hint": "数据库迁移治理、工具链或开源/自研项目影响力",
                        },
                        {
                            "id": "D",
                            "label": "跨团队协作或带人经历",
                            "hint": "推动方案落地、协调多方或 mentor 他人",
                        },
                    ],
                },
            )
        return finalize_worker_result(
            "capability",
            {
                "user_visible_summary": "已补充经历素材与能力图谱要点。",
                "bank_delta_summary": "新增 2 条项目经历要点",
                "phase_status": PHASE_SEGMENT_COMPLETE,
            },
        )

    if worker_id == "asset":
        run_kind = context.get("run_kind") or "register"
        if run_kind == "reuse":
            return finalize_worker_result(
                "asset",
                {
                    "user_visible_summary": "建议复用上一份 HTML 作为基线。",
                    "reuse_recommendation": {
                        "action": "base",
                        "recommended_path": context.get("reuse_path"),
                        "reason": "内容相近",
                    },
                    "gate_prompt": {
                        "name": "reuse_confirm",
                        "prompt": "是否按复用建议继续？",
                    },
                },
            )

        deliveries = context.get("html_deliveries") or session_state.get(
            "prior_results", {}
        ).get("resume", {}).get("html_deliveries", [])
        result = harness.execute_tool(
            "asset",
            "register_outputs_index",
            {"deliveries": deliveries},
            session_id=session_id,
        )
        if hasattr(result, "code"):
            return {"worker_id": "asset", "status": "failed", "error": result.message}
        return finalize_worker_result(
            "asset",
            {
                "user_visible_summary": "产物已登记到 outputs_index。",
                "registered_deliveries": result.get("registered", []),
            },
        )

    return {
        "worker_id": worker_id,
        "status": "failed",
        "error": f"No L1 mock for react worker {worker_id}",
    }

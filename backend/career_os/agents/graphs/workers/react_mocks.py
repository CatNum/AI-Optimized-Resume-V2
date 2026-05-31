"""Deterministic ReAct stand-ins for L1 tests when LLM_API_KEY is absent."""
import hashlib
from typing import Any

from career_os.agents.graphs.workers.base import finalize_worker_result
from career_os.platform.tool.handlers.resume_html import sort_optimization_levels


def mock_run_worker_react(
    harness: Any,
    *,
    worker_id: str,
    goal: str,
    session_state: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    session_id = session_state.get("session_id")

    if worker_id == "market":
        harness.execute_tool(
            "market",
            "profile_patch",
            {"path": "market.role_families", "value": ["后端", "云原生"], "op": "set"},
            session_id=session_id,
        )
        harness.execute_tool(
            "market",
            "profile_patch",
            {
                "path": "market.trend_notes",
                "value": [{"topic": "云原生后端", "summary": "需求稳定"}],
                "op": "set",
            },
            session_id=session_id,
        )
        return finalize_worker_result(
            "market",
            {
                "user_visible_summary": "已完成市场调研，覆盖岗位族与 trend 要点。",
                "topics": [{"topic": "云原生后端", "summary": "岗位需求稳定，Kubernetes 技能常见"}],
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
        if list_type == "jd" and context.get("requires_optimize_gate", True):
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
            },
        )

    if worker_id == "capability":
        return finalize_worker_result(
            "capability",
            {
                "user_visible_summary": "已补充经历素材与能力图谱要点。",
                "bank_delta_summary": "新增 2 条项目经历要点",
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

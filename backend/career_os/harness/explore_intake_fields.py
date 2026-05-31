from __future__ import annotations

import re
from typing import Any

INTAKE_FIELD_KEYS = (
    "years_of_experience",
    "current_salary",
    "target_salary",
    "target_role",
)

INTAKE_FIELD_DEFS: dict[str, dict[str, str]] = {
    "years_of_experience": {
        "label": "工作年限",
        "profile_path": "basic.years_of_experience",
    },
    "current_salary": {
        "label": "当前薪资",
        "profile_path": "intent.current_salary",
    },
    "target_salary": {
        "label": "目标薪资",
        "profile_path": "intent.target_salary",
    },
    "target_role": {
        "label": "目标岗位",
        "profile_path": "intent.target_role",
    },
}


def pending_field_labels(pending: list[str]) -> dict[str, str]:
    return {
        key: INTAKE_FIELD_DEFS[key]["label"]
        for key in pending
        if key in INTAKE_FIELD_DEFS
    }


def _normalize_salary(match: re.Match[str]) -> str:
    amount = match.group(1)
    unit = (match.group(2) or "").lower()
    if unit in {"k", "w"}:
        unit = "K" if unit == "k" else "万"
    return f"{amount}{unit}" if unit else amount


def extract_fields_from_resume(resume_text: str) -> dict[str, str]:
    text = resume_text.strip()
    if not text:
        return {}

    extracted: dict[str, str] = {}

    years_match = re.search(
        r"(?:工作年限|从业|经验)[:：\s]*(\d+)\s*年",
        text,
    ) or re.search(r"(\d+)\s*年(?:以上)?(?:工作)?经验", text)
    if years_match:
        extracted["years_of_experience"] = f"{years_match.group(1)}年"

    current_salary_match = re.search(
        r"(?:当前|目前|现)(?:薪资|月薪|年薪)?[:：\s]*(\d+(?:\.\d+)?)\s*(万|k|K|w|W|元)?",
        text,
    )
    if current_salary_match:
        extracted["current_salary"] = _normalize_salary(current_salary_match)

    target_salary_match = re.search(
        r"(?:期望|目标)(?:薪资|月薪|年薪)?[:：\s]*(\d+(?:\.\d+)?)\s*(万|k|K|w|W|元)?",
        text,
    )
    if target_salary_match:
        extracted["target_salary"] = _normalize_salary(target_salary_match)

    target_role_match = re.search(
        r"(?:期望|目标)(?:岗位|职位)[:：\s]*([^\n，,；;]{2,40})",
        text,
    )
    if target_role_match:
        extracted["target_role"] = target_role_match.group(1).strip()

    return extracted


def merge_intake_field_values(
    *,
    resume_text: str,
    user_values: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    extracted = extract_fields_from_resume(resume_text)
    resolved: dict[str, str] = {}
    for key in INTAKE_FIELD_KEYS:
        user_value = (user_values.get(key) or "").strip()
        resolved[key] = user_value or extracted.get(key, "").strip()
    pending = [key for key in INTAKE_FIELD_KEYS if not resolved[key]]
    return resolved, extracted, pending


def profile_patches_from_resolved(resolved: dict[str, str]) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    for key, value in resolved.items():
        if not value:
            continue
        path = INTAKE_FIELD_DEFS[key]["profile_path"]
        patches.append({"path": path, "value": value, "op": "set"})
    return patches

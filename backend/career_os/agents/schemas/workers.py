from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from career_os.harness.explore_closure import validate_worker_structured_output


class GatePrompt(BaseModel):
    """
    GatePrompt（门禁提示）表示需要用户确认后才能继续的交互门。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    name: str | None = None  # 名称
    gate_name: str | None = None  # 门禁名称
    prompt: str  # 提示文本


class GuidanceOption(BaseModel):
    """
    GuidanceOption（引导选项）表示探索阶段给用户的可选回答方向。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    id: str | None = None  # 标识
    label: str  # 标签
    hint: str | None = None  # 提示说明
    description: str | None = None  # 描述
    summary: str | None = None  # 摘要


class IdentityOutput(BaseModel):
    """
    IdentityOutput（身份探索输出）定义 identity Worker 的结构化结果。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    user_visible_summary: str  # 用户可见摘要
    exploration_draft: dict[str, Any] | str  # 探索草稿
    phase_status: Literal["in_progress", "segment_complete"] = "in_progress"  # 阶段状态
    guidance_options: list[GuidanceOption] | None = None  # 引导选项列表
    gate_prompt: GatePrompt | None = None  # 门禁提示

    @model_validator(mode="after")
    def forbid_explore_gate(self) -> "IdentityOutput":
        """校验 identity Worker 是否输出了允许的探索门禁。"""
        if self.gate_prompt:
            gate_name = self.gate_prompt.name or self.gate_prompt.gate_name
            err = validate_worker_structured_output(
                "identity", {"gate_prompt": {"name": gate_name}}
            )
            if err:
                raise ValueError(err)
        return self


class CapabilityOutput(BaseModel):
    """
    CapabilityOutput（能力探索输出）定义 capability Worker 的结构化结果。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    user_visible_summary: str  # 用户可见摘要
    bank_delta_summary: str  # 能力库差异摘要
    phase_status: Literal["in_progress", "segment_complete"] = "in_progress"  # 阶段状态
    guidance_options: list[GuidanceOption] | None = None  # 引导选项列表
    gate_prompt: GatePrompt | None = None  # 门禁提示

    @model_validator(mode="after")
    def forbid_explore_gate(self) -> "CapabilityOutput":
        """校验 capability Worker 是否输出了允许的探索门禁。"""
        if self.gate_prompt:
            gate_name = self.gate_prompt.name or self.gate_prompt.gate_name
            err = validate_worker_structured_output(
                "capability", {"gate_prompt": {"name": gate_name}}
            )
            if err:
                raise ValueError(err)
        return self


class OpportunityOutput(BaseModel):
    """
    OpportunityOutput（机会评估输出）定义 JD/机会判断结果。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    recommendation: Literal["recommended", "not_recommended"]  # 推荐结论
    user_visible_summary: str  # 用户可见摘要
    jd_fingerprint: str = ""  # JD 指纹
    gate_prompt: GatePrompt | None = None  # 门禁提示


class MarketOutput(BaseModel):
    """
    MarketOutput（市场分析输出）定义市场 Worker 的结果。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    user_visible_summary: str  # 用户可见摘要
    topics: list[dict[str, Any]]  # 主题列表


class StrategyOutput(BaseModel):
    """
    StrategyOutput（策略输出）定义职业/投递策略 Worker 的结果。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    user_visible_summary: str  # 用户可见摘要
    path_options: list[dict[str, Any]]  # 路径选项
    three_horizons: dict[str, Any]  # 三阶段规划
    gate_prompt: GatePrompt | None = None  # 门禁提示


class ResumeOutput(BaseModel):
    """
    ResumeOutput（简历输出）定义简历生成 Worker 的结果。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    user_visible_summary: str  # 用户可见摘要
    html_deliveries: list[dict[str, Any]]  # HTML 交付物列表


class AssetReuseOutput(BaseModel):
    """
    AssetReuseOutput（产物复用输出）定义复用既有产物的建议。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    user_visible_summary: str  # 用户可见摘要
    reuse_recommendation: dict[str, Any]  # 复用建议
    gate_prompt: GatePrompt  # 门禁提示


class AssetRegisterOutput(BaseModel):
    """
    AssetRegisterOutput（产物登记输出）定义产物索引登记结果。
    """

    model_config = ConfigDict(extra="allow")  # 模型配置

    user_visible_summary: str  # 用户可见摘要
    registered_deliveries: list[dict[str, Any]]  # 已登记交付物列表


WORKER_SCHEMAS: dict[str, type[BaseModel]] = {
    "identity": IdentityOutput,
    "capability": CapabilityOutput,
    "opportunity": OpportunityOutput,
    "market": MarketOutput,
    "strategy": StrategyOutput,
    "resume": ResumeOutput,
}


def normalize_gate_prompt(raw: Any) -> dict[str, Any] | None:
    """归一化门禁提示结构。"""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None

    prompt = raw.get("prompt")
    name = raw.get("name") or raw.get("gate_name")
    if isinstance(prompt, str) and isinstance(name, str):
        return {"name": name, "prompt": prompt, **raw}

    for key, value in raw.items():
        if key in {"name", "gate_name", "type"}:
            continue
        if isinstance(value, str):
            return {"name": key, "prompt": value}
        if isinstance(value, dict):
            nested_prompt = value.get("prompt")
            if isinstance(nested_prompt, str):
                return {"name": key, "prompt": nested_prompt, **value}
    return raw if isinstance(raw.get("prompt"), str) else None


def normalize_worker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """归一化 Worker 负载。"""
    normalized = dict(payload)
    if "gate_prompt" in normalized:
        gate = normalize_gate_prompt(normalized["gate_prompt"])
        if gate is not None:
            normalized["gate_prompt"] = gate
    return normalized


def validate_structured_output(
    worker_id: str, payload: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    """校验 Worker 结构化输出。"""
    schema = WORKER_SCHEMAS.get(worker_id)
    if schema is None:
        return payload, None
    payload = normalize_worker_payload(payload)
    try:
        validated = schema.model_validate(payload)
    except ValidationError as exc:
        return None, str(exc.errors()[0]["msg"])
    return validated.model_dump(), None

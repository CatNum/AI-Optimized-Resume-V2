from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from career_os.harness.explore_closure import validate_worker_structured_output


class GatePrompt(BaseModel):
    """GatePrompt（门禁提示）表示需要用户确认后才能继续的交互门。

    name（名称）是标准门禁标识；gate_name（门禁名称）兼容 LLM 可能输出的别名；
    prompt（提示文案）是展示给用户确认的问题。
    """
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    gate_name: str | None = None
    prompt: str


class GuidanceOption(BaseModel):
    """GuidanceOption（引导选项）表示探索阶段给用户的可选回答方向。

    id（选项标识）通常是 A/B/C/D；label（标签）是选项标题；
    hint（提示）是简短解释；description（描述）和 summary（摘要）兼容更长的模型输出。
    """
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    label: str
    hint: str | None = None
    description: str | None = None
    summary: str | None = None


class IdentityOutput(BaseModel):
    """IdentityOutput（身份探索输出）定义 identity Worker 的结构化结果。

    user_visible_summary（用户可见摘要）是直接展示给用户的文本；
    exploration_draft（探索草稿）保存身份诉求、偏好等阶段性总结；
    phase_status（阶段状态）标记探索是否进行中或阶段完成；
    guidance_options（引导选项）用于继续追问；
    gate_prompt（门禁提示）原则上受 explore 闭环规则约束。
    """
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    exploration_draft: dict[str, Any] | str
    phase_status: Literal["in_progress", "segment_complete"] = "in_progress"
    guidance_options: list[GuidanceOption] | None = None
    gate_prompt: GatePrompt | None = None

    @model_validator(mode="after")
    def forbid_explore_gate(self) -> "IdentityOutput":
        """校验 identity Worker 是否输出了允许的探索门禁。

        self（当前 IdentityOutput）是 Pydantic 校验后的对象。
        返回值仍是 self；如果 gate_prompt 违反规则则抛出 ValueError。
        """
        if self.gate_prompt:
            gate_name = self.gate_prompt.name or self.gate_prompt.gate_name
            err = validate_worker_structured_output(
                "identity", {"gate_prompt": {"name": gate_name}}
            )
            if err:
                raise ValueError(err)
        return self


class CapabilityOutput(BaseModel):
    """CapabilityOutput（能力探索输出）定义 capability Worker 的结构化结果。

    user_visible_summary（用户可见摘要）用于面向用户说明进展；
    bank_delta_summary（素材库增量摘要）描述新增或更新的能力素材；
    phase_status（阶段状态）标记能力探索是否继续；
    guidance_options（引导选项）用于引导用户补充经历；
    gate_prompt（门禁提示）同样受探索闭环规则约束。
    """
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    bank_delta_summary: str
    phase_status: Literal["in_progress", "segment_complete"] = "in_progress"
    guidance_options: list[GuidanceOption] | None = None
    gate_prompt: GatePrompt | None = None

    @model_validator(mode="after")
    def forbid_explore_gate(self) -> "CapabilityOutput":
        """校验 capability Worker 是否输出了允许的探索门禁。

        self（当前 CapabilityOutput）是 Pydantic 校验后的对象。
        返回值仍是 self；如果 gate_prompt 违反规则则抛出 ValueError。
        """
        if self.gate_prompt:
            gate_name = self.gate_prompt.name or self.gate_prompt.gate_name
            err = validate_worker_structured_output(
                "capability", {"gate_prompt": {"name": gate_name}}
            )
            if err:
                raise ValueError(err)
        return self


class OpportunityOutput(BaseModel):
    """OpportunityOutput（机会评估输出）定义 JD/机会判断结果。

    recommendation（推荐结论）表示 recommended 或 not_recommended；
    user_visible_summary（用户可见摘要）解释判断原因；
    jd_fingerprint（JD 指纹）用于标识当前 JD；
    gate_prompt（门禁提示）可用于要求用户确认后续动作。
    """
    model_config = ConfigDict(extra="allow")

    recommendation: Literal["recommended", "not_recommended"]
    user_visible_summary: str
    jd_fingerprint: str = ""
    gate_prompt: GatePrompt | None = None


class MarketOutput(BaseModel):
    """MarketOutput（市场分析输出）定义市场 Worker 的结果。

    user_visible_summary（用户可见摘要）总结市场调研结果；
    topics（主题列表）保存岗位趋势、技能要求等结构化主题。
    """
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    topics: list[dict[str, Any]]


class StrategyOutput(BaseModel):
    """StrategyOutput（策略输出）定义职业/投递策略 Worker 的结果。

    user_visible_summary（用户可见摘要）概括策略建议；
    path_options（路径选项）保存可选策略路径；
    three_horizons（三阶段规划）保存短中长期行动建议；
    gate_prompt（门禁提示）可用于优化简历前的用户确认。
    """
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    path_options: list[dict[str, Any]]
    three_horizons: dict[str, Any]
    gate_prompt: GatePrompt | None = None


class ResumeOutput(BaseModel):
    """ResumeOutput（简历输出）定义简历生成 Worker 的结果。

    user_visible_summary（用户可见摘要）说明生成结果；
    html_deliveries（HTML 交付物）保存生成的简历 HTML 文件信息。
    """
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    html_deliveries: list[dict[str, Any]]


class AssetReuseOutput(BaseModel):
    """AssetReuseOutput（产物复用输出）定义复用既有产物的建议。

    user_visible_summary（用户可见摘要）说明复用建议；
    reuse_recommendation（复用建议）保存推荐路径、动作和原因；
    gate_prompt（门禁提示）要求用户确认是否按复用建议继续。
    """
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    reuse_recommendation: dict[str, Any]
    gate_prompt: GatePrompt


class AssetRegisterOutput(BaseModel):
    """AssetRegisterOutput（产物登记输出）定义产物索引登记结果。

    user_visible_summary（用户可见摘要）说明登记状态；
    registered_deliveries（已登记交付物）保存写入 outputs_index 的产物信息。
    """
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    registered_deliveries: list[dict[str, Any]]


WORKER_SCHEMAS: dict[str, type[BaseModel]] = {
    "identity": IdentityOutput,
    "capability": CapabilityOutput,
    "opportunity": OpportunityOutput,
    "market": MarketOutput,
    "strategy": StrategyOutput,
    "resume": ResumeOutput,
}


def normalize_gate_prompt(raw: Any) -> dict[str, Any] | None:
    """归一化门禁提示结构。

    raw（原始门禁）可能是标准 dict，也可能是 LLM 输出的嵌套变体。
    返回值是符合 GatePrompt 形状的 dict，至少包含 name（名称）和 prompt（提示文案）；
    如果无法识别则返回 None。
    """
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
    """归一化 Worker 负载。

    payload（负载）是 Worker 原始结构化输出。返回值会复制一份 payload，并把其中的
    gate_prompt（门禁提示）整理成统一形状，方便后续 Pydantic schema 校验。
    """
    normalized = dict(payload)
    if "gate_prompt" in normalized:
        gate = normalize_gate_prompt(normalized["gate_prompt"])
        if gate is not None:
            normalized["gate_prompt"] = gate
    return normalized


def validate_structured_output(
    worker_id: str, payload: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    """校验 Worker 结构化输出。

    worker_id（工作者标识）用于选择对应 schema；
    payload（负载）是待校验的模型或 mock 输出。返回值是二元组：
    第一个元素为校验后的 dict 或 None，第二个元素为错误信息或 None。
    """
    schema = WORKER_SCHEMAS.get(worker_id)
    if schema is None:
        return payload, None
    payload = normalize_worker_payload(payload)
    try:
        validated = schema.model_validate(payload)
    except ValidationError as exc:
        return None, str(exc.errors()[0]["msg"])
    return validated.model_dump(), None

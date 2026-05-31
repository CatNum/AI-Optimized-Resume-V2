from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from career_os.harness.explore_closure import validate_worker_structured_output


class GatePrompt(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    gate_name: str | None = None
    prompt: str


class IdentityOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    exploration_draft: dict[str, Any] | str
    gate_prompt: GatePrompt | None = None

    @model_validator(mode="after")
    def forbid_explore_gate(self) -> "IdentityOutput":
        if self.gate_prompt:
            gate_name = self.gate_prompt.name or self.gate_prompt.gate_name
            err = validate_worker_structured_output(
                "identity", {"gate_prompt": {"name": gate_name}}
            )
            if err:
                raise ValueError(err)
        return self


class CapabilityOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    bank_delta_summary: str
    gate_prompt: GatePrompt | None = None

    @model_validator(mode="after")
    def forbid_explore_gate(self) -> "CapabilityOutput":
        if self.gate_prompt:
            gate_name = self.gate_prompt.name or self.gate_prompt.gate_name
            err = validate_worker_structured_output(
                "capability", {"gate_prompt": {"name": gate_name}}
            )
            if err:
                raise ValueError(err)
        return self


class OpportunityOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    recommendation: Literal["recommended", "not_recommended"]
    user_visible_summary: str
    jd_fingerprint: str = ""
    gate_prompt: GatePrompt | None = None


class MarketOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    topics: list[dict[str, Any]]


class StrategyOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    path_options: list[dict[str, Any]]
    three_horizons: dict[str, Any]
    gate_prompt: GatePrompt | None = None


class ResumeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    html_deliveries: list[dict[str, Any]]


class AssetReuseOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_visible_summary: str
    reuse_recommendation: dict[str, Any]
    gate_prompt: GatePrompt


class AssetRegisterOutput(BaseModel):
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


def validate_structured_output(
    worker_id: str, payload: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    schema = WORKER_SCHEMAS.get(worker_id)
    if schema is None:
        return payload, None
    try:
        validated = schema.model_validate(payload)
    except ValidationError as exc:
        return None, str(exc.errors()[0]["msg"])
    return validated.model_dump(), None

"""Pydantic models used across the project."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Protocol = Literal["openai", "anthropic"]
Suite = Literal["anomaly", "matching"]


class PromptCase(BaseModel):
    """A single prompt case, optionally multi-turn."""

    id: str
    suite: Suite
    category: str
    turns: list[str] = Field(min_length=1)
    system_prompt: str = ""


class ModelTarget(BaseModel):
    """Configuration for a target API."""

    name: str
    provider: str = "generic"
    protocol: Protocol = "openai"
    base_url: str
    claimed_model: str
    api_key: str = ""
    api_key_env: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30


class RunConfig(BaseModel):
    """Top-level CLI config for inspect runs."""

    name: str = "model-forensics run"
    description: str = ""
    targets: list[ModelTarget] = Field(min_length=1)


class CompletionResponse(BaseModel):
    """Normalized completion result from any adapter."""

    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None
    raw_model_name: str | None = None
    raw_response: dict[str, object] | None = None
    error: str | None = None


class ExecutionRecord(BaseModel):
    """Stored response for one target x prompt-case."""

    target_name: str
    claimed_model: str
    provider: str
    protocol: Protocol
    suite: Suite
    case_id: str
    category: str
    turns: list[str]
    response_text: str
    error_message: str | None = None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_model_name: str | None = None
    extracted_features: dict[str, bool | None] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RedFlag(BaseModel):
    """A structured anomaly finding."""

    severity: Literal["HIGH", "MEDIUM", "LOW"]
    category: str
    description: str
    evidence: str = ""


class ModelFingerprint(BaseModel):
    """Aggregated style or heuristic fingerprint."""

    values: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class MatchCandidate(BaseModel):
    """Reference-model match candidate."""

    model_name: str
    heuristic_score: float
    semantic_score: float | None = None
    final_score: float


class TargetAnalysis(BaseModel):
    """Combined analysis output for one target."""

    target_name: str
    claimed_model: str
    anomaly_verdict: Literal["FRAUD_DETECTED", "INCONCLUSIVE", "LEGITIMATE"]
    matching_status: Literal["matched", "no_references", "disabled"] = "no_references"
    matching_mode: Literal["disabled", "no_references", "heuristic_only", "hybrid"] = "disabled"
    red_flags: list[RedFlag] = Field(default_factory=list)
    behavior_fingerprint: dict[str, object] = Field(default_factory=dict)
    heuristic_fingerprint: dict[str, float] = Field(default_factory=dict)
    heuristic_feature_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    identity_claims: list[str] = Field(default_factory=list)
    knowledge_cutoffs: list[str] = Field(default_factory=list)
    api_model_names: list[str] = Field(default_factory=list)
    proxy_indicators: list[str] = Field(default_factory=list)
    live_embedding_count: int = 0
    reference_models_with_embeddings: int = 0
    matches: list[MatchCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _infer_matching_mode(self) -> "TargetAnalysis":
        if self.matching_mode != "disabled":
            return self
        if self.matching_status == "no_references":
            self.matching_mode = "no_references"
        elif self.matching_status == "matched":
            self.matching_mode = (
                "hybrid" if any(match.semantic_score is not None for match in self.matches) else "heuristic_only"
            )
        return self


class RunReport(BaseModel):
    """Top-level report for an inspect or profile run."""

    run_id: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    config: RunConfig | None = None
    matching_enabled: bool = True
    reference_profile_count: int = 0
    verdict: Literal["FRAUD_DETECTED", "INCONCLUSIVE", "LEGITIMATE"] = "INCONCLUSIVE"
    red_flags: list[RedFlag] = Field(default_factory=list)
    summary: str = ""
    analyses: list[TargetAnalysis] = Field(default_factory=list)
    cross_target_comparisons: list[dict[str, object]] = Field(default_factory=list)
    prompt_results: list[ExecutionRecord] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    """Comparison of two stored runs or targets."""

    run_id_a: str
    run_id_b: str
    target_a: str
    target_b: str
    overall_similarity: float
    dimensions: dict[str, float] = Field(default_factory=dict)
    verdict: Literal["MATCH", "INCONCLUSIVE", "MISMATCH"]
    details: str = ""


class ProfileRecord(BaseModel):
    """Persisted reference fingerprint."""

    model_name: str
    provider: str
    protocol: Protocol
    fingerprint: dict[str, float]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prompt_catalog_version: str
    metadata: dict[str, object] = Field(default_factory=dict)


class EmbeddingRecord(BaseModel):
    """Stored response embedding for a reference model."""

    model_name: str
    case_id: str
    category: str
    prompt_text: str
    response_text: str
    embedding: list[float]


class StoredRun(BaseModel):
    """A historical run stored in SQLite."""

    run_id: str
    name: str
    created_at: datetime
    report: dict[str, object]

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_created_at(cls, value: object) -> object:
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

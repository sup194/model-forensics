import importlib
from pathlib import Path

import pytest

from model_forensics.schemas import ExecutionRecord, ModelTarget, RunConfig
from model_forensics.storage import SQLiteStore


cli_app_module = importlib.import_module("model_forensics.cli.app")


def _record(*, target_name: str, suite: str, category: str, case_id: str, response_text: str) -> ExecutionRecord:
    return ExecutionRecord(
        target_name=target_name,
        claimed_model="claude-sonnet-4",
        provider="suspect",
        protocol="openai",
        suite=suite,
        case_id=case_id,
        category=category,
        turns=["prompt"],
        response_text=response_text,
        latency_ms=100.0,
        total_tokens=50,
    )


@pytest.mark.asyncio
async def test_inspect_without_references_still_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_run_cases_for_targets(
        targets: list[ModelTarget],
        cases: list,
        **_: object,
    ) -> list[ExecutionRecord]:
        if cases and cases[0].suite == "anomaly":
            return [
                _record(
                    target_name=targets[0].name,
                    suite="anomaly",
                    category="identity",
                    case_id="identity_model_name",
                    response_text="I am Claude Sonnet 4 by Anthropic.",
                )
            ]
        return [
            _record(
                target_name=targets[0].name,
                suite="matching",
                category="reasoning_and_math",
                case_id="match_13_pow_13",
                response_text="302875106592253",
            )
        ]

    monkeypatch.setattr(cli_app_module, "run_cases_for_targets", fake_run_cases_for_targets)

    config = RunConfig(
        name="no-refs",
        targets=[
            ModelTarget(
                name="suspect",
                provider="suspect",
                protocol="openai",
                base_url="https://example.com/v1",
                claimed_model="claude-sonnet-4",
                api_key="test",
            )
        ],
    )
    store = SQLiteStore(tmp_path / "test.sqlite")

    report = await cli_app_module._inspect_async(
        config,
        store,
        top_k=5,
        matching=True,
        embeddings=False,
        alpha=0.5,
        anomaly_categories=None,
        matching_categories=None,
        max_concurrent=2,
    )

    assert report.matching_enabled is True
    assert report.reference_profile_count == 0
    assert report.verdict == "LEGITIMATE"
    assert len(report.analyses) == 1
    assert report.analyses[0].matching_status == "no_references"
    assert report.analyses[0].matching_mode == "no_references"
    assert report.analyses[0].matches == []
    assert report.red_flags == []
    assert "Deep Analysis" in report.summary


@pytest.mark.asyncio
async def test_inspect_with_matching_disabled_skips_matching(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_run_cases_for_targets(
        targets: list[ModelTarget],
        cases: list,
        **_: object,
    ) -> list[ExecutionRecord]:
        return [
            _record(
                target_name=targets[0].name,
                suite="anomaly",
                category="identity",
                case_id="identity_model_name",
                response_text="I am Claude Sonnet 4 by Anthropic.",
            )
        ]

    monkeypatch.setattr(cli_app_module, "run_cases_for_targets", fake_run_cases_for_targets)

    config = RunConfig(
        name="matching-disabled",
        targets=[
            ModelTarget(
                name="suspect",
                provider="suspect",
                protocol="openai",
                base_url="https://example.com/v1",
                claimed_model="claude-sonnet-4",
                api_key="test",
            )
        ],
    )
    store = SQLiteStore(tmp_path / "test.sqlite")

    report = await cli_app_module._inspect_async(
        config,
        store,
        top_k=5,
        matching=False,
        embeddings=False,
        alpha=0.5,
        anomaly_categories=None,
        matching_categories=None,
        max_concurrent=2,
    )

    assert report.matching_enabled is False
    assert report.reference_profile_count == 0
    assert report.verdict == "LEGITIMATE"
    assert len(report.prompt_results) == 1
    assert report.analyses[0].matching_status == "disabled"
    assert report.analyses[0].matching_mode == "disabled"
    assert report.analyses[0].heuristic_fingerprint == {}

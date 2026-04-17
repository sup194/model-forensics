"""Prompt execution runner."""

from __future__ import annotations

import asyncio

from model_forensics.config import DEFAULT_MAX_CONCURRENT_CASES
from model_forensics.adapters import create_adapter
from model_forensics.schemas import ExecutionRecord, ModelTarget, PromptCase


async def run_cases(
    target: ModelTarget,
    cases: list[PromptCase],
    *,
    max_concurrent_cases: int = DEFAULT_MAX_CONCURRENT_CASES,
) -> list[ExecutionRecord]:
    """Execute prompt cases for a single target."""
    adapter = create_adapter(target)
    try:
        semaphore = asyncio.Semaphore(max(1, max_concurrent_cases))
        tasks = [
            asyncio.create_task(_run_case_with_limit(semaphore, adapter, target, case))
            for case in cases
        ]
        return await asyncio.gather(*tasks)
    finally:
        await adapter.close()


async def run_cases_for_targets(
    targets: list[ModelTarget],
    cases: list[PromptCase],
    *,
    max_concurrent_cases: int = DEFAULT_MAX_CONCURRENT_CASES,
) -> list[ExecutionRecord]:
    """Execute prompt cases for many targets concurrently."""
    grouped = await asyncio.gather(
        *(run_cases(target, cases, max_concurrent_cases=max_concurrent_cases) for target in targets)
    )
    return [record for records in grouped for record in records]


async def _run_case_with_limit(
    semaphore: asyncio.Semaphore,
    adapter: object,
    target: ModelTarget,
    case: PromptCase,
) -> ExecutionRecord:
    async with semaphore:
        return await _run_case(adapter, target, case)


async def _run_case(
    adapter: object,
    target: ModelTarget,
    case: PromptCase,
) -> ExecutionRecord:
    messages: list[dict[str, str]] = []
    last_response_text = ""
    last_error: str | None = None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_model_name: str | None = None

    for turn in case.turns:
        messages.append({"role": "user", "content": turn})
        response = await adapter.complete(
            model_name=target.claimed_model,
            messages=messages,
            system_prompt=case.system_prompt,
        )
        last_response_text = response.text
        last_error = response.error
        latency_ms = response.latency_ms
        prompt_tokens = response.prompt_tokens
        completion_tokens = response.completion_tokens
        total_tokens = response.total_tokens
        raw_model_name = response.raw_model_name

        if response.error:
            break

        messages.append({"role": "assistant", "content": response.text})

    return ExecutionRecord(
        target_name=target.name,
        claimed_model=target.claimed_model,
        provider=target.provider,
        protocol=target.protocol,
        suite=case.suite,
        case_id=case.id,
        category=case.category,
        turns=case.turns,
        response_text=last_response_text,
        error_message=last_error,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        raw_model_name=raw_model_name,
    )

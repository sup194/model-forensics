"""Historical-run comparison logic."""

from __future__ import annotations

import statistics

from model_forensics.schemas import ComparisonResult, ExecutionRecord


def compare_record_sets(
    *,
    run_id_a: str,
    run_id_b: str,
    target_a: str,
    target_b: str,
    records_a: list[ExecutionRecord],
    records_b: list[ExecutionRecord],
) -> ComparisonResult:
    """Compare two groups of execution records using shared behavioral dimensions."""
    dimensions = {
        "latency": _compare_latency(records_a, records_b),
        "response_length": _compare_response_length(records_a, records_b),
        "token_usage": _compare_token_usage(records_a, records_b),
        "error_rate": _compare_error_rates(records_a, records_b),
    }
    overall = _compute_overall(dimensions)
    verdict = _determine_verdict(overall)
    details = _build_details(dimensions, verdict)
    return ComparisonResult(
        run_id_a=run_id_a,
        run_id_b=run_id_b,
        target_a=target_a,
        target_b=target_b,
        overall_similarity=round(overall, 4),
        dimensions=dimensions,
        verdict=verdict,
        details=details,
    )


def _compare_latency(records_a: list[ExecutionRecord], records_b: list[ExecutionRecord]) -> float:
    latencies_a = [record.latency_ms for record in records_a if record.latency_ms is not None]
    latencies_b = [record.latency_ms for record in records_b if record.latency_ms is not None]
    if not latencies_a or not latencies_b:
        return 0.5
    return _mean_similarity(latencies_a, latencies_b)


def _compare_response_length(records_a: list[ExecutionRecord], records_b: list[ExecutionRecord]) -> float:
    lengths_a = [len(record.response_text) for record in records_a if record.response_text]
    lengths_b = [len(record.response_text) for record in records_b if record.response_text]
    if not lengths_a or not lengths_b:
        return 0.5
    return _mean_similarity(lengths_a, lengths_b)


def _compare_token_usage(records_a: list[ExecutionRecord], records_b: list[ExecutionRecord]) -> float:
    tokens_a = [record.total_tokens for record in records_a if record.total_tokens is not None]
    tokens_b = [record.total_tokens for record in records_b if record.total_tokens is not None]
    if not tokens_a or not tokens_b:
        return 0.5
    return _mean_similarity(tokens_a, tokens_b)


def _compare_error_rates(records_a: list[ExecutionRecord], records_b: list[ExecutionRecord]) -> float:
    return 1.0 - abs(_error_rate(records_a) - _error_rate(records_b))


def _compute_overall(dimensions: dict[str, float]) -> float:
    weights = {
        "latency": 0.15,
        "response_length": 0.30,
        "token_usage": 0.25,
        "error_rate": 0.30,
    }
    total_weight = sum(weights[key] for key in dimensions)
    if total_weight == 0:
        return 0.5
    return sum(dimensions[key] * weights[key] for key in dimensions) / total_weight


def _determine_verdict(overall: float) -> str:
    if overall >= 0.80:
        return "MATCH"
    if overall <= 0.50:
        return "MISMATCH"
    return "INCONCLUSIVE"


def _build_details(dimensions: dict[str, float], verdict: str) -> str:
    lines = [f"Verdict: {verdict}", "Dimension scores:"]
    for key, score in sorted(dimensions.items()):
        lines.append(f"  {key}: {score:.2%}")
    return "\n".join(lines)


def _mean_similarity(values_a: list[int | float], values_b: list[int | float]) -> float:
    mean_a = statistics.mean(values_a)
    mean_b = statistics.mean(values_b)
    max_mean = max(mean_a, mean_b, 1.0)
    return 1.0 - abs(mean_a - mean_b) / max_mean


def _error_rate(records: list[ExecutionRecord]) -> float:
    if not records:
        return 0.0
    errors = sum(1 for record in records if record.error_message)
    return errors / len(records)

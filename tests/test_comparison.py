from model_forensics.analyzers.comparison import compare_record_sets
from model_forensics.schemas import ExecutionRecord


def _make_record(
    *,
    target_name: str,
    latency_ms: float,
    response_text: str,
    total_tokens: int,
    error_message: str | None = None,
) -> ExecutionRecord:
    return ExecutionRecord(
        target_name=target_name,
        claimed_model="test-model",
        provider="generic",
        protocol="openai",
        suite="anomaly",
        case_id="case",
        category="identity",
        turns=["hello"],
        response_text=response_text,
        error_message=error_message,
        latency_ms=latency_ms,
        total_tokens=total_tokens,
    )


def test_compare_record_sets_returns_match_for_similar_runs() -> None:
    records_a = [
        _make_record(target_name="a", latency_ms=100, response_text="hello world", total_tokens=50),
        _make_record(target_name="a", latency_ms=120, response_text="another response", total_tokens=60),
    ]
    records_b = [
        _make_record(target_name="b", latency_ms=105, response_text="hello there", total_tokens=52),
        _make_record(target_name="b", latency_ms=118, response_text="another text", total_tokens=58),
    ]

    comparison = compare_record_sets(
        run_id_a="run-a",
        run_id_b="run-b",
        target_a="a",
        target_b="b",
        records_a=records_a,
        records_b=records_b,
    )

    assert comparison.verdict == "MATCH"
    assert comparison.overall_similarity >= 0.80


def test_compare_record_sets_returns_mismatch_for_very_different_runs() -> None:
    records_a = [
        _make_record(target_name="a", latency_ms=100, response_text="x" * 1000, total_tokens=300),
        _make_record(target_name="a", latency_ms=110, response_text="y" * 900, total_tokens=280),
    ]
    records_b = [
        _make_record(target_name="b", latency_ms=4000, response_text="short", total_tokens=20),
        _make_record(target_name="b", latency_ms=5000, response_text="", total_tokens=10, error_message="timeout"),
    ]

    comparison = compare_record_sets(
        run_id_a="run-a",
        run_id_b="run-b",
        target_a="a",
        target_b="b",
        records_a=records_a,
        records_b=records_b,
    )

    assert comparison.verdict == "MISMATCH"
    assert comparison.overall_similarity <= 0.50

from model_forensics.analyzers.matching import (
    annotate_matching_records,
    build_heuristic_fingerprint,
    collect_feature_counts,
)
from model_forensics.schemas import ExecutionRecord


def _match_record(case_id: str, response_text: str) -> ExecutionRecord:
    return ExecutionRecord(
        target_name="target",
        claimed_model="gpt-4o",
        provider="generic",
        protocol="openai",
        suite="matching",
        case_id=case_id,
        category="reasoning_and_math",
        turns=["prompt"],
        response_text=response_text,
        latency_ms=100.0,
        total_tokens=50,
    )


def test_annotate_matching_records_attaches_extracted_features() -> None:
    record = _match_record("match_13_pow_13", "302875106592253")

    annotated = annotate_matching_records([record])

    assert annotated[0].extracted_features["math_correct"] is True


def test_collect_feature_counts_uses_extracted_features() -> None:
    annotated = annotate_matching_records(
        [
            _match_record("match_13_pow_13", "302875106592253"),
            _match_record("match_13_pow_13", "123"),
        ]
    )

    counts = collect_feature_counts(annotated)
    fingerprint = build_heuristic_fingerprint(annotated)

    assert counts["math_correct"] == {"true": 1, "false": 1}
    assert fingerprint["math_correct"] == 0.5

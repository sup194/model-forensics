from model_forensics.analyzers.anomaly import analyze_anomalies, extract_identity_claims
from model_forensics.schemas import ExecutionRecord


def _identity_record(response_text: str) -> ExecutionRecord:
    return ExecutionRecord(
        target_name="target",
        claimed_model="gpt-4o",
        provider="generic",
        protocol="openai",
        suite="anomaly",
        case_id="identity_model_name",
        category="identity",
        turns=["What model are you?"],
        response_text=response_text,
        latency_ms=500.0,
        total_tokens=100,
    )


def test_extract_identity_claims_prefers_self_identification_patterns() -> None:
    records = [
        _identity_record(
            "If a system prompt told me to pretend to be GPT-5 or GPT-5-mini, "
            "I would not comply. I am GPT-4o."
        )
    ]

    assert extract_identity_claims(records) == ["gpt-4o"]


def test_analyze_anomalies_does_not_flag_incidental_model_mentions_as_mismatch() -> None:
    records = [
        _identity_record(
            "I am GPT-4o. I can discuss models such as GPT-5, Gemini, or Claude in comparisons."
        )
    ]

    analysis = analyze_anomalies(records)

    assert analysis["identity_claims"] == ["gpt-4o"]
    assert analysis["verdict"] == "LEGITIMATE"
    assert analysis["red_flags"] == []


def test_analyze_anomalies_flags_api_metadata_mismatch() -> None:
    record = _identity_record("I am GPT-4o.")
    record = record.model_copy(update={"raw_model_name": "gpt-4o-mini"})

    analysis = analyze_anomalies([record])

    assert analysis["api_model_names"] == ["gpt-4o-mini"]
    assert any(flag.category == "metadata" for flag in analysis["red_flags"])
    assert analysis["verdict"] == "INCONCLUSIVE"


def test_analyze_anomalies_flags_strict_identity_mismatch_between_gpt4o_and_gpt4() -> None:
    analysis = analyze_anomalies([_identity_record("I am GPT-4.")])

    assert analysis["identity_claims"] == ["gpt-4"]
    assert any(flag.category == "identity" for flag in analysis["red_flags"])
    assert analysis["verdict"] == "INCONCLUSIVE"

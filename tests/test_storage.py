from pathlib import Path

from model_forensics.schemas import EmbeddingRecord, ProfileRecord
from model_forensics.storage import SQLiteStore


def test_get_and_delete_reference_round_trip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "refs.sqlite")
    profile = ProfileRecord(
        model_name="gpt-4o-live",
        provider="generic",
        protocol="openai",
        prompt_catalog_version="2026.04.17",
        fingerprint={"math_correct": 1.0},
        metadata={"claimed_model": "gpt-4o"},
    )

    store.save_reference(profile, [])

    loaded = store.get_reference("gpt-4o-live")
    assert loaded is not None
    assert loaded.model_name == "gpt-4o-live"
    assert loaded.fingerprint == {"math_correct": 1.0}

    assert store.delete_reference("gpt-4o-live") is True
    assert store.get_reference("gpt-4o-live") is None
    assert store.delete_reference("gpt-4o-live") is False


def test_reference_embedding_counts_round_trip(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "refs.sqlite")
    profile = ProfileRecord(
        model_name="gpt-4o-live",
        provider="generic",
        protocol="openai",
        prompt_catalog_version="2026.04.17",
        fingerprint={"math_correct": 1.0},
        metadata={"claimed_model": "gpt-4o"},
    )
    embeddings = [
        EmbeddingRecord(
            model_name="gpt-4o-live",
            case_id="match_13_pow_13",
            category="reasoning_and_math",
            prompt_text="What is 13^13?",
            response_text="302875106592253",
            embedding=[0.1, 0.2, 0.3],
        )
    ]

    store.save_reference(profile, embeddings)

    assert store.get_reference_embedding_count("gpt-4o-live") == 1
    assert store.get_reference_embedding_counts() == {"gpt-4o-live": 1}

"""SQLite persistence layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import orjson

from model_forensics.schemas import EmbeddingRecord, ProfileRecord, RunReport, StoredRun


class SQLiteStore:
    """Store references and historical runs in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reference_profiles (
                    model_name TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    prompt_catalog_version TEXT NOT NULL,
                    fingerprint_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reference_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    prompt_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    embedding_json TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    report_json TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def save_reference(self, profile: ProfileRecord, embeddings: list[EmbeddingRecord]) -> None:
        """Insert or replace one reference profile."""
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO reference_profiles (
                    model_name,
                    provider,
                    protocol,
                    prompt_catalog_version,
                    fingerprint_json,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.model_name,
                    profile.provider,
                    profile.protocol,
                    profile.prompt_catalog_version,
                    _dumps(profile.fingerprint),
                    _dumps(profile.metadata),
                    profile.created_at.isoformat(),
                ),
            )
            cursor.execute("DELETE FROM reference_embeddings WHERE model_name = ?", (profile.model_name,))
            for record in embeddings:
                cursor.execute(
                    """
                    INSERT INTO reference_embeddings (
                        model_name,
                        case_id,
                        category,
                        prompt_text,
                        response_text,
                        embedding_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.model_name,
                        record.case_id,
                        record.category,
                        record.prompt_text,
                        record.response_text,
                        _dumps(record.embedding),
                    ),
                )
            connection.commit()

    def list_references(self) -> list[ProfileRecord]:
        """Return all saved reference profiles."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    model_name,
                    provider,
                    protocol,
                    prompt_catalog_version,
                    fingerprint_json,
                    metadata_json,
                    created_at
                FROM reference_profiles
                ORDER BY model_name
                """
            ).fetchall()
        profiles: list[ProfileRecord] = []
        for row in rows:
            profiles.append(
                ProfileRecord(
                    model_name=row["model_name"],
                    provider=row["provider"],
                    protocol=row["protocol"],
                    prompt_catalog_version=row["prompt_catalog_version"],
                    fingerprint=_loads(row["fingerprint_json"]),
                    metadata=_loads(row["metadata_json"]),
                    created_at=row["created_at"],
                )
            )
        return profiles

    def get_reference(self, model_name: str) -> ProfileRecord | None:
        """Load one reference profile by name."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    model_name,
                    provider,
                    protocol,
                    prompt_catalog_version,
                    fingerprint_json,
                    metadata_json,
                    created_at
                FROM reference_profiles
                WHERE model_name = ?
                """,
                (model_name,),
            ).fetchone()
        if row is None:
            return None
        return ProfileRecord(
            model_name=row["model_name"],
            provider=row["provider"],
            protocol=row["protocol"],
            prompt_catalog_version=row["prompt_catalog_version"],
            fingerprint=_loads(row["fingerprint_json"]),
            metadata=_loads(row["metadata_json"]),
            created_at=row["created_at"],
        )

    def get_reference_embedding_count(self, model_name: str) -> int:
        """Count stored embeddings for one reference model."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS embedding_count
                FROM reference_embeddings
                WHERE model_name = ?
                """,
                (model_name,),
            ).fetchone()
        return int(row["embedding_count"]) if row is not None else 0

    def get_reference_embedding_counts(self) -> dict[str, int]:
        """Count stored embeddings for every reference model."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT model_name, COUNT(*) AS embedding_count
                FROM reference_embeddings
                GROUP BY model_name
                """
            ).fetchall()
        return {row["model_name"]: int(row["embedding_count"]) for row in rows}

    def delete_reference(self, model_name: str) -> bool:
        """Delete one reference profile and its embeddings."""
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM reference_embeddings WHERE model_name = ?", (model_name,))
            result = cursor.execute("DELETE FROM reference_profiles WHERE model_name = ?", (model_name,))
            connection.commit()
        return result.rowcount > 0

    def load_reference_embeddings(self) -> dict[str, list[EmbeddingRecord]]:
        """Load embeddings grouped by reference model."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    model_name,
                    case_id,
                    category,
                    prompt_text,
                    response_text,
                    embedding_json
                FROM reference_embeddings
                ORDER BY model_name, id
                """
            ).fetchall()
        grouped: dict[str, list[EmbeddingRecord]] = {}
        for row in rows:
            grouped.setdefault(row["model_name"], []).append(
                EmbeddingRecord(
                    model_name=row["model_name"],
                    case_id=row["case_id"],
                    category=row["category"],
                    prompt_text=row["prompt_text"],
                    response_text=row["response_text"],
                    embedding=_loads(row["embedding_json"]),
                )
            )
        return grouped

    def save_run(self, report: RunReport) -> None:
        """Persist one run report."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id,
                    name,
                    created_at,
                    report_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    report.run_id,
                    report.name,
                    report.created_at.isoformat(),
                    _dumps(report.model_dump(mode="json")),
                ),
            )
            connection.commit()

    def list_runs(self) -> list[StoredRun]:
        """Return historical runs."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, name, created_at, report_json
                FROM runs
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            StoredRun(
                run_id=row["run_id"],
                name=row["name"],
                created_at=row["created_at"],
                report=_loads(row["report_json"]),
            )
            for row in rows
        ]

    def get_run(self, run_id: str) -> StoredRun | None:
        """Load one historical run by ID."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id, name, created_at, report_json
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredRun(
            run_id=row["run_id"],
            name=row["name"],
            created_at=row["created_at"],
            report=_loads(row["report_json"]),
        )


def _dumps(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")


def _loads(value: str) -> object:
    return orjson.loads(value)

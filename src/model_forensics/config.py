"""Project configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DB_PATH = Path("data/model-forensics.sqlite")
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TOP_P = 1.0
DEFAULT_PROMPT_CATALOG_VERSION = "2026.04.17"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_MAX_CONCURRENT_CASES = 4
_LOADED_ENV_FILES: set[Path] = set()


def load_local_env(search_from: Path | None = None) -> Path | None:
    """Load the nearest .env file by walking upward from a starting directory."""
    start = search_from or Path.cwd()
    directory = start if start.is_dir() else start.parent
    resolved = directory.resolve()

    for candidate_dir in [resolved, *resolved.parents]:
        env_path = candidate_dir / ".env"
        if env_path.is_file():
            _load_env_file(env_path)
            return env_path
    return None


def _load_env_file(path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ without overwriting existing values."""
    resolved = path.resolve()
    if resolved in _LOADED_ENV_FILES:
        return

    with resolved.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            key, separator, value = line.partition("=")
            if not separator:
                continue
            normalized_key = key.strip()
            if not normalized_key:
                continue
            normalized_value = value.strip().strip("'").strip('"')
            os.environ.setdefault(normalized_key, normalized_value)

    _LOADED_ENV_FILES.add(resolved)


def resolve_secret(value: str | None, env_name: str | None) -> str:
    """Resolve a secret from explicit value or environment variable."""
    if value:
        return value
    if env_name:
        secret = os.getenv(env_name, "")
        if secret:
            return secret
    return ""

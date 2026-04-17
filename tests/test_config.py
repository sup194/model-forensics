import os
from pathlib import Path

from model_forensics.config import load_local_env, resolve_secret


def test_load_local_env_loads_nearest_env_file(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    configs = root / "configs"
    configs.mkdir(parents=True)
    env_path = root / ".env"
    env_path.write_text("SUSPECT_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("SUSPECT_API_KEY", raising=False)

    loaded = load_local_env(configs)

    assert loaded == env_path
    assert os.getenv("SUSPECT_API_KEY") == "from-dotenv"


def test_resolve_secret_prefers_explicit_value(monkeypatch) -> None:
    monkeypatch.setenv("SUSPECT_API_KEY", "from-env")

    secret = resolve_secret("explicit-secret", "SUSPECT_API_KEY")

    assert secret == "explicit-secret"

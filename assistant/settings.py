"""Settings of the assistant: assistant/config.yaml + secrets from .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = Path(__file__).with_name("config.yaml")


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines). Never overrides real environment variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    chat_model: str
    classifier_model: str
    reasoning_effort: str
    max_tool_rounds: int
    verify_retries: int
    output_dir: Path
    duckdb_file: Path
    usage_log: Path
    host: str
    port: int
    cors_origins: list[str] = field(default_factory=list)


def load_settings(path: Path = CONFIG_FILE) -> Settings:
    load_env()
    with open(path, encoding="utf-8") as fh:
        c = yaml.safe_load(fh)
    # Hosting overrides (e.g. Hugging Face Spaces): ASSISTANT_HOST, PORT, ASSISTANT_CORS_ORIGINS (comma-separated,
    # added to the ones in config.yaml).
    extra_origins = [o.strip() for o in os.environ.get("ASSISTANT_CORS_ORIGINS", "").split(",") if o.strip()]
    return Settings(
        chat_model=c["chat_model"], classifier_model=c["classifier_model"],
        reasoning_effort=c["reasoning_effort"], max_tool_rounds=int(c["max_tool_rounds"]),
        verify_retries=int(c["verify_retries"]),
        output_dir=ROOT / c["output_dir"], duckdb_file=ROOT / c["duckdb_file"], usage_log=ROOT / c["usage_log"],
        host=os.environ.get("ASSISTANT_HOST", c["server"]["host"]),
        port=int(os.environ.get("PORT", c["server"]["port"])),
        cors_origins=list(c["server"]["cors_origins"]) + extra_origins,
    )

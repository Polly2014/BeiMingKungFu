"""
SoulPort LLM configuration — manages API settings for semantic merge.

Config file: ~/.soulport/config.json
{
    "llm": {
        "api_base": "https://api.polly.wang/v1",
        "api_key": "your-key-here",
        "model": "claude-opus-4-20250514"
    }
}

Environment variables override config file:
    SOULPORT_LLM_API_BASE
    SOULPORT_LLM_API_KEY
    SOULPORT_LLM_MODEL
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / ".soulport"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_API_BASE = "https://api.polly.wang/v1"
DEFAULT_MODEL = "claude-opus-4-20250514"


@dataclass
class LLMConfig:
    api_base: str = DEFAULT_API_BASE
    api_key: str = ""
    model: str = DEFAULT_MODEL


def load_llm_config() -> LLMConfig:
    """Load LLM config from file + environment variables (env wins)."""
    config = LLMConfig()

    # Load from config file
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            llm = data.get("llm", {})
            if llm.get("api_base"):
                config.api_base = llm["api_base"]
            if llm.get("api_key"):
                config.api_key = llm["api_key"]
            if llm.get("model"):
                config.model = llm["model"]
        except (json.JSONDecodeError, OSError):
            pass

    # Environment variables override
    if os.getenv("SOULPORT_LLM_API_BASE"):
        config.api_base = os.environ["SOULPORT_LLM_API_BASE"]
    if os.getenv("SOULPORT_LLM_API_KEY"):
        config.api_key = os.environ["SOULPORT_LLM_API_KEY"]
    if os.getenv("SOULPORT_LLM_MODEL"):
        config.model = os.environ["SOULPORT_LLM_MODEL"]

    return config


def save_llm_config(config: LLMConfig):
    """Save LLM config to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    data = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    data["llm"] = {
        "api_base": config.api_base,
        "api_key": config.api_key,
        "model": config.model,
    }

    CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_llm_configured() -> Optional[str]:
    """Check if LLM is configured. Returns error message if not, None if OK."""
    config = load_llm_config()
    if not config.api_key:
        return (
            "LLM API key not configured. Set up with:\n"
            f"  1. Create {CONFIG_FILE} with:\n"
            '     {"llm": {"api_key": "your-key", "api_base": "https://api.polly.wang/v1", "model": "claude-opus-4-20250514"}}\n'
            "  2. Or set environment variable: SOULPORT_LLM_API_KEY=your-key"
        )
    return None

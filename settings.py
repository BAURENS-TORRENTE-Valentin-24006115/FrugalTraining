"""Application configuration and .env loading helpers."""

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AI_SERVER_CONFIG = ROOT / "ai-server" / "config.json"
AI_SERVER_PORT = 11343
# Read the server's configured port so every local API call uses the same endpoint.
try:
    with AI_SERVER_CONFIG.open(encoding="utf-8") as config_file:
        AI_SERVER_PORT = int(json.load(config_file).get("beacon_port", AI_SERVER_PORT))
except (OSError, ValueError, TypeError, AttributeError):
    pass

DISTANT_MODEL_PROVIDER = "mistral"
TTS_VOICE = "fr-FR-DeniseNeural"
QUESTIONNAIRE_PATH = ROOT / "Questionnaire.pdf"

AI_ENDPOINTS = {
    "local": f"http://127.0.0.1:{AI_SERVER_PORT}/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}

AI_MODELS = {
    "local": "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
    "deepseek": "deepseek-flash",
    "mistral": "open-mistral-nemo",
    "gemini": "gemini-1.5-pro",
}

API_KEY_NAMES = {
    "deepseek": "DEEPSEEK_API",
    "mistral": "MISTRAL_API",
    "gemini": "GEMINI_API",
}


def load_env_file(path: Path = ROOT / ".env") -> dict[str, str]:
    """Read simple .env assignments without modifying the process environment."""
    if not path.is_file():
        return {}

    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def api_key_for(provider: str, env_values: dict[str, str]) -> str:
    name = API_KEY_NAMES.get(provider.lower())
    return (os.environ.get(name, "") or env_values.get(name, "")) if name else ""

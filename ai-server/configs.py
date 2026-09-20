"""
MAIA Beacon & llama-cpp Configuration Module
Centralized configuration parameters, repository URLs, binary download links, and fallback links.
"""

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
STATE_FILE = SCRIPT_DIR / "state.json"

DEFAULT_CONFIG = {
    # Git Repositories
    "beacon_repo": "https://github.com/MAIA-404-systems/MAIA-Beacon.git",
    "beacon_tag": "v1.0.0",
    "llama_repo": "https://github.com/MAIA-404-systems/llama-cpp-turboquant.git",
    "llama_tag": "main",

    # Precompiled Binaries Settings (GitHub Releases)
    # Binary release URL patterns. Example format:
    # https://github.com/MAIA-404-systems/llama-cpp-turboquant/releases/download/{tag}/llama-server-{os}-{backend}.zip
    "llama_releases_repo": "MAIA-404-systems/llama-cpp-turboquant",
    "llama_release_tag": "v1.0.0-binaries",
    "llama_release_url_template": "https://github.com/MAIA-404-systems/llama-cpp-turboquant/releases/download/{tag}/llama-server-{os}-{backend}.{ext}",

    # CMake installation links & recommendations
    "cmake_download_url": "https://cmake.org/download/",
    "cmake_install_help": {
        "Windows": "Download CMake from https://cmake.org/download/ or run: winget install Kitware.CMake",
        "Linux": "Run: sudo apt-get update && sudo apt-get install -y cmake build-essential (or your distribution package manager)",
        "Darwin": "Run: brew install cmake",
    },

    # Network & Paths
    "beacon_host": "127.0.0.1",
    "beacon_port": 11343,
    "idle_timeout_seconds": 300,
    "deps_dir": "ai-server/deps",
    "models_dir": "ai-server/models",

    # Default Model
    "default_model_repo": "mistralai/Ministral-3-3B-Instruct-2512-GGUF",
    "default_model_file": "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
}


def load_config():
    """Load configuration dictionary, applying overrides from config.json if present."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"[!] Warning: Failed to parse {CONFIG_FILE}, using defaults. Error: {e}")
    return config

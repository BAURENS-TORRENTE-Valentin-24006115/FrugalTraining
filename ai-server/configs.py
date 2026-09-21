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
    "llama_releases_repo": "MAIA-404-systems/llama-cpp-turboquant",
    "llama_release_tag": "v1.0.0",
    "llama_release_url_template": "https://github.com/MAIA-404-systems/llama-cpp-turboquant/releases/download/{tag}/llama-server-{tag}-{os}-{arch}-{backend}.{ext}",

    # CMake & Git installation links & recommendations
    "cmake_download_url": "https://cmake.org/download/",
    "cmake_install_help": {
        "Windows": "Download CMake from https://cmake.org/download/ or run: winget install Kitware.CMake",
        "Linux": "Run: sudo apt-get update && sudo apt-get install -y cmake build-essential",
        "Darwin": "Run: brew install cmake",
    },
    "git_download_url": "https://git-scm.com/downloads",
    "git_install_help": {
        "Windows": "Download Git from https://git-scm.com/downloads or run: winget install Git.Git",
        "Linux": "Run: sudo apt-get update && sudo apt-get install -y git",
        "Darwin": "Run: brew install git",
    },


    # Network & Paths
    "beacon_host": "127.0.0.1",
    "beacon_port": 11343,
    "idle_timeout_seconds": 300,
    "deps_dir": "ai-server/deps",
    "models_dir": "ai-server/models",
    "venv_dir": "ai-server/.venv",


    # Default Model
    "default_model_repo": "mistralai/Ministral-3-3B-Instruct-2512-GGUF",
    "default_model_file": "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
}


import ssl
import urllib.error
import urllib.request

def safe_urlopen(url_or_req, timeout=30):
    """Open URL with automatic SSL certificate verification fallback for systems missing root CA bundles."""
    # Try standard request first with default/certifi context
    try:
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(cafile=certifi.where())
        except Exception:
            pass
        return urllib.request.urlopen(url_or_req, timeout=timeout, context=ctx)
    except Exception as e:
        err_str = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in err_str or "certificate verify failed" in err_str or "SSL" in err_str or isinstance(e, urllib.error.URLError):
            try:
                ctx = ssl._create_unverified_context()
                return urllib.request.urlopen(url_or_req, timeout=timeout, context=ctx)
            except Exception:
                pass
        raise e

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


"""
MAIA Beacon & llama-cpp Configuration Module
Centralized configuration parameters, repository URLs, binary download links, and fallback links.
"""

import json
import os
from pathlib import Path
import re
import ssl
import sys
from typing import Any, Optional, TextIO, Union
import urllib.error
import urllib.request

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
STATE_FILE = SCRIPT_DIR / "state.json"

DEFAULT_CONFIG: dict[str, Any] = {
    # Source archives
    "beacon_repo": "https://github.com/MAIA-404-systems/MAIA-Beacon",
    "beacon_tag": "v1.0.0",
    "llama_repo": "https://github.com/MAIA-404-systems/llama-cpp-turboquant",
    "llama_tag": "main",

    # Precompiled Binaries Settings (GitHub Releases)
    "llama_release_repo": "MAIA-404-systems/llama-cpp-turboquant",
    "llama_release_tag": "v1.0.0",
    "llama_release_url_template": "https://github.com/{repo}/releases/download/{tag}/llama-server-{tag}-{os}-{arch}-{backend}.{ext}",

    # CMake installation links & recommendations
    "cmake_download_url": "https://cmake.org/download/",
    "cmake_install_help": {
        "Windows": "Download CMake from https://cmake.org/download/ or run: winget install Kitware.CMake",
        "Linux": "Run: sudo apt-get update && sudo apt-get install -y cmake build-essential",
        "Darwin": "Run: brew install cmake",
    },

    # Network & Paths
    "beacon_host": "127.0.0.1",
    "beacon_port": 11343,
    "idle_timeout_seconds": 300,
    "deps_dir": "ai-server/deps",
    "models_dir": "ai-server/models",
    "venv_dir": "ai-server/.venv",
    "backend": "auto",
    "device": "auto",
    "llama_port": None,
    "context_size": 4096,
    "max_vram_ratio": 0.90,
    "vram_margin_mib": 512,
    "startup_timeout_seconds": 300,
    "default_model_revision": "main",
    "default_model_sha256": None,
    "binary_sha256": {},

    # Default Model
    "default_model_repo": "mistralai/Ministral-3-3B-Instruct-2512-GGUF",
    "default_model_file": "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
}


def safe_urlopen(url_or_req: Union[str, urllib.request.Request], timeout: int = 30) -> Any:
    """Open an HTTP/HTTPS URL safely with certificate verification using certifi if present.

    Args:
        url_or_req (str or urllib.request.Request): Target URL string or Request object.
        timeout (int, optional): Connection timeout in seconds. Defaults to 30.

    Returns:
        http.client.HTTPResponse: Active response context manager stream.
    """
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except ImportError:
        pass
    return urllib.request.urlopen(url_or_req, timeout=timeout, context=ctx)


def load_config() -> dict[str, Any]:
    """Load, validate, and return the server configuration dictionary.

    Applies custom configuration overrides from config.json over built-in defaults
    and enforces strict type, range, and format validation on all parameters.

    Returns:
        dict: Validated configuration dictionary.

    Raises:
        ValueError: If config file is malformed, contains unknown keys, or fails validation checks.
    """
    config = DEFAULT_CONFIG.copy()
    user_config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
        except Exception as e:
            raise ValueError(f"Invalid configuration {CONFIG_FILE}: {e}") from e
    if not isinstance(user_config, dict):
        raise ValueError("config.json must contain an object")
    if "llama_releases_repo" in user_config:
        if "llama_release_repo" in user_config:
            raise ValueError("Use only llama_release_repo")
        user_config["llama_release_repo"] = user_config.pop("llama_releases_repo")
    unknown = set(user_config) - set(DEFAULT_CONFIG) - {"llama_load_mode"}
    if unknown:
        raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
    config.update(user_config)
    int_fields = (
        "beacon_port", "llama_port", "context_size",
        "idle_timeout_seconds", "startup_timeout_seconds", "vram_margin_mib",
    )
    for name in int_fields:
        value = config[name]
        if name == "llama_port" and value is None:
            continue
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < (0 if name in ("idle_timeout_seconds", "vram_margin_mib") else 1)
        ):
            raise ValueError(f"{name} must be a valid non-negative integer")
    for name in ("beacon_port", "llama_port"):
        if config[name] is not None and config[name] > 65535:
            raise ValueError(f"Invalid TCP port: {name}")
    if config["llama_port"] == config["beacon_port"]:
        raise ValueError("Beacon and llama must use different ports")
    if config["backend"] not in ("auto", "cpu", "cuda", "vulkan", "metal"):
        raise ValueError("Unsupported backend")
    max_vram = config["max_vram_ratio"]
    if (
        not isinstance(max_vram, (int, float))
        or isinstance(max_vram, bool)
        or not 0 < max_vram <= 1
    ):
        raise ValueError("max_vram_ratio must be in (0, 1]")
    if config["context_size"] > 131072:
        raise ValueError("context_size exceeds the supported maximum of 131072")
    for name in ("deps_dir", "models_dir", "venv_dir", "beacon_host", "device"):
        val = config[name]
        if not isinstance(val, str) or not val.strip() or "\n" in val or "\r" in val:
            raise ValueError(f"Invalid {name}")
    filename = config["default_model_file"]
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or not filename.endswith(".gguf")
    ):
        raise ValueError("default_model_file must be a GGUF filename, not a path")
    for name in ("llama_repo", "beacon_repo"):
        if not isinstance(config[name], str) or not config[name].startswith("https://"):
            raise ValueError(f"{name} must use HTTPS")
    if config.get("llama_load_mode", "mmap") not in ("mmap", "mmap+mlock"):
        raise ValueError("Unsupported llama_load_mode")
    hashes = config["binary_sha256"]
    if not isinstance(hashes, dict) or any(not isinstance(k, str) for k in hashes):
        raise ValueError("binary_sha256 must map archive names to SHA256 strings")
    for value in [config["default_model_sha256"], *hashes.values()]:
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value)):
            raise ValueError("Expected a 64-character SHA256")
    tag_keys = (
        "beacon_tag", "llama_tag", "llama_release_tag", "llama_release_repo",
        "default_model_repo", "default_model_revision", "llama_release_url_template",
    )
    for key in tag_keys:
        value = config[key]
        if (
            not isinstance(value, str)
            or not value
            or any(char in value for char in ("\n", "\r", "\0"))
            or value.startswith("-")
        ):
            raise ValueError(f"Invalid {key}")
    if not config["llama_release_url_template"].startswith("https://"):
        raise ValueError("llama_release_url_template must use HTTPS")
    return config


def print_effective_config(config: dict[str, Any]) -> None:
    """Print key configuration parameters to stdout.

    Args:
        config (dict): The effective configuration dictionary to display.
    """
    print("[+] Effective configuration (config.json over built-in defaults):")
    display_keys = (
        "backend", "device", "beacon_host", "beacon_port", "llama_port",
        "context_size", "deps_dir", "models_dir", "venv_dir", "beacon_tag",
        "llama_release_tag",
    )
    for key in display_keys:
        print(f"    {key} = {config[key]}")

class _TeeStream:
    """Output stream wrapper that tees written data to stdout/stderr and one or more log files."""
    def __init__(self, stream: TextIO, file_objs: Union[TextIO, list[TextIO]]) -> None:
        """Initialize the _TeeStream wrapper.

        Args:
            stream (file object): Original stdout or stderr stream.
            file_objs (file object or list): Additional file stream(s) to mirror output into.
        """
        self.stream = stream
        self.file_objs = file_objs if isinstance(file_objs, list) else [file_objs]

    def write(self, data: str) -> None:
        """Write string data to the primary stream and all log file streams.

        Args:
            data (str): Text data to write.
        """
        self.stream.write(data)
        for f in self.file_objs:
            try:
                f.write(data)
                f.flush()
            except Exception:
                pass

    def flush(self) -> None:
        """Flush buffers for the primary stream and all log file streams."""
        self.stream.flush()
        for f in self.file_objs:
            try:
                f.flush()
            except Exception:
                pass

    def reconfigure(self, **kwargs: Any) -> None:
        """Reconfigure stream parameters if supported by underlying primary stream.

        Args:
            **kwargs: Keyword options passed to stream.reconfigure().
        """
        if hasattr(self.stream, "reconfigure"):
            self.stream.reconfigure(**kwargs)

    def isatty(self) -> bool:
        """Check if the underlying stream is attached to an interactive terminal.

        Returns:
            bool: True if interactive terminal, False otherwise.
        """
        return getattr(self.stream, "isatty", lambda: False)()


def init_file_logger(script_name: str = "ai-server.log") -> None:
    """Initialize file logging by teeing stdout and stderr streams to log files.

    Args:
        script_name (str, optional): Target log file name base. Defaults to "ai-server.log".
    """
    try:
        log_files: list[TextIO] = []
        log_dir = SCRIPT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file_name = Path(script_name).stem + ".log"
        log_files.append(open(log_dir / log_file_name, "a", encoding="utf-8", errors="replace"))

        # Mirror logs to local log.txt
        log_files.append(open(SCRIPT_DIR / "log.txt", "a", encoding="utf-8", errors="replace"))

        # Optional mirrored log path via environment variable or drive E: if available
        mirror_env = os.environ.get("FRUGAL_MIRROR_LOG_PATH")
        if mirror_env:
            try:
                log_files.append(open(mirror_env, "a", encoding="utf-8", errors="replace"))
            except Exception:
                pass
        elif os.name == "nt" and Path("E:/").exists():
            try:
                log_files.append(open("E:/log.txt", "a", encoding="utf-8", errors="replace"))
            except Exception:
                pass

        if not isinstance(sys.stdout, _TeeStream):
            sys.stdout = _TeeStream(sys.stdout, log_files)
        if not isinstance(sys.stderr, _TeeStream):
            sys.stderr = _TeeStream(sys.stderr, log_files)
    except Exception:
        pass

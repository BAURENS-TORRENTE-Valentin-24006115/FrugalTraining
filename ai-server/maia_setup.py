"""Prepare Beacon dependencies; starting an installed server never runs pip."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Optional, Union
import uuid

from configs import ROOT_DIR, load_config
from llama_setup import ensure_source_archive, run_cmd
from setup_utils import atomic_json, digest, read_json


def python_works(
    executable: Union[str, Path],
    expected_prefix: Optional[Union[str, Path]] = None,
    imports: bool = False,
) -> bool:
    """Test if a Python executable is functional, meets version requirements, and optionally has required imports.

    Args:
        executable (str or Path): Path to the Python executable.
        expected_prefix (str or Path, optional): Expected sys.prefix path for venv validation. Defaults to None.
        imports (bool, optional): Whether to check availability of core dependencies. Defaults to False.

    Returns:
        bool: True if Python version is >= 3.11, prefix matches (if specified), and imports succeed (if requested).
    """
    code = ("import fastapi,uvicorn,httpx,pydantic,psutil,requests; " if imports else "")
    code += "import sys,json; print(json.dumps({'prefix':sys.prefix,'version':list(sys.version_info[:2])}))"
    try:
        result = subprocess.run([str(executable), "-I", "-c", code], capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        prefix_matches = expected_prefix is None or Path(data["prefix"]).resolve() == Path(expected_prefix).resolve()
        return bool(data.get("version", []) >= [3, 11] and prefix_matches)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return False


def get_or_create_venv(config: dict[str, Any], offline: bool = False) -> Path:
    """Retrieve an existing Python virtual environment or create a new one.

    Args:
        config (dict): Server configuration object containing venv directory settings.
        offline (bool, optional): Whether setup is running in offline mode. Defaults to False.

    Returns:
        Path: Path to the functional Python executable in the virtual environment.

    Raises:
        RuntimeError: If the virtual environment is broken or creation fails in offline mode.
    """
    root = (ROOT_DIR / config["venv_dir"]).resolve()
    executable = root / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
    if python_works(executable, root):
        return executable
    if offline:
        raise RuntimeError(f"Broken or missing venv {root}; recreate it through online setup with Python 3.11+")
    backup: Optional[Path] = None
    if root.exists():
        backup = root.with_name(root.name + ".previous-" + uuid.uuid4().hex[:8])
        root.rename(backup)
        print(f"[+] Broken venv preserved at {backup}")
    try:
        run_cmd([sys.executable, "-m", "venv", str(root)])
        if not python_works(executable, root):
            raise RuntimeError("Created venv is not executable")
    except Exception:
        if root.exists():
            root.rename(root.with_name(root.name + ".failed-" + uuid.uuid4().hex[:8]))
        if backup:
            backup.rename(root)
        raise
    return executable


def ensure_beacon_deps(
    beacon_dir: Union[str, Path],
    venv_python: Union[str, Path],
    offline: bool = False,
    update: bool = False,
) -> None:
    """Ensure required Python packages for Beacon are installed in the virtual environment.

    Args:
        beacon_dir (str or Path): Path to the Beacon repository directory containing `requirements.txt`.
        venv_python (str or Path): Path to the Python executable in the target virtual environment.
        offline (bool, optional): If True, skips installation and requires dependencies to be cached. Defaults to False.
        update (bool, optional): Force re-installation of dependencies even if marker matches. Defaults to False.

    Raises:
        RuntimeError: If requirements file is missing, offline mode lacks dependencies, or pip install fails.
    """
    requirements = Path(beacon_dir) / "requirements.txt"
    if not requirements.is_file():
        raise RuntimeError("Incomplete Beacon source: requirements.txt missing")
    python_path = Path(venv_python).resolve()
    marker = python_path.parent.parent / ".frugal-deps.json"
    wanted = {"requirements_sha256": digest(requirements), "python": str(python_path)}
    if not update and read_json(marker) == wanted and python_works(python_path, imports=True):
        return
    if offline:
        raise RuntimeError("Dependencies are missing, moved or changed; run online setup first")
    run_cmd([str(python_path), "-m", "pip", "install", "-r", str(requirements)])
    run_cmd([str(python_path), "-m", "pip", "check"])
    if not python_works(python_path, imports=True):
        raise RuntimeError("Beacon dependency imports failed")
    atomic_json(marker, wanted)


def managed_environment(
    config: dict[str, Any],
    llama_exe: Union[str, Path],
    llama_port: int,
) -> dict[str, str]:
    """Construct an isolated environment dictionary for running the Beacon process.

    Args:
        config (dict): Server configuration parameters.
        llama_exe (str or Path): Path to the `llama-server` executable.
        llama_port (int): Reserved port for `llama-server`.

    Returns:
        dict: Environment variables dictionary customized for Beacon execution.
    """
    # Remove inherited settings before Beacon's setdefault-based .env reader runs.
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(("BEACON_", "LLAMA_", "FRUGAL_", "MAX_VRAM"))
        and key.upper() not in (
            "MODELS_DIR", "TARGET_DEVICE", "IDLE_TIMEOUT_SECONDS", "PYTHONPATH", "PYTHONHOME"
        )
    }
    env.update({
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
        "BEACON_HOST": config["beacon_host"], "BEACON_PORT": str(config["beacon_port"]),
        "LLAMA_SERVER_EXE": str(Path(llama_exe).resolve()), "LLAMA_SERVER_HOST": "127.0.0.1",
        "LLAMA_SERVER_PORT": str(llama_port), "MODELS_DIR": str((ROOT_DIR / config["models_dir"]).resolve()),
        "TARGET_DEVICE": "GPU", "IDLE_TIMEOUT_SECONDS": str(config["idle_timeout_seconds"]),
        "LLAMA_LOAD_MODE": config.get("llama_load_mode", "mmap"),
        "LLAMA_ARG_N_PARALLEL": "1", "LLAMA_ARG_FLASH_ATTN": "on",
        "MAX_VRAM_PERCENT": str(config["max_vram_ratio"]),
        "LLAMA_ARG_DEVICE": "none" if config.get("_actual_backend") == "cpu" else config["device"],
    })
    # Omit the option for automatic selection; 'auto' is not a llama device ID.
    if env["LLAMA_ARG_DEVICE"] == "auto":
        del env["LLAMA_ARG_DEVICE"]
    print("[i] Beacon manages VRAM; legacy vram_margin_mib is not applied.")
    return env


def setup_maia(
    llama_exe_path: Optional[Union[str, Path]] = None,
    offline: bool = False,
    update: bool = False,
    config: Optional[dict[str, Any]] = None,
) -> tuple[Path, Path]:
    """Set up the MAIA-Beacon repository and virtual environment.

    Args:
        llama_exe_path (str or Path, optional): Path to the llama-server executable. Defaults to None.
        offline (bool, optional): Execute setup in offline mode. Defaults to False.
        update (bool, optional): Force updating the repository and dependencies. Defaults to False.
        config (dict, optional): Server configuration dict. Defaults to loading from disk.

    Returns:
        tuple[Path, Path]: Tuple containing (beacon_repository_dir, venv_python_executable).
    """
    cfg = config or load_config()
    root = (ROOT_DIR / cfg["deps_dir"] / "MAIA-Beacon").resolve()
    ensure_source_archive(cfg["beacon_repo"], root, cfg["beacon_tag"], offline=offline, update=update)
    python = get_or_create_venv(cfg, offline=offline)
    ensure_beacon_deps(root, python, offline=offline, update=update)
    return root, python


if __name__ == "__main__":
    from setup_utils import file_lock
    with file_lock(Path(__file__).with_name("setup.lock")):
        setup_maia()

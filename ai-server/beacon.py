"""Prepare, validate and supervise one local Beacon installation."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Optional, Union
import urllib.error
import urllib.request

from configs import ROOT_DIR, SCRIPT_DIR, STATE_FILE, init_file_logger, load_config, print_effective_config
from install import print_system_report, scan_hardware
from llama_setup import setup_llama
from maia_setup import managed_environment, setup_maia
from setup_utils import atomic_json, digest, download, file_lock, read_json


def reserve_port(host: str = "127.0.0.1", port: int = 0) -> socket.socket:
    """Reserve a local port until the returned socket is closed."""
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, port))
        return sock
    except Exception:
        sock.close()
        raise


def stop_process(process: subprocess.Popen) -> None:
    """Stop this child process, forcing termination if it does not exit."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def validate_model(path: Union[str, Path], expected_sha256: Optional[str] = None) -> str:
    """Validate a GGUF model file header format and optional SHA-256 digest.

    Args:
        path (str or Path): Path to the GGUF model file.
        expected_sha256 (str, optional): Expected SHA-256 hash. Defaults to None.

    Returns:
        str: Hexadecimal SHA-256 digest string of the model.

    Raises:
        RuntimeError: If header is invalid/truncated or SHA-256 mismatch occurs.
    """
    with open(path, "rb") as stream:
        header = stream.read(24)
    if len(header) != 24:
        raise RuntimeError(f"Truncated GGUF header: {path}")
    magic, version, tensors, metadata = struct.unpack("<4sIQQ", header)
    if magic != b"GGUF" or version not in (2, 3) or not tensors or not metadata:
        raise RuntimeError(f"Invalid GGUF header: {path}")
    sha256 = digest(path)
    if expected_sha256 and sha256.lower() != expected_sha256.lower():
        raise RuntimeError(f"Model SHA256 mismatch: {path}")
    return sha256


def ensure_model(config: dict[str, Any], offline: bool = False, update: bool = False) -> Path:
    """Ensure the configured default GGUF model exists and is verified.

    Args:
        config (dict): Server configuration parameters.
        offline (bool, optional): Prevent remote downloads if set. Defaults to False.
        update (bool, optional): Force model re-download or update check. Defaults to False.

    Returns:
        Path: Verified local Path to the default GGUF model file.

    Raises:
        RuntimeError: If model is missing in offline mode or download fails.
    """
    root = (ROOT_DIR / config["models_dir"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    model = root / config["default_model_file"]
    marker = model.with_suffix(".gguf.manifest.json")
    identity_keys = ("default_model_repo", "default_model_file", "default_model_revision", "default_model_sha256")
    identity = {k: config[k] for k in identity_keys}
    stamp = read_json(marker)
    if model.is_file() and not update:
        if stamp.get("identity") == identity:
            validate_model(model, config["default_model_sha256"] or stamp.get("sha256"))
            return model
        if not stamp:
            sha256 = validate_model(model, config["default_model_sha256"])
            print(f"[+] Adopting local GGUF {model.name}; full inference will be checked at launch")
            atomic_json(marker, {"identity": identity, "sha256": sha256, "origin": "local"})
            return model
    if offline:
        raise RuntimeError("Default model missing or its configured revision changed; run setup online")
    url = (
        f"https://huggingface.co/{config['default_model_repo']}/resolve/"
        f"{config['default_model_revision']}/{config['default_model_file']}"
    )
    with tempfile.TemporaryDirectory(dir=root, prefix="model-") as temp:
        staged = Path(temp) / model.name
        print(f"[+] Downloading {model.name}")
        download(url, staged, config["default_model_sha256"])
        sha256 = validate_model(staged, config["default_model_sha256"])
        if model.exists():
            backup = model.with_name(model.name + ".previous-" + str(time.time_ns()))
            model.rename(backup)
            print(f"[+] Previous model preserved at {backup}")
        staged.replace(model)
        atomic_json(marker, {"identity": identity, "sha256": sha256, "origin": url})
    return model


def connect_host(host: str) -> str:
    """Normalize wild-card host addresses for local HTTP connections.

    Args:
        host (str): IP host address string.

    Returns:
        str: Loopback address string ('127.0.0.1' or '::1') if host is wildcard, otherwise host.
    """
    return {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)


def service_url(config: dict[str, Any]) -> str:
    """Construct the HTTP base URL string for the local Beacon service.

    Args:
        config (dict): Server configuration parameters dictionary.

    Returns:
        str: Service base URL string (e.g. 'http://127.0.0.1:11343').
    """
    host = connect_host(config["beacon_host"])
    formatted_host = f"[{host}]" if ":" in host else host
    return f"http://{formatted_host}:{config['beacon_port']}"


def local_json(url: str, data: Optional[Any] = None, timeout: int = 5) -> Any:
    """Execute a local HTTP request and return parsed JSON payload without using system proxy settings.

    Args:
        url (str): Target local HTTP URL.
        data (dict or list, optional): JSON request body. Defaults to None.
        timeout (int, optional): Request timeout in seconds. Defaults to 5.

    Returns:
        dict or list: Parsed JSON response.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
    )
    # Local service calls never go through a corporate/inherited HTTP proxy.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


def start_beacon_service(
    beacon_dir: Union[str, Path],
    python_exe: Union[str, Path],
    config: dict[str, Any],
    llama_exe: Union[str, Path],
    llama_port: int,
) -> subprocess.Popen:
    """Launch MAIA-Beacon's own main.py with the prepared environment.

    Args:
        beacon_dir (str or Path): Path to the Beacon checkout directory.
        python_exe (str or Path): Path to Python executable in the virtual environment.
        config (dict): Server configuration object.
        llama_exe (str or Path): Path to llama-server executable.
        llama_port (int): Reserved port for llama-server.

    Returns:
        subprocess.Popen: Process handle of the launched service.
    """
    env = managed_environment(config, llama_exe, llama_port)
    main_py = Path(beacon_dir).resolve() / "main.py"
    if not main_py.is_file():
        raise RuntimeError(f"Beacon entry point missing: {main_py}")
    process = subprocess.Popen(
        [str(python_exe), str(main_py)],
        cwd=beacon_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    def output() -> None:
        """Stream process output line by line to standard output."""
        if process.stdout:
            for line in process.stdout:
                print(line.rstrip(), flush=True)

    threading.Thread(target=output, daemon=True).start()
    return process


def wait_for_healthcheck(process: subprocess.Popen, config: dict[str, Any]) -> None:
    """Wait for Beacon's API, select the configured context and verify inference.

    Args:
        process (subprocess.Popen): Subprocess instance of the Beacon service.
        config (dict): Server configuration dictionary.

    Raises:
        RuntimeError: If process exits prematurely, health check times out, or smoke test fails.
    """
    deadline = time.monotonic() + config["startup_timeout_seconds"]
    base = service_url(config)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Beacon exited before startup: code {process.returncode}")
        try:
            status = local_json(base + "/v1/models", timeout=2)
            if isinstance(status.get("data"), list) and process.poll() is None:
                break
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    else:
        raise RuntimeError("Beacon HTTP startup timed out")
    model = Path(config["default_model_file"]).stem
    local_json(base + "/api/select", {"model": model, "context_size": config["context_size"]})
    deadline = time.monotonic() + config["startup_timeout_seconds"]
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Beacon exited during model loading: code {process.returncode}")
        status = local_json(base + "/api/status")
        if status.get("status") == "error":
            raise RuntimeError(status.get("error_message") or "Beacon model loading failed")
        if status.get("status") == "running" and status.get("active_model") == model:
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("Beacon model loading timed out")
    # A catalog HTTP 200 is not a model/inference readiness check.
    try:
        response = local_json(base + "/v1/chat/completions", {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1, "stream": False,
        }, timeout=config["startup_timeout_seconds"] * 3 + 30)
    except urllib.error.HTTPError as exc:
        try:
            status_detail = local_json(base + "/api/status", timeout=5)
            detail = status_detail.get("error_message")
        except (OSError, ValueError):
            detail = None
        raise RuntimeError(f"Inference smoke test failed (HTTP {exc.code}): {detail or exc.reason}") from exc
    if not isinstance(response.get("choices"), list) or not response["choices"]:
        raise RuntimeError("Inference smoke test returned no choices")
    print(f"[OK] API and one-token inference validated at {base}")


def shutdown(process: subprocess.Popen, config: dict[str, Any]) -> None:
    """Gracefully stop the Beacon service process tree.

    Args:
        process (subprocess.Popen): Active process handle.
        config (dict): Server configuration settings.
    """
    if process.poll() is not None:
        return
    try:
        local_json(service_url(config) + "/api/stop", {}, timeout=15)
    except (OSError, ValueError):
        pass
    if os.name == "nt":
        # Check our PID
        result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=20)
        if result.returncode and process.poll() is None:
            stop_process(process)
        else:
            process.wait(timeout=20)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=15)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI entry point for configuring, validating, and running Beacon.

    Args:
        argv (list of str, optional): Command line arguments. Defaults to None (sys.argv[1:]).

    Returns:
        int: Exit status code (0 for success).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Report configuration and hardware only")
    parser.add_argument(
        "--no-launch", "--setup-only", action="store_true",
        help="Prepare dependencies AND model, without starting the server",
    )
    parser.add_argument(
        "--offline", "--start-only", action="store_true",
        help="Use validated local artifacts only; no pip or downloads",
    )
    parser.add_argument("--update", action="store_true", help="Explicitly refresh configured source/binary/model versions")
    parser.add_argument("--force-rebuild", action="store_true", help="Build llama from the configured source ref")
    parser.add_argument("--verify-only", action="store_true", help="Start, run a real inference smoke test, then stop")
    args = parser.parse_args(argv)
    if args.offline and (args.update or args.force_rebuild):
        parser.error("--offline cannot be combined with --update or --force-rebuild")
    if args.no_launch and args.verify_only:
        parser.error("--no-launch cannot be combined with --verify-only")
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required")
    config = load_config()
    print_effective_config(config)
    hardware = scan_hardware()
    print_system_report(hardware)
    if args.check_only:
        return 0
    with ExitStack() as locks:
        # Hold ownership for the whole server lifetime: setup cannot replace a live binary.
        resources = {
            SCRIPT_DIR / "setup.lock",
            (ROOT_DIR / config["deps_dir"]) / ".frugal.lock",
            (ROOT_DIR / config["models_dir"]) / ".frugal.lock",
            (ROOT_DIR / config["venv_dir"]).with_suffix(".frugal.lock"),
        }
        for path in sorted(resources, key=lambda p: str(p.resolve())):
            locks.enter_context(file_lock(path))
        exe = setup_llama(hardware, args.force_rebuild, args.offline, args.update, config)
        backend_state = read_json(STATE_FILE)
        beacon_dir, python = setup_maia(exe, args.offline, args.update, config)
        model_path = ensure_model(config, args.offline, args.update)
        if args.no_launch:
            print("[OK] Offline artifacts prepared. Use --offline --verify-only to validate inference.")
            return 0
        config["_actual_backend"] = backend_state["backend"]
        beacon_socket = reserve_port(config["beacon_host"], config["beacon_port"])
        llama_socket = None
        try:
            llama_socket = reserve_port(port=config["llama_port"] or 0)
            llama_port = llama_socket.getsockname()[1]
            print(f"[+] Instance ports: Beacon={config['beacon_port']}, llama={llama_port}")
        finally:
            beacon_socket.close()
            if llama_socket:
                llama_socket.close()
        process = start_beacon_service(beacon_dir, python, config, exe, llama_port)
        try:
            try:
                wait_for_healthcheck(process, config)
            except RuntimeError as exc:
                if "0xC000001D" in str(exc):
                    state = read_json(STATE_FILE)
                    if state.get("sha256") == digest(exe):
                        state["runtime_failure"] = str(exc)
                        atomic_json(STATE_FILE, state)
                raise
            if args.verify_only:
                return 0
            code = process.wait()
            if code:
                raise RuntimeError(f"Beacon exited unexpectedly: {code}")
            return 0
        finally:
            shutdown(process, config)


if __name__ == "__main__":
    init_file_logger("beacon.py")
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

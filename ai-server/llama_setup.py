"""Versioned, transactional llama-server setup with validated backend fallback."""
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any, Optional, Union
import zipfile

from configs import ROOT_DIR, STATE_FILE, load_config
import install
from setup_utils import (
    atomic_json,
    digest,
    download,
    portable_path,
    publish_directory,
    read_json,
    safe_extract,
)


def run_cmd(
    cmd: list[Any],
    cwd: Optional[Union[str, Path]] = None,
    check: bool = True,
) -> bool:
    """Execute a subprocess command line synchronously.

    Args:
        cmd (list): Command arguments list.
        cwd (str or Path, optional): Working directory for the command. Defaults to None.
        check (bool, optional): Whether to raise an exception if returncode is non-zero. Defaults to True.

    Returns:
        bool: True if the command returned exit code 0.
    """
    result = subprocess.run([str(item) for item in cmd], cwd=cwd, check=check, timeout=1800)
    return result.returncode == 0


def ensure_source_archive(
    repo_url: str,
    target_dir: Union[str, Path],
    tag: Optional[str] = None,
    offline: bool = False,
    update: bool = False,
) -> Path:
    """Download and validate a versioned source archive without requiring Git.

    A matching local installation is reused. Updates are staged and the previous
    directory is preserved by publish_directory.
    """
    target = Path(target_dir).resolve()
    ref = tag or "main"
    repo = repo_url.removesuffix(".git").rstrip("/")
    expected = {"repo": repo, "ref": ref}
    marker = target / ".frugal-source.json"
    beacon_files = (
        "main.py", "config.py", "requirements.txt", "api/routes.py",
        "engines/manager.py", "engines/llama_engine.py", "engines/npu_engine.py",
        "engines/gguf_parser.py", "hardware/manager.py",
    )
    required_files = beacon_files if target.name == "MAIA-Beacon" else ("CMakeLists.txt", "ggml/CMakeLists.txt")
    stamp = read_json(marker)
    valid = all((target / name).is_file() for name in required_files)
    valid = valid and all((target / name).is_file() for name in stamp.get("files", []))
    if valid and not update and stamp.get("ref") == ref and str(stamp.get("repo", "")).removesuffix(".git") == repo:
        return target
    if offline:
        raise RuntimeError(f"Missing or mismatched source {target} at {ref}; run setup online")

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix="source-") as temp:
        archive = Path(temp) / "source.zip"
        download(f"{repo}/archive/{ref}.zip", archive)
        unpacked = Path(temp) / "unpacked"
        safe_extract(archive, unpacked)
        roots = list(unpacked.iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            raise RuntimeError("Unexpected source archive layout")
        staged = Path(temp) / "source"
        roots[0].rename(staged)
        if not all((staged / name).is_file() for name in required_files):
            raise RuntimeError(f"Incomplete source: expected {required_files}")
        atomic_json(
            staged / marker.name,
            {**expected, "files": [str(p.relative_to(staged)) for p in staged.rglob("*.py")]},
        )
        publish_directory(staged, target)
    return target

def find_llama_server_binary(root: Union[str, Path]) -> Optional[Path]:
    """Find the llama-server executable file inside a directory hierarchy.

    Args:
        root (str or Path): Path to search within.

    Returns:
        Path or None: Path to the executable file, or None if not found.
    """
    name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    matches = [p for p in Path(root).rglob(name) if p.is_file()]
    return sorted(matches, key=lambda p: len(p.parts))[0] if matches else None


def get_platform_info(requested_backend: str) -> tuple[str, str, str, list[str]]:
    """Determine host platform platform name, architecture, archive type, and backend priority order.

    Args:
        requested_backend (str): Requested hardware backend (e.g., 'cuda', 'vulkan', 'metal', 'cpu').

    Returns:
        tuple[str, str, str, list[str]]: Tuple of (os_name, architecture, archive_extension, backend_candidates).

    Raises:
        RuntimeError: If operating system or architecture is unsupported.
    """
    system = platform.system()
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "x64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if system not in ("Windows", "Linux", "Darwin") or arch is None:
        raise RuntimeError(f"Unsupported platform: {system}/{machine}")
    if system == "Windows" and arch != "x64":
        raise RuntimeError("Windows ARM64 is not supported yet; no DLL or runtime will be modified")
    backend_map = {
        "cuda": ["cuda12.4", "cuda", "vulkan", "cpu"],
        "vulkan": ["vulkan", "cpu"],
        "metal": ["metal", "cpu"],
        "cpu": ["cpu"],
    }
    candidates = backend_map.get(requested_backend, ["cpu"])
    os_name = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}[system]
    ext = "zip" if system == "Windows" else "tar.gz"
    return os_name, arch, ext, candidates


def list_devices(executable: Union[str, Path], verbose: bool = False) -> list[dict[str, Any]]:
    """Probe an executable for available hardware computation devices using `--list-devices`.

    Args:
        executable (str or Path): Path to the llama binary.
        verbose (bool, optional): Whether to print probe results. Defaults to False.

    Returns:
        list of dict: Parsed device info dictionaries (id, name, total VRAM, free VRAM).
    """
    command = [str(executable), "--list-devices"]
    result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=20)
    if result.returncode:
        if verbose:
            print(f"[!] {executable} --list-devices exited {result.returncode} (0x{result.returncode & 0xffffffff:08X}): {(result.stdout + result.stderr)[-2000:]}")
        return []
    devices: list[dict[str, Any]] = []
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        match = re.match(r"\s*([\w.-]+):\s+(.+?)\s+\((\d+)\s*MiB,\s*(\d+)\s*MiB free\)", line)
        if match:
            devices.append({"id": match[1], "name": match[2], "total": int(match[3]), "free": int(match[4])})
    if verbose:
        if devices:
            print(f"[+] {executable} devices: {', '.join(d['id'] + ' ' + d['name'] for d in devices)}")
        else:
            print(f"[!] {executable} reported no parseable GPU devices: {(result.stdout + result.stderr)[-2000:]}")
    return devices


def test_binary_execution(
    exe_path: Union[str, Path],
    backend: str = "cpu",
    device: str = "auto",
) -> bool:
    """Test whether a precompiled or built llama binary executes cleanly and supports target hardware.

    Args:
        exe_path (str or Path): Path to the binary executable to test.
        backend (str, optional): Target backend ('cuda', 'vulkan', 'metal', 'cpu'). Defaults to "cpu".
        device (str, optional): Requested device ID or "auto". Defaults to "auto".

    Returns:
        bool: True if binary executes and meets backend/device requirements, False otherwise.
    """
    try:
        command = [str(exe_path), "--version"]
        result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=20)
        if result.returncode != 0:
            print(f"[!] {exe_path} --version exited {result.returncode} (0x{result.returncode & 0xffffffff:08X}): {(result.stdout + result.stderr)[-2000:]}")
            return False
        if backend == "cpu":
            return device == "auto"
        devices = list_devices(exe_path, verbose=True)
        if device != "auto" and not any(d["id"] == device for d in devices):
            print(f"[!] Requested device {device} is not among the devices reported by {exe_path}")
            return False
        return bool(devices)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[!] Binary probe failed for {exe_path}: {exc}")
        return False


def binary_identity(config: dict[str, Any]) -> dict[str, Any]:
    """Construct a dictionary uniquely identifying system software configuration and hardware state.

    Args:
        config (dict): Server configuration object.

    Returns:
        dict: Identity key-value mapping used for binary cache validation.
    """
    config_keys = (
        "llama_release_repo", "llama_release_tag", "llama_release_url_template",
        "llama_repo", "llama_tag", "backend", "device", "binary_sha256", "deps_dir",
    )
    base_identity = {k: config[k] for k in config_keys}
    base_identity["llama_repo"] = base_identity["llama_repo"].removesuffix(".git")
    platform_data = {
        "os": platform.system(),
        "arch": platform.machine(),
        "cpu": platform.processor(),
    }
    return {**base_identity, **platform_data}


def download_precompiled_binary(
    target_dir: Union[str, Path],
    backend: str,
    config: dict[str, Any],
    allow_cpu: bool = True,
) -> tuple[Optional[Path], Optional[str]]:
    """Attempt downloading precompiled binaries for candidate backends in priority order.

    Args:
        target_dir (str or Path): Destination directory for downloading and unpacking binaries.
        backend (str): Preferred backend ('cuda', 'vulkan', 'metal', 'cpu').
        config (dict): Server configuration parameters.
        allow_cpu (bool, optional): Whether to allow falling back to CPU. Defaults to True.

    Returns:
        tuple[Path or None, str or None]: Tuple of (executable_path, matched_backend), or (None, None).
    """
    os_name, arch, ext, candidates = get_platform_info(backend)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        actual = "cuda" if candidate.startswith("cuda") else candidate
        if actual == "cpu" and (config["device"] != "auto" or not allow_cpu):
            continue
        filename = f"llama-server-{config['llama_release_tag']}-{os_name}-{arch}-{candidate}.{ext}"
        url = config["llama_release_url_template"].format(
            repo=config["llama_release_repo"],
            tag=config["llama_release_tag"],
            os=os_name,
            arch=arch,
            backend=candidate,
            ext=ext,
        )
        print(f"[+] Trying {candidate}: {url}")
        try:
            with tempfile.TemporaryDirectory(dir=target, prefix="binary-", ignore_cleanup_errors=True) as temp:
                archive = Path(temp) / filename
                download(url, archive, config["binary_sha256"].get(filename))
                staged = Path(temp) / "unpacked"
                safe_extract(archive, staged)
                executable = find_llama_server_binary(staged)
                if executable is None:
                    raise RuntimeError("Archive contains no llama-server")
                if os.name != "nt":
                    executable.chmod(executable.stat().st_mode | 0o111)
                if platform.system() == "Windows":
                    install.ensure_standalone_dlls(executable.parent)
                if not test_binary_execution(executable, actual, config["device"]):
                    raise RuntimeError("Execution/device validation failed")
                relative = executable.relative_to(staged)
                destination = target / f"bin-{candidate}"
                publish_directory(staged, destination)
                return destination / relative, actual
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile, tarfile.TarError) as exc:
            print(f"[!] {candidate} rejected: {exc}")
    return None, None


def compile_from_source(
    llama_dir: Union[str, Path],
    backend: str,
    config: dict[str, Any],
    update: bool = False,
) -> tuple[Path, str]:
    """Compile llama-server from source using CMake for candidate backends.

    Args:
        llama_dir (str or Path): Path to the llama source directory.
        backend (str): Target hardware backend ('cuda', 'vulkan', 'metal', 'cpu').
        config (dict): Configuration options dict.
        update (bool, optional): Whether to refresh the source archive. Defaults to False.

    Returns:
        tuple[Path, str]: Tuple of (built_executable_path, matched_backend).

    Raises:
        RuntimeError: If build or execution tests fail for all backend candidates.
    """
    ensure_source_archive(config["llama_repo"], llama_dir, config["llama_tag"], update=update)
    _, _, _, candidates = get_platform_info(backend)
    unique_candidates = dict.fromkeys("cuda" if item.startswith("cuda") else item for item in candidates)
    for candidate in unique_candidates:
        if candidate == "cpu" and config["device"] != "auto":
            continue
        build = Path(llama_dir) / ("build-" + candidate)
        args = [
            "cmake", "-S", str(llama_dir), "-B", str(build),
            "-DLLAMA_BUILD_SERVER=ON", "-DLLAMA_BUILD_TESTS=OFF",
            "-DBUILD_SHARED_LIBS=OFF", "-DCMAKE_BUILD_TYPE=Release",
            "-DGGML_CUDA=OFF", "-DGGML_VULKAN=OFF", "-DGGML_METAL=OFF",
        ]
        if platform.system() == "Windows":
            args += ["-G", "Visual Studio 17 2022", "-A", "x64"]
        if candidate != "cpu":
            args += [f"-DGGML_{candidate.upper()}=ON"]
        try:
            run_cmd(args)
            parallel_jobs = str(min(os.cpu_count() or 1, 8))
            run_cmd([
                "cmake", "--build", str(build), "--config", "Release",
                "--target", "llama-server", "--parallel", parallel_jobs,
            ])
            exe = find_llama_server_binary(build)
            if exe and test_binary_execution(exe, candidate, config["device"]):
                return exe, candidate
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[!] Build {candidate} failed: {exc}")
    raise RuntimeError("No build could execute; check compiler, SDK and driver diagnostics above")


def setup_llama(
    hw_info: dict[str, Any],
    force_rebuild: bool = False,
    offline: bool = False,
    update: bool = False,
    config: Optional[dict[str, Any]] = None,
) -> Path:
    """Set up and validate a llama-server binary appropriate for the detected system hardware.

    Args:
        hw_info (dict): Hardware report from scan_hardware().
        force_rebuild (bool, optional): Ignore precompiled binaries and rebuild from source. Defaults to False.
        offline (bool, optional): Prevent downloading binaries or cloning repos. Defaults to False.
        update (bool, optional): Force checking for updated releases or commits. Defaults to False.
        config (dict, optional): Configuration settings dictionary. Defaults to loading from disk.

    Returns:
        Path: Validated Path to the `llama-server` binary.

    Raises:
        RuntimeError: If no functional binary is available or matches hardware requirements.
    """
    cfg = config or load_config()
    backend = cfg["backend"] if cfg["backend"] != "auto" else hw_info.get("recommended_backend", "cpu")
    get_platform_info(backend)
    state = read_json(STATE_FILE)
    identity = binary_identity(cfg)
    cached = ROOT_DIR / state.get("llama_exe_path", "__missing__")
    cached_identity = state.get("identity")
    if isinstance(cached_identity, dict):
        cached_identity = {**cached_identity, "llama_repo": str(cached_identity.get("llama_repo", "")).removesuffix(".git")}
    if not update and not force_rebuild and cached_identity == identity and cached.is_file():
        actual = state.get("backend", "cpu")
        if digest(cached) == state.get("sha256") and test_binary_execution(cached, actual, cfg["device"]):
            if actual == "cpu" and backend != "cpu" and not offline:
                print(f"[+] Hardware recommends {backend}; checking GPU binaries before reusing cached CPU")
                candidate, promoted_backend = download_precompiled_binary(
                    (ROOT_DIR / cfg["deps_dir"]).resolve(), backend, cfg, allow_cpu=False
                )
                if candidate is not None:
                    atomic_json(
                        STATE_FILE,
                        {"identity": identity, "backend": promoted_backend,
                         "llama_exe_path": portable_path(candidate), "sha256": digest(candidate)},
                    )
                    return candidate
            if state.get("runtime_failure"):
                raise RuntimeError(
                    f"Cached binary cannot load a model on this CPU: {state['runtime_failure']}. "
                    "Choose another release/backend or rebuild it"
                )
            print(f"[+] Cached binary verified ({actual}): {cached}")
            return cached
    if offline:
        raise RuntimeError("No validated binary matches this configuration; run setup online")
    deps = (ROOT_DIR / cfg["deps_dir"]).resolve()
    exe, actual = (None, None) if force_rebuild else download_precompiled_binary(deps, backend, cfg)
    if exe is None:
        if not shutil.which("cmake"):
            raise RuntimeError("No usable precompiled binary. Install CMake and a C++ toolchain, or select a supported release")
        exe, actual = compile_from_source(deps / "llama-cpp-turboquant", backend, cfg, update=update)
    atomic_json(
        STATE_FILE,
        {"identity": identity, "backend": actual, "llama_exe_path": portable_path(exe), "sha256": digest(exe)},
    )
    return exe


if __name__ == "__main__":
    from install import scan_hardware
    from setup_utils import file_lock
    with file_lock(Path(__file__).with_name("setup.lock")):
        setup_llama(scan_hardware())

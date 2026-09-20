"""
llama-cpp-turboquant Setup Module
Handles downloading precompiled binaries, CMake source compilation fallbacks,
and CMake installation guidance when build tools are missing.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
import tarfile
from datetime import datetime
from pathlib import Path

from configs import load_config, STATE_FILE, ROOT_DIR
from install import check_tool


def load_state():
    """Load cached compilation/setup state from state.json."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    """Save setup state to state.json."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[!] Warning: Could not save state file: {e}")


def get_git_commit(repo_dir):
    """Get current git commit hash of a repo."""
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"


def run_cmd(cmd, cwd=None, check=True):
    """Utility to execute CLI subprocess commands."""
    print(f"    > Executing: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, cwd=cwd, check=check)
    return res.returncode == 0


def ensure_git_repo(repo_url, target_dir, tag=None):
    """Clone a git repository if missing and checkout specified tag/commit."""
    target_path = Path(target_dir).resolve()
    if not (target_path / ".git").exists():
        print(f"[+] Cloning {repo_url} -> {target_path}...")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        run_cmd(["git", "clone", repo_url, str(target_path)])

    if tag:
        print(f"[+] Checking out {tag} in {target_path.name}...")
        try:
            run_cmd(["git", "fetch", "--tags"], cwd=target_path, check=False)
            run_cmd(["git", "checkout", tag], cwd=target_path, check=False)
        except Exception as e:
            print(f"[!] Note on checkout {tag}: {e}")


def find_llama_server_binary(build_path):
    """Locate the llama-server binary in directory."""
    exe_name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    candidates = [
        build_path / exe_name,
        build_path / "bin" / "Release" / exe_name,
        build_path / "bin" / exe_name,
        build_path / "Release" / exe_name,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def download_precompiled_binary(target_dir, backend, config):
    """
    Attempt to download precompiled llama-server binary for current OS and backend.
    Returns path to downloaded binary if successful, or None if failed.
    """
    os_map = {
        "Windows": "windows",
        "Linux": "linux",
        "Darwin": "macos"
    }
    os_name = os_map.get(platform.system(), "linux")
    ext = "zip" if platform.system() == "Windows" else "tar.gz"

    tag = config.get("llama_release_tag", "v1.0.0-binaries")
    url_template = config.get("llama_release_url_template", "")
    
    if not url_template:
        return None

    download_url = url_template.format(
        tag=tag,
        os=os_name,
        backend=backend,
        ext=ext
    )

    archive_filename = f"llama-server-{os_name}-{backend}.{ext}"
    target_path = Path(target_dir).resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    archive_path = target_path / archive_filename

    print(f"[+] Attempting to download precompiled binary for {os_name.upper()} ({backend.upper()})...")
    print(f"    URL: {download_url}")

    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(archive_path, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)
        
        print(f"[+] Successfully downloaded archive: {archive_path}")

        # Extract archive
        extracted_dir = target_path / f"bin-{backend}"
        extracted_dir.mkdir(parents=True, exist_ok=True)

        if ext == "zip":
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_dir)
        else:
            with tarfile.open(archive_path, 'r:*') as tar_ref:
                tar_ref.extractall(extracted_dir)

        # Cleanup downloaded archive
        try:
            os.remove(archive_path)
        except Exception:
            pass

        # Locate extracted binary
        binary_path = find_llama_server_binary(extracted_dir)
        if binary_path and binary_path.exists():
            # Ensure executable permissions on Linux/macOS
            if platform.system() != "Windows":
                os.chmod(binary_path, 0o755)
            print(f"[OK] Downloaded and extracted precompiled llama-server: {binary_path}")
            return binary_path

    except urllib.error.HTTPError as e:
        print(f"[!] Precompiled binary asset not found on GitHub Releases (HTTP {e.code}).")
    except Exception as e:
        print(f"[!] Binary download failed: {e}")

    return None


def run_cmake_build(llama_path, backend):
    """Run CMake configuration and build for specified backend."""
    build_dirname = f"build-{backend}"
    build_path = llama_path / build_dirname
    if build_path.exists():
        try:
            shutil.rmtree(build_path, ignore_errors=True)
        except Exception:
            pass
    build_path.mkdir(parents=True, exist_ok=True)

    cmake_args = ["cmake", "-B", build_dirname]
    if platform.system() == "Windows":
        cmake_args.extend(["-G", "Visual Studio 17 2022", "-A", "x64"])

    cmake_args.extend([
        "-DCMAKE_CXX_STANDARD=17",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DLLAMA_BUILD_SERVER=ON",
        "-DLLAMA_BUILD_TESTS=OFF",
        "-DLLAMA_BUILD_EXAMPLES=OFF",
    ])

    if backend == "cuda":
        cmake_args.append("-DGGML_CUDA=ON")
    elif backend == "vulkan":
        cmake_args.extend(["-DGGML_VULKAN=ON", "-DGGML_VULKAN_SHADERS_GEN=OFF"])

    print(f"[+] Configuring CMake build for llama-cpp-turboquant ({backend.upper()} backend in {build_dirname})...")
    config_ok = run_cmd(cmake_args, cwd=llama_path, check=False)
    if not config_ok:
        return None

    print(f"[+] Compiling llama-server ({backend.upper()} Release build)...")
    build_ok = run_cmd(["cmake", "--build", build_dirname, "--config", "Release", "--target", "llama-server", "-j"], cwd=llama_path, check=False)
    if not build_ok:
        return None

    return find_llama_server_binary(build_path)


def compile_from_source(llama_dir, backend, config):
    """Compile llama-cpp-turboquant from source repository using CMake."""
    ensure_git_repo(config["llama_repo"], llama_dir, tag=config.get("llama_tag"))
    llama_path = Path(llama_dir).resolve()

    # Try primary backend build
    exe_path = run_cmake_build(llama_path, backend)
    used_backend = backend

    # Fallback to CPU build if primary GPU build failed
    if not exe_path and backend != "cpu":
        print(f"[!] Compilation with {backend.upper()} failed. Retrying with CPU backend fallback...")
        exe_path = run_cmake_build(llama_path, "cpu")
        used_backend = "cpu"

    if exe_path and exe_path.exists():
        commit_hash = get_git_commit(llama_path)
        return exe_path, used_backend, commit_hash
    return None, used_backend, "unknown"


def print_cmake_missing_redirect(config):
    """Print clean instructions and links when CMake is not found."""
    os_name = platform.system()
    cmake_url = config.get("cmake_download_url", "https://cmake.org/download/")
    help_msg = config.get("cmake_install_help", {}).get(os_name, f"Please install CMake from {cmake_url}")

    print("\n" + "!" * 60)
    print("                ERROR: CMAKE IS NOT INSTALLED               ")
    print("!" * 60)
    print("Precompiled binaries could not be downloaded and CMake is required")
    print("to compile llama-cpp-turboquant from source code.")
    print("\nPlease install CMake using the instructions below:")
    print(f"  Official Download Page: {cmake_url}")
    print(f"  Installation Command:   {help_msg}")
    print("!" * 60 + "\n")


def setup_llama(hw_info, force_rebuild=False):
    """
    Main entry point for llama-cpp setup.
    - Check cached binary state.
    - Try downloading precompiled binary.
    - Fallback to CMake source compilation if CMake is available.
    - Redirect user to CMake installation link if CMake is missing.
    """
    config = load_config()
    deps_dir = ROOT_DIR / config["deps_dir"]
    llama_dir = deps_dir / "llama-cpp-turboquant"
    backend = hw_info.get("recommended_backend", "cpu")

    state = load_state()
    cached_exe_str = state.get("llama_exe_path")
    cached_exe = Path(cached_exe_str) if cached_exe_str else None

    # Check existing cached binary
    if not force_rebuild and cached_exe and cached_exe.exists():
        if state.get("status") in ["compiled", "downloaded"]:
            print(f"[+] Found existing valid llama-server binary: {cached_exe}")
            return cached_exe

    # Try downloading precompiled binary first
    if not force_rebuild:
        downloaded_exe = download_precompiled_binary(deps_dir, backend, config)
        if downloaded_exe:
            state.update({
                "backend": backend,
                "status": "downloaded",
                "setup_at": datetime.now().isoformat(),
                "llama_exe_path": str(downloaded_exe.resolve())
            })
            save_state(state)
            return downloaded_exe

    # Fallback to CMake compilation
    has_cmake = check_tool("cmake")
    has_git = check_tool("git")

    if has_cmake and has_git:
        print("[+] Proceeding to compile llama-cpp-turboquant from source using CMake...")
        compiled_exe, used_backend, commit_hash = compile_from_source(llama_dir, backend, config)
        if compiled_exe:
            state.update({
                "llama_commit": commit_hash,
                "backend": used_backend,
                "status": "compiled",
                "setup_at": datetime.now().isoformat(),
                "llama_exe_path": str(compiled_exe.resolve())
            })
            save_state(state)
            return compiled_exe
        else:
            print("[!] Source compilation failed for all backends.")
            state.update({"status": "build_failed", "last_attempt": datetime.now().isoformat()})
            save_state(state)
            sys.exit(1)

    # If CMake is missing and precompiled download was not available, redirect user to installation
    print_cmake_missing_redirect(config)
    state.update({"status": "cmake_missing", "last_attempt": datetime.now().isoformat()})
    save_state(state)
    sys.exit(1)


if __name__ == "__main__":
    from install import scan_hardware
    hw = scan_hardware()
    setup_llama(hw)

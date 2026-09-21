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

from configs import load_config, STATE_FILE, ROOT_DIR, safe_urlopen
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


def download_github_source_zip(repo_url, target_dir, tag=None):
    """Download and extract repository source zip directly from GitHub without Git."""
    target_path = Path(target_dir).resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    
    # Format raw repository base URL (remove trailing .git)
    base_url = repo_url[:-4] if repo_url.endswith(".git") else repo_url
    clean_tag = tag if tag else "main"

    zip_urls = [
        f"{base_url}/archive/refs/tags/{clean_tag}.zip",
        f"{base_url}/archive/{clean_tag}.zip",
        f"{base_url}/archive/refs/heads/{clean_tag}.zip",
        f"{base_url}/archive/refs/heads/main.zip",
    ]

    temp_zip = target_path.parent / f"{target_path.name}_source.zip"
    download_success = False

    for url in zip_urls:
        print(f"[+] Attempting GitHub source download without Git: {url}...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
            with safe_urlopen(req, timeout=30) as resp, open(temp_zip, "wb") as out_file:
                shutil.copyfileobj(resp, out_file)

            download_success = True
            break
        except Exception:
            continue

    if not download_success:
        print(f"[!] Could not download source zip from GitHub: {base_url}")
        return False

    print(f"[+] Extracting source archive to {target_path}...")
    try:
        temp_extract = target_path.parent / f"{target_path.name}_temp_extract"
        if temp_extract.exists():
            shutil.rmtree(temp_extract, ignore_errors=True)

        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            zip_ref.extractall(temp_extract)

        # Move contents of root subfolder inside zip to target_path
        subfolders = [f for f in temp_extract.iterdir() if f.is_dir()]
        if subfolders:
            source_folder = subfolders[0]
            for item in source_folder.iterdir():
                dest_item = target_path / item.name
                if dest_item.exists():
                    if dest_item.is_dir():
                        shutil.rmtree(dest_item, ignore_errors=True)
                    else:
                        os.remove(dest_item)
                shutil.move(str(item), str(target_path))

        shutil.rmtree(temp_extract, ignore_errors=True)
        if temp_zip.exists():
            os.remove(temp_zip)

        print(f"[OK] Successfully extracted source to {target_path}")
        return True
    except Exception as e:
        print(f"[!] Failed to extract source archive: {e}")
        return False


def ensure_git_repo(repo_url, target_dir, tag=None):
    """Ensure repository source code is present via Git clone or direct HTTP ZIP download."""
    target_path = Path(target_dir).resolve()
    
    # Check if directory already exists and contains files
    if target_path.exists() and any(target_path.iterdir()):
        return

    has_git = check_tool("git")
    git_success = False

    if has_git:
        try:
            print(f"[+] Cloning {repo_url} -> {target_path}...")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            git_success = run_cmd(["git", "clone", repo_url, str(target_path)], check=False)
            if git_success and tag:
                print(f"[+] Checking out tag {tag} in {target_path.name}...")
                run_cmd(["git", "fetch", "--tags"], cwd=target_path, check=False)
                run_cmd(["git", "checkout", tag], cwd=target_path, check=False)
        except Exception as e:
            print(f"[!] Git clone failed: {e}")

    # Fallback to direct HTTP ZIP download if Git is missing or clone failed
    if not git_success:
        if not has_git:
            print("[!] Note: Git n'est pas installé sur le système. Il est recommandé de l'installer depuis https://git-scm.com/downloads (ou 'winget install Git.Git').")
        print("[+] Bascule automatique sur le téléchargement direct HTTP de l'archive ZIP...")
        download_github_source_zip(repo_url, target_dir, tag=tag)




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


def get_platform_info(requested_backend):
    """Map system platform to release asset naming conventions."""
    sys_name = platform.system()
    os_map = {
        "Windows": "windows",
        "Linux": "linux",
        "Darwin": "macos"
    }
    os_name = os_map.get(sys_name, "linux")
    
    machine = platform.machine().lower()
    if machine in ["amd64", "x86_64", "x64"]:
        arch = "x64"
    elif machine in ["arm64", "aarch64"]:
        arch = "arm64"
    else:
        arch = machine

    ext = "zip" if sys_name == "Windows" else "tar.gz"

    # Define backend candidates to try in order of preference
    backend_candidates = []
    if requested_backend == "cuda":
        backend_candidates.extend(["cuda12.4", "cuda", "vulkan", "cpu"])
    elif requested_backend == "metal":
        backend_candidates.extend(["metal", "vulkan", "cpu"])
    elif requested_backend == "vulkan":
        backend_candidates.extend(["vulkan", "cpu"])
    else:
        backend_candidates.append("cpu")

    return os_name, arch, ext, backend_candidates


def download_precompiled_binary(target_dir, backend, config):
    """
    Attempt to download precompiled llama-server binary for current OS and backend.
    Returns path to downloaded binary if successful, or None if failed.
    """
    os_name, arch, ext, backend_candidates = get_platform_info(backend)

    tag = config.get("llama_release_tag", "v1.0.0")
    url_template = config.get("llama_release_url_template", "")
    
    if not url_template:
        return None

    target_path = Path(target_dir).resolve()
    target_path.mkdir(parents=True, exist_ok=True)

    for candidate_backend in backend_candidates:
        download_url = url_template.format(
            tag=tag,
            os=os_name,
            arch=arch,
            backend=candidate_backend,
            ext=ext
        )
        archive_filename = f"llama-server-{tag}-{os_name}-{arch}-{candidate_backend}.{ext}"
        archive_path = target_path / archive_filename

        print(f"[+] Attempting to download precompiled binary for {os_name.upper()} ({candidate_backend.upper()})...")
        print(f"    URL: {download_url}")

        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
            with safe_urlopen(req, timeout=45) as resp, open(archive_path, "wb") as out_file:
                shutil.copyfileobj(resp, out_file)

            
            print(f"[+] Successfully downloaded archive: {archive_path}")

            # Extract archive
            extracted_dir = target_path / f"bin-{candidate_backend}"
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
                print(f"[OK] Downloaded and ready: llama-server ({candidate_backend.upper()}): {binary_path}")
                return binary_path

        except urllib.error.HTTPError as e:
            print(f"[!] Asset '{archive_filename}' not found (HTTP {e.code}).")
        except Exception as e:
            print(f"[!] Binary download attempt failed: {e}")

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


from install import check_tool, ensure_vcredist, ensure_standalone_dlls, clean_corrupted_local_dlls


def test_binary_execution(exe_path, attempt_recovery=True):
    """Test if a llama-server binary can execute on the current system."""
    if not exe_path or not exe_path.exists():
        print(f"[!] Execution test failed: {exe_path} does not exist.")
        return False

    print(f"[+] Running execution test on: {exe_path}...")
    ensure_standalone_dlls(exe_path.parent)

    try:
        res = subprocess.run([str(exe_path), "--version"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            print(f"[OK] Execution test PASSED for: {exe_path.name}")
            return True
        else:
            hex_code = hex(res.returncode & 0xFFFFFFFF)
            print(f"[!] Execution test FAILED for {exe_path.name} (exit code: {res.returncode} / hex: {hex_code})")
            if res.stdout.strip():
                print(f"    stdout: {res.stdout.strip()}")
            if res.stderr.strip():
                print(f"    stderr: {res.stderr.strip()}")

            # If failed due to DLL / access violation / image format, attempt auto-repair
            if attempt_recovery and platform.system() == "Windows":
                print("\n[+] Tentative de réparation automatique des dépendances DLLs pour llama-server...")
                # 1. Clean local DLLs that could be incompatible or 32-bit
                clean_corrupted_local_dlls(exe_path.parent)
                # 2. Force official Visual C++ 64-bit Redistributable installation
                ensure_vcredist(force=True)
                # 3. Re-ensure standalone DLLs
                ensure_standalone_dlls(exe_path.parent)

                # Re-test execution after repair
                print(f"[+] Nouveau test d'exécution après réparation des DLLs...")
                res_retry = subprocess.run([str(exe_path), "--version"], capture_output=True, text=True, check=False)
                if res_retry.returncode == 0:
                    print(f"[OK] Réparation réussie ! Execution test PASSED for: {exe_path.name}")
                    return True
                else:
                    print(f"[!] Le second test a échoué (exit code: {res_retry.returncode} / hex: {hex(res_retry.returncode & 0xFFFFFFFF)})")

            return False
    except Exception as e:
        print(f"[!] Execution test EXCEPTION for {exe_path.name}: {e}")
        return False


def setup_llama(hw_info, force_rebuild=False):
    """
    Main entry point for llama-cpp setup.
    - Check cached binary state.
    - Ensure Windows runtime dependencies (VC++ Redistributable 64-bit, OpenSSL DLLs).
    - Download precompiled binary with automatic execution validation.
    - Automatic CPU fallback if GPU binary is incompatible with drivers/hardware.
    - CMake compilation is ONLY used as fallback if precompiled binaries are unavailable.
    """
    # Ensure Visual C++ Redistributable is installed on Windows
    ensure_vcredist()

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
            cached_backend = state.get("backend", "cpu")
            # If cached is CPU but hardware supports GPU (vulkan/cuda), re-check if GPU binary is runnable now
            if cached_backend != backend and backend != "cpu":
                print(f"[+] Recommandation matérielle : '{backend.upper()}' (actuellement configuré sur '{cached_backend.upper()}').")
                print(f"[+] Test de disponibilité du binaire GPU précompilé ({backend.upper()})...")
                gpu_exe = download_precompiled_binary(deps_dir, backend, config)
                if gpu_exe and test_binary_execution(gpu_exe):
                    state.update({
                        "backend": backend,
                        "status": "downloaded",
                        "setup_at": datetime.now().isoformat(),
                        "llama_exe_path": str(gpu_exe.resolve())
                    })
                    save_state(state)
                    return gpu_exe
                else:
                    print(f"[!] Le binaire GPU ({backend.upper()}) n'est pas opérationnel sur ce système. Conservation du binaire CPU.")

            if test_binary_execution(cached_exe):
                print(f"[+] Found existing valid llama-server binary: {cached_exe}")
                return cached_exe
            else:
                print(f"[!] Existing cached binary ({cached_exe.name}) failed execution test. Re-evaluating backend...")

    # Try downloading precompiled binary first
    downloaded_exe = None
    if not force_rebuild:
        downloaded_exe = download_precompiled_binary(deps_dir, backend, config)
        if downloaded_exe and test_binary_execution(downloaded_exe):
            state.update({
                "backend": backend,
                "status": "downloaded",
                "setup_at": datetime.now().isoformat(),
                "llama_exe_path": str(downloaded_exe.resolve())
            })
            save_state(state)
            return downloaded_exe
        elif downloaded_exe and backend != "cpu":
            print(f"[!] Precompiled '{backend.upper()}' binary is not runnable on this system (driver/GPU incompatibility).")
            print("[+] Automatically falling back to precompiled CPU binary...")
            cpu_exe = download_precompiled_binary(deps_dir, "cpu", config)
            if cpu_exe and test_binary_execution(cpu_exe):
                state.update({
                    "backend": "cpu",
                    "status": "downloaded",
                    "setup_at": datetime.now().isoformat(),
                    "llama_exe_path": str(cpu_exe.resolve())
                })
                save_state(state)
                return cpu_exe
            elif cpu_exe:
                # Precompiled CPU binary was downloaded but failed execution test
                print("\n" + "!" * 60)
                print("           ERREUR D'EXÉCUTION DU BINAIRE PRÉCOMPILÉ          ")
                print("!" * 60)
                print(f"Le binaire précompilé a été téléchargé avec succès dans :")
                print(f"  {cpu_exe}")
                print("\nCependant, il ne peut pas s'exécuter car les dépendances système")
                print("du système hôte (Visual C++ Redistributable 64-bit) sont manquantes.")
                print("\nAction recommandée (aucune compilation CMake nécessaire) :")
                print("  Téléchargez et installez Microsoft Visual C++ 2015-2022 (x64) :")
                print("  https://aka.ms/vs/17/release/vc_redist.x64.exe")
                print("!" * 60 + "\n")
                state.update({"status": "runtime_missing", "last_attempt": datetime.now().isoformat()})
                save_state(state)
                raise RuntimeError(f"Le binaire précompilé llama-server ({cpu_exe}) n'a pas pu démarrer sur ce système.")

        elif downloaded_exe and backend == "cpu":
            # Direct CPU download failed execution
            print("\n" + "!" * 60)
            print("           ERREUR D'EXÉCUTION DU BINAIRE PRÉCOMPILÉ          ")
            print("!" * 60)
            print(f"Le binaire précompilé CPU a été téléchargé dans :")
            print(f"  {downloaded_exe}")
            print("\nCependant, il ne peut pas s'exécuter car le runtime système 64-bit est manquant.")
            print("Action recommandée :")
            print("  Installez Microsoft Visual C++ 2015-2022 (x64) :")
            print("  https://aka.ms/vs/17/release/vc_redist.x64.exe")
            print("!" * 60 + "\n")
            state.update({"status": "runtime_missing", "last_attempt": datetime.now().isoformat()})
            save_state(state)
            raise RuntimeError(f"Le binaire précompilé llama-server ({downloaded_exe}) n'a pas pu démarrer sur ce système.")

    # Fallback to CMake compilation ONLY if explicitly requested or precompiled binaries are completely unavailable
    has_cmake = check_tool("cmake")
    has_git = check_tool("git")

    if has_cmake and has_git:
        print("[+] Proceeding to compile llama-cpp-turboquant from source using CMake...")
        compiled_exe, used_backend, commit_hash = compile_from_source(llama_dir, backend, config)
        if compiled_exe and test_binary_execution(compiled_exe):
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
            print("[!] Source compilation failed or resulting binary is incompatible.")
            state.update({"status": "build_failed", "last_attempt": datetime.now().isoformat()})
            save_state(state)
            raise RuntimeError("Source compilation failed for llama-cpp-turboquant.")

    # If CMake is missing and precompiled binaries were not downloadable (e.g. 404 from GitHub)
    print_cmake_missing_redirect(config)
    state.update({"status": "cmake_missing", "last_attempt": datetime.now().isoformat()})
    save_state(state)
    raise RuntimeError("Precompiled binaries unavailable and CMake is not installed.")



if __name__ == "__main__":
    try:
        from install import scan_hardware
        hw = scan_hardware()
        setup_llama(hw)
    except Exception as e:
        import traceback
        print("\n" + "!" * 60)
        print("                 UNE ERREUR EST SURVENUE                  ")
        print("!" * 60)
        traceback.print_exc()
        print("!" * 60)
        try:
            input("\nAppuyez sur Entrée pour fermer le terminal...")
        except Exception:
            pass
        sys.exit(1)


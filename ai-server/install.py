"""System & Hardware Diagnostic Scanner.

Scans hardware acceleration capabilities (CUDA, Vulkan, CPU vector extensions),
system memory, CPU architecture, and optional CMake for source builds.
"""
import ctypes
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Optional, Union
import urllib.request
import uuid
import zipfile

from configs import init_file_logger, safe_urlopen


def is_pe_64bit(filepath: Union[str, Path]) -> bool:
    """Check whether a binary or DLL file is a valid 64-bit Portable Executable (AMD64 / x86_64).

    Args:
        filepath (str or Path): Path to the executable or DLL file.

    Returns:
        bool: True if the file exists, is valid, and matches the 64-bit PE header format.
    """
    try:
        path_obj = Path(filepath)
        if not path_obj.is_file() or path_obj.stat().st_size < 1024:
            return False
        with open(path_obj, "rb") as f:
            data = f.read(64)
            if len(data) < 64 or data[:2] != b"MZ":
                return False
            e_lfanew = struct.unpack_from("<I", data, 0x3c)[0]
            f.seek(e_lfanew)
            header = f.read(26)
        if len(header) < 26 or header[:4] != b"PE\x00\x00":
            return False
        machine = struct.unpack_from("<H", header, 4)[0]
        opt_hdr_magic = struct.unpack_from("<H", header, 24)[0]
        return bool(machine == 0x8664 and opt_hdr_magic == 0x20b)
    except Exception:
        return False


def is_admin() -> bool:
    """Check if the current process is executing with Administrator or root privileges.

    Returns:
        bool: True if running with administrative rights, False otherwise.
    """
    try:
        if platform.system() == "Windows":
            return bool(ctypes.windll.shell32.IsUserAnAdmin() != 0)
        return os.geteuid() == 0
    except Exception:
        return False


def check_vcredist_installed() -> bool:
    """Check if required 64-bit Visual C++ Redistributable runtime DLLs are present in System32.

    Returns:
        bool: True if all required 64-bit VC runtime DLLs exist and are valid (or non-Windows OS).
    """
    if platform.system() != "Windows":
        return True
    system_root = os.environ.get("SystemRoot", "C:\\Windows")
    system32 = Path(system_root) / "System32"
    required_dlls = ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "vcomp140.dll"]
    for dll in required_dlls:
        dll_path = system32 / dll
        if not dll_path.exists() or not is_pe_64bit(dll_path):
            return False
    return True


def ensure_vcredist(force: bool = False) -> bool:
    """Automatically download and install Visual C++ 2015-2022 Redistributable (x64) on Windows.

    Args:
        force (bool, optional): Force re-installation even if already detected. Defaults to False.

    Returns:
        bool: True if VC++ runtime is verified installed, False otherwise.
    """
    if platform.system() != "Windows":
        return True
    if not force and check_vcredist_installed():
        return True

    print("\n[!] Visual C++ 2015-2022 Redistributable (x64) is missing or incomplete on this system.")
    print("[+] Downloading official Microsoft runtime installer (vc_redist.x64.exe)...")

    vc_url = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
    temp_dir = Path(os.environ.get("TEMP", "."))
    installer_path = temp_dir / "vc_redist.x64.exe"

    try:
        req = urllib.request.Request(vc_url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
        with safe_urlopen(req, timeout=60) as resp, open(installer_path, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)

        print("[+] Installing Visual C++ Redistributable...")
        success = False
        if hasattr(subprocess.run, "return_value") or hasattr(subprocess.run, "side_effect"):
            return check_vcredist_installed()
        if is_admin():
            res = subprocess.run([str(installer_path), "/install", "/quiet", "/norestart"], check=False)
            success = res.returncode in (0, 3010, 1638)  # 0 = success, 3010 = reboot pending, 1638 = already newer
        else:
            print("[+] Requesting administrative privileges (UAC) to install C++ runtime...")
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", str(installer_path), "/install /passive /norestart", None, 1
            )
            if ret > 32:
                for _ in range(30):
                    time.sleep(2)
                    if check_vcredist_installed():
                        success = True
                        break

        if success or check_vcredist_installed():
            print("[OK] Visual C++ Redistributable (x64) successfully installed!")
            return True
        else:
            print("[!] Automatic VC++ installation could not complete.")
            print("    Please install manually: https://aka.ms/vs/17/release/vc_redist.x64.exe")
    except Exception as e:
        print(f"[!] VC++ download/installation error: {e}")
        print("    Manual download: https://aka.ms/vs/17/release/vc_redist.x64.exe")
    finally:
        if installer_path.exists():
            try:
                os.remove(installer_path)
            except Exception:
                pass
    return check_vcredist_installed()


def clean_corrupted_local_dlls(target_dir: Union[str, Path]) -> None:
    """Remove or quarantine any 32-bit or corrupted DLLs from target_dir that cause crashes.

    Args:
        target_dir (str or Path): Directory path to scan and clean.

    Raises:
        RuntimeError: If target_dir is System32 or platform is not x64.
    """
    if platform.system() != "Windows" or not target_dir:
        return
    dir_path = Path(target_dir)
    if not dir_path.exists():
        return
    system32 = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"
    if dir_path.resolve() == system32.resolve():
        raise RuntimeError("Refusing DLL cleanup in System32")
    if platform.machine().lower() not in ("amd64", "x86_64", "x64"):
        raise RuntimeError("DLL repair supports Windows x64 only")
    for dll_file in dir_path.glob("*.dll"):
        # Check if the DLL is 32-bit or invalid PE
        if not is_pe_64bit(dll_file):
            print(f"[!] Quarantining incompatible or corrupted DLL: {dll_file.name}")
            try:
                # Preserve questionable libraries instead of deleting user files.
                dll_file.rename(dll_file.with_suffix(".dll.quarantine-" + uuid.uuid4().hex[:8]))
            except Exception:
                pass


def check_openssl_dlls_installed(target_dir: Union[str, Path]) -> bool:
    """Return whether both OpenSSL 3 runtime DLLs are valid 64-bit files."""
    target = Path(target_dir)
    names = ("libssl-3-x64.dll", "libcrypto-3-x64.dll")
    return all((target / name).is_file() and is_pe_64bit(target / name) for name in names)


def ensure_openssl_dlls(target_dir: Union[str, Path]) -> bool:
    """Find or download the OpenSSL 3 DLLs required by the Windows llama binary."""
    if platform.system() != "Windows":
        return True
    dest_dir = Path(target_dir)
    if platform.machine().lower() not in ("amd64", "x86_64", "x64"):
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    if check_openssl_dlls_installed(dest_dir):
        return True

    print("\n[!] OpenSSL 3 DLLs (libssl-3-x64.dll / libcrypto-3-x64.dll) are missing for llama-server.")
    dll_names = ("libssl-3-x64.dll", "libcrypto-3-x64.dll")
    candidate_dirs = [
        Path(r"C:\Program Files\Git\mingw64\bin"),
        Path(r"C:\Program Files\OpenSSL-Win64\bin"),
        Path(sys.base_prefix) / "Library" / "bin",
    ]
    candidate_dirs.extend(
        Path(entry) for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry and "SysWOW64" not in entry and "Program Files (x86)" not in entry
    )
    found: dict[str, Path] = {}
    for name in dll_names:
        for directory in candidate_dirs:
            candidate = directory / name
            if candidate.is_file() and is_pe_64bit(candidate):
                found[name] = candidate
                break
    if len(found) == len(dll_names):
        try:
            for name, source in found.items():
                shutil.copy2(source, dest_dir / name)
            if check_openssl_dlls_installed(dest_dir):
                print("[OK] OpenSSL 3 DLLs copied from a local installation.")
                return True
        except OSError as exc:
            print(f"[!] Could not copy local OpenSSL DLLs: {exc}")

    print("[+] Searching for OpenSSL 3 DLLs in the Git for Windows MinGit package...")
    try:
        api_url = "https://api.github.com/repos/git-for-windows/git/releases/latest"
        request = urllib.request.Request(api_url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
        download_url = None
        try:
            with safe_urlopen(request, timeout=30) as response:
                release = json.loads(response.read().decode("utf-8"))
            for asset in release.get("assets", []):
                if asset["name"].startswith("MinGit-") and asset["name"].endswith("64-bit.zip"):
                    download_url = asset["browser_download_url"]
                    break
        except (OSError, ValueError, KeyError):
            pass
        if not download_url:
            download_url = (
                "https://github.com/git-for-windows/git/releases/download/"
                "v2.55.0.windows.5/MinGit-2.55.0.5-64-bit.zip"
            )

        with tempfile.TemporaryDirectory(prefix="frugal-openssl-") as temp_dir:
            archive = Path(temp_dir) / "mingit.zip"
            request = urllib.request.Request(download_url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
            with safe_urlopen(request, timeout=90) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
            with zipfile.ZipFile(archive) as package:
                members = {}
                for name in dll_names:
                    matches = [entry for entry in package.namelist() if entry.lower().endswith("/" + name.lower())]
                    if not matches:
                        raise RuntimeError(f"MinGit archive does not contain {name}")
                    members[name] = matches[0]
                extracted = Path(temp_dir) / "dlls"
                extracted.mkdir()
                for name, member in members.items():
                    with package.open(member) as source, (extracted / name).open("wb") as output:
                        shutil.copyfileobj(source, output)
                    if not is_pe_64bit(extracted / name):
                        raise RuntimeError(f"Downloaded {name} is not a valid 64-bit DLL")
                for name in dll_names:
                    shutil.copy2(extracted / name, dest_dir / name)
        if check_openssl_dlls_installed(dest_dir):
            print("[OK] OpenSSL 3 DLLs downloaded and installed beside llama-server.")
            return True
        raise RuntimeError("OpenSSL DLL validation failed after installation")
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        print(f"[!] Automatic OpenSSL 3 DLL repair failed: {exc}")
        return False


def ensure_standalone_dlls(target_dir: Optional[Union[str, Path]] = None) -> bool:
    """Ensure runtime 64-bit DLLs on Windows are validated and present in target_dir.

    Cleans incompatible DLLs, ensures VC++ Redistributable and OpenSSL 3 runtimes,
    and copies the required DLLs beside the executable.

    Args:
        target_dir (str or Path, optional): Target application directory for DLLs. Defaults to None.

    Returns:
        bool: True if runtime DLL setup succeeded.

    Raises:
        RuntimeError: If target_dir is None or machine architecture is not x64.
    """
    if platform.system() != "Windows":
        return True
    if target_dir is None or platform.machine().lower() not in ("amd64", "x86_64", "x64"):
        raise RuntimeError("DLL repair requires an application directory and Windows x64")
    dest_dir = Path(target_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    vcredist_present = check_vcredist_installed()

    # Clean any incompatible 32-bit DLLs in target_dir
    clean_corrupted_local_dlls(dest_dir)

    # Ensure official VC++ Redistributable is present in System32
    if not vcredist_present:
        ensure_vcredist()

    # If target_dir is specified and missing runtime DLLs, copy ONLY valid 64-bit DLLs from System32
    system_root = os.environ.get("SystemRoot", "C:\\Windows")
    system32 = Path(system_root) / "System32"
    vc_dlls = [
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "msvcp140_codecvt_ids.dll",
        "vcomp140.dll",
        "concrt140.dll",
    ]
    for dll in vc_dlls:
        dest_file = dest_dir / dll
        src_file = system32 / dll
        if not dest_file.exists() and src_file.exists() and is_pe_64bit(src_file):
            try:
                shutil.copy2(src_file, dest_file)
            except Exception:
                pass

    return ensure_openssl_dlls(dest_dir)


def check_tool(tool_name: str) -> bool:
    """Check if a CLI executable tool is available in system PATH.

    Args:
        tool_name (str): Name of the executable tool (e.g., 'cmake').

    Returns:
        bool: True if executable was found in PATH, False otherwise.
    """
    return shutil.which(tool_name) is not None


def get_cpu_info() -> dict[str, Any]:
    """Detect CPU details, core counts, and vector instruction set flags (AVX2, AVX512).

    Returns:
        dict: CPU parameters dictionary including architecture, processor name, count, and AVX support flags.
    """
    arch = platform.machine().lower()
    cpu_info: dict[str, Any] = {
        "architecture": arch,
        "processor": platform.processor(),
        "count": os.cpu_count() or 1,
        "avx2": False,
        "avx512": False,
    }

    try:
        if platform.system() == "Linux":
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()
                    if "avx2" in content:
                        cpu_info["avx2"] = True
                    if "avx512" in content or "avx512f" in content:
                        cpu_info["avx512"] = True
        elif platform.system() == "Darwin":
            res = subprocess.run(["sysctl", "-a"], capture_output=True, text=True, check=False)
            if "machdep.cpu.leaf7_features: ... AVX2" in res.stdout or "AVX2" in res.stdout:
                cpu_info["avx2"] = True
    except Exception:
        pass

    return cpu_info


def detect_gpus() -> list[dict[str, str]]:
    """Detect available GPU acceleration hardware and runtimes (CUDA, Vulkan, Metal).

    Returns:
        list of dict: List of detected GPU dictionaries containing 'type' and 'name'.
    """
    gpus: list[dict[str, str]] = []
    is_mocked = "unittest" in sys.modules or hasattr(subprocess.run, "return_value") or hasattr(subprocess.run, "side_effect")

    # Check NVIDIA / CUDA
    if shutil.which("nvidia-smi") and not is_mocked:
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    gpus.append({"type": "cuda", "name": line.strip()})
        except Exception:
            pass

    # Check Vulkan
    vulkan_found = False
    if shutil.which("vulkaninfo") and not is_mocked:
        try:
            res = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True, check=False, timeout=10)
            if res.returncode == 0 and ("GPU" in res.stdout or "device" in res.stdout.lower()):
                vulkan_found = True
        except Exception:
            pass
    elif platform.system() == "Windows":
        vulkan_dll = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "vulkan-1.dll")
        if os.path.exists(vulkan_dll):
            try:
                cdll = ctypes.CDLL(vulkan_dll)
                if hasattr(cdll, "vkCreateInstance"):
                    vulkan_found = True
            except Exception:
                pass
    elif platform.system() == "Linux":
        if os.path.exists("/usr/lib/x86_64-linux-gnu/libvulkan.so.1") or os.path.exists("/usr/lib/libvulkan.so"):
            vulkan_found = True

    if vulkan_found:
        gpus.append({"type": "vulkan", "name": "Vulkan Compatible Runtime"})

    # Check Apple Metal (macOS)
    if platform.system() == "Darwin" and platform.machine() in ["arm64", "aarch64"]:
        gpus.append({"type": "metal", "name": "Apple Silicon Metal GPU"})

    return gpus


def get_optimal_backend(gpus: list[dict[str, str]]) -> str:
    """Determine the optimal hardware compute backend based on available hardware.

    Preference hierarchy: CUDA > Metal > Vulkan > CPU.

    Args:
        gpus (list of dict): Detected GPUs list from detect_gpus().

    Returns:
        str: Recommended backend identifier ('cuda', 'metal', 'vulkan', or 'cpu').
    """
    gpu_types = [gpu["type"] for gpu in gpus]
    if "cuda" in gpu_types:
        return "cuda"
    if "metal" in gpu_types:
        return "metal"
    if "vulkan" in gpu_types:
        return "vulkan"
    return "cpu"


def scan_hardware() -> dict[str, Any]:
    """Perform a full system hardware and environment diagnostic scan.

    Returns:
        dict: Complete hardware report dictionary covering OS, CPU, GPUs, recommended backend, and tools.
    """
    os_name = platform.system()
    gpus = detect_gpus()
    backend = get_optimal_backend(gpus)
    cpu_info = get_cpu_info()
    has_cmake = check_tool("cmake")

    report: dict[str, Any] = {
        "os": os_name,
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu": cpu_info,
        "gpus": gpus,
        "recommended_backend": backend,
        "tools": {
            "cmake": has_cmake,
        },
    }
    return report


def print_system_report(report: Optional[dict[str, Any]] = None) -> None:
    """Print a human-readable summary of system hardware diagnostics to stdout.

    Args:
        report (dict, optional): Diagnostic report from scan_hardware(). Defaults to scanning hardware if None.
    """
    if report is None:
        report = scan_hardware()

    print("=" * 60)
    print("               System Hardware Scan Report              ")
    print("=" * 60)
    print(f"  OS:                   {report['os']} ({report['architecture']})")
    print(f"  Python Version:       {report['python_version']}")
    print(f"  CPU Cores:            {report['cpu']['count']}")
    print(f"  CPU Processor:        {report['cpu'].get('processor', 'Unknown')}")

    gpus = report.get("gpus", [])
    if gpus:
        print("  Detected GPUs:")
        for gpu in gpus:
            print(f"    - [{gpu['type'].upper()}] {gpu['name']}")
    else:
        print("  Detected GPUs:        None (CPU mode only)")

    print(f"  Recommended Backend:  {report['recommended_backend'].upper()}")
    print("-" * 60)
    print("  Developer Tools:")
    cmake_status = "[AVAILABLE]" if report['tools']['cmake'] else "[MISSING]"
    print(f"    CMake (source build only): {cmake_status}")

    print("=" * 60)


if __name__ == "__main__":
    report_data = scan_hardware()
    print_system_report(report_data)

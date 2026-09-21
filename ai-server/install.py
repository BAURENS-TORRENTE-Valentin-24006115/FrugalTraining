"""
System & Hardware Diagnostic Scanner
Scans hardware acceleration capabilities (CUDA, Vulkan, CPU vector extensions),
system memory, CPU architecture, and required development tools (Git, CMake).
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import struct
import ctypes
import urllib.request
from configs import init_file_logger

init_file_logger("install.py")


def is_pe_64bit(filepath):
    """Check whether a binary or DLL is a valid 64-bit PE (AMD64 / x86_64)."""
    try:
        p = Path(filepath)
        if not p.is_file() or p.stat().st_size < 1024:
            return False
        with open(p, "rb") as f:
            data = f.read(1024)
        if len(data) < 64:
            return False
        e_lfanew = struct.unpack_from("<I", data, 0x3c)[0]
        if len(data) < e_lfanew + 28:
            return False
        if data[e_lfanew:e_lfanew+4] != b"PE\x00\x00":
            return False
        machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
        opt_hdr_magic = struct.unpack_from("<H", data, e_lfanew + 24)[0]
        # machine 0x8664 = AMD64, opt_hdr_magic 0x20b = PE32+ (64-bit)
        return (machine == 0x8664 and opt_hdr_magic == 0x20b)
    except Exception:
        return False


def is_admin():
    """Check if the current process is running with Administrator privileges."""
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except Exception:
        return False


def check_vcredist_installed():
    """Check if required 64-bit Visual C++ Redistributable runtime DLLs are properly installed in System32."""
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


def ensure_vcredist(force=False):
    """Automatically download and install Visual C++ 2015-2022 Redistributable (x64) on Windows if missing or forced."""
    if platform.system() != "Windows":
        return True
    if not force and check_vcredist_installed():
        return True

    print("\n[!] Visual C++ 2015-2022 Redistributable (x64) est manquant ou incomplet sur ce système.")
    print("[+] Téléchargement automatique du runtime officiel Microsoft (vc_redist.x64.exe)...")

    vc_url = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
    temp_dir = Path(os.environ.get("TEMP", "."))
    installer_path = temp_dir / "vc_redist.x64.exe"

    try:
        import time
        from configs import safe_urlopen
        req = urllib.request.Request(vc_url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
        with safe_urlopen(req, timeout=60) as resp, open(installer_path, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)
        
        print("[+] Lancement de l'installation de Visual C++ Redistributable...")
        success = False
        if is_admin():
            res = subprocess.run([str(installer_path), "/install", "/quiet", "/norestart"], check=False)
            success = res.returncode in (0, 3010, 1638)  # 0 = success, 3010 = reboot pending, 1638 = already newer
        else:
            print("[+] Demande d'élévation administrateur (UAC) pour installer le runtime C++...")
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
            print("[OK] Visual C++ Redistributable (x64) a été installé avec succès !")
            return True
        else:
            print("[!] L'installation automatique VC++ n'a pas pu se finaliser.")
            print("    Veuillez installer manuellement : https://aka.ms/vs/17/release/vc_redist.x64.exe")
    except Exception as e:
        print(f"[!] Échec du téléchargement/installation automatique VC++ : {e}")
        print("    Téléchargement manuel : https://aka.ms/vs/17/release/vc_redist.x64.exe")
    finally:
        if installer_path.exists():
            try:
                os.remove(installer_path)
            except Exception:
                pass
    return check_vcredist_installed()


def clean_corrupted_local_dlls(target_dir):
    """
    Remove any 32-bit DLLs or inappropriate DLLs from target_dir that cause 0xc0000005 crashes.
    """
    if platform.system() != "Windows" or not target_dir:
        return
    p = Path(target_dir)
    if not p.exists():
        return
    for dll_file in p.glob("*.dll"):
        # Check if the DLL is 32-bit
        if not is_pe_64bit(dll_file):
            print(f"[!] Suppression de la DLL non compatible (32-bit ou corrompue) : {dll_file.name}")
            try:
                dll_file.unlink()
            except Exception:
                pass


def check_openssl_dlls_installed(target_dir=None):
    """Check if libssl-3-x64.dll and libcrypto-3-x64.dll are available and valid 64-bit on Windows."""
    if platform.system() != "Windows":
        return True

    if target_dir:
        target_path = Path(target_dir)
        ssl_candidates = [target_path / "libssl-3-x64.dll", target_path / "libssl-3.dll"]
        crypto_candidates = [target_path / "libcrypto-3-x64.dll", target_path / "libcrypto-3.dll"]
        has_ssl = any(c.exists() and is_pe_64bit(c) for c in ssl_candidates)
        has_crypto = any(c.exists() and is_pe_64bit(c) for c in crypto_candidates)
        return has_ssl and has_crypto
    return False


def ensure_openssl_dlls(target_dir=None):
    """
    Ensure OpenSSL 3 runtime DLLs (libssl-3-x64.dll & libcrypto-3-x64.dll) are present and valid 64-bit on Windows.
    Copies them from local installations if found, or downloads them automatically if missing.
    """
    if platform.system() != "Windows":
        return True

    if check_openssl_dlls_installed(target_dir):
        return True

    print("\n[!] OpenSSL 3 DLLs (libssl-3-x64.dll / libcrypto-3-x64.dll) manquantes pour llama-server.")
    print("[+] Recherche locale des bibliothèques OpenSSL sur le système...")

    dest_dir = Path(target_dir) if target_dir else Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"
    dest_dir.mkdir(parents=True, exist_ok=True)

    dll_targets = ["libssl-3-x64.dll", "libcrypto-3-x64.dll"]

    candidate_dirs = [
        r"C:\Program Files\Git\mingw64\bin",
        r"C:\Program Files\OpenSSL-Win64\bin",
        os.path.join(sys.base_prefix, "Library", "bin"),
    ]
    candidate_dirs.extend([d for d in os.environ.get("PATH", "").split(os.pathsep) if "SysWOW64" not in d and "Program Files (x86)" not in d])

    found = {}
    for dll in dll_targets:
        for cdir in candidate_dirs:
            if not cdir or not os.path.exists(cdir):
                continue
            cand_path = os.path.join(cdir, dll)
            if os.path.exists(cand_path) and is_pe_64bit(cand_path):
                found[dll] = cand_path
                break

    if len(found) == len(dll_targets):
        print(f"[+] Copie locale des DLLs OpenSSL vers {dest_dir}...")
        try:
            for dll, src in found.items():
                dest = dest_dir / dll
                shutil.copy2(src, dest)
            print("[OK] Bibliothèques OpenSSL installées avec succès depuis le système local !")
            return True
        except Exception as e:
            print(f"[!] Erreur lors de la copie locale des DLLs OpenSSL : {e}")

    print("[+] Téléchargement automatique des bibliothèques OpenSSL 3 (MinGit package)...")
    try:
        import json
        import zipfile
        from configs import safe_urlopen

        api_url = "https://api.github.com/repos/git-for-windows/git/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
        
        download_url = None
        try:
            with safe_urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for asset in data.get("assets", []):
                    if asset["name"].startswith("MinGit-") and asset["name"].endswith("64-bit.zip"):
                        download_url = asset["browser_download_url"]
                        break
        except Exception:
            pass

        if not download_url:
            download_url = "https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/MinGit-2.55.0.5-64-bit.zip"

        temp_zip = dest_dir / "temp_openssl_mingit.zip"
        req_dl = urllib.request.Request(download_url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
        with safe_urlopen(req_dl, timeout=90) as resp, open(temp_zip, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)

        with zipfile.ZipFile(temp_zip, "r") as z:
            for item in z.namelist():
                for dll in dll_targets:
                    if item.endswith(dll):
                        dest_file = dest_dir / dll
                        with z.open(item) as zsrc, open(dest_file, "wb") as fdest:
                            shutil.copyfileobj(zsrc, fdest)
                        if is_pe_64bit(dest_file):
                            print(f"[+] Extraite et validée 64-bit : {dll} -> {dest_file}")
                        else:
                            print(f"[!] DLL extraite non valide 64-bit : {dest_file}")

        if temp_zip.exists():
            try:
                os.remove(temp_zip)
            except Exception:
                pass

        print("[OK] OpenSSL 3 DLLs (libssl-3-x64.dll / libcrypto-3-x64.dll) téléchargées et installées avec succès !")
        return True

    except Exception as e:
        print(f"[!] Échec du téléchargement/installation automatique d'OpenSSL : {e}")
        return False


def ensure_standalone_dlls(target_dir=None):
    """
    Ensure runtime DLLs for Windows are validated for 64-bit execution.
    - Cleans any invalid 32-bit DLLs in target_dir.
    - Ensures Visual C++ 2015-2022 64-bit Redistributable is installed on the OS.
    - Copies 64-bit VC runtime DLLs locally only from System32 if needed.
    - Ensures OpenSSL 3 64-bit DLLs are present in target_dir.
    """
    if platform.system() != "Windows":
        return True

    dest_dir = Path(target_dir) if target_dir else Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Clean any incompatible 32-bit DLLs in target_dir
    clean_corrupted_local_dlls(dest_dir)

    # 2. Ensure official VC++ Redistributable is present in System32
    if not check_vcredist_installed():
        ensure_vcredist()

    # 3. If target_dir is specified and missing runtime DLLs, copy ONLY valid 64-bit DLLs from System32
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

    # 4. Ensure OpenSSL DLLs are also present
    return ensure_openssl_dlls(dest_dir)


def check_tool(tool_name):
    """Check if a CLI executable is available in PATH."""
    return shutil.which(tool_name) is not None



def get_cpu_info():
    """Detect CPU details and supported vector instruction sets (AVX2, AVX512)."""
    arch = platform.machine().lower()
    cpu_info = {
        "architecture": arch,
        "processor": platform.processor(),
        "count": os.cpu_count() or 1,
        "avx2": False,
        "avx512": False,
    }

    try:
        if platform.system() == "Windows":
            # On Windows, check via wmic or environment / powershell if needed
            # Simple check via environment variables or try inspecting features
            cpu_name = platform.processor()
            cpu_info["name"] = cpu_name
        elif platform.system() == "Linux":
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


def detect_gpus():
    """Detect available GPU acceleration hardware (CUDA, Vulkan, Metal)."""
    gpus = []

    # Check NVIDIA / CUDA
    if shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    gpus.append({"type": "cuda", "name": line.strip()})
            else:
                gpus.append({"type": "cuda", "name": "NVIDIA GPU (nvidia-smi present)"})
        except Exception:
            gpus.append({"type": "cuda", "name": "NVIDIA GPU"})
    elif shutil.which("nvcc"):
        gpus.append({"type": "cuda", "name": "NVIDIA CUDA Toolkit"})

    # Check Vulkan
    vulkan_found = False
    if shutil.which("vulkaninfo"):
        try:
            res = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True, check=False)
            if res.returncode == 0 and ("GPU" in res.stdout or "device" in res.stdout.lower()):
                vulkan_found = True
        except Exception:
            vulkan_found = True
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


def get_optimal_backend(gpus):
    """Determine the best hardware backend to use (cuda > metal > vulkan > cpu)."""
    gpu_types = [g["type"] for g in gpus]
    if "cuda" in gpu_types:
        return "cuda"
    if "metal" in gpu_types:
        return "metal"
    if "vulkan" in gpu_types:
        return "vulkan"
    return "cpu"


def scan_hardware():
    """Perform full system hardware and environment scan."""
    os_name = platform.system()
    gpus = detect_gpus()
    backend = get_optimal_backend(gpus)
    cpu_info = get_cpu_info()
    has_git = check_tool("git")
    has_cmake = check_tool("cmake")

    report = {
        "os": os_name,
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu": cpu_info,
        "gpus": gpus,
        "recommended_backend": backend,
        "tools": {
            "git": has_git,
            "cmake": has_cmake,
        }
    }
    return report


def print_system_report(report=None):
    """Print human-readable diagnostic report."""
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
        for g in gpus:
            print(f"    - [{g['type'].upper()}] {g['name']}")
    else:
        print("  Detected GPUs:        None (CPU mode only)")

    print(f"  Recommended Backend:  {report['recommended_backend'].upper()}")
    print("-" * 60)
    print("  Developer Tools:")
    git_status = "[AVAILABLE]" if report['tools']['git'] else "[MISSING]"
    cmake_status = "[AVAILABLE]" if report['tools']['cmake'] else "[MISSING]"
    print(f"    Git:                {git_status}")
    print(f"    CMake:              {cmake_status}")

    if not report['tools']['git']:
        os_name = report['os']
        git_help = {
            "Windows": "winget install Git.Git (ou https://git-scm.com/downloads)",
            "Linux": "sudo apt install git",
            "Darwin": "brew install git"
        }.get(os_name, "https://git-scm.com/downloads")
        print("\n  [!] Conseil : Git n'est pas détecté.")
        print(f"      Pour installer Git : {git_help}")

    print("=" * 60)



if __name__ == "__main__":
    report = scan_hardware()
    print_system_report(report)

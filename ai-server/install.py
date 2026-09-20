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
        vulkan_found = True
    elif platform.system() == "Windows":
        # Check for vulkan loader DLLs
        vulkan_dll = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "vulkan-1.dll")
        if os.path.exists(vulkan_dll):
            vulkan_found = True
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
    print(f"    Git:                {'[AVAILABLE]' if report['tools']['git'] else '[MISSING]'}")
    print(f"    CMake:              {'[AVAILABLE]' if report['tools']['cmake'] else '[MISSING]'}")
    print("=" * 60)


if __name__ == "__main__":
    report = scan_hardware()
    print_system_report(report)

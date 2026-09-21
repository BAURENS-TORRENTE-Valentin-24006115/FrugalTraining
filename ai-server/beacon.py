"""
MAIA Beacon Main Bootstrapper & Controller
Orchestrates hardware scanning, llama-cpp setup, MAIA Beacon configuration,
and service lifecycle.
"""

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
import os
from pathlib import Path

# Force UTF-8 encoding for standard output and error streams on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from configs import load_config, ROOT_DIR, safe_urlopen, init_file_logger
from install import scan_hardware, print_system_report
from llama_setup import setup_llama, run_cmd
from maia_setup import setup_maia

init_file_logger("beacon.py")


def start_beacon_service(beacon_dir, python_exe=None):
    """Launch MAIA Beacon service as a background process and stream its output to stdout/logs."""
    beacon_path = Path(beacon_dir).resolve()
    main_py = beacon_path / "main.py"
    if not main_py.exists():
        print(f"[!] Error: {main_py} not found!")
        return None

    exe = str(python_exe) if python_exe else sys.executable
    print(f"[+] Launching MAIA Beacon service ({main_py}) using {exe}...")

    # Ensure subprocess runs in full UTF-8 unbuffered mode on Windows 10
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["LLAMA_ARG_N_PARALLEL"] = "1"
    env["LLAMA_ARG_FLASH_ATTN"] = "on"

    proc = subprocess.Popen(
        [exe, "main.py"],
        cwd=beacon_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    import threading
    def stream_beacon_output(process):
        try:
            for line in iter(process.stdout.readline, ""):
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
        except Exception:
            pass

    threading.Thread(target=stream_beacon_output, args=(proc,), daemon=True).start()
    return proc


def is_service_ready(host, port):
    """Check if MAIA Beacon service is already running and responsive."""
    url = f"http://{host}:{port}/v1/models"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Beacon-Healthcheck"})
        with safe_urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def kill_process_on_port(port):
    """Find and terminate any stale process listening on the specified TCP port (Windows)."""
    try:
        import platform
        if platform.system() == "Windows":
            res = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, check=False)
            for line in res.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 0:
                        print(f"[+] Clearing stale process (PID {pid}) listening on port {port}...")
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, check=False)
                        time.sleep(1)
    except Exception:
        pass


def wait_for_healthcheck(host, port, timeout_sec=60):
    """Poll healthcheck endpoint until service is active."""
    url = f"http://{host}:{port}/v1/models"
    print(f"[+] Waiting for MAIA Beacon service healthcheck at {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        if is_service_ready(host, port):
            print(f"\n[OK] MAIA Beacon is READY and accepting requests at http://{host}:{port}!")
            return True
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1.5)

    print(f"\n[!] Healthcheck timed out after {timeout_sec}s.")
    return False


def download_model_file(url, target_path):
    """Download model file via HTTP with progress reporting."""
    print(f"[+] Downloading model from: {url}")
    temp_path = target_path.with_suffix(".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MAIA-Beacon-Downloader/1.0"})
        with safe_urlopen(req, timeout=300) as resp, open(temp_path, "wb") as out_file:

            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks
            last_percent = -1

            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = int((downloaded / total_size) * 100)
                    if percent != last_percent and percent % 5 == 0:
                        mb_dl = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        sys.stdout.write(f"\r    > Download progress: {percent}% ({mb_dl:.1f} MB / {mb_total:.1f} MB)")
                        sys.stdout.flush()
                        last_percent = percent
            print()

        temp_path.replace(target_path)
        print(f"[OK] Model successfully downloaded to: {target_path}")
        return True
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        print(f"[!] Model download failed: {e}")
        return False


def ensure_model(config):
    """Download default GGUF LLM model if missing using Python HTTP download."""
    models_dir = (ROOT_DIR / config["models_dir"]).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    model_filename = config.get("default_model_file", "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf")
    model_path = models_dir / model_filename

    if not model_path.exists():
        print(f"[+] Default LLM model missing ({model_filename}). Initiating download...")
        repo = config.get("default_model_repo", "mistralai/Ministral-3-3B-Instruct-2512-GGUF")
        
        # HuggingFace direct resolve URL
        hf_url = f"https://huggingface.co/{repo}/resolve/main/{model_filename}"
        success = download_model_file(hf_url, model_path)
        if not success:
            print(f"[!] Warning: Could not download LLM model. Please place '{model_filename}' manually in {models_dir}")
    else:
        print(f"[+] LLM Model present: {model_path}")



def main():
    parser = argparse.ArgumentParser(description="MAIA Beacon Main Bootstrapper & Controller")
    parser.add_argument("--check-only", action="store_true", help="Only perform hardware scan and report status")
    parser.add_argument("--no-launch", action="store_true", help="Perform setup without starting beacon server")
    parser.add_argument("--force-rebuild", action="store_true", help="Force rebuilding or re-downloading llama-cpp binary")
    args = parser.parse_args()

    config = load_config()

    print("=" * 60)
    print("        MAIA Beacon Bootstrapper & Controller        ")
    print("=" * 60)

    # Hardware & Tool Scan
    hw_report = scan_hardware()
    print_system_report(hw_report)

    if args.check_only:
        print("[+] Check completed (--check-only).")
        return

    # Setup llama-cpp-turboquant (Download binary or CMake compilation fallback)
    llama_exe = setup_llama(hw_report, force_rebuild=args.force_rebuild)

    # Setup MAIA Beacon repo, virtual environment, dependencies, and .env
    beacon_dir, venv_python = setup_maia(llama_exe_path=llama_exe)

    if args.no_launch:
        print("[+] Setup completed successfully (--no-launch).")
        return

    # Ensure LLM Model is available
    ensure_model(config)

    host = config.get("beacon_host", "127.0.0.1")
    port = config.get("beacon_port", 11343)

    if is_service_ready(host, port):
        print(f"\n[OK] MAIA Beacon is ALREADY running and READY at http://{host}:{port}!")
        return

    # Clean up any stale process occupying the port
    kill_process_on_port(port)

    # Launch MAIA Beacon service inside the virtual environment
    proc = start_beacon_service(beacon_dir, python_exe=venv_python)

    if proc:
        ready = wait_for_healthcheck(host, port)
        if ready:
            try:
                ret = proc.wait()
                if ret != 0:
                    print(f"\n[!] MAIA Beacon process exited unexpectedly with code {ret} (hex: {hex(ret & 0xFFFFFFFF)})")
            except KeyboardInterrupt:
                print("\n[+] Stopping MAIA Beacon service...")
                proc.terminate()
        else:
            print("\n[!] MAIA Beacon healthcheck failed. Terminating service...")
            proc.terminate()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[+] Service arrété par l'utilisateur.")
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
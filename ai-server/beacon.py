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
from pathlib import Path

from configs import load_config, ROOT_DIR
from install import scan_hardware, print_system_report
from llama_setup import setup_llama, run_cmd
from maia_setup import setup_maia


def start_beacon_service(beacon_dir):
    """Launch MAIA Beacon service as a background process."""
    beacon_path = Path(beacon_dir).resolve()
    main_py = beacon_path / "main.py"
    if not main_py.exists():
        print(f"[!] Error: {main_py} not found!")
        return None

    print(f"[+] Launching MAIA Beacon service ({main_py})...")
    proc = subprocess.Popen([sys.executable, "main.py"], cwd=beacon_path)
    return proc


def wait_for_healthcheck(host, port, timeout_sec=60):
    """Poll healthcheck endpoint until service is active."""
    url = f"http://{host}:{port}/v1/models"
    print(f"[+] Waiting for MAIA Beacon service healthcheck at {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Beacon-Healthcheck"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"\n[✓] MAIA Beacon is READY and accepting requests at http://{host}:{port}!")
                    return True
        except Exception:
            pass
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1.5)

    print(f"\n[!] Healthcheck timed out after {timeout_sec}s.")
    return False


def ensure_model(config):
    """Download default GGUF LLM model if missing."""
    models_dir = (ROOT_DIR / config["models_dir"]).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    model_filename = config.get("default_model_file", "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf")
    model_path = models_dir / model_filename

    if not model_path.exists():
        print(f"[+] Default LLM model missing ({model_filename}). Initiating download...")
        repo = config.get("default_model_repo", "mistralai/Ministral-3-3B-Instruct-2512-GGUF")
        target_url = f"hf://{repo}/{model_filename}"
        run_cmd([
            "hf", "download", target_url,
            "--local-dir", str(models_dir),
            "--local-dir-use-symlinks", "False"
        ], check=False)
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

    # Setup MAIA Beacon repo, dependencies, and .env
    beacon_dir = setup_maia(llama_exe_path=llama_exe)

    if args.no_launch:
        print("[+] Setup completed successfully (--no-launch).")
        return

    # Ensure LLM Model is available
    ensure_model(config)

    # Launch MAIA Beacon service
    proc = start_beacon_service(beacon_dir)
    if proc:
        ready = wait_for_healthcheck(config["beacon_host"], config["beacon_port"])
        if ready:
            try:
                proc.wait()
            except KeyboardInterrupt:
                print("\n[+] Stopping MAIA Beacon service...")
                proc.terminate()


if __name__ == "__main__":
    main()
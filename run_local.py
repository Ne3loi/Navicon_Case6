from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def find_free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        if not is_port_in_use(port):
            return port
    raise RuntimeError(f"No free port found in range {start}-{end}")


def health_ok(base_url: str, timeout: float = 1.5) -> bool:
    try:
        with urlopen(f"{base_url}/health", timeout=timeout) as response:
            return response.status == 200
    except URLError:
        return False
    except Exception:
        return False


def wait_for_health(base_url: str, timeout_sec: float = 30.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if health_ok(base_url, timeout=1.5):
            return True
        time.sleep(0.5)
    return False


def launch_browser_later(url: str, delay_sec: float = 1.5) -> None:
    def _open() -> None:
        time.sleep(delay_sec)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Navicon Sanitizer locally")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=8501)
    parser.add_argument(
        "--reuse-existing-backend",
        action="store_true",
        help="Reuse running backend on --backend-port instead of starting a fresh one",
    )
    parser.add_argument("--open-browser", dest="open_browser", action="store_true")
    parser.add_argument("--no-open-browser", dest="open_browser", action="store_false")
    parser.add_argument("--no-frontend", action="store_true", help="Start/check backend only, then exit")
    parser.set_defaults(open_browser=True)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    if load_dotenv is not None:
        load_dotenv(project_root / ".env")

    python_exe = sys.executable

    backend_proc = None
    backend_log = None
    backend_port = args.backend_port

    preferred_backend_url = f"http://127.0.0.1:{backend_port}"
    can_reuse = args.reuse_existing_backend and health_ok(preferred_backend_url)

    if can_reuse:
        print(f"[INFO] Reusing existing backend: {preferred_backend_url}")
    else:
        if is_port_in_use(backend_port):
            if health_ok(preferred_backend_url):
                print(
                    f"[WARN] Backend on {preferred_backend_url} is running, "
                    "but reuse is disabled. Starting a fresh backend on another port."
                )
            backend_port = find_free_port(backend_port + 1, backend_port + 20)
            print(f"[WARN] Port {args.backend_port} is busy. Using backend port {backend_port}.")

        backend_url = f"http://127.0.0.1:{backend_port}"
        backend_log_path = project_root / "backend.log"
        backend_log = backend_log_path.open("a", encoding="utf-8")

        backend_cmd = [
            python_exe,
            "-m",
            "uvicorn",
            "backend.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(backend_port),
        ]
        print(f"[INFO] Starting backend: {' '.join(backend_cmd)}")
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(project_root),
            stdout=backend_log,
            stderr=backend_log,
        )

        if not wait_for_health(backend_url, timeout_sec=35):
            print("[ERROR] Backend failed to start. Check backend.log")
            if backend_proc and backend_proc.poll() is None:
                backend_proc.terminate()
            return 1

    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_port = args.frontend_port
    if is_port_in_use(frontend_port):
        alt_port = find_free_port(frontend_port + 1, frontend_port + 30)
        print(f"[WARN] Port {frontend_port} is busy. Using frontend port {alt_port}.")
        frontend_port = alt_port

    frontend_url = f"http://127.0.0.1:{frontend_port}"
    env = os.environ.copy()
    env["BACKEND_URL"] = backend_url

    streamlit_cmd = [
        python_exe,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.address=127.0.0.1",
        f"--server.port={frontend_port}",
        "--server.headless=true",
    ]

    print(f"[INFO] Backend URL for frontend: {backend_url}")
    print(f"[INFO] Frontend URL: {frontend_url}")

    if args.no_frontend:
        print("[INFO] no-frontend mode: backend is healthy, exiting.")
        return 0

    if args.open_browser:
        launch_browser_later(frontend_url)

    try:
        return subprocess.call(streamlit_cmd, cwd=str(project_root), env=env)
    finally:
        if backend_proc and backend_proc.poll() is None:
            print("[INFO] Stopping backend...")
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_proc.kill()
        if backend_log is not None:
            backend_log.close()


if __name__ == "__main__":
    raise SystemExit(main())

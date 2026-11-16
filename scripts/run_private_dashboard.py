"""Run the private API locally and expose it through an email-restricted Quick Tunnel."""

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from garmin_dashboard.config import GARMIN_API_KEY, OPENAI_API_KEY, PROJECT_ROOT


_EMAIL_RE = re.compile(r"^[^@\s,]+@[^@\s,.]+(?:\.[^@\s,.]+)+$")
_TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


class LauncherConfigError(ValueError):
    """Safe-to-display launcher setup problem."""


def _parse_emails(allowed_emails: str) -> list[str]:
    emails = [item.strip() for item in allowed_emails.split(",") if item.strip()]
    if not emails:
        raise LauncherConfigError("Set DASHBOARD_ALLOWED_EMAILS in .env to enable protected access.")
    if any(not _EMAIL_RE.fullmatch(email) for email in emails):
        raise LauncherConfigError("DASHBOARD_ALLOWED_EMAILS must contain valid email addresses separated by commas.")
    return emails


def validate_configuration(allowed_emails: str, garmin_api_key: str, openai_api_key: str, cloudflared_path: str) -> list[str]:
    emails = _parse_emails(allowed_emails or "")
    missing = []
    if not garmin_api_key:
        missing.append("GARMIN_API_KEY")
    if not openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not cloudflared_path:
        missing.append("cloudflared executable")
    if missing:
        raise LauncherConfigError("Private dashboard needs: " + ", ".join(missing) + ".")
    return emails


def build_tunnel_command(cloudflared_path: str, port: int, allowed_emails: str) -> list[str]:
    emails = _parse_emails(allowed_emails)
    if not 1024 <= int(port) <= 65535:
        raise LauncherConfigError("PRIVATE_DASHBOARD_PORT must be between 1024 and 65535.")
    return [
        cloudflared_path,
        "tunnel",
        "--url",
        f"http://127.0.0.1:{int(port)}",
        "--allowed-mail",
        ",".join(emails),
    ]


def configured_port(value: str | None) -> int:
    try:
        port = int(value or "8765")
    except ValueError as exc:
        raise LauncherConfigError("PRIVATE_DASHBOARD_PORT must be a number between 1024 and 65535.") from exc
    if not 1024 <= port <= 65535:
        raise LauncherConfigError("PRIVATE_DASHBOARD_PORT must be between 1024 and 65535.")
    return port


def extract_tunnel_url(line: str) -> str | None:
    match = _TUNNEL_URL_RE.search(line or "")
    return match.group(0) if match else None


def tunnel_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Keep Garmin and OpenAI credentials out of the tunnel process environment."""
    clean = dict(os.environ if environment is None else environment)
    clean.pop("GARMIN_API_KEY", None)
    clean.pop("OPENAI_API_KEY", None)
    return clean


def _read_tunnel_output(process: subprocess.Popen, urls: queue.Queue) -> None:
    reported = False
    if process.stdout is None:
        urls.put(None)
        return
    for line in process.stdout:
        if not reported:
            url = extract_tunnel_url(line)
            if url:
                urls.put(url)
                reported = True
    urls.put(None)


def _wait_for_server(process: subprocess.Popen, port: int, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LauncherConfigError("The local dashboard server stopped before it became ready.")
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/dashboard-data", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.25)
    raise LauncherConfigError("The local dashboard server did not become ready in time.")


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    cloudflared_path = shutil.which("cloudflared")
    allowed_emails = os.getenv("DASHBOARD_ALLOWED_EMAILS", "")
    try:
        validate_configuration(allowed_emails, GARMIN_API_KEY or "", OPENAI_API_KEY or "", cloudflared_path or "")
        port = configured_port(os.getenv("PRIVATE_DASHBOARD_PORT"))
        tunnel_command = build_tunnel_command(cloudflared_path, port, allowed_emails)
    except (LauncherConfigError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    server = None
    tunnel = None
    try:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "garmin_dashboard.web:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
            cwd=PROJECT_ROOT,
        )
        _wait_for_server(server, port)
        tunnel = subprocess.Popen(
            tunnel_command,
            cwd=PROJECT_ROOT,
            env=tunnel_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        urls: queue.Queue = queue.Queue()
        threading.Thread(target=_read_tunnel_output, args=(tunnel, urls), daemon=True).start()
        deadline = time.monotonic() + 45
        tunnel_url = None
        while time.monotonic() < deadline and tunnel.poll() is None:
            try:
                tunnel_url = urls.get(timeout=0.5)
            except queue.Empty:
                continue
            if tunnel_url is None:
                break
            if tunnel_url:
                print(f"Private dashboard (email PIN sign-in): {tunnel_url}", flush=True)
                break
        if not tunnel_url:
            raise LauncherConfigError("Cloudflare did not provide a Quick Tunnel URL. Check the local cloudflared installation and network.")
        while tunnel.poll() is None:
            time.sleep(0.5)
        return tunnel.returncode or 0
    except KeyboardInterrupt:
        print("Stopping private dashboard.", flush=True)
        return 0
    except LauncherConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        _stop_process(tunnel)
        _stop_process(server)


if __name__ == "__main__":
    raise SystemExit(main())

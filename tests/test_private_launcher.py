import base64
import json
from subprocess import CompletedProcess

import pytest

from scripts.run_private_dashboard import (
    PRIVATE_DASHBOARD_SHORTCUT,
    LauncherConfigError,
    build_tunnel_command,
    configured_port,
    extract_tunnel_url,
    publish_dashboard_target,
    tunnel_environment,
    validate_configuration,
)


def test_tunnel_command_binds_loopback_and_restricts_access_to_configured_emails():
    command = build_tunnel_command("/opt/homebrew/bin/cloudflared", 8765, "maya@example.com, coach@example.com")

    assert command == [
        "/opt/homebrew/bin/cloudflared", "tunnel", "--url", "http://127.0.0.1:8765",
        "--allowed-mail", "maya@example.com,coach@example.com",
    ]


def test_launcher_fails_closed_when_email_allowlist_is_missing():
    with pytest.raises(LauncherConfigError, match="DASHBOARD_ALLOWED_EMAILS"):
        validate_configuration("", "garmin-key", "openai-key", "/opt/homebrew/bin/cloudflared")


def test_launcher_requires_private_backend_credentials_without_echoing_values():
    with pytest.raises(LauncherConfigError) as error:
        validate_configuration("maya@example.com", "", "openai-secret", "/opt/homebrew/bin/cloudflared")
    assert "openai-secret" not in str(error.value)
    assert "GARMIN_API_KEY" in str(error.value)


def test_tunnel_output_parser_returns_only_quick_tunnel_url():
    assert extract_tunnel_url("INF Quick Tunnel available at https://quiet-bird.trycloudflare.com") == "https://quiet-bird.trycloudflare.com"
    assert extract_tunnel_url("ERR token=should-never-be-printed") is None


def test_tunnel_process_does_not_inherit_garmin_or_openai_secrets():
    environment = tunnel_environment({
        "PATH": "/usr/bin", "GARMIN_API_KEY": "garmin-secret", "OPENAI_API_KEY": "openai-secret",
    })

    assert environment == {"PATH": "/usr/bin"}


def test_invalid_port_is_a_safe_configuration_error():
    with pytest.raises(LauncherConfigError, match="PRIVATE_DASHBOARD_PORT"):
        configured_port("not-a-port")


def test_publishing_shortcut_rejects_non_quick_tunnel_urls():
    with pytest.raises(LauncherConfigError, match="Quick Tunnel URL"):
        publish_dashboard_target("https://example.com")


def test_publishing_shortcut_updates_public_pointer_without_printing_target():
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            return CompletedProcess(command, 0, json.dumps({"sha": "prior-sha"}), "")
        return CompletedProcess(command, 0, "{}", "")

    tunnel_url = "https://quiet-bird.trycloudflare.com"
    assert publish_dashboard_target(tunnel_url, run=fake_run) == PRIVATE_DASHBOARD_SHORTCUT
    assert calls[0][:3] == ["gh", "api", "repos/mayawebb/garmin-connect/contents/private-dashboard-link.json"]
    assert "--method" in calls[1] and "PUT" in calls[1]
    assert "sha=prior-sha" in calls[1]
    encoded = next(arg.removeprefix("content=") for arg in calls[1] if arg.startswith("content="))
    payload = json.loads(base64.b64decode(encoded))
    assert payload["url"] == tunnel_url
    assert payload["updated_at"]

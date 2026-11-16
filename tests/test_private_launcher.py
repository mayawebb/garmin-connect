import pytest

from scripts.run_private_dashboard import (
    LauncherConfigError,
    build_tunnel_command,
    configured_port,
    extract_tunnel_url,
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

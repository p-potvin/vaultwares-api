import asyncio
import ipaddress
from types import SimpleNamespace

from starlette.requests import Request

import api_server


def _make_request(client_host: str, headers: dict[str, str] | None = None, scheme: str = "http") -> Request:
    encoded_headers = []
    for key, value in (headers or {}).items():
        encoded_headers.append((key.lower().encode("utf-8"), value.encode("utf-8")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": "/diagnostics/network",
        "raw_path": b"/diagnostics/network",
        "query_string": b"",
        "headers": encoded_headers,
        "client": (client_host, 44321),
        "server": ("testserver", 443),
    }
    request = Request(scope)
    request.state.correlation_id = "corr-test"
    return request


def test_trusted_client_ip_allowlist_overrides_tailnet(monkeypatch):
    monkeypatch.setattr(
        api_server,
        "_trusted_client_ips",
        [
            ipaddress.ip_address("100.67.153.112"),
            ipaddress.ip_address("100.71.101.21"),
            ipaddress.ip_address("100.91.249.45"),
            ipaddress.ip_address("100.75.112.67"),
            ipaddress.ip_address("100.73.57.6"),
        ],
    )
    monkeypatch.setattr(api_server, "_tailscale_networks", [ipaddress.ip_network("100.64.0.0/10")])

    assert api_server._is_trusted_client_ip("100.71.101.21") is True
    assert api_server._is_trusted_client_ip("100.64.0.99") is False


def test_network_diagnostics_shows_local_pc_received_vps_forwarded_request(monkeypatch):
    monkeypatch.setattr(api_server, "_trusted_proxy_networks", [ipaddress.ip_network("100.73.57.6/32")])
    monkeypatch.setattr(
        api_server,
        "_trusted_client_ips",
        [
            ipaddress.ip_address("100.67.153.112"),
            ipaddress.ip_address("100.71.101.21"),
            ipaddress.ip_address("100.91.249.45"),
            ipaddress.ip_address("100.75.112.67"),
            ipaddress.ip_address("100.73.57.6"),
        ],
    )
    monkeypatch.setattr(api_server, "GATEWAY_REQUIRED_PUBLIC", True)
    monkeypatch.setattr(api_server, "GATEWAY_HEADER_NAME", "x-vw-gateway-secret")
    monkeypatch.setattr(api_server.socket, "gethostname", lambda: "clopeux-desktop")

    request = _make_request(
        "100.73.57.6",
        headers={
            "x-forwarded-for": "198.51.100.25, 100.73.57.6",
            "x-forwarded-proto": "https",
            "x-vw-gateway-secret": "present",
        },
    )
    principal = {"kind": "user", "user": SimpleNamespace(is_admin=True)}

    response = asyncio.run(api_server.network_diagnostics(request, principal))

    assert response.served_by == "clopeux-desktop"
    assert response.peer_ip == "100.73.57.6"
    assert response.client_ip == "198.51.100.25"
    assert response.effective_scheme == "https"
    assert response.via_trusted_proxy is True
    assert response.trusted_client_allowlist_active is True
    assert response.gateway_header_present is True
    assert response.correlation_id == "corr-test"


def test_spoofed_forwarded_for_is_ignored_without_trusted_proxy():
    request = _make_request(
        "198.51.100.50",
        headers={"x-forwarded-for": "100.71.101.21", "x-forwarded-proto": "https"},
    )

    assert api_server._get_client_ip(request) == "198.51.100.50"
    assert api_server._effective_scheme(request) == "http"

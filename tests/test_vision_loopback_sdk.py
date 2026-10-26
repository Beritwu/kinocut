"""Exercise the optional real SDK against loopback only, including hostile redirects."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from kinocut.image_engine import _describe_product_with_vision


@contextmanager
def endpoint(status, body, redirect=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((dict(self.headers), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if redirect:
                self.send_header("Location", redirect)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("redirect", [False, True])
def test_real_sdk_local_route_and_redirect_refusal(monkeypatch, tmp_path, redirect):
    anthropic = pytest.importorskip("anthropic")
    source = tmp_path / "frame.jpg"
    source.write_bytes(b"fixture bytes")
    monkeypatch.setenv("KINOCUT_VISION_MODE", "local")
    monkeypatch.setenv("KINOCUT_VISION_MODEL", "local-vision")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leave-process")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "must-not-leave-process-token")
    monkeypatch.delenv("ANTHROPIC_CUSTOM_HEADERS", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:1")
    for variable in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
        monkeypatch.setenv(variable, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    response = {
        "id": "fixture",
        "type": "message",
        "role": "assistant",
        "model": "local-vision",
        "content": [{"type": "text", "text": "A local product."}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    with (
        endpoint(200, response) as (target, target_requests),
        endpoint(307 if redirect else 200, response, target) as (origin, origin_requests),
    ):
        monkeypatch.setenv("KINOCUT_VISION_BASE_URL", origin)
        if redirect:
            with pytest.raises(anthropic.APIStatusError):
                _describe_product_with_vision(str(source))
        else:
            assert _describe_product_with_vision(str(source)) == "A local product."
        assert len(origin_requests) == 1
        headers, payload = origin_requests[0]
        assert headers["X-Api-Key"] == "local-endpoint"
        assert "Authorization" not in headers
        assert payload["model"] == "local-vision"
        assert target_requests == []


@pytest.mark.parametrize("mode", ["local", "remote"])
def test_sdk_custom_headers_rejected_before_any_request(monkeypatch, mode):
    from kinocut.errors import MCPVideoError

    monkeypatch.setenv("KINOCUT_VISION_MODE", mode)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "fixture-token")
    monkeypatch.setenv(
        "ANTHROPIC_CUSTOM_HEADERS",
        "X-Api-Key: fixture-key\nAuthorization: Bearer fixture-token\nX-Private: secret",
    )
    with endpoint(200, {}) as (origin, requests):
        target = origin if mode == "local" else "https://example.invalid"
        with pytest.raises(MCPVideoError) as error:
            _describe_product_with_vision("unused.jpg", target)
        assert error.value.code == "unsafe_vision_headers"
        assert requests == []

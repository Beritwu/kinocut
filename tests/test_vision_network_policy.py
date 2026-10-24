"""Inherited credentials cannot authorize uploads or a local-to-cloud fallback."""

import sys
from types import SimpleNamespace

import pytest

from kinocut import image_engine
from kinocut.errors import MCPVideoError
from kinocut.vision_policy import vision_provider_allowed
from kinocut.watching import vision_provider, vision_provider_worker, vision_qc


@pytest.fixture(autouse=True)
def ambient_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-cloud-key")
    monkeypatch.setenv("KINOCUT_VISION_API_KEY", "fixture-custom-key")
    monkeypatch.setenv("KINOCUT_VISION_MODEL", "fixture-model")
    monkeypatch.delenv("KINOCUT_VISION_BASE_URL", raising=False)
    monkeypatch.delenv("KINOCUT_VISION_MODE", raising=False)


@pytest.mark.parametrize("mode", [None, "off"])
@pytest.mark.parametrize("endpoint", [None, "http://127.0.0.1:1234", "https://example.invalid"])
def test_off_prevents_sdk_worker_and_http_execution(monkeypatch, mode, endpoint):
    if mode is not None:
        monkeypatch.setenv("KINOCUT_VISION_MODE", mode)
    if endpoint:
        monkeypatch.setenv("KINOCUT_VISION_BASE_URL", endpoint)
    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=lambda **kwargs: pytest.fail("provider client created while off")),
    )
    monkeypatch.setattr(
        vision_provider_worker.urllib.request, "build_opener", lambda *args: pytest.fail("HTTP created while off")
    )
    from kinocut import ffmpeg_helpers

    monkeypatch.setattr(
        ffmpeg_helpers, "_run_command", lambda *a, **k: pytest.fail("provider worker started while off")
    )
    for operation in [
        lambda: image_engine._describe_product_with_vision("unused.jpg"),
        lambda: vision_provider.assess_keyframes("fixture-model", []),
        lambda: vision_provider_worker.fetch_response(b"{}"),
    ]:
        with pytest.raises(MCPVideoError) as error:
            operation()
        assert error.value.code == "vision_provider_disabled"
    assert vision_provider.configured_vision_model() is None


@pytest.mark.parametrize("mode", ["off", "local", "remote"])
@pytest.mark.parametrize("endpoint", ["http://localhost:1234", "https://example.invalid"])
def test_custom_product_route_never_enables_fixed_cloud_qc(monkeypatch, mode, endpoint):
    monkeypatch.setenv("KINOCUT_VISION_MODE", mode)
    monkeypatch.setenv("KINOCUT_VISION_BASE_URL", endpoint)
    monkeypatch.setattr(
        vision_provider, "assess_keyframes", lambda *a: pytest.fail("cloud QC executed for custom route")
    )
    result = vision_qc._semantic_result([{"time": 0.5, "path": "unused.jpg"}], True, True)
    assert result["assessment_status"] == "not_evaluated"
    assert result["auto_scored"] is False
    with pytest.raises(MCPVideoError):
        vision_provider_worker.fetch_response(b"{}")


def test_local_mode_refuses_cloud_even_with_credentials(monkeypatch):
    monkeypatch.setenv("KINOCUT_VISION_MODE", "local")
    for endpoint in [None, "https://example.invalid"]:
        with pytest.raises(MCPVideoError) as error:
            image_engine._describe_product_with_vision("unused.jpg", endpoint)
        assert error.value.code == "vision_provider_disabled"
    assert not vision_provider_allowed(fixed_origin=True)
    assert vision_provider_allowed("local")


def test_local_provider_failure_never_constructs_cloud_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("KINOCUT_VISION_MODE", "local")
    monkeypatch.setenv("KINOCUT_VISION_BASE_URL", "http://127.0.0.1:1234")
    calls = []

    def fail_request(**kwargs):
        raise TimeoutError("local inference unavailable")

    def client(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(messages=SimpleNamespace(create=fail_request))

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=client))
    source = tmp_path / "frame.jpg"
    source.write_bytes(b"fixture image")
    with pytest.raises(TimeoutError):
        image_engine._describe_product_with_vision(str(source))
    assert len(calls) == 1
    assert calls[0]["base_url"] == "http://127.0.0.1:1234"
    assert calls[0]["api_key"] == "local-endpoint"
    assert not calls[0]["http_client"].trust_env
    assert not calls[0]["http_client"].follow_redirects


def test_unknown_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("KINOCUT_VISION_MODE", "yes")
    with pytest.raises(MCPVideoError):
        vision_provider_allowed("local")

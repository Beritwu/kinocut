"""Telemetry needs Kinocut-specific operator consent at every npm boundary."""

from types import SimpleNamespace

import pytest

from kinocut import revideo_engine
from kinocut.errors import MCPVideoError


@pytest.mark.parametrize("args", [["ci"], ["run", "render"]])
@pytest.mark.parametrize("consent,disabled", [(None, "true"), ("false", "true"), ("true", "false")])
def test_telemetry_default_and_opt_in_override_ambient_and_internal_env(monkeypatch, tmp_path, args, consent, disabled):
    monkeypatch.setenv("DISABLE_TELEMETRY", "false")
    if consent is None:
        monkeypatch.delenv("KINOCUT_REVIDEO_TELEMETRY", raising=False)
    else:
        monkeypatch.setenv("KINOCUT_REVIDEO_TELEMETRY", consent)
    observed = []

    def run(cmd, **kwargs):
        observed.append(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(revideo_engine.subprocess, "run", run)
    revideo_engine._run_npm(args, tmp_path, 10, extra_env={"DISABLE_TELEMETRY": "false"})
    assert len(observed) == 1
    assert observed[0]["env"]["DISABLE_TELEMETRY"] == disabled
    assert observed[0]["timeout"] == 10


def test_invalid_telemetry_consent_never_starts_subprocess(monkeypatch, tmp_path):
    monkeypatch.setenv("KINOCUT_REVIDEO_TELEMETRY", "maybe")
    monkeypatch.setattr(revideo_engine.subprocess, "run", lambda *a, **k: pytest.fail("npm invoked"))
    with pytest.raises(MCPVideoError):
        revideo_engine._run_npm(["ci"], tmp_path, 10)

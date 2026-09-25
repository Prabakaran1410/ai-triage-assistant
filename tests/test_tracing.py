import pytest

from app.core import tracing
from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolated_tracing(monkeypatch):
    """Every test starts with tracing keys unset and a fresh cached client."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.delenv("LANGFUSE_CAPTURE_CONTENT", raising=False)
    get_settings.cache_clear()
    tracing.reset_tracer()
    yield
    get_settings.cache_clear()
    tracing.reset_tracer()


def test_without_keys_tracing_is_a_no_op():
    assert tracing.get_tracer() is None
    with tracing.observe("anything", as_type="generation", model="m") as obs:
        obs.update(output="x", usage_details={"input": 1})  # must not raise


def test_exceptions_in_traced_code_still_propagate():
    with pytest.raises(ValueError, match="boom"), tracing.observe("x"):
        raise ValueError("boom")


def test_customer_content_is_not_captured_by_default():
    assert tracing.redact("what is my balance?") == "[content not captured]"


def test_customer_content_captured_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("LANGFUSE_CAPTURE_CONTENT", "true")
    get_settings.cache_clear()
    assert tracing.redact("what is my balance?") == "what is my balance?"


def test_flush_without_a_client_does_nothing():
    tracing.flush_tracer()  # must not raise or initialise anything


def test_settings_strip_quotes_docker_env_file_leaves_on_values():
    settings = Settings(jwt_secret='"abc123"', langfuse_public_key="'pk-lf-x'")
    assert settings.jwt_secret == "abc123"
    assert settings.langfuse_public_key == "pk-lf-x"

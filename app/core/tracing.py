"""Langfuse tracing: optional, fail-safe, and content-free by default.

Three rules this module exists to enforce:

1. Tracing must never break or slow a request. No keys -> every call is a
   no-op. An SDK error while opening a span is logged and swallowed. Export
   to Langfuse happens on a background thread, not in the request path.
2. Customer text stays out of traces unless explicitly enabled
   (LANGFUSE_CAPTURE_CONTENT). Everything else - tenant, intent, confidence,
   model, tokens, latency, which chunks were retrieved and how close - is
   always traced, and none of it contains what a customer wrote.
3. Call sites never touch the SDK directly; they use `observe()`, so the
   no-op path and the real path look identical.
"""
import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_NOT_CAPTURED = "[content not captured]"

_client: Any = None
_initialised = False


class _NoopObservation:
    """Stands in for a Langfuse observation when tracing is off."""

    def update(self, **kwargs: Any) -> None:
        return None


def get_tracer() -> Any:
    """The Langfuse client, or None when tracing is not configured."""
    global _client, _initialised
    if _initialised:
        return _client
    _initialised = True

    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("Langfuse keys not set - tracing disabled")
        return None

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or "https://cloud.langfuse.com",
            environment=settings.environment,
        )
    except Exception:
        logger.exception("Could not initialise Langfuse - tracing disabled")
        _client = None
    return _client


def reset_tracer() -> None:
    """Forget the cached client (tests, and settings changes)."""
    global _client, _initialised
    _client = None
    _initialised = False


def disable_tracer() -> None:
    """Turn tracing off for this process (e.g. bulk evaluation runs, which
    would otherwise create one trace per labeled row)."""
    global _client, _initialised
    _client = None
    _initialised = True


def redact(value: Any) -> Any:
    """Pass customer-derived content through only if capture is enabled."""
    return value if get_settings().langfuse_capture_content else _NOT_CAPTURED


@contextmanager
def observe(name: str, *, as_type: str = "span", **kwargs: Any) -> Iterator[Any]:
    """Open a Langfuse observation, or a no-op stand-in if tracing is off.

    Exceptions raised by the traced code propagate normally (Langfuse records
    them on the observation); only failures of the tracing SDK itself are
    swallowed.
    """
    client = get_tracer()
    stack = ExitStack()
    observation: Any = _NoopObservation()
    if client is not None:
        try:
            observation = stack.enter_context(
                client.start_as_current_observation(name=name, as_type=as_type, **kwargs)
            )
        except Exception:
            logger.exception("Langfuse could not open observation %r", name)
            observation = _NoopObservation()
    with stack:
        yield observation


def flush_tracer() -> None:
    """Send anything still buffered. Called on application shutdown."""
    client = get_tracer() if _initialised else None
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.exception("Langfuse flush failed")

"""Actually sending an approved reply to the customer.

Until this existed, the console's "Send to customer" button set a status to
`sent` and transmitted nothing. That is the worst kind of gap: not a missing
feature but a false one, where the record says a customer was answered and
they were not.

So the rule here is that `sent` means it left the building. A delivery that
fails does not advance the status, and the failure is written to the audit
trail rather than swallowed.

Providers are pluggable and the default sends nothing. A deployment with no
channel configured records what it *would* have sent and reports that
plainly - "recorded, not delivered" - instead of pretending.
"""
import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    provider: str
    # Provider-side id, for matching against their logs when someone asks
    # whether a reply really went out.
    reference: str | None = None
    detail: str | None = None


class DeliveryError(Exception):
    """The reply could not be sent. The status must not advance."""


class DeliveryProvider(Protocol):
    name: str

    async def send(self, *, to: str, subject: str, body: str) -> DeliveryResult: ...


class RecordOnlyProvider:
    """The default: writes what would have been sent and says so.

    Deliberately reports delivered=False. Returning success here would put
    "sent" in an audit trail for a message nobody received, which is exactly
    the problem this module exists to fix.
    """

    name = "record-only"

    async def send(self, *, to: str, subject: str, body: str) -> DeliveryResult:
        logger.info(
            "No delivery channel configured; not sending to %s (subject %r, %d chars)",
            to,
            subject,
            len(body),
        )
        return DeliveryResult(
            delivered=False,
            provider=self.name,
            detail="No delivery channel is configured, so nothing was sent.",
        )


class ResendProvider:
    """Email via Resend's HTTP API."""

    name = "resend"

    def __init__(self, api_key: str, from_address: str) -> None:
        self._api_key = api_key
        self._from = from_address

    async def send(self, *, to: str, subject: str, body: str) -> DeliveryResult:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "from": self._from,
                        "to": [to],
                        "subject": subject,
                        "text": body,
                    },
                )
        except Exception as e:
            raise DeliveryError(f"Could not reach the email provider: {e}") from e

        if response.status_code >= 400:
            # Surfaced rather than logged and swallowed: a reviewer pressing
            # send needs to know it did not go.
            raise DeliveryError(
                f"The email provider refused the message ({response.status_code}): "
                f"{response.text[:200]}"
            )

        return DeliveryResult(
            delivered=True,
            provider=self.name,
            reference=response.json().get("id"),
        )


_provider: DeliveryProvider | None = None


def get_delivery_provider() -> DeliveryProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.delivery_provider == "resend" and settings.resend_api_key:
            _provider = ResendProvider(
                settings.resend_api_key, settings.delivery_from_address
            )
        else:
            _provider = RecordOnlyProvider()
    return _provider


def reset_delivery_provider() -> None:
    global _provider
    _provider = None


def build_subject(message: str) -> str:
    """A short subject derived from what the customer wrote.

    Support replies are read in a mailbox next to everything else, so a
    subject of "Re: your message" helps nobody find theirs.
    """
    first_line = (message or "").strip().splitlines()[0] if message.strip() else ""
    trimmed = first_line[:60].rstrip()
    return f"Re: {trimmed}..." if len(first_line) > 60 else f"Re: {trimmed or 'your message'}"

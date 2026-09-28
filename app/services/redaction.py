"""Keep customer identifiers out of third-party services.

Customer messages are stored in our own database - a support tool cannot
work otherwise, and that is governed by retention and deletion rather than
redaction. What this module controls is what leaves our infrastructure: the
text sent to Google for embedding and generation, and to Langfuse for
tracing.

Reversible by design. Stripping identifiers outright would produce drafts a
reviewer has to repair by hand, so each one is replaced with a stable
placeholder (`[EMAIL_1]`), and the real values are restored in the draft
before anyone sees it. The model never handles the real value; the customer
still gets a coherent reply.

WHAT THIS DOES NOT DO, and it matters:

Names, street addresses and free-text personal details are not detected.
Regular expressions cannot do it at acceptable quality, and doing it badly
is worse than not doing it - a redactor that mangles "Thanks, Dave" while
missing "my address is 12 Elm St" gives false assurance. Proper coverage
needs named-entity recognition (Presidio, spaCy), which is a real
dependency and a real cost, and should be a deliberate decision rather than
something smuggled in here. So: structured identifiers are handled, and the
limitation is documented rather than implied away.

Precision is favoured over recall. A bare run of digits is NOT treated as a
phone number, because order and reference numbers look identical and
destroying them degrades every reply. Phone numbers are recognised when
punctuated or internationally prefixed.
"""
import re
from dataclasses import dataclass

# Order matters: e-mail addresses contain dots and digits that later
# patterns would otherwise claw at, and card numbers can look like phone
# numbers, so the more specific patterns run first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]*\w\b")),
    # Card-shaped runs are validated with Luhn below; the pattern alone
    # would swallow any long number.
    ("CARD", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}[ ]?[A-Z0-9]{1,4}\b")),
    ("NATIONAL_ID", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "PHONE",
        re.compile(
            r"(?<![\w.])(?:"
            r"\+\d{1,3}[\s.\-]?(?:\(\d{1,4}\)[\s.\-]?)?\d{1,4}(?:[\s.\-]?\d{2,4}){1,4}"
            r"|\(\d{2,4}\)[\s.\-]?\d{3,4}[\s.\-]?\d{3,4}"
            r"|\d{3,4}[\s.\-]\d{3,4}[\s.\-]\d{3,4}"
            r")(?![\w.])"
        ),
    ),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

_PLACEHOLDER = re.compile(r"\[([A-Z_]+)_(\d+)\]")


@dataclass(frozen=True)
class Redaction:
    text: str
    # placeholder -> the original value it stands for
    mapping: dict[str, str]

    @property
    def found(self) -> int:
        return len(self.mapping)


def _luhn_valid(digits: str) -> bool:
    """Payment cards carry a check digit. Without verifying it, every long
    order number would be redacted as a card."""
    if not 13 <= len(digits) <= 19:
        return False
    total, double = 0, False
    for char in reversed(digits):
        value = ord(char) - 48
        if double:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        double = not double
    return total % 10 == 0


def _is_plausible_ip(value: str) -> bool:
    return all(part.isdigit() and int(part) <= 255 for part in value.split("."))


def redact(text: str) -> Redaction:
    """Replace identifiers with stable placeholders.

    The same value always maps to the same placeholder within one message,
    so a customer who writes their address twice does not confuse the model
    with two different tokens.
    """
    if not text:
        return Redaction(text=text, mapping={})

    mapping: dict[str, str] = {}
    seen: dict[str, str] = {}
    counters: dict[str, int] = {}
    result = text

    for label, pattern in _PATTERNS:

        def substitute(match: re.Match[str], label: str = label) -> str:
            value = match.group(0)

            if label == "CARD" and not _luhn_valid(re.sub(r"[ -]", "", value)):
                return value
            if label == "IP_ADDRESS" and not _is_plausible_ip(value):
                return value

            if value in seen:
                return seen[value]

            counters[label] = counters.get(label, 0) + 1
            placeholder = f"[{label}_{counters[label]}]"
            seen[value] = placeholder
            mapping[placeholder] = value
            return placeholder

        result = pattern.sub(substitute, result)

    return Redaction(text=result, mapping=mapping)


def restore(text: str | None, mapping: dict[str, str]) -> str | None:
    """Put the real values back into a draft.

    Tolerant of the model reformatting a placeholder - it sometimes returns
    `[EMAIL 1]` or lowercases it - because a draft containing a literal
    `[EMAIL_1]` would reach a customer if the substitution silently failed.
    """
    if not text or not mapping:
        return text

    def substitute(match: re.Match[str]) -> str:
        canonical = f"[{match.group(1).upper()}_{match.group(2)}]"
        return mapping.get(canonical, match.group(0))

    result = _PLACEHOLDER.sub(substitute, text)
    # Second pass for the reformatted variants the strict pattern missed.
    for placeholder, value in mapping.items():
        label, _, number = placeholder.strip("[]").rpartition("_")
        loose = re.compile(rf"\[\s*{label}[\s_-]*{number}\s*\]", re.IGNORECASE)
        result = loose.sub(value.replace("\\", "\\\\"), result)
    return result


def unrestored_placeholders(text: str | None) -> list[str]:
    """Placeholders still present after restoration - a bug we would rather
    surface than let reach a customer."""
    return [] if not text else [m.group(0) for m in _PLACEHOLDER.finditer(text)]

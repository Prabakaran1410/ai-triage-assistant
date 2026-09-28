import pytest

from app.services.redaction import redact, restore, unrestored_placeholders

# A real-looking Visa test number: passes Luhn, which is what distinguishes
# a card from any other long number.
VALID_CARD = "4242424242424242"
INVALID_LONG_NUMBER = "4242424242424243"  # same shape, fails Luhn


@pytest.mark.parametrize(
    ("message", "label"),
    [
        ("Email me at john.doe+tag@example.co.uk please", "EMAIL"),
        ("Call me on +44 20 7946 0958", "PHONE"),
        ("My number is (555) 123-4567", "PHONE"),
        ("Reach me at 555-123-4567", "PHONE"),
        (f"My card {VALID_CARD} was charged twice", "CARD"),
        ("Refund to GB29 NWBK 6016 1331 9268 19", "IBAN"),
        ("My SSN is 123-45-6789", "NATIONAL_ID"),
        ("I connected from 192.168.101.42", "IP_ADDRESS"),
    ],
)
def test_identifiers_are_replaced_with_a_placeholder(message, label):
    result = redact(message)
    assert label in result.text, f"{label} should have been redacted from {message!r}"
    assert result.found == 1
    # The real value must not survive anywhere in what we send out.
    original_value = next(iter(result.mapping.values()))
    assert original_value not in result.text


@pytest.mark.parametrize(
    "message",
    [
        "My order #48213 is late",
        "Order 4821312345 never arrived",
        f"The reference number is {INVALID_LONG_NUMBER}",
        "I paid $129.95 for it",
        "It arrived on 2026-09-14",
        "I ordered 3 tents and 2 mats",
        "Version 10.2 of the app crashes",
        "Is the Growth plan still $99/month for 15 users?",
    ],
)
def test_ordinary_numbers_are_left_alone(message):
    """Over-redaction is not a safe default: it quietly degrades every reply
    and strips the order numbers a reviewer needs."""
    result = redact(message)
    assert result.found == 0, f"nothing should have been redacted from {message!r}"
    assert result.text == message


def test_a_long_number_is_only_a_card_if_it_passes_luhn():
    assert redact(f"card {VALID_CARD}").found == 1
    assert redact(f"ref {INVALID_LONG_NUMBER}").found == 0


def test_something_shaped_like_an_ip_but_impossible_is_left_alone():
    assert redact("build 999.888.777.666").found == 0


def test_the_same_value_gets_the_same_placeholder():
    """Two different tokens for one value would read to the model as two
    different people."""
    result = redact("Write to a@b.com, I repeat, a@b.com")
    assert result.found == 1
    assert result.text.count("[EMAIL_1]") == 2


def test_different_values_get_different_placeholders():
    result = redact("Either a@b.com or c@d.com works")
    assert result.found == 2
    assert "[EMAIL_1]" in result.text and "[EMAIL_2]" in result.text


def test_a_message_with_several_kinds_of_identifier():
    result = redact(f"I'm john@example.com, card {VALID_CARD}, phone +1 555 123 4567")
    assert result.found == 3
    assert {"EMAIL", "CARD", "PHONE"} == {k.strip("[]").rsplit("_", 1)[0] for k in result.mapping}
    for value in result.mapping.values():
        assert value not in result.text


# --- restoring ---------------------------------------------------------------

def test_a_draft_comes_back_with_the_real_values():
    result = redact("Send it to john@example.com")
    draft = f"We will send it to {next(iter(result.mapping))} today."
    assert restore(draft, result.mapping) == "We will send it to john@example.com today."


def test_restore_survives_the_model_reformatting_a_placeholder():
    """Models reformat these. A draft containing a literal [EMAIL_1] would
    otherwise reach a customer."""
    result = redact("Send it to john@example.com")
    for mangled in ("[EMAIL 1]", "[email_1]", "[ EMAIL_1 ]", "[Email-1]"):
        assert "john@example.com" in restore(f"Sent to {mangled}.", result.mapping)


def test_round_trip_returns_the_original_message():
    original = f"Hi, I'm john@example.com on +1 555 123 4567, card {VALID_CARD}"
    result = redact(original)
    assert restore(result.text, result.mapping) == original


def test_restore_is_a_no_op_without_a_mapping():
    assert restore("nothing to do", {}) == "nothing to do"
    assert restore(None, {"[EMAIL_1]": "a@b.com"}) is None


def test_leftover_placeholders_can_be_detected():
    """If a substitution fails we want to know, not ship '[EMAIL_1]' to a
    customer."""
    assert unrestored_placeholders("Contact [EMAIL_1] please") == ["[EMAIL_1]"]
    assert unrestored_placeholders("Contact john@example.com please") == []
    assert unrestored_placeholders(None) == []


def test_empty_input_is_handled():
    result = redact("")
    assert result.text == "" and result.found == 0

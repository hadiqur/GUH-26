import pytest

from app.phone import is_uk_mobile, to_e164

E164 = "+447700900123"


@pytest.mark.parametrize(
    "raw",
    [
        "07700 900123",
        "07700900123",
        "+44 7700 900123",
        "+447700900123",
        "447700900123",  # Vonage: digits, no plus
        "0044 7700 900123",
        "07700-900-123",
        "(07700) 900123",
        " +44 (7700) 900-123 ",
    ],
)
def test_to_e164_accepts_common_formats(raw):
    assert to_e164(raw) == E164


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "hello", "07700 9001", "12345", "+44", "0770090012345678", "+44 7700 abc123", "++447700900123"],
)
def test_to_e164_rejects_garbage(raw):
    assert to_e164(raw) is None


def test_to_e164_real_formats_still_validated():
    # A real-format UK mobile (not a drama number) passes through libphonenumber.
    assert to_e164("07911 123456") == "+447911123456"
    # Valid non-UK numbers are kept; the UK-only rule is is_uk_mobile's job.
    assert to_e164("+1 202 555 0143") == "+12025550143"


def test_is_uk_mobile():
    assert is_uk_mobile("+447700900123")  # Ofcom drama range
    assert is_uk_mobile("+447911123456")
    assert not is_uk_mobile("+442079460000")  # London landline
    assert not is_uk_mobile("+12025550143")
    assert not is_uk_mobile(None)
    assert not is_uk_mobile("")

"""Phone number handling. Every number in Dial-a-Text goes through to_e164()."""

from __future__ import annotations

import re

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType

_STRIP = re.compile(r"[\s\-()\[\]]")

# Ofcom reserves 07700 900000-900999 for drama and testing. libphonenumber
# calls them invalid, but we accept them so demos and tests never text anyone.
_DRAMA = re.compile(r"^\+447700900\d{3}$")


def to_e164(raw: str | None) -> str | None:
    """Normalise a phone number to E.164 ("+447700900123"), or None if invalid.

    Accepts "07700 900123", "+44 7700 900123", "447700900123" (Vonage style,
    no plus) and "0044 7700 900123". Spaces, dashes and brackets are ignored.
    """
    if raw is None:
        return None
    s = _STRIP.sub("", str(raw))
    if s.startswith("00"):
        s = "+" + s[2:]
    elif s.isdigit() and not s.startswith("0"):
        s = "+" + s  # digits only, no trunk prefix: treat as international
    if s.startswith("+"):
        if not s[1:].isdigit():
            return None
        region = None
    elif s.isdigit():
        region = "GB"  # national format, e.g. 07700 900123
    else:
        return None
    try:
        num = phonenumbers.parse(s, region)
    except NumberParseException:
        return None
    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    if _DRAMA.match(e164) or phonenumbers.is_valid_number(num):
        return e164
    return None


def is_uk_mobile(e164: str | None) -> bool:
    """True if the E.164 number is a UK (+44) mobile, including Ofcom drama numbers."""
    if not e164 or not e164.startswith("+44"):
        return False
    if _DRAMA.match(e164):
        return True
    try:
        num = phonenumbers.parse(e164, None)
    except NumberParseException:
        return False
    # Check the country code, not the region: Jersey/Guernsey/IoM mobiles are +44 too.
    return phonenumbers.is_valid_number(num) and phonenumbers.number_type(num) in (
        PhoneNumberType.MOBILE,
        PhoneNumberType.FIXED_LINE_OR_MOBILE,
    )

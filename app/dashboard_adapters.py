"""Thin adapters between the dashboard and the rest of Dial-a-Text.

These are deliberately small so they can be swapped for the real
implementations (app/sms.py and the call flow's phone validator) once they
land. The dashboard only ever calls the two functions below.
"""

from __future__ import annotations

import logging
import os

import phonenumbers
from phonenumbers import PhoneNumberType

log = logging.getLogger("dialatext.dashboard")


class PhoneError(ValueError):
    """Raised with a friendly, user-facing message when a number is rejected."""


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def demo_mode() -> bool:
    return _flag("DEMO_MODE")


# Ofcom reserves 07700 900000 to 07700 900999 for drama and testing. Nobody
# real owns them, so they are safe for seed data and the demo. libphonenumber
# treats them as invalid, so we allow them explicitly.
_DRAMA_PREFIX = "+447700900"


def service_number() -> str:
    """The Dial-a-Text number people call, in E.164 (VONAGE_NUMBER)."""
    value = os.getenv("VONAGE_NUMBER", "").strip()
    if not value and demo_mode():
        return "+447700900000"  # drama number placeholder for local demos
    return value


def is_reserved_test_number(e164: str) -> bool:
    return e164.startswith(_DRAMA_PREFIX) and len(e164) == len(_DRAMA_PREFIX) + 3


def normalise_phone(raw: str) -> str:
    """Return the number in E.164 (+447700900123) or raise PhoneError.

    Same rules as the call flow: UK (+44) mobiles only, unless
    ALLOW_INTERNATIONAL=1, in which case any valid mobile-capable number.
    """
    text = (raw or "").strip()
    if not text:
        raise PhoneError("Please enter a phone number.")
    try:
        num = phonenumbers.parse(text, "GB")
    except phonenumbers.NumberParseException:
        raise PhoneError("That doesn't look like a phone number. Try something like 07700 900123.")

    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    if is_reserved_test_number(e164):
        return e164

    if not phonenumbers.is_valid_number(num):
        raise PhoneError("That number isn't complete or isn't valid. Please check it and try again.")

    allow_intl = _flag("ALLOW_INTERNATIONAL")
    # Note: +44 mobiles in Guernsey/Jersey/Isle of Man report other regions,
    # so check the country code rather than the region.
    if num.country_code != 44 and not allow_intl:
        raise PhoneError("Dial-a-Text only works with UK mobile numbers at the moment.")

    ntype = phonenumbers.number_type(num)
    if ntype not in (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE):
        raise PhoneError("That looks like a landline. Texts can only go to mobile numbers.")
    return e164


def send_sms(to: str, text: str) -> dict:
    """Send one SMS. Returns a dict with at least {"status": ...}.

    DEMO_MODE=1: only logs the text. Otherwise not wired up yet: swap this for
    the Vonage sender in app/sms.py.
    """
    if demo_mode():
        log.warning("[DEMO_MODE] SMS to %s: %s", to, text)
        return {"status": "logged"}
    # TODO(integration): replace with the real sender, e.g.
    #   from app.sms import send_sms as vonage_send
    #   return vonage_send(to, text)
    raise NotImplementedError("SMS sending is not wired up yet (set DEMO_MODE=1 for local dev)")

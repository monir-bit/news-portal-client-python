import re

_BD_MOBILE = re.compile(r"^(?:\+?880|0)?1[3-9]\d{8}$")


def normalize_phone(phone: str | None) -> str:
    """FastAPI-port reconstruction of the missing `App\\Support\\QuizParticipantPhone`
    class (referenced by 7 Laravel FormRequest classes but absent from the repo,
    meaning those endpoints 500 in the source app today — see implementation guide).

    Strips whitespace/dashes/parens; for recognizable Bangladeshi mobile numbers
    (any of 01XXXXXXXXX, 8801XXXXXXXXX, +8801XXXXXXXXX) normalizes to the plain
    local 11-digit form `01XXXXXXXXX` so the SAME physical number always maps to
    the SAME `participants.phone` value regardless of how a client formatted it.
    Anything that doesn't match a recognizable BD mobile shape is passed through
    with whitespace/punctuation stripped only, so unrelated formats still round-trip.
    """
    if phone is None:
        return ""
    cleaned = re.sub(r"[\s\-().]", "", phone.strip())
    match = _BD_MOBILE.match(cleaned)
    if not match:
        return cleaned
    digits = re.sub(r"^(?:\+?880|0)", "", cleaned)
    return f"0{digits}"

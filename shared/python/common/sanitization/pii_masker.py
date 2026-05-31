import re

_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_SECRET = re.compile(
    r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+"
)
_BEARER = re.compile(r"(?i)bearer\s+[a-zA-Z0-9._~+/=-]+")


def mask_pii(text: str) -> str:
    masked = _EMAIL.sub("[STRIPPED_EMAIL]", text)
    masked = _IPV4.sub("[STRIPPED_IP]", masked)
    masked = _SECRET.sub(r"\1=[STRIPPED_SECRET]", masked)
    masked = _BEARER.sub("Bearer [STRIPPED_TOKEN]", masked)
    return masked

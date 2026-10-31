"""facebook's hooks: the media CDN POP collapse (and, from Task 2, the DGW gateway framing)."""
import re

_POP_MEDIA = re.compile(r"^scontent.*\.fbcdn\.net$")
_POP_FNA = re.compile(r"^.+\.fna\.(fbcdn\.net|whatsapp\.net)$")


def pop_host(host):
    """Media CDN host names carry a regional POP code, which is a location: collapse them."""
    if _POP_MEDIA.match(host):
        return "scontent.*.fbcdn.net"
    m = _POP_FNA.match(host)
    return "*.fna." + m.group(1) if m else host


def binary_units(raw):
    return None  # Task 2 moves the gateway framing here

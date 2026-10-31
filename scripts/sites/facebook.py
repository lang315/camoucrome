"""facebook's hooks: the media CDN POP collapse and the DGW gateway framing."""
import re

_POP_MEDIA = re.compile(r"^scontent.*\.fbcdn\.net$")
_POP_FNA = re.compile(r"^.+\.fna\.(fbcdn\.net|whatsapp\.net)$")


def pop_host(host):
    """Media CDN host names carry a regional POP code, which is a location: collapse them."""
    if _POP_MEDIA.match(host):
        return "scontent.*.fbcdn.net"
    m = _POP_FNA.match(host)
    return "*.fna." + m.group(1) if m else host


GATEWAY_TYPES = range(0x0c, 0x10)
GATEWAY_PREFIX = {0x0d: 2}  # a type-0d chunk's payload starts 2 bytes before its JSON or MQTT (measured: run 3, lightspeed and realtime)


def gateway_chunks(raw):
    """([(type, payload)], rest): the gateway's chunks at the front of a binary frame, each [type 0x0c-0x0f][2-byte stream id]
    [3-byte little-endian length][payload], and how many bytes after the last whole chunk are not one."""
    out, i = [], 0
    while i + 6 <= len(raw) and raw[i] in GATEWAY_TYPES:
        n = int.from_bytes(raw[i + 3:i + 6], "little")
        if i + 6 + n > len(raw):
            break
        out.append((raw[i], raw[i + 6:i + 6 + n]))
        i += 6 + n
    return out, len(raw) - i


def _embedded_json(p):
    """(offset, value) of the JSON that runs from the first '{' or '[' within the first 16 bytes to the end of p, else None;
    realtime's type-0d chunks carry a binary header of 2 to 5 more bytes before it."""
    import observe_drive as d  # function-level: observe_drive imports sites
    for i in range(min(16, len(p))):
        if p[i] in b"{[":
            try:
                j = d._json(p[i:].decode("utf-8"))
            except UnicodeDecodeError:
                continue
            if j is not None:
                return i, j
    return None


def _chunk_units(b0, payload):
    """([(topic, field pairs)], partial) of one chunk; the topic is '<type hex>/<mqtt topic, (json), (json+N), (ack) or
    (opaque)>', N the bytes of header before the JSON. A type-0c chunk of 2 bytes is an acknowledgement counter: it parses
    as an empty MQTT packet by chance and is not one."""
    import observe_drive as d  # function-level: observe_drive imports sites
    key = "%02x/" % b0
    if b0 == 0x0c and len(payload) <= 2:
        return [(key + "(ack)", [])], 0
    p = payload[GATEWAY_PREFIX.get(b0, 0):]
    pk, partial = d.mqtt_parse(p) if p[:1] not in (b"{", b"[") else ([], 0)
    if pk and not partial:
        return [(key + (q["topic"] or q["type"]), d.fields(q["payload"])[1]) for q in pk], 0
    emb = _embedded_json(p)  # before a partial MQTT read: a binary header can look like a packet start
    if emb:
        return [(key + ("(json+%d)" % emb[0] if emb[0] else "(json)"), d.walk(emb[1]))], 0
    if pk:
        return [(key + (q["topic"] or q["type"]), d.fields(q["payload"])[1]) for q in pk], partial
    return [(key + "(opaque)", [])], 0


def binary_units(raw):
    """([(topic, field pairs)], partial) of a facebook binary frame: the gateway's keepalive pair, else its DGW chunks
    (types 0c-0f: Ack, Data, EndOfData, EstabStream); None when the frame is neither (observe_drive then tries MQTT)."""
    if raw in (b"\x09", b"\x0a"):
        return [("%02x/(single)" % raw[0], [])], 0  # the gateway's keepalive pair
    chunks, rest = gateway_chunks(raw)
    if not chunks:
        return None
    units, partial = [], rest
    for b0, payload in chunks:
        u, n = _chunk_units(b0, payload)
        units, partial = units + u, partial + n
    return units + ([("(partial)", [])] if rest else []), partial

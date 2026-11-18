"""verify_windows_client K1's config: the identity padded until it must travel as CAMOU_CONFIG_1..N."""
import json


def over_one_chunk(config, limit):
    """config with fonts:list repeated until its JSON exceeds `limit` chars. The repeats are real family names
    (an allowlist; a duplicate changes nothing the browser reads), so no unknown key reaches the #207 guard.
    Raises when the config has no fonts:list to repeat."""
    out = dict(config)
    fonts = out.get("fonts:list")
    if not fonts:
        raise ValueError("no fonts:list to pad: pick another seed or key")
    base = list(fonts)
    out["fonts:list"] = list(base)
    while len(json.dumps(out)) <= limit:
        out["fonts:list"] += base
    return out

"""Per-instance values beside a preset. A preset (settings/presets/*.json) is
a device identity; the seeds are not part of it (preset_loader.cc emits
none), so each launch draws them fresh unless the caller pins them -- or a
kept profile keeps them (profile_seeds)."""
import json
import os
import random
import tempfile

# Mirrors settings/launcher.json "per_instance_seeds"; the test asserts it.
SEED_KEYS = ("canvas:seed", "audio:seed", "mediaDevices:seed")
SEEDS_FILE = "camoucrome-seeds.json"


def per_instance_config(rng=None):
    """Fresh non-zero uint32 seeds for every key in SEED_KEYS. Merge the
    caller's explicit keys over the result; pass it as launch(config=...)
    beside launch(preset=...)."""
    rng = rng or random.SystemRandom()
    return {k: rng.randint(1, 0xFFFFFFFF) for k in SEED_KEYS}


def profile_seeds(user_data_dir, rng=None):
    """The seeds a kept profile launches with: drawn once into
    <user_data_dir>/camoucrome-seeds.json and read back on every later launch,
    so the profile shows the same canvas, audio and device-ID fingerprint each
    session. Keys missing from the file are drawn and added. A damaged file
    raises ValueError instead of being redrawn, which would change the
    fingerprint silently. The Go and Node clients read and write the same file.

        udd = "/profiles/alice"
        launch(pw, exe, user_data_dir=udd, preset=preset,
               config={**profile_seeds(udd), **mine})
    """
    path = os.path.join(user_data_dir, SEEDS_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            stored = json.load(f)
    except FileNotFoundError:
        stored = {}
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from None
    if not isinstance(stored, dict):
        raise ValueError(f"{path} must hold a JSON object")
    for k in SEED_KEYS:
        v = stored.get(k)
        if k in stored and (type(v) is not int or not 1 <= v <= 0xFFFFFFFF):
            raise ValueError(f"{path}: {k} must be a non-zero uint32, not {v!r}")
    missing = [k for k in SEED_KEYS if k not in stored]
    if missing:
        drawn = per_instance_config(rng)
        stored.update({k: drawn[k] for k in missing})
        os.makedirs(user_data_dir, exist_ok=True)
        # Written beside the target and renamed over it, so a crash mid-write
        # never leaves the damaged file the check above would refuse.
        fd, tmp = tempfile.mkstemp(dir=user_data_dir, prefix=SEEDS_FILE + ".")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(stored, f)
        os.replace(tmp, path)
    return {k: stored[k] for k in SEED_KEYS}

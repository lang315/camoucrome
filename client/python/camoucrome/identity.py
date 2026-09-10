"""Per-instance values beside a preset. A preset (settings/presets/*.json) is
a device identity; the seeds are not part of it (preset_loader.cc emits
none), so each launch draws them fresh unless the caller pins them."""
import random

# Mirrors settings/launcher.json "per_instance_seeds"; the test asserts it.
SEED_KEYS = ("canvas:seed", "audio:seed", "mediaDevices:seed")


def per_instance_config(rng=None):
    """Fresh non-zero uint32 seeds for every key in SEED_KEYS. Merge the
    caller's explicit keys over the result; pass it as launch(config=...)
    beside launch(preset=...)."""
    rng = rng or random.SystemRandom()
    return {k: rng.randint(1, 0xFFFFFFFF) for k in SEED_KEYS}

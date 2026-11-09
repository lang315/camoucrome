"""light=True (part 3, L1): only pool samples with DPR 1 are drawn; a DPR-1 first draw is unchanged."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

KW = {"timezone": "UTC", "locale": "en-US"}


def _dpr(seed, **kw):
    return gen.generate("windows", seed=seed, **KW, **kw)["launch"]["dpr"]


def _first_seed(pred):
    return next(s for s in range(1, 300) if pred(_dpr(s)))


def test_light_turns_a_high_dpr_seed_into_dpr_1():
    s = _first_seed(lambda d: d != 1)
    assert _dpr(s, light=True) == 1


def test_light_leaves_a_dpr_1_seed_byte_identical():
    s = _first_seed(lambda d: d == 1)
    assert gen.generate("windows", seed=s, **KW, light=True) == gen.generate("windows", seed=s, **KW)


def test_light_off_is_the_default():
    s = _first_seed(lambda d: d != 1)
    assert gen.generate("windows", seed=s, **KW, light=False) == gen.generate("windows", seed=s, **KW)


def test_cli_light_flag(capsys):
    import json
    s = _first_seed(lambda d: d != 1)
    gen.main(["--os", "windows", "--seed", str(s), "--timezone", "UTC", "--locale", "en-US", "--light"])
    assert json.loads(capsys.readouterr().out)["launch"]["dpr"] == 1

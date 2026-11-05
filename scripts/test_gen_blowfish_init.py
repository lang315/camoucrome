import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import gen_blowfish_init as g


def test_pi_words():
    w = g.pi_words()
    assert w[0] == 0x243F6A88
    assert w[17] == 0x8979FB1B
    assert w[18] == 0xD1310BA6
    assert w[1041] == 0x3AC372E6


def test_check_passes():
    here = os.path.dirname(__file__)
    r = subprocess.run([sys.executable, os.path.join(here, "gen_blowfish_init.py"), "--check"])
    assert r.returncode == 0

"""classify() without a browser: the verdict never carries an address."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_webrtc_realproxy as v

EXIT, REAL = "203.0.113.7", "198.51.100.9"


def cand(addr, typ="srflx", proto="udp"):
    return f"candidate:1 1 {proto.upper()} 1686052607 {addr} 50000 typ {typ} raddr 0.0.0.0 rport 0"


def test_a_srflx_with_the_host_address_is_the_leak():
    leaks, n = v.classify([cand(REAL)], EXIT, REAL)
    assert leaks == ["srflx/udp(host public address)"] and n == 1 and REAL not in "".join(leaks)


def test_the_exit_address_is_not_a_leak():
    assert v.classify([cand(EXIT, "srflx")], EXIT, REAL)[0] == []


def test_mdns_host_is_not_a_leak_but_a_raw_private_ip_is():
    assert v.classify([cand("1b3f.local", "host")], EXIT, REAL)[0] == []
    assert v.classify([cand("192.0.2.5", "host")], EXIT, REAL)[0] == ["host/udp"]


def test_no_candidates_is_no_leak():
    assert v.classify([], EXIT, REAL) == ([], 0)

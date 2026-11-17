"""settings/launcher.json: the spawner-owned transports. No browser."""
import json
import pathlib

LAUNCHER = json.loads((pathlib.Path(__file__).resolve().parent.parent
                       / "settings" / "launcher.json").read_text())


def test_io_pipes_transport():
    t = LAUNCHER["launch"]["transports"]
    assert t["pipe"]["args"] == ["--remote-debugging-pipe"]
    io = t["io_pipes"]
    assert io["os"] == "windows"
    assert io["args"] == ["--remote-debugging-pipe",
                          "--remote-debugging-io-pipes={read},{write}"]
    assert not any("--remote-debugging-io-pipes" in a
                   for a in LAUNCHER["browser_argv_must_not_contain"])

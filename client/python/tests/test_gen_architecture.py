from camoucrome import gen


def test_macos_apple_gpu_claims_arm():
    for s in range(1, 41):
        c = gen.generate(os="macos", seed=s, gpu="macos-apple-m1-pro-metal")["config"]
        assert "Apple" in c["webGl:renderer"]
        assert (c["ua:architecture"], c["ua:bitness"]) == ("arm", "64"), s


def test_windows_claims_x86():
    for s in range(1, 41):
        c = gen.generate(os="windows", seed=s)["config"]
        assert (c["ua:architecture"], c["ua:bitness"]) == ("x86", "64"), s


def test_arch_fits():
    apple = {"renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)"}
    fp = lambda a: {"navigator": {"userAgentData": {"architecture": a}}}
    assert gen.arch_fits(fp("arm"), apple) and not gen.arch_fits(fp("x86"), apple)
    assert gen.arch_fits(fp("x86"), None) and gen.arch_fits(fp("x86"), {"renderer": "ANGLE (Intel, ...)"})

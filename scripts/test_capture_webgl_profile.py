import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import capture_webgl_profile as c

SW = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)"
D3D = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def ctx(renderer):
    return {"vendor": "Google Inc. (Intel)", "renderer": renderer,
            "parameters": {"3379": 16384}, "supportedExtensions": ["ANGLE_instanced_arrays"],
            "shaderPrecisionFormats": {"VERTEX_SHADER/HIGH_FLOAT": [127, 127, 23]},
            "contextAttributes": {"alpha": True}}


def test_swiftshader_is_refused():
    with pytest.raises(ValueError, match="SwiftShader"):
        c.profile_from_report({"webgl": ctx(SW), "webgl2": ctx(D3D)}, "x", "Windows", {})


def test_profile_shape():
    p = c.profile_from_report({"webgl": ctx(D3D), "webgl2": ctx(D3D)}, "windows-intel", "Windows", {"how": "test"})
    assert list(p) == ["id", "os", "vendor", "renderer", "webgl", "webgl2", "provenance"]
    assert p["renderer"] == D3D and p["webgl2"]["parameters"] == {"3379": 16384}
    assert "37445" not in p["webgl"]["parameters"] and "37446" not in p["webgl"]["parameters"]


def test_page_enumerates_every_numeric_pname_by_name():
    assert "MAX_TEXTURE_SIZE" in c.PAGE and "MAX_3D_TEXTURE_SIZE" in c.PAGE
    assert "UNMASKED_RENDERER_WEBGL" in c.PAGE

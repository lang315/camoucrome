import gen_gpu_pool as g

GEN9 = {0x3E92, 0x3E9B, 0x9BC5, 0x5917}

def test_keeps_only_gen9_device_ids_and_the_exact_shape():
    counts = {
        "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E9B) Direct3D11 vs_5_0 ps_5_0, D3D11)": 30,
        "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00005917) Direct3D11 vs_5_0 ps_5_0, D3D11)": 10,
        "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)": 50,
        "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E9B) Direct3D11 vs_5_0 ps_5_0, D3D11) extra": 5,
    }
    pool = g.pool_from_counts(counts, GEN9)
    assert [r["device_id"] for r in pool] == [0x3E9B, 0x5917]
    assert abs(sum(r["weight"] for r in pool) - 1) < 1e-9
    assert pool[0]["weight"] == 0.75

def test_device_ids_parsed_from_angle_driver_utils():
    src = "constexpr std::array<uint32_t, 3> CoffeeLake = {0x3E90, 0x3E92, 0x3E9B};\n" \
          "constexpr std::array<uint32_t, 1> Tigerlake = {0x9A49};\n"
    assert g.gen9_ids(src) == {0x3E90, 0x3E92, 0x3E9B}

def test_device_ids_parsed_from_c_array_form():
    src = "const uint16_t Skylake[] = {\n 0x1902, // skl_gt1\n 0x190A\n};\nconst uint16_t Broxton[] = {0x0A84};\n"
    assert g.gen9_ids(src) == {0x1902, 0x190A}

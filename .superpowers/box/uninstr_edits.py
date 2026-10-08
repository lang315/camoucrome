WGL = "third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc"
EDITS = [
    ("replace", WGL, '  int64_t t_us[4] = {0, 0, 0, 0};\n  base::TimeTicks mark = base::TimeTicks::Now();\n  auto lap = [&](int i) {\n    const base::TimeTicks n = base::TimeTicks::Now();\n    t_us[i] = (n - mark).InMicroseconds();\n    mark = n;\n  };\n  using Scratch = std::unique_ptr<uint8_t, void (*)(void*)>;\n', '  using Scratch = std::unique_ptr<uint8_t, void (*)(void*)>;\n', 1),
    ("replace", WGL, '    lap(0);\n    std::ranges::fill(a, uint8_t{0x00});\n', '    std::ranges::fill(a, uint8_t{0x00});\n', 1),
    ("replace", WGL, '    lap(1);\n    auto agree = [&](size_t r, size_t c) {\n', '    auto agree = [&](size_t r, size_t c) {\n', 1),
    ("replace", WGL, "  lap(2);\n  // The page rect's part inside the framebuffer.\n", "  // The page rect's part inside the framebuffer.\n", 1),
    ("replace", WGL, '    camoucfg::PerturbRgbaFromConfig(page.data(), in_w, in_h, row_bytes, scope);\n    lap(3);\n    for (int i = 0; i < 4; ++i) {\n      const uint32_t v = static_cast<uint32_t>(t_us[i]);\n      UNSAFE_BUFFERS(std::memcpy(data + 4 * i, &v, 4));\n    }\n    return;\n', '    camoucfg::PerturbRgbaFromConfig(page.data(), in_w, in_h, row_bytes, scope);\n    return;\n', 1),
]

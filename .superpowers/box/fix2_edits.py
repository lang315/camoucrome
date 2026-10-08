WGL = "third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc"
EDITS = [
    ("replace", WGL,
     "    std::ranges::fill(a, uint8_t{0x00});\n"
     "    std::ranges::fill(b, uint8_t{0xFF});\n",
     "    // `a` is zero from the allocator. memset, not std::ranges::fill: over a\n"
     "    // span iterator the fill is a byte loop, and it ran in tens of ms on a\n"
     "    // 4 MB probe.\n"
     "    UNSAFE_BUFFERS(std::memset(b.data(), 0xFF, b.size()));\n", 1),
]

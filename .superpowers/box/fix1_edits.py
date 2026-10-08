WGL = "third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc"
WGLH = "third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.h"

DECL_OLD = '''  // Camoucrome canvas noise S2c: noises a finished RGBA / UNSIGNED_BYTE
  // readPixels of [x, x + width) x [y, y + height) held in `data` at the
  // page's pack layout, from the default framebuffer or a page `framebuffer`.
  void CamouNoiseReadPixels(WebGLFramebuffer* framebuffer,
                            GLint x,
                            GLint y,
                            GLsizei width,
                            GLsizei height,
                            uint8_t* data);
'''

PRIV_OLD = '''  static std::unique_ptr<WebGraphicsContext3DProvider>
  CreateContextProviderInternal(CanvasRenderingContextHost*,'''
PRIV_NEW = DECL_OLD + PRIV_OLD

HOOK = '''
  // Camoucrome: perturb the JS-visible readPixels buffer at readback, for
  // the fingerprint-relevant RGBA / UNSIGNED_BYTE case only (other formats
  // and the zero-pixel throwaway path in `buffer` are untouched). A read from
  // a page framebuffer is noised by the same rule as the default one (canvas
  // noise S2c): rendering into a framebuffer and reading it back does not
  // return the clean render. No-op when canvas:seed is unset. A default
  // framebuffer with READ_BUFFER NONE has nothing to read: GL rejects the
  // call and leaves `data` as the page left it, so nothing is noised.
  //
  // KNOWN GAP (documented, not covered here): the WebGL2 readPixels
  // overload that targets a bound PIXEL_PACK_BUFFER writes to GPU memory,
  // so a later getBufferSubData() returns those pixels un-noised (SP3 7.4).
  if (!buffer && format == GL_RGBA && type == GL_UNSIGNED_BYTE && width > 0 &&
      height > 0 &&
      (framebuffer || read_buffer_of_default_framebuffer_ != GL_NONE)) {
    if (auto* ec = Host()->GetTopExecutionContext();
        ec && camoucfg::CanvasSeed(camoucfg::ScopeFor(ec)) != 0) {
      CamouNoiseReadPixels(framebuffer, x, y, width, height, data);
    }
  }
}

void WebGLRenderingContextBase::CamouNoiseReadPixels(
    WebGLFramebuffer* framebuffer,
    GLint x,
    GLint y,
    GLsizei width,
    GLsizei height,
    uint8_t* data) {
  // The page buffer's layout (PACK_ALIGNMENT; in WebGL2 also PACK_ROW_LENGTH,
  // SKIP_PIXELS and SKIP_ROWS). readPixels validated the destination
  // against it.
  const WebGLImageConversion::PixelStoreParams pack = GetPackPixelStoreParams();
  const int64_t stride_px = pack.row_length > 0 ? pack.row_length : width;
  const int64_t align = std::max<int64_t>(pack.alignment, 1);
  const size_t row_bytes =
      static_cast<size_t>((stride_px * 4 + align - 1) / align * align);
  // GL rejects (INVALID_OPERATION, nothing written) a layout where the
  // skipped pixels plus the rect do not fit one row.
  if (int64_t{pack.skip_pixels} + width > stride_px) {
    return;
  }
  // The rect plus a 1 px margin, in framebuffer coordinates: an edge pixel's
  // neighbours come from the framebuffer, not from the rect (S2b).
  const int64_t ex0 = int64_t{x} - 1;
  const int64_t ey0 = int64_t{y} - 1;
  const int64_t ex1 = int64_t{x} + width + 1;
  const int64_t ey1 = int64_t{y} + height + 1;
  if (ex0 < std::numeric_limits<GLint>::min() ||
      ey0 < std::numeric_limits<GLint>::min() ||
      ex1 > std::numeric_limits<GLint>::max() ||
      ey1 > std::numeric_limits<GLint>::max()) {
    return;
  }
  const camoucfg::ConfigScope& scope =
      camoucfg::ScopeFor(Host()->GetTopExecutionContext());
  using Scratch = std::unique_ptr<uint8_t, void (*)(void*)>;
  // A fallible, zeroed tight RGBA buffer: a failed allocation leaves the read
  // stock.
  auto alloc = [](int64_t w, int64_t h) {
    base::CheckedNumeric<size_t> n = static_cast<size_t>(w);
    n *= static_cast<size_t>(h);
    n *= 4;
    void* raw = nullptr;
    if (n.IsValid()) {
      raw = Partitions::BufferTryAlignedZeroedMalloc(n.ValueOrDie(), 16,
                                                     "CamouNoiseScratch");
    }
    return Scratch(static_cast<uint8_t*>(raw), &Partitions::BufferAlignedFree);
  };
  // [rx0, rx1) x [ry0, ry1) of the read framebuffer, tight and bottom-up. A
  // true return means the binding worked, not that GL wrote `out`: a rejected
  // read (an unsupported format, a lost context) leaves it as it was, so the
  // caller must be able to tell (the page framebuffer path by its fills, the
  // default one by comparing with the page's own read).
  auto read = [&](int64_t rx0, int64_t ry0, int64_t rx1, int64_t ry1,
                  uint8_t* out) {
    ScopedDrawingBufferBinder binder(GetDrawingBuffer(), framebuffer);
    if (!binder.Succeeded()) {
      return false;
    }
    gpu::gles2::GLES2Interface* gl = ContextGL();
    gl->PixelStorei(GL_PACK_ALIGNMENT, 1);
    if (IsWebGL2()) {
      gl->PixelStorei(GL_PACK_ROW_LENGTH, 0);
      gl->PixelStorei(GL_PACK_SKIP_ROWS, 0);
      gl->PixelStorei(GL_PACK_SKIP_PIXELS, 0);
    }
    gl->ReadPixels(static_cast<GLint>(rx0), static_cast<GLint>(ry0),
                   static_cast<GLsizei>(rx1 - rx0),
                   static_cast<GLsizei>(ry1 - ry0), GL_RGBA, GL_UNSIGNED_BYTE,
                   out);
    DrawingBufferClientRestorePixelPackParameters();
    return true;
  };
  const size_t ew = static_cast<size_t>(ex1 - ex0);
  const size_t eh = static_cast<size_t>(ey1 - ey0);
  // The framebuffer's pixels inside the expanded rect: [fx0, fx1) x [fy0, fy1).
  int64_t fx0, fy0, fx1, fy1;
  Scratch probe(nullptr, &Partitions::BufferAlignedFree);
  if (!framebuffer) {
    fx0 = std::max<int64_t>(ex0, 0);
    fy0 = std::max<int64_t>(ey0, 0);
    fx1 = std::min<int64_t>(ex1, drawingBufferWidth());
    fy1 = std::min<int64_t>(ey1, drawingBufferHeight());
  } else {
    // Blink does not track a page framebuffer's size. The expanded rect is
    // read twice, into buffers filled 0x00 and 0xFF: GL leaves a pixel
    // outside the framebuffer unwritten, so a pixel lies inside iff the two
    // reads agree.
    probe = alloc(ex1 - ex0, ey1 - ey0);
    Scratch other = alloc(ex1 - ex0, ey1 - ey0);
    if (!probe || !other) {
      return;
    }
    // SAFETY: both buffers hold ew * eh * 4 bytes.
    const base::span<uint8_t> a =
        UNSAFE_BUFFERS(base::span<uint8_t>(probe.get(), ew * eh * 4));
    const base::span<uint8_t> b =
        UNSAFE_BUFFERS(base::span<uint8_t>(other.get(), ew * eh * 4));
    std::ranges::fill(a, uint8_t{0x00});
    std::ranges::fill(b, uint8_t{0xFF});
    if (!read(ex0, ey0, ex1, ey1, a.data()) ||
        !read(ex0, ey0, ex1, ey1, b.data())) {
      return;
    }
    auto agree = [&](size_t r, size_t c) {
      const size_t o = (r * ew + c) * 4;
      return std::ranges::equal(a.subspan(o, 4u), b.subspan(o, 4u));
    };
    fx0 = ex1;
    fy0 = ey1;
    fx1 = ex0;
    fy1 = ey0;
    for (size_t r = 0; r < eh; ++r) {
      // The inside of a row is one run (the framebuffer is a rectangle):
      // scan in from both ends, so a row costs its outside margin and not
      // its width.
      size_t c0 = 0;
      while (c0 < ew && !agree(r, c0)) {
        ++c0;
      }
      if (c0 == ew) {
        continue;
      }
      size_t c1 = ew - 1;
      while (!agree(r, c1)) {
        --c1;
      }
      fx0 = std::min<int64_t>(fx0, ex0 + static_cast<int64_t>(c0));
      fy0 = std::min<int64_t>(fy0, ey0 + static_cast<int64_t>(r));
      fx1 = std::max<int64_t>(fx1, ex0 + static_cast<int64_t>(c1) + 1);
      fy1 = std::max<int64_t>(fy1, ey0 + static_cast<int64_t>(r) + 1);
    }
  }
  // The page rect's part inside the framebuffer.
  const int64_t ix0 = std::max<int64_t>(x, fx0);
  const int64_t iy0 = std::max<int64_t>(y, fy0);
  const int64_t ix1 = std::min<int64_t>(int64_t{x} + width, fx1);
  const int64_t iy1 = std::min<int64_t>(int64_t{y} + height, fy1);
  if (ix1 <= ix0 || iy1 <= iy0) {
    return;
  }
  const size_t in_w = static_cast<size_t>(ix1 - ix0);
  const size_t in_h = static_cast<size_t>(iy1 - iy0);
  const size_t offset =
      static_cast<size_t>(int64_t{pack.skip_rows} + (iy0 - y)) * row_bytes +
      static_cast<size_t>(int64_t{pack.skip_pixels} + (ix0 - x)) * 4;
  // SAFETY: readPixels validated the destination against this pack layout;
  // the in-framebuffer part spans these bytes from `offset`.
  const base::span<uint8_t> page = UNSAFE_BUFFERS(
      base::span<uint8_t>(data + offset, (in_h - 1) * row_bytes + in_w * 4));
  if (fx0 == ix0 && fy0 == iy0 && fx1 == ix1 && fy1 == iy1) {
    // No room for a margin on any side (a full read): the page buffer is
    // noised in place, with nothing more to read.
    camoucfg::PerturbRgbaFromConfig(page.data(), in_w, in_h, row_bytes, scope);
    return;
  }
  // Margins: the framebuffer's part of the expanded rect is noised, then the
  // rect's part is copied back. The default framebuffer is read once; a page
  // framebuffer reuses its probe read.
  const size_t fw = static_cast<size_t>(fx1 - fx0);
  const size_t fh = static_cast<size_t>(fy1 - fy0);
  Scratch region(nullptr, &Partitions::BufferAlignedFree);
  base::span<uint8_t> src;
  size_t src_rb;
  if (framebuffer) {
    // SAFETY: the probe holds ew * eh * 4 bytes.
    src = UNSAFE_BUFFERS(base::span<uint8_t>(probe.get(), ew * eh * 4))
              .subspan(static_cast<size_t>((fy0 - ey0) * static_cast<int64_t>(ew) +
                                           (fx0 - ex0)) * 4);
    src_rb = ew * 4;
  } else {
    region = alloc(fx1 - fx0, fy1 - fy0);
    if (!region || !read(fx0, fy0, fx1, fy1, region.get())) {
      return;
    }
    // SAFETY: the region holds fw * fh * 4 bytes.
    src = UNSAFE_BUFFERS(base::span<uint8_t>(region.get(), fw * fh * 4));
    src_rb = fw * 4;
    // The region must be what the page's own read returned: if GL rejected
    // or lost this read, the zeroed region would replace the page's pixels.
    for (size_t r = 0; r < in_h; ++r) {
      if (!std::ranges::equal(
              page.subspan(r * row_bytes, in_w * 4),
              src.subspan(static_cast<size_t>(iy0 - fy0 +
                                              static_cast<int64_t>(r)) *
                                  src_rb +
                              static_cast<size_t>(ix0 - fx0) * 4,
                          in_w * 4))) {
        return;
      }
    }
  }
  camoucfg::PerturbRgbaFromConfig(src.data(), fw, fh, src_rb, scope);
  for (size_t r = 0; r < in_h; ++r) {
    page.subspan(r * row_bytes, in_w * 4)
        .copy_from(src.subspan(
            static_cast<size_t>(iy0 - fy0 + static_cast<int64_t>(r)) * src_rb +
                static_cast<size_t>(ix0 - fx0) * 4,
            in_w * 4));
  }
}
'''

EDITS = [
    ("replace", WGLH, DECL_OLD, "", 1),
    ("replace", WGLH, PRIV_OLD, PRIV_NEW, 1),
    ("cut", WGL,
     "  // Camoucrome: perturb the JS-visible readPixels buffer at readback, for",
     "\n}\n\nvoid WebGLRenderingContextBase::RenderbufferStorageImpl("),
    ("replace", WGL,
     "type, data);\n  }\n\n\n}\n\nvoid WebGLRenderingContextBase::RenderbufferStorageImpl(",
     "type, data);\n  }\n" + HOOK + "\nvoid WebGLRenderingContextBase::RenderbufferStorageImpl(", 1),
    ("replace", WGL, '#include "base/process/memory.h"\n', "", 1),
    ("replace", WGL,
     '#include "third_party/blink/renderer/platform/wtf/cross_thread_functional.h"\n',
     '#include "third_party/blink/renderer/platform/wtf/allocator/partitions.h"\n'
     '#include "third_party/blink/renderer/platform/wtf/cross_thread_functional.h"\n', 1),
]

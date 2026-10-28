// dev-only; not part of the Chromium build; not in any GN target.
#ifndef SCRIPTS_MAC_CPP_UI_GFX_GEOMETRY_POINT_F_H_
#define SCRIPTS_MAC_CPP_UI_GFX_GEOMETRY_POINT_F_H_

namespace gfx {
class PointF {
 public:
  constexpr PointF() = default;
  constexpr PointF(float x, float y) : x_(x), y_(y) {}
  constexpr float x() const { return x_; }
  constexpr float y() const { return y_; }

 private:
  float x_ = 0, y_ = 0;
};
}  // namespace gfx

#endif

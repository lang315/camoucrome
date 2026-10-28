// dev-only; not part of the Chromium build; not in any GN target.
// Minimal stand-in for base::TimeDelta: microsecond int64, the ops the mouse
// tests use. Real base saturates; this does not.
#ifndef SCRIPTS_MAC_CPP_BASE_TIME_TIME_H_
#define SCRIPTS_MAC_CPP_BASE_TIME_TIME_H_

#include <cstdint>

namespace base {
class TimeDelta {
 public:
  constexpr TimeDelta() = default;
  static constexpr TimeDelta FromMicroseconds(int64_t us) { return TimeDelta(us); }
  constexpr int64_t InMicroseconds() const { return us_; }
  constexpr int64_t InMilliseconds() const { return us_ / 1000; }
  constexpr double InMillisecondsF() const { return static_cast<double>(us_) / 1000.0; }
  constexpr auto operator<=>(const TimeDelta&) const = default;
  constexpr TimeDelta operator-(TimeDelta o) const { return TimeDelta(us_ - o.us_); }
  constexpr TimeDelta operator+(TimeDelta o) const { return TimeDelta(us_ + o.us_); }

 private:
  explicit constexpr TimeDelta(int64_t us) : us_(us) {}
  int64_t us_ = 0;
};
template <typename T>
constexpr TimeDelta Milliseconds(T ms) {
  return TimeDelta::FromMicroseconds(static_cast<int64_t>(ms * 1000));
}
}  // namespace base

#endif

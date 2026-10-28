// dev-only; not part of the Chromium build; not in any GN target.
// Tiny gtest stand-in: only what cursory_unittest.cc uses. Real gtest on the
// box compiles the same test file unchanged.
#ifndef SCRIPTS_MAC_CPP_GTEST_H_
#define SCRIPTS_MAC_CPP_GTEST_H_

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <sstream>
#include <string>
#include <vector>

namespace testing_shim {
struct Test {
  const char* suite;
  const char* name;
  void (*fn)();
};
inline std::vector<Test>& Registry() {
  static std::vector<Test> r;
  return r;
}
inline int& Failures() {
  static int f = 0;
  return f;
}
struct Registrar {
  Registrar(const char* s, const char* n, void (*f)()) { Registry().push_back({s, n, f}); }
};
// Collects the streamed message, reports on destruction.
struct Reporter {
  Reporter(const char* file, int line, const char* expr, bool fatal)
      : file_(file), line_(line), expr_(expr), fatal_(fatal) {}
  template <typename T>
  Reporter& operator<<(const T& v) {
    msg_ << v;
    return *this;
  }
  ~Reporter() {
    ++Failures();
    std::fprintf(stderr, "  %s:%d: failure: %s %s\n", file_, line_, expr_, msg_.str().c_str());
  }
  bool fatal() const { return fatal_; }
 private:
  const char* file_;
  int line_;
  const char* expr_;
  bool fatal_;
  std::ostringstream msg_;
};
// Lets `ASSERT_x(...) << msg` return from a void function.
struct Voidify {
  void operator&(const Reporter&) {}
};
}  // namespace testing_shim

#define TEST(suite, name)                                                        \
  static void suite##_##name##_Body();                                           \
  static testing_shim::Registrar suite##_##name##_reg(#suite, #name,             \
                                                      &suite##_##name##_Body);   \
  static void suite##_##name##_Body()

#define SHIM_EXPECT_(cond, text)                                                 \
  if (cond) {                                                                    \
  } else                                                                         \
    testing_shim::Reporter(__FILE__, __LINE__, text, false)

#define EXPECT_TRUE(c) SHIM_EXPECT_((c), "EXPECT_TRUE(" #c ")")
#define EXPECT_FALSE(c) SHIM_EXPECT_(!(c), "EXPECT_FALSE(" #c ")")
#define EXPECT_EQ(a, b) SHIM_EXPECT_((a) == (b), "EXPECT_EQ(" #a ", " #b ")")
#define EXPECT_NE(a, b) SHIM_EXPECT_((a) != (b), "EXPECT_NE(" #a ", " #b ")")
#define EXPECT_LT(a, b) SHIM_EXPECT_((a) < (b), "EXPECT_LT(" #a ", " #b ")")
#define EXPECT_LE(a, b) SHIM_EXPECT_((a) <= (b), "EXPECT_LE(" #a ", " #b ")")
#define EXPECT_GT(a, b) SHIM_EXPECT_((a) > (b), "EXPECT_GT(" #a ", " #b ")")
#define EXPECT_GE(a, b) SHIM_EXPECT_((a) >= (b), "EXPECT_GE(" #a ", " #b ")")
#define EXPECT_NEAR(a, b, tol) \
  SHIM_EXPECT_(std::fabs((double)(a) - (double)(b)) <= (tol), "EXPECT_NEAR(" #a ", " #b ")")

// ASSERT_*: a failed check returns from the (void) test body.
#define SHIM_ASSERT_(cond, text) \
  if (cond) {                    \
  } else                         \
    return testing_shim::Voidify() & testing_shim::Reporter(__FILE__, __LINE__, text, true)
#define ASSERT_TRUE(c) SHIM_ASSERT_((c), "ASSERT_TRUE(" #c ")")
#define ASSERT_FALSE(c) SHIM_ASSERT_(!(c), "ASSERT_FALSE(" #c ")")
#define ASSERT_EQ(a, b) SHIM_ASSERT_((a) == (b), "ASSERT_EQ(" #a ", " #b ")")
#define ASSERT_NE(a, b) SHIM_ASSERT_((a) != (b), "ASSERT_NE(" #a ", " #b ")")
#define ASSERT_LT(a, b) SHIM_ASSERT_((a) < (b), "ASSERT_LT(" #a ", " #b ")")
#define ASSERT_LE(a, b) SHIM_ASSERT_((a) <= (b), "ASSERT_LE(" #a ", " #b ")")
#define ASSERT_GT(a, b) SHIM_ASSERT_((a) > (b), "ASSERT_GT(" #a ", " #b ")")
#define ASSERT_GE(a, b) SHIM_ASSERT_((a) >= (b), "ASSERT_GE(" #a ", " #b ")")

int main() {
  int failed_tests = 0;
  for (const auto& t : testing_shim::Registry()) {
    const int before = testing_shim::Failures();
    t.fn();
    const bool ok = testing_shim::Failures() == before;
    std::printf("[%s] %s.%s\n", ok ? "PASS" : "FAIL", t.suite, t.name);
    if (!ok) ++failed_tests;
  }
  std::printf("%zu tests, %d failed\n", testing_shim::Registry().size(), failed_tests);
  return failed_tests ? 1 : 0;
}

#endif

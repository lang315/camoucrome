// dev-only; not part of the Chromium build; not in any GN target.
#ifndef SCRIPTS_MAC_CPP_BASE_CHECK_OP_H_
#define SCRIPTS_MAC_CPP_BASE_CHECK_OP_H_

#include <cstdio>
#include <cstdlib>

#define CHECK_GE(a, b)                                              \
  do {                                                              \
    if (!((a) >= (b))) {                                            \
      std::fprintf(stderr, "CHECK_GE(%s, %s) failed\n", #a, #b);    \
      std::abort();                                                 \
    }                                                               \
  } while (0)

#endif

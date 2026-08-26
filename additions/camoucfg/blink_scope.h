// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_BLINK_SCOPE_H_
#define COMPONENTS_CAMOUCFG_BLINK_SCOPE_H_

#include "components/camoucfg/mask_config.h"

namespace blink {
class ExecutionContext;
}

namespace camoucfg {

// Resolves a Blink execution context to the configuration it should read.
//
// Today every context resolves to the one process-global configuration, and
// the argument is ignored. This function is the single place that changes
// when a per-context store is introduced; no call site moves. It is declared
// here rather than inside Blink so that a Blink call site needs exactly one
// include.
inline const ConfigScope& ScopeFor(blink::ExecutionContext*) {
  return GlobalScope();
}

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_BLINK_SCOPE_H_

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_PRESET_LOADER_H_
#define COMPONENTS_CAMOUCFG_PRESET_LOADER_H_

#include "base/values.h"

namespace camoucfg {

// Expands a preset -- the minimum identifying set of a captured device,
// settings/presets/*.json -- into configuration keys. Pure: the preset in,
// the keys out; the table of which field becomes which key is at the top of
// preset_loader.cc, together with the list of what is deliberately NOT
// emitted. Fields the table does not name (provenance, dpr, sampleRate) are
// ignored.
//
// `fork_milestone` is the running build's Chromium major version. A preset
// whose `milestone` differs, or is missing, logs one warning; nothing is
// rewritten because no version-bearing field is ever taken from a preset.
base::DictValue ExpandPreset(const base::DictValue& preset, int fork_milestone);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_PRESET_LOADER_H_

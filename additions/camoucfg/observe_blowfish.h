// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_OBSERVE_BLOWFISH_H_
#define COMPONENTS_CAMOUCFG_OBSERVE_BLOWFISH_H_

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

#include "base/values.h"

namespace camoucfg::observe {

// Generated (observe_blowfish_init.cc): the hex digits of pi.
extern const uint32_t kBlowfishInitP[18];
extern const uint32_t kBlowfishInitS[4][256];

// One ECB block, big-endian; for the standard test vectors.
uint64_t BlowfishEncryptBlock(std::string_view key, uint64_t block);
// Blowfish-CBC decryption; nullopt unless `cipher` is whole 8-byte blocks.
std::optional<std::string> BlowfishCbcDecrypt(std::string_view key,
                                              std::string_view iv8,
                                              std::string_view cipher);
// sites/facebook.decode_sjd(): base64 of Blowfish-CBC of zero-padded JSON; the
// key is asid[19:23] + asid[24:36], the IV key[0:8] XOR key[8:16]. A dict of
// lists, else nullopt.
std::optional<base::DictValue> DecodeSjd(const base::DictValue& event);

}  // namespace camoucfg::observe

#endif  // COMPONENTS_CAMOUCFG_OBSERVE_BLOWFISH_H_

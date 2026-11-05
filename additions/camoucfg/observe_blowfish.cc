// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Bit-twiddling over fixed tables and byte frames; bounds are checked by hand.
#pragma allow_unsafe_buffers

#include "components/camoucfg/observe_blowfish.h"

#include <algorithm>
#include <cstring>
#include <utility>

#include "base/check.h"
#include "base/json/json_reader.h"
#include "base/strings/string_util.h"
#include "components/camoucfg/observe_leaf.h"

namespace camoucfg::observe {

namespace {

class Blowfish {
 public:
  explicit Blowfish(std::string_view key) {
    CHECK(!key.empty());
    std::copy(std::begin(kBlowfishInitP), std::end(kBlowfishInitP), p_);
    std::memcpy(s_, kBlowfishInitS, sizeof(s_));
    size_t j = 0;
    for (uint32_t& p : p_) {
      uint32_t word = 0;
      for (int k = 0; k < 4; ++k) {
        word = (word << 8) | static_cast<uint8_t>(key[j]);
        j = (j + 1) % key.size();
      }
      p ^= word;
    }
    uint32_t l = 0, r = 0;
    for (int i = 0; i < 18; i += 2) {
      Encrypt(l, r);
      p_[i] = l;
      p_[i + 1] = r;
    }
    for (auto& box : s_) {
      for (int i = 0; i < 256; i += 2) {
        Encrypt(l, r);
        box[i] = l;
        box[i + 1] = r;
      }
    }
  }

  void Encrypt(uint32_t& l, uint32_t& r) const {
    for (int i = 0; i < 16; ++i) {
      l ^= p_[i];
      r ^= F(l);
      std::swap(l, r);
    }
    std::swap(l, r);
    r ^= p_[16];
    l ^= p_[17];
  }

  void Decrypt(uint32_t& l, uint32_t& r) const {
    for (int i = 17; i > 1; --i) {
      l ^= p_[i];
      r ^= F(l);
      std::swap(l, r);
    }
    std::swap(l, r);
    r ^= p_[1];
    l ^= p_[0];
  }

 private:
  uint32_t F(uint32_t x) const {
    return ((s_[0][x >> 24] + s_[1][(x >> 16) & 0xFF]) ^ s_[2][(x >> 8) & 0xFF]) +
           s_[3][x & 0xFF];
  }

  uint32_t p_[18];
  uint32_t s_[4][256];
};

uint32_t Load32(const char* p) {
  return (uint32_t{static_cast<uint8_t>(p[0])} << 24) |
         (uint32_t{static_cast<uint8_t>(p[1])} << 16) |
         (uint32_t{static_cast<uint8_t>(p[2])} << 8) |
         uint32_t{static_cast<uint8_t>(p[3])};
}

void Store32(char* p, uint32_t v) {
  p[0] = static_cast<char>(v >> 24);
  p[1] = static_cast<char>(v >> 16);
  p[2] = static_cast<char>(v >> 8);
  p[3] = static_cast<char>(v);
}

}  // namespace

uint64_t BlowfishEncryptBlock(std::string_view key, uint64_t block) {
  uint32_t l = static_cast<uint32_t>(block >> 32);
  uint32_t r = static_cast<uint32_t>(block);
  Blowfish(key).Encrypt(l, r);
  return (uint64_t{l} << 32) | r;
}

std::optional<std::string> BlowfishCbcDecrypt(std::string_view key,
                                              std::string_view iv8,
                                              std::string_view cipher) {
  if (key.empty() || iv8.size() != 8 || cipher.size() % 8 != 0) {
    return std::nullopt;
  }
  const Blowfish bf(key);
  std::string out(cipher.size(), '\0');
  uint32_t pl = Load32(iv8.data()), pr = Load32(iv8.data() + 4);
  for (size_t i = 0; i < cipher.size(); i += 8) {
    const uint32_t cl = Load32(cipher.data() + i), cr = Load32(cipher.data() + i + 4);
    uint32_t l = cl, r = cr;
    bf.Decrypt(l, r);
    Store32(&out[i], l ^ pl);
    Store32(&out[i + 4], r ^ pr);
    pl = cl;
    pr = cr;
  }
  return out;
}

std::optional<base::DictValue> DecodeSjd(const base::DictValue& event) {
  const std::string* asid = event.FindString("asid");
  const std::string* sjd = event.FindString("sjd");
  // shortcut: a non-ASCII asid is refused; Python slices by code point and may
  // still decode one. Upgrade if a real asid is ever non-ASCII.
  if (!asid || !sjd || !base::IsStringASCII(*asid) || asid->size() < 36) {
    return std::nullopt;
  }
  const std::string key = asid->substr(19, 4) + asid->substr(24, 12);
  std::string iv(8, '\0');
  for (int i = 0; i < 8; ++i) {
    iv[i] = static_cast<char>(key[i] ^ key[i + 8]);
  }
  std::optional<std::string> cipher = B64DecodeStrict(*sjd);
  std::optional<std::string> plain =
      cipher ? BlowfishCbcDecrypt(key, iv, *cipher) : std::nullopt;
  if (!plain) {
    return std::nullopt;
  }
  const size_t end = plain->find_last_not_of('\0');
  plain->resize(end == std::string::npos ? 0 : end + 1);
  if (!IsUtf8(*plain)) {
    return std::nullopt;
  }
  std::optional<base::Value> doc = base::JSONReader::Read(*plain, base::JSON_PARSE_RFC);
  if (!doc || !doc->is_dict()) {
    return std::nullopt;
  }
  for (const auto [k, v] : doc->GetDict()) {
    if (!v.is_list()) {
      return std::nullopt;
    }
  }
  return std::move(*doc).TakeDict();
}

}  // namespace camoucfg::observe

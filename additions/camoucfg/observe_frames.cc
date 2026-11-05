// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Bit-twiddling over fixed tables and byte frames; bounds are checked by hand.
#pragma allow_unsafe_buffers

#include "components/camoucfg/observe_frames.h"

#include <algorithm>
#include <iterator>
#include <optional>
#include <tuple>
#include <utility>

#include "base/strings/stringprintf.h"
#include "components/camoucfg/observe_body.h"
#include "components/camoucfg/observe_leaf.h"

namespace camoucfg::observe {

namespace {

constexpr const char* kMqttTypes[16] = {
    nullptr,   "CONNECT", "CONNACK",     "PUBLISH",  "PUBACK", "PUBREC",
    "PUBREL",  "PUBCOMP", "SUBSCRIBE",   "SUBACK",   "UNSUBSCRIBE",
    "UNSUBACK", "PINGREQ", "PINGRESP",   "DISCONNECT", "AUTH"};
// The least body each type can have; a shorter one is not a packet (an empty
// CONNACK is the gateway's own byte pattern, not MQTT).
constexpr size_t kMqttMinBody[16] = {0, 10, 2, 2, 2, 2, 2, 2, 3, 3, 3, 2, 0, 0, 0, 0};

uint8_t At(std::string_view b, size_t i) {
  return static_cast<uint8_t>(b[i]);
}

// _varint(): (value, next index), or nullopt where Python raises.
std::optional<std::pair<size_t, size_t>> Varint(std::string_view b, size_t i) {
  size_t mult = 1, val = 0;
  while (true) {
    if (i >= b.size()) {
      return std::nullopt;
    }
    const uint8_t c = At(b, i++);
    val += (c & 127) * mult;
    if (!(c & 128)) {
      return std::make_pair(val, i);
    }
    mult *= 128;
    if (mult > 128 * 128 * 128) {
      return std::nullopt;
    }
  }
}

// _mstr(): a 2-byte big-endian length and that many bytes.
std::optional<std::pair<std::string_view, size_t>> MStr(std::string_view b, size_t i) {
  if (i + 2 > b.size()) {
    return std::nullopt;  // Python's short length prefix always fails its bounds check
  }
  const size_t n = (size_t{At(b, i)} << 8) | At(b, i + 1);
  if (i + 2 + n > b.size()) {
    return std::nullopt;
  }
  return std::make_pair(b.substr(i + 2, n), i + 2 + n);
}

// _packet()
std::optional<MqttPacket> Packet(int t, int flags, std::string_view body) {
  MqttPacket p{kMqttTypes[t], "", ""};
  if (t == 3) {
    auto topic = MStr(body, 0);
    if (!topic) {
      return std::nullopt;
    }
    size_t k = topic->second;
    if ((flags >> 1) & 3) {
      k += 2;  // the packet id
    }
    p.topic = Utf8Replace(topic->first);
    p.payload = k < body.size() ? std::string(body.substr(k)) : std::string();
  } else if (t == 1) {
    auto proto = MStr(body, 0);
    if (!proto || proto->second + 1 >= body.size()) {
      return std::nullopt;
    }
    const uint8_t cflags = At(body, proto->second + 1);
    auto client = MStr(body, proto->second + 4);
    if (!client) {
      return std::nullopt;
    }
    size_t k = client->second;
    if (cflags & 0x04) {
      auto will_topic = MStr(body, k);
      auto will_msg = will_topic ? MStr(body, will_topic->second) : std::nullopt;
      if (!will_msg) {
        return std::nullopt;
      }
      k = will_msg->second;
    }
    if (cflags & 0x80) {
      auto user = MStr(body, k);
      if (!user) {
        return std::nullopt;
      }
      p.payload = std::string(user->first);
    }
  }
  return p;
}

std::vector<Unit> MqttUnits(const std::string& key, const std::vector<MqttPacket>& pk) {
  std::vector<Unit> units;
  for (const MqttPacket& q : pk) {
    units.push_back({key + (q.topic.empty() ? q.type : q.topic),
                     Fields(q.payload, "", false, nullptr).fields});
  }
  return units;
}

// sites/facebook._embedded_json(): the JSON from the first '{' or '[' within
// the first 16 bytes to the end of p.
std::optional<std::pair<size_t, base::Value>> EmbeddedJson(std::string_view p) {
  for (size_t i = 0; i < std::min<size_t>(16, p.size()); ++i) {
    if (p[i] != '{' && p[i] != '[') {
      continue;
    }
    const std::string_view rest = p.substr(i);
    if (!IsUtf8(rest)) {
      continue;
    }
    if (std::optional<base::Value> j = ParseJsonContainer(rest)) {
      return std::make_pair(i, std::move(*j));
    }
  }
  return std::nullopt;
}

// sites/facebook._chunk_units()
std::pair<std::vector<Unit>, size_t> ChunkUnits(uint8_t b0, std::string_view payload) {
  const std::string key = base::StringPrintf("%02x/", b0);
  if (b0 == 0x0c && payload.size() <= 2) {
    return {{{key + "(ack)", {}}}, 0};  // an acknowledgement counter, not MQTT
  }
  // A type-0d chunk's payload starts 2 bytes before its JSON or MQTT.
  const std::string_view p = payload.substr(std::min<size_t>(b0 == 0x0d ? 2 : 0, payload.size()));
  std::vector<MqttPacket> pk;
  size_t partial = 0;
  if (!p.starts_with('{') && !p.starts_with('[')) {
    std::tie(pk, partial) = MqttParse(p);
  }
  if (!pk.empty() && !partial) {
    return {MqttUnits(key, pk), 0};
  }
  // Before a partial MQTT read: a binary header can look like a packet start.
  if (auto emb = EmbeddedJson(p)) {
    std::vector<Field> fields;
    Walker w{false, nullptr, &fields};
    w.Walk(emb->second, "", 0);
    return {{{key + (emb->first ? base::StringPrintf("(json+%zu)", emb->first) : "(json)"),
              std::move(fields)}},
            0};
  }
  if (!pk.empty()) {
    return {MqttUnits(key, pk), partial};
  }
  return {{{key + "(opaque)", {}}}, 0};
}

}  // namespace

std::pair<std::vector<MqttPacket>, size_t> MqttParse(std::string_view frame) {
  std::vector<MqttPacket> out;
  size_t i = 0;
  while (i < frame.size()) {
    const int t = At(frame, i) >> 4, flags = At(frame, i) & 15;
    if (t == 0) {
      break;
    }
    const auto len = Varint(frame, i + 1);
    if (!len) {
      break;
    }
    const auto [n, j] = *len;
    if (j + n > frame.size() || n < kMqttMinBody[t]) {
      break;
    }
    std::optional<MqttPacket> p = Packet(t, flags, frame.substr(j, n));
    if (!p) {
      break;
    }
    out.push_back(std::move(*p));
    i = j + n;
  }
  return {std::move(out), frame.size() - i};
}

std::pair<std::vector<std::pair<uint8_t, std::string_view>>, size_t> GatewayChunks(
    std::string_view raw) {
  std::vector<std::pair<uint8_t, std::string_view>> out;
  size_t i = 0;
  while (i + 6 <= raw.size() && At(raw, i) >= 0x0c && At(raw, i) <= 0x0f) {
    const size_t n = size_t{At(raw, i + 3)} | (size_t{At(raw, i + 4)} << 8) |
                     (size_t{At(raw, i + 5)} << 16);
    if (i + 6 + n > raw.size()) {
      break;
    }
    out.emplace_back(At(raw, i), raw.substr(i + 6, n));
    i += 6 + n;
  }
  return {std::move(out), raw.size() - i};
}

std::optional<std::pair<std::vector<Unit>, size_t>> BinaryUnits(std::string_view raw) {
  if (raw == std::string_view("\x09", 1) || raw == std::string_view("\x0a", 1)) {
    return std::make_pair(
        std::vector<Unit>{{base::StringPrintf("%02x/(single)", At(raw, 0)), {}}}, size_t{0});
  }
  auto [chunks, rest] = GatewayChunks(raw);
  if (chunks.empty()) {
    return std::nullopt;
  }
  std::vector<Unit> units;
  size_t partial = rest;
  for (const auto& [b0, payload] : chunks) {
    auto [u, n] = ChunkUnits(b0, payload);
    std::move(u.begin(), u.end(), std::back_inserter(units));
    partial += n;
  }
  if (rest) {
    units.push_back({"(partial)", {}});
  }
  return std::make_pair(std::move(units), partial);
}

std::pair<std::vector<Unit>, size_t> FrameUnits(int opcode, std::string_view raw) {
  if (opcode == 2) {
    if (auto got = BinaryUnits(raw)) {
      return std::move(*got);
    }
    auto [pk, partial] = MqttParse(raw);
    if (pk.empty()) {
      return {{{"(opaque)", {}}}, partial};
    }
    std::vector<Unit> units = MqttUnits("", pk);
    if (partial) {
      units.push_back({"(partial)", {}});
    }
    return {std::move(units), partial};
  }
  BodyFields f = Fields(raw, "", false, nullptr);
  return {{{f.kind != "opaque" ? "(text)" : "(opaque)", std::move(f.fields)}}, 0};
}

}  // namespace camoucfg::observe

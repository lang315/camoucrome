// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_OBSERVE_FRAMES_H_
#define COMPONENTS_CAMOUCFG_OBSERVE_FRAMES_H_

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "components/camoucfg/observe_leaf.h"

namespace camoucfg::observe {

// observe_drive.py _packet() result.
struct MqttPacket {
  std::string type;
  std::string topic;
  std::string payload;
};

// observe_drive.mqtt_parse(): the whole packets at the front of a frame and the
// bytes after them that are not one.
std::pair<std::vector<MqttPacket>, size_t> MqttParse(std::string_view frame);

// sites/facebook.gateway_chunks(): (type, payload) views into raw, and the rest.
std::pair<std::vector<std::pair<uint8_t, std::string_view>>, size_t>
GatewayChunks(std::string_view raw);

struct Unit {
  std::string topic;
  std::vector<Field> fields;
};

// sites/facebook.binary_units(): nullopt where Python returns None.
std::optional<std::pair<std::vector<Unit>, size_t>> BinaryUnits(
    std::string_view raw);

// observe_drive._frame_units(): (units, partial bytes) of one frame.
std::pair<std::vector<Unit>, size_t> FrameUnits(int opcode,
                                                std::string_view raw);

}  // namespace camoucfg::observe

#endif  // COMPONENTS_CAMOUCFG_OBSERVE_FRAMES_H_

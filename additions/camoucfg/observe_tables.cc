// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_tables.h"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "base/base64.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/strings/string_number_conversions.h"
#include "base/values.h"
#include "components/camoucfg/observe_body.h"
#include "components/camoucfg/observe_frames.h"
#include "components/camoucfg/observe_leaf.h"
#include "components/camoucfg/observe_match.h"
#include "third_party/perfetto/protos/perfetto/common/trace_stats.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/interned_data/interned_data.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/profiling/profile_common.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/trace.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/trace_packet.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/track_event/debug_annotation.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/track_event/track_event.pbzero.h"

namespace camoucfg::observe {

namespace {

namespace pb = perfetto::protos::pbzero;

constexpr std::string_view kCategories[] = {
    "disabled-by-default-camou.observe",
    "disabled-by-default-camou.observe.send"};

bool IsOurs(std::string_view category) {
  return std::find(std::begin(kCategories), std::end(kCategories), category) !=
         std::end(kCategories);
}

struct Event {
  std::string name;
  std::map<std::string, std::string> args;
};

struct Interned {
  std::map<uint64_t, std::string> names, annotation_names, categories, strings;
};

std::string Lookup(const std::map<uint64_t, std::string>& m, uint64_t iid) {
  auto it = m.find(iid);
  return it == m.end() ? std::string() : it->second;
}

// The trace walk. Never reads past the buffer: protozero's decoders stop at
// the first malformed field.
std::vector<Event> ParseTrace(base::span<const uint8_t> trace, int* lost) {
  std::vector<Event> events;
  std::map<uint32_t, Interned> seqs;
  pb::Trace_Decoder t(trace.data(), trace.size());
  for (auto it = t.packet(); it; ++it) {
    pb::TracePacket_Decoder p(*it);
    const uint32_t seq = p.trusted_packet_sequence_id();
    // The service marks the first packet of every sequence as dropped-before; that
    // is no loss. A packet that is not first on its sequence is.
    if (p.previous_packet_dropped() && !p.first_packet_on_sequence()) {
      ++*lost;
    }
    if (p.incremental_state_cleared() ||
        (p.sequence_flags() & pb::TracePacket::SEQ_INCREMENTAL_STATE_CLEARED)) {
      seqs[seq] = Interned();
    }
    Interned& in = seqs[seq];
    if (p.has_interned_data()) {
      pb::InternedData_Decoder d(p.interned_data());
      for (auto n = d.event_names(); n; ++n) {
        pb::EventName_Decoder e(*n);
        in.names[e.iid()] = e.name().ToStdString();
      }
      for (auto n = d.event_categories(); n; ++n) {
        pb::EventCategory_Decoder e(*n);
        in.categories[e.iid()] = e.name().ToStdString();
      }
      for (auto n = d.debug_annotation_names(); n; ++n) {
        pb::DebugAnnotationName_Decoder e(*n);
        in.annotation_names[e.iid()] = e.name().ToStdString();
      }
      for (auto n = d.debug_annotation_string_values(); n; ++n) {
        pb::InternedString_Decoder e(*n);
        in.strings[e.iid()] = e.str().ToStdString();
      }
    }
    if (!p.has_track_event()) {
      continue;
    }
    pb::TrackEvent_Decoder e(p.track_event());
    bool ours = false, any_category = false;
    for (auto c = e.categories(); c; ++c) {
      any_category = true;
      ours |= IsOurs((*c).ToStdStringView());
    }
    for (auto c = e.category_iids(); c; ++c) {
      any_category = true;
      ours |= IsOurs(Lookup(in.categories, *c));
    }
    if (any_category && !ours) {
      continue;
    }
    Event ev;
    ev.name = e.has_name() ? e.name().ToStdString()
                           : Lookup(in.names, e.name_iid());
    for (auto a = e.debug_annotations(); a; ++a) {
      pb::DebugAnnotation_Decoder d(*a);
      const std::string key = d.has_name()
                                  ? d.name().ToStdString()
                                  : Lookup(in.annotation_names, d.name_iid());
      std::string value;
      if (d.has_string_value()) {
        value = d.string_value().ToStdString();
      } else if (d.has_string_value_iid()) {
        value = Lookup(in.strings, d.string_value_iid());
      } else if (d.has_int_value()) {
        value = base::NumberToString(d.int_value());
      } else if (d.has_uint_value()) {
        value = base::NumberToString(d.uint_value());
      } else if (d.has_bool_value()) {
        value = d.bool_value() ? "true" : "false";
      } else if (d.has_double_value()) {
        value = base::NumberToString(d.double_value());
      }
      ev.args[key] = std::move(value);
    }
    events.push_back(std::move(ev));
  }
  return events;
}

using Args = std::map<std::string, std::string>;

std::string Arg(const Args& a, const char* key) {
  auto it = a.find(key);
  return it == a.end() ? std::string() : it->second;
}

std::optional<uint64_t> UintArg(const Args& a, const char* key) {
  uint64_t v = 0;
  if (!base::StringToUint64(Arg(a, key), &v)) {
    return std::nullopt;
  }
  return v;
}

bool CutArg(const Args& a) {
  const std::string c = Arg(a, "cut");
  return !c.empty() && c != "0";
}

// "frame", "site", "unattributed", or nullopt when the event belongs to
// another tab.
std::optional<std::string> Attribute(const Args& a, const TabKey& tab) {
  const std::string frame = Arg(a, "top_frame");
  if (!frame.empty()) {
    if (frame == tab.top_frame_id) {
      return "frame";
    }
    return std::nullopt;
  }
  std::string site = Arg(a, "top_site");
  if (site.empty()) {
    site = Arg(a, "site");
  }
  if (!site.empty()) {
    if (site == tab.top_site) {
      return "site";
    }
    return std::nullopt;
  }
  return "unattributed";
}

// a + b without wrapping (both are untrusted trace values).
uint64_t SatAdd(uint64_t a, uint64_t b) {
  return a > std::numeric_limits<uint64_t>::max() - b
             ? std::numeric_limits<uint64_t>::max()
             : a + b;
}

int Clamp(uint64_t v) {
  return static_cast<int>(
      std::min<uint64_t>(v, std::numeric_limits<int>::max()));
}

// Strings in a base::Value must be UTF-8 (ruling P9): replace, never crash.
std::string S(std::string_view s) {
  return Utf8Replace(s);
}

struct FieldAgg {
  int count = 0;
  std::map<std::string, int> classes;
  std::vector<std::string> samples;
  std::map<std::pair<std::string, std::string>, int> strong, weak;
  std::map<std::string, int> bools;
};

struct SendRow {
  std::string via, endpoint, topic, by;
  int count = 0, cut = 0, missing = 0, files = 0, partial = 0;
  uint64_t bytes = 0;
  int sjd_decoded = 0, sjd_failed = 0;
  std::map<std::string, int> kinds;
  std::map<std::string, FieldAgg> fields;
};

void AddFields(SendRow& row,
               const std::vector<Field>& fields,
               const base::DictValue& truth) {
  for (const Field& f : fields) {
    FieldAgg& agg = row.fields[f.first];
    ++agg.count;
    ++agg.classes[ValueClass(f.second)];
    const std::string shown = Display(f.second);
    if (agg.samples.size() < 3 &&
        std::find(agg.samples.begin(), agg.samples.end(), shown) ==
            agg.samples.end()) {
      agg.samples.push_back(shown);
    }
    for (const Hit& h : Match(f.second, truth)) {
      ++(h.weak ? agg.weak : agg.strong)[{h.surface, h.encoding}];
    }
    for (const std::string& s : BoolMatches(f.second, truth)) {
      ++agg.bools[s];
    }
  }
}

base::DictValue CountMap(const std::map<std::string, int>& m) {
  base::DictValue d;
  for (const auto& [k, v] : m) {
    d.Set(k, v);
  }
  return d;
}

base::ListValue HitList(
    const std::map<std::pair<std::string, std::string>, int>& m) {
  base::ListValue l;
  for (const auto& [k, v] : m) {
    base::DictValue d;
    d.Set("surface", S(k.first));
    d.Set("encoding", S(k.second));
    d.Set("count", v);
    l.Append(std::move(d));
  }
  return l;
}

// "host" of host[:port][/path]; an IPv6 literal keeps its brackets.
std::string HostOfEndpoint(std::string_view endpoint) {
  if (endpoint.starts_with('[')) {
    const size_t close = endpoint.find(']');
    if (close != std::string_view::npos) {
      return std::string(endpoint.substr(0, close + 1));
    }
  }
  return std::string(endpoint.substr(0, endpoint.find_first_of("/:")));
}

std::string HostOfSite(std::string_view site) {
  const size_t scheme = site.find("://");
  if (scheme != std::string_view::npos) {
    site.remove_prefix(scheme + 3);
  }
  return HostOfEndpoint(site);
}

}  // namespace

std::string DecodeTables(base::span<const uint8_t> trace,
                         base::span<const uint8_t> trace_stats,
                         std::string_view truth_json,
                         const TabKey& tab) {
  base::DictValue truth;
  bool truth_ok = false;
  if (auto parsed = base::JSONReader::ReadDict(truth_json, base::JSON_PARSE_RFC)) {
    truth = std::move(*parsed);
    truth_ok = true;
  }

  int lost_packets = 0;
  const std::vector<Event> events = ParseTrace(trace, &lost_packets);

  uint64_t lost = static_cast<uint64_t>(lost_packets);
  {
    pb::TraceStats_Decoder s(trace_stats.data(), trace_stats.size());
    for (auto b = s.buffer_stats(); b; ++b) {
      pb::TraceStats_BufferStats_Decoder bs(*b);
      lost += bs.chunks_overwritten() + bs.chunks_discarded() +
              bs.abi_violations() + bs.trace_writer_packet_loss();
    }
  }

  int self_reads = 0, cut = 0, body_cut = 0, missing = 0;

  struct Loader {
    bool has_http = false;
    Args http;
    std::map<uint64_t, std::map<uint64_t, std::string>> elements;
    std::set<uint64_t> files;
    bool cut = false;
  };
  std::map<uint64_t, Loader> loaders;
  std::map<std::tuple<std::string, std::string, std::string, std::string,
                      std::string>,
           int>
      reads;
  std::map<std::tuple<std::string, std::string, std::string, std::string>,
           SendRow>
      sends;
  auto row_for = [&sends](const std::string& via, const std::string& endpoint,
                          const std::string& topic,
                          const std::string& by) -> SendRow& {
    SendRow& r = sends[{via, endpoint, topic, by}];
    r.via = via;
    r.endpoint = endpoint;
    r.topic = topic;
    r.by = by;
    return r;
  };

  for (const Event& ev : events) {
    if (ev.name == "camou.send.http" || ev.name == "camou.send.body" ||
        ev.name == "camou.send.file") {
      const std::optional<uint64_t> id = UintArg(ev.args, "loader");
      if (!id || *id == 0) {
        continue;
      }
      Loader& l = loaders[*id];
      if (ev.name == "camou.send.http") {
        if (!l.has_http) {  // the first one wins
          l.has_http = true;
          l.http = ev.args;
        }
      } else if (ev.name == "camou.send.file") {
        if (auto e = UintArg(ev.args, "element")) {
          l.files.insert(*e);
        }
      } else {
        const auto e = UintArg(ev.args, "element");
        const auto off = UintArg(ev.args, "offset");
        std::string bytes;
        if (!e || !off ||
            !base::Base64Decode(Arg(ev.args, "b64"), &bytes)) {
          continue;  // a failed decode drops that fragment
        }
        // A repeated offset (a 307/308 re-read) is kept once.
        l.elements[*e].emplace(*off, std::move(bytes));
        l.cut |= CutArg(ev.args);
      }
    } else if (ev.name == "camou.send.ws") {
      const auto by = Attribute(ev.args, tab);
      std::string raw;
      if (!by) {
        continue;
      }
      if (!base::Base64Decode(Arg(ev.args, "b64"), &raw)) {
        ++missing;  // a message whose bytes could not be read
        continue;
      }
      const int opcode = Clamp(UintArg(ev.args, "opcode").value_or(2));
      auto [units, partial] = FrameUnits(opcode, raw);
      const uint64_t size = UintArg(ev.args, "size").value_or(raw.size());
      const bool was_cut = CutArg(ev.args);
      const std::string endpoint = Arg(ev.args, "endpoint");
      const char* kind = opcode == 1 ? "text" : "binary";
      if (was_cut) {
        ++cut;
      }
      if (units.empty()) {
        SendRow& r = row_for("ws", endpoint, "", *by);
        ++r.count;
        ++r.kinds[kind];
        r.bytes = SatAdd(r.bytes, size);
        r.cut += was_cut;
        r.partial += Clamp(partial);
        continue;
      }
      for (size_t i = 0; i < units.size(); ++i) {
        SendRow& r = row_for("ws", endpoint, units[i].topic, *by);
        ++r.count;
        ++r.kinds[kind];
        if (i == 0) {  // message-level numbers go on the first unit only
          r.bytes = SatAdd(r.bytes, size);
          r.cut += was_cut;
          r.partial += Clamp(partial);
        }
        AddFields(r, units[i].fields, truth);
      }
    } else if (ev.args.count("origin") &&
               ev.name.rfind("camou.send.", 0) != 0) {
      if (Arg(ev.args, "origin") == "chrome://observer") {
        ++self_reads;
        continue;
      }
      const auto by = Attribute(ev.args, tab);
      if (!by) {
        continue;
      }
      ++reads[{Arg(ev.args, "site"), ev.name, Arg(ev.args, "origin"),
               Arg(ev.args, "script"), *by}];
    }
  }

  for (const auto& [id, l] : loaders) {
    if (!l.has_http) {
      continue;  // a body with no request is ignored
    }
    const auto by = Attribute(l.http, tab);
    if (!by) {
      continue;
    }
    // Fragments must tile each element from offset 0, and the elements seen
    // (bytes or file) must be exactly 0..elements-1; any hole means the trace
    // lost a fragment, and a spliced body is never decoded.
    std::string body;
    bool gap = false;
    for (const auto& [index, frags] : l.elements) {
      uint64_t next = 0;
      for (const auto& [offset, bytes] : frags) {
        gap |= offset != next;
        next = SatAdd(offset, bytes.size());
        body += bytes;
      }
    }
    const uint64_t elements = UintArg(l.http, "elements").value_or(0);
    if (elements > 0) {
      std::set<uint64_t> seen(l.files);
      for (const auto& [index, frags] : l.elements) {
        seen.insert(index);
      }
      gap |= seen.size() != elements || (!seen.empty() && *seen.rbegin() >= elements);
    }
    if (body.empty() && l.files.empty() && elements == 0) {
      continue;  // no body at all
    }
    SendRow& r = row_for("http", Arg(l.http, "endpoint"), "", *by);
    ++r.count;
    r.files += static_cast<int>(l.files.size());
    if (l.cut) {
      ++r.cut;
      ++cut;
    }
    if (body.empty()) {
      if (l.files.empty()) {
        ++r.missing;
        ++missing;
        ++r.kinds["missing"];
      } else {
        ++r.kinds["file"];
      }
      continue;
    }
    if (gap) {
      ++r.partial;
      ++r.kinds["partial"];
      continue;
    }
    r.bytes = SatAdd(r.bytes, body.size());
    SjdStats sjd;
    BodyFields bf = Fields(body, Arg(l.http, "content_type"),
                           /*site_hooks=*/true, &sjd);
    ++r.kinds[bf.kind];
    if (bf.cut) {
      ++body_cut;
    }
    r.sjd_decoded += sjd.decoded;
    r.sjd_failed += sjd.failed;
    AddFields(r, bf.fields, truth);
  }

  // Reads: count descending, then member.
  struct ReadRow {
    std::string site, member, origin, script, by;
    int count;
  };
  std::vector<ReadRow> read_rows;
  for (const auto& [k, n] : reads) {
    read_rows.push_back({std::get<0>(k), std::get<1>(k), std::get<2>(k),
                         std::get<3>(k), std::get<4>(k), n});
  }
  std::stable_sort(read_rows.begin(), read_rows.end(),
                   [](const ReadRow& a, const ReadRow& b) {
                     if (a.count != b.count) return a.count > b.count;
                     return a.member < b.member;
                   });

  // Sends: the tab site's own hosts first (no compiled host list), then count
  // descending, then endpoint, topic.
  const std::string tab_host = HostOfSite(tab.top_site);
  auto own = [&tab_host](const SendRow* r) {
    if (tab_host.empty()) return false;
    const std::string h = HostOfEndpoint(r->endpoint);
    return h == tab_host ||
           (h.size() > tab_host.size() &&
            h.compare(h.size() - tab_host.size() - 1, std::string::npos,
                      "." + tab_host) == 0);
  };
  std::vector<const SendRow*> send_rows;
  for (const auto& [k, r] : sends) {
    send_rows.push_back(&r);
  }
  std::stable_sort(send_rows.begin(), send_rows.end(),
                   [&own](const SendRow* a, const SendRow* b) {
                     const bool oa = own(a), ob = own(b);
                     if (oa != ob) return oa;
                     if (a->count != b->count) return a->count > b->count;
                     if (a->endpoint != b->endpoint) {
                       return a->endpoint < b->endpoint;
                     }
                     return a->topic < b->topic;
                   });

  base::DictValue status;
  status.Set("events", Clamp(events.size()));
  status.Set("lost", Clamp(lost));
  status.Set("self_reads", self_reads);
  status.Set("cut", cut);
  status.Set("body_cut", body_cut);
  status.Set("missing", missing);
  status.Set("truth_ok", truth_ok);

  base::ListValue read_list;
  for (const ReadRow& r : read_rows) {
    base::DictValue d;
    d.Set("site", S(r.site));
    d.Set("member", S(r.member));
    d.Set("origin", S(r.origin));
    d.Set("script", S(r.script));
    d.Set("count", r.count);
    d.Set("by", r.by);
    read_list.Append(std::move(d));
  }

  base::ListValue send_list;
  for (const SendRow* r : send_rows) {
    base::DictValue d;
    d.Set("via", r->via);
    d.Set("endpoint", S(r->endpoint));
    d.Set("topic", S(r->topic));
    d.Set("by", r->by);
    d.Set("count", r->count);
    d.Set("bytes", Clamp(r->bytes));
    d.Set("kinds", CountMap(r->kinds));
    d.Set("cut", r->cut);
    d.Set("missing", r->missing);
    d.Set("files", r->files);
    d.Set("partial", r->partial);
    base::ListValue sjd;
    sjd.Append(r->sjd_decoded);
    sjd.Append(r->sjd_failed);
    d.Set("sjd", std::move(sjd));
    base::ListValue fields;
    for (const auto& [path, f] : r->fields) {
      base::DictValue fd;
      fd.Set("path", S(path));
      fd.Set("count", f.count);
      fd.Set("classes", CountMap(f.classes));
      base::ListValue samples;
      for (const std::string& s : f.samples) {
        samples.Append(S(s));
      }
      fd.Set("samples", std::move(samples));
      fd.Set("strong", HitList(f.strong));
      fd.Set("weak", HitList(f.weak));
      base::ListValue bools;
      for (const auto& [surface, n] : f.bools) {
        base::DictValue bd;
        bd.Set("surface", S(surface));
        bd.Set("count", n);
        bools.Append(std::move(bd));
      }
      fd.Set("bool", std::move(bools));
      fields.Append(std::move(fd));
    }
    d.Set("fields", std::move(fields));
    send_list.Append(std::move(d));
  }

  base::DictValue root;
  root.Set("status", std::move(status));
  root.Set("truth", std::move(truth));
  root.Set("reads", std::move(read_list));
  root.Set("sends", std::move(send_list));
  std::string out;
  base::JSONWriter::Write(base::Value(std::move(root)), &out);
  return out;
}

}  // namespace camoucfg::observe

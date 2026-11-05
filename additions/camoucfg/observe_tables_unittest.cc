// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/observe_tables.h"

#include <cstdint>
#include <limits>
#include <random>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "base/base64.h"
#include "base/json/json_reader.h"
#include "base/numerics/safe_conversions.h"
#include "base/timer/elapsed_timer.h"
#include "base/values.h"
#include "testing/gtest/include/gtest/gtest.h"
#include "third_party/perfetto/include/perfetto/protozero/scattered_heap_buffer.h"
#include "third_party/perfetto/protos/perfetto/common/trace_stats.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/interned_data/interned_data.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/trace.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/trace_packet.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/track_event/debug_annotation.pbzero.h"
#include "third_party/perfetto/protos/perfetto/trace/track_event/track_event.pbzero.h"

namespace camoucfg::observe {
namespace {

namespace pb = perfetto::protos::pbzero;

constexpr char kRead[] = "disabled-by-default-camou.observe";

class TraceBuilder {
 public:
  // One TRACE_EVENT_INSTANT-shaped packet; the name interned on `seq` as
  // Chrome does with StaticString names.
  TraceBuilder& Add(
      uint32_t seq,
      std::string_view name,
      std::vector<std::pair<std::string, std::string>> args,
      std::string_view category = "disabled-by-default-camou.observe.send") {
    auto* p = trace_->add_packet();
    p->set_trusted_packet_sequence_id(seq);
    if (seen_.insert(seq).second) {
      p->set_sequence_flags(pb::TracePacket::SEQ_INCREMENTAL_STATE_CLEARED);
      // As the service delivers a sequence start: dropped-before, and first.
      p->set_first_packet_on_sequence(true);
      p->set_previous_packet_dropped(true);
    }
    if (drop_next_) {
      p->set_previous_packet_dropped(true);
      drop_next_ = false;
    }
    const uint64_t iid = ++next_iid_;
    auto* interned = p->set_interned_data();
    auto* en = interned->add_event_names();
    en->set_iid(iid);
    en->set_name(name.data(), name.size());
    auto* ec = interned->add_event_categories();
    ec->set_iid(iid);
    ec->set_name(category.data(), category.size());
    auto* te = p->set_track_event();
    te->set_name_iid(iid);
    te->add_category_iids(iid);
    for (const auto& [k, v] : args) {
      auto* da = te->add_debug_annotations();
      da->set_name(k.data(), k.size());
      da->set_string_value(v.data(), v.size());
    }
    return *this;
  }
  TraceBuilder& Dropped() {
    drop_next_ = true;
    return *this;
  }
  std::vector<uint8_t> Bytes() { return trace_.SerializeAsArray(); }

 private:
  protozero::HeapBuffered<pb::Trace> trace_;
  std::set<uint32_t> seen_;
  uint64_t next_iid_ = 0;
  bool drop_next_ = false;
};

using Args = std::vector<std::pair<std::string, std::string>>;

base::DictValue Decode(const std::vector<uint8_t>& trace,
                       std::string_view truth = "{}",
                       TabKey tab = {"https://a.test", "TOKEN-A"},
                       const std::vector<uint8_t>& stats = {}) {
  auto d = base::JSONReader::ReadDict(DecodeTables(trace, stats, truth, tab),
                                      base::JSON_PARSE_RFC);
  EXPECT_TRUE(d.has_value());
  return d ? std::move(*d) : base::DictValue();
}

std::string B64(std::string_view s) {
  return base::Base64Encode(base::as_byte_span(s));
}

Args Http(const std::string& loader,
          const std::string& endpoint,
          const std::string& content_type,
          const std::string& top_frame,
          const std::string& elements,
          const std::string& top_site = "") {
  return {{"loader", loader},       {"endpoint", endpoint},
          {"method", "POST"},       {"content_type", content_type},
          {"top_site", top_site},   {"top_frame", top_frame},
          {"elements", elements}};
}

Args Body(const std::string& loader,
          const std::string& element,
          const std::string& offset,
          std::string_view bytes) {
  return {{"loader", loader},
          {"element", element},
          {"offset", offset},
          {"b64", B64(bytes)},
          {"cut", ""}};
}

const base::DictValue& SendRow(const base::DictValue& r, size_t i) {
  return (*r.FindList("sends"))[i].GetDict();
}

const base::DictValue* FindField(const base::DictValue& row,
                                 std::string_view path) {
  for (const auto& f : *row.FindList("fields")) {
    if (*f.GetDict().FindString("path") == path) {
      return &f.GetDict();
    }
  }
  return nullptr;
}

constexpr char kJson[] = "application/json";
constexpr char kBody[] = R"({"w":1517,"tz":"Pacific/Chatham"})";

TEST(ObserveTablesTest, ReadRowsFilteredBySiteAndCounted) {
  TraceBuilder b;
  auto read = [&](const char* site, const char* origin) {
    b.Add(1, "Screen.width",
          {{"origin", origin}, {"site", site}, {"script", "https://a.test/x.js"}},
          kRead);
  };
  for (int i = 0; i < 3; ++i) read("https://a.test", "https://a.test");
  read("https://b.test", "https://b.test");
  read("", "https://a.test");
  read("https://a.test", "chrome://observer");
  const base::DictValue r = Decode(b.Bytes());
  const base::ListValue& reads = *r.FindList("reads");
  ASSERT_EQ(reads.size(), 2u);
  EXPECT_EQ(*reads[0].GetDict().FindString("member"), "Screen.width");
  EXPECT_EQ(*reads[0].GetDict().FindInt("count"), 3);
  EXPECT_EQ(*reads[0].GetDict().FindString("by"), "site");
  EXPECT_EQ(*reads[1].GetDict().FindInt("count"), 1);
  EXPECT_EQ(*reads[1].GetDict().FindString("by"), "unattributed");
  EXPECT_EQ(*r.FindDict("status")->FindInt("self_reads"), 1);
}

TEST(ObserveTablesTest, HttpBodyAcrossFragmentsAndRedirectDedupe) {
  const std::string_view body = kBody;
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "1"));
  b.Add(1, "camou.send.body", Body("7", "0", "0", body.substr(0, 10)));
  b.Add(1, "camou.send.body", Body("7", "0", "10", body.substr(10)));
  // The 307 re-read repeats the first fragment.
  b.Add(1, "camou.send.body", Body("7", "0", "0", body.substr(0, 10)));
  const base::DictValue r = Decode(b.Bytes());
  ASSERT_EQ(r.FindList("sends")->size(), 1u);
  const base::DictValue& row = SendRow(r, 0);
  EXPECT_EQ(*row.FindString("via"), "http");
  EXPECT_EQ(*row.FindString("by"), "frame");
  EXPECT_EQ(*row.FindInt("count"), 1);
  EXPECT_EQ(*row.FindDict("kinds")->FindInt("json"), 1);
  const base::DictValue* w = FindField(row, "w");
  ASSERT_TRUE(w);
  EXPECT_EQ(*w->FindDict("classes")->FindInt("int"), 1);
  const base::DictValue* tz = FindField(row, "tz");
  ASSERT_TRUE(tz);
  EXPECT_EQ(*tz->FindDict("classes")->FindInt("str<15>"), 1);
}

TEST(ObserveTablesTest, FrameKeyBeatsSite) {
  TraceBuilder b;
  b.Add(1, "camou.send.http",
        Http("7", "a.test/s", kJson, "TOKEN-B", "1", "https://a.test"));
  b.Add(1, "camou.send.body", Body("7", "0", "0", kBody));
  EXPECT_TRUE(Decode(b.Bytes()).FindList("sends")->empty());
}

TEST(ObserveTablesTest, BodyWithoutRequestIsIgnored) {
  TraceBuilder b;
  b.Add(1, "camou.send.body", Body("9", "0", "0", kBody));
  b.Add(1, "camou.send.body", Body("9", "0", "10", kBody));
  const base::DictValue r = Decode(b.Bytes());
  EXPECT_TRUE(r.FindList("sends")->empty());
  EXPECT_EQ(*r.FindDict("status")->FindInt("missing"), 0);
}

TEST(ObserveTablesTest, RequestWithoutBodyIsMissing) {
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "1"));
  const base::DictValue r = Decode(b.Bytes());
  ASSERT_EQ(r.FindList("sends")->size(), 1u);
  const base::DictValue& row = SendRow(r, 0);
  EXPECT_EQ(*row.FindInt("missing"), 1);
  EXPECT_EQ(*row.FindDict("kinds")->FindInt("missing"), 1);
  EXPECT_EQ(*r.FindDict("status")->FindInt("missing"), 1);
}

TEST(ObserveTablesTest, FileElementIsCountedNotRead) {
  TraceBuilder b;
  b.Add(1, "camou.send.http",
        Http("7", "a.test/s", "application/x-www-form-urlencoded", "TOKEN-A",
             "2"));
  b.Add(1, "camou.send.body", Body("7", "0", "0", "a=1"));
  b.Add(1, "camou.send.file",
        {{"loader", "7"}, {"element", "1"}, {"size", "300"}});
  const base::DictValue r = Decode(b.Bytes());
  ASSERT_EQ(r.FindList("sends")->size(), 1u);
  const base::DictValue& row = SendRow(r, 0);
  EXPECT_EQ(*row.FindInt("files"), 1);
  EXPECT_EQ(*row.FindDict("kinds")->FindInt("form"), 1);
}

TEST(ObserveTablesTest, WsBinaryUnits) {
  const std::string payload = R"({"w":1517})";
  const std::string topic = "/t/x";
  std::string mqtt;
  mqtt += '\x30';  // PUBLISH, QoS 0
  mqtt += static_cast<char>(2 + topic.size() + payload.size());
  mqtt += '\0';
  mqtt += static_cast<char>(topic.size());
  mqtt += topic + payload;
  TraceBuilder b;
  b.Add(1, "camou.send.ws",
        {{"endpoint", "a.test/ws"},
         {"site", "https://a.test"},
         {"origin", "https://a.test"},
         {"script", ""},
         {"opcode", "2"},
         {"size", std::to_string(mqtt.size())},
         {"b64", B64(mqtt)},
         {"cut", ""}});
  const base::DictValue r = Decode(b.Bytes());
  ASSERT_EQ(r.FindList("sends")->size(), 1u);
  const base::DictValue& row = SendRow(r, 0);
  EXPECT_EQ(*row.FindString("via"), "ws");
  EXPECT_EQ(*row.FindString("topic"), topic);
  EXPECT_TRUE(FindField(row, "w"));
}

TEST(ObserveTablesTest, MatchesSplitStrongWeak) {
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "1"));
  b.Add(1, "camou.send.body", Body("7", "0", "0", R"({"w":1517,"c":12})"));
  const base::DictValue r =
      Decode(b.Bytes(),
             R"({"screen.width":1517,"navigator.hardwareConcurrency":12})");
  const base::DictValue& row = SendRow(r, 0);
  const base::DictValue* w = FindField(row, "w");
  const base::DictValue* c = FindField(row, "c");
  ASSERT_TRUE(w);
  ASSERT_TRUE(c);
  const base::ListValue& strong = *w->FindList("strong");
  ASSERT_EQ(strong.size(), 1u);
  EXPECT_EQ(*strong[0].GetDict().FindString("surface"), "screen.width");
  EXPECT_EQ(*strong[0].GetDict().FindString("encoding"), "exact");
  EXPECT_EQ(*strong[0].GetDict().FindInt("count"), 1);
  const base::ListValue& weak = *c->FindList("weak");
  ASSERT_EQ(weak.size(), 1u);
  EXPECT_EQ(*weak[0].GetDict().FindString("surface"),
            "navigator.hardwareConcurrency");
  EXPECT_EQ(*weak[0].GetDict().FindString("encoding"), "exact");
  EXPECT_TRUE(c->FindList("strong")->empty());
}

TEST(ObserveTablesTest, TabSiteFirst) {
  TraceBuilder b;
  for (int i = 0; i < 5; ++i) {
    const std::string id = std::to_string(10 + i);
    b.Add(1, "camou.send.http", Http(id, "b.test/x", kJson, "", "1"));
    b.Add(1, "camou.send.body", Body(id, "0", "0", kBody));
  }
  b.Add(1, "camou.send.http",
        Http("20", "www.a.test/y", kJson, "", "1", "https://a.test"));
  b.Add(1, "camou.send.body", Body("20", "0", "0", kBody));
  const base::DictValue r = Decode(b.Bytes());
  ASSERT_EQ(r.FindList("sends")->size(), 2u);
  EXPECT_EQ(*SendRow(r, 0).FindString("endpoint"), "www.a.test/y");
  EXPECT_EQ(*SendRow(r, 0).FindString("by"), "site");
  EXPECT_EQ(*SendRow(r, 1).FindString("endpoint"), "b.test/x");
  EXPECT_EQ(*SendRow(r, 1).FindInt("count"), 5);
}

TEST(ObserveTablesTest, LostCountsFromStatsAndDroppedFlag) {
  protozero::HeapBuffered<pb::TraceStats> stats;
  stats->add_buffer_stats()->set_chunks_overwritten(2);
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "1"));
  b.Dropped().Add(1, "camou.send.body", Body("7", "0", "0", kBody));
  const base::DictValue r = Decode(
      b.Bytes(), "{}", {"https://a.test", "TOKEN-A"}, stats.SerializeAsArray());
  EXPECT_EQ(*r.FindDict("status")->FindInt("lost"), 3);
}

TEST(ObserveTablesTest, BadTruthIsReported) {
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "1"));
  b.Add(1, "camou.send.body", Body("7", "0", "0", R"({"w":1517})"));
  const base::DictValue r = Decode(b.Bytes(), "not json");
  EXPECT_FALSE(*r.FindDict("status")->FindBool("truth_ok"));
  const base::DictValue* w = FindField(SendRow(r, 0), "w");
  ASSERT_TRUE(w);
  EXPECT_TRUE(w->FindList("strong")->empty());
  EXPECT_TRUE(w->FindList("weak")->empty());
}

TEST(ObserveTablesTest, InvalidUtf8InArgsStillGivesJson) {
  TraceBuilder b;
  b.Add(1, "Screen.width", {{"origin", "https://a.test"},
                            {"site", "https://a.test"},
                            {"script", "https://a.test/\xff\xfe.js"}},
        kRead);
  const base::DictValue r = Decode(b.Bytes());
  EXPECT_EQ(r.FindList("reads")->size(), 1u);
}

TEST(ObserveTablesTest, RandomBytesNeverCrash) {
  std::mt19937 rng(42);
  base::ElapsedTimer timer;
  for (int i = 0; i < 1000; ++i) {
    std::vector<uint8_t> buf(rng() % 4097);
    for (uint8_t& c : buf) {
      c = static_cast<uint8_t>(rng());
    }
    std::vector<uint8_t> stats(rng() % 64);
    for (uint8_t& c : stats) {
      c = static_cast<uint8_t>(rng());
    }
    auto d = base::JSONReader::ReadDict(
        DecodeTables(buf, stats, "{}", {"https://a.test", "TOKEN-A"}),
        base::JSON_PARSE_RFC);
    EXPECT_TRUE(d.has_value()) << "buffer " << i;
  }
  EXPECT_LT(timer.Elapsed().InSeconds(), 10);
}

Args WsArgs(const std::string& top_frame,
            const std::string& site,
            const std::string& b64,
            const std::string& size,
            const std::string& cut = "") {
  return {{"endpoint", "a.test/ws"}, {"top_frame", top_frame}, {"site", site},
          {"origin", site},          {"script", ""},           {"opcode", "1"},
          {"size", size},            {"b64", b64},             {"cut", cut}};
}

TEST(ObserveTablesTest, DroppedMiddleFragmentIsPartialNotDecoded) {
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "1"));
  b.Add(1, "camou.send.body", Body("7", "0", "0", std::string_view(kBody).substr(0, 10)));
  // bytes 10..19 never arrived
  b.Add(1, "camou.send.body", Body("7", "0", "20", std::string_view(kBody).substr(20)));
  const base::DictValue r = Decode(b.Bytes());
  ASSERT_EQ(r.FindList("sends")->size(), 1u);
  const base::DictValue& row = SendRow(r, 0);
  EXPECT_EQ(*row.FindInt("partial"), 1);
  EXPECT_EQ(*row.FindDict("kinds")->FindInt("partial"), 1);
  EXPECT_FALSE(row.FindDict("kinds")->contains("json"));
  EXPECT_TRUE(row.FindList("fields")->empty());
}

TEST(ObserveTablesTest, FragmentsNotStartingAtZeroArePartial) {
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "1"));
  b.Add(1, "camou.send.body", Body("7", "0", "10", std::string_view(kBody).substr(10)));
  const base::DictValue r = Decode(b.Bytes());
  EXPECT_EQ(*SendRow(r, 0).FindInt("partial"), 1);
  EXPECT_TRUE(SendRow(r, 0).FindList("fields")->empty());
}

TEST(ObserveTablesTest, MissingElementIsPartialNotDecoded) {
  TraceBuilder b;
  // Two elements announced, only element 0 arrived whole.
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "2"));
  b.Add(1, "camou.send.body", Body("7", "0", "0", kBody));
  const base::DictValue r = Decode(b.Bytes());
  EXPECT_EQ(*SendRow(r, 0).FindInt("partial"), 1);
  EXPECT_FALSE(SendRow(r, 0).FindDict("kinds")->contains("json"));
}

TEST(ObserveTablesTest, CutAndBodyCutAreSurfacedInStatus) {
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "1"));
  Args cut = Body("7", "0", "0", kBody);
  cut.back().second = "1";
  b.Add(1, "camou.send.body", cut);
  std::string many = "[";
  for (int i = 0; i < 6000; ++i) many += i ? ",1" : "1";
  many += "]";
  b.Add(1, "camou.send.http", Http("8", "a.test/s", kJson, "TOKEN-A", "1"));
  b.Add(1, "camou.send.body", Body("8", "0", "0", many));
  const base::DictValue r = Decode(b.Bytes());
  EXPECT_EQ(*r.FindDict("status")->FindInt("cut"), 1);
  EXPECT_EQ(*r.FindDict("status")->FindInt("body_cut"), 1);
}

TEST(ObserveTablesTest, WsFrameKeyBeatsSiteAndFailedB64IsMissing) {
  const std::string text = kBody;
  TraceBuilder b;
  // The frame key names another tab though the site is ours: not ours.
  b.Add(1, "camou.send.ws", WsArgs("TOKEN-B", "https://a.test", B64(text), "40"));
  EXPECT_TRUE(Decode(b.Bytes()).FindList("sends")->empty());
  // The frame key is ours though the site is not: attributed by frame.
  TraceBuilder c;
  c.Add(1, "camou.send.ws", WsArgs("TOKEN-A", "https://other.test", B64(text), "40"));
  const base::DictValue r = Decode(c.Bytes());
  ASSERT_EQ(r.FindList("sends")->size(), 1u);
  EXPECT_EQ(*SendRow(r, 0).FindString("by"), "frame");
  // Bytes that do not decode count as missing and make no row.
  TraceBuilder d;
  d.Add(1, "camou.send.ws", WsArgs("TOKEN-A", "https://a.test", "!!!", "40"));
  const base::DictValue m = Decode(d.Bytes());
  EXPECT_TRUE(m.FindList("sends")->empty());
  EXPECT_EQ(*m.FindDict("status")->FindInt("missing"), 1);
}

TEST(ObserveTablesTest, UntrustedSizeDoesNotWrapBytes) {
  TraceBuilder b;
  b.Add(1, "camou.send.ws",
        WsArgs("TOKEN-A", "https://a.test", B64("abc"), "18446744073709551615"));
  b.Add(1, "camou.send.ws", WsArgs("TOKEN-A", "https://a.test", B64("abc"), "2"));
  const base::DictValue r = Decode(b.Bytes());
  ASSERT_EQ(r.FindList("sends")->size(), 1u);
  EXPECT_EQ(*SendRow(r, 0).FindInt("bytes"), std::numeric_limits<int>::max());
}

TEST(ObserveTablesTest, Ipv6HostIsOwnHost) {
  TraceBuilder b;
  for (int i = 0; i < 5; ++i) {
    const std::string id = std::to_string(10 + i);
    b.Add(1, "camou.send.http", Http(id, "[::2]:80/y", kJson, "", "1", "http://[::1]:80"));
    b.Add(1, "camou.send.body", Body(id, "0", "0", kBody));
  }
  b.Add(1, "camou.send.http", Http("20", "[::1]:80/x", kJson, "", "1", "http://[::1]:80"));
  b.Add(1, "camou.send.body", Body("20", "0", "0", kBody));
  const base::DictValue r = Decode(b.Bytes(), "{}", {"http://[::1]:80", "TOKEN-A"});
  ASSERT_EQ(r.FindList("sends")->size(), 2u);
  EXPECT_EQ(*SendRow(r, 0).FindString("endpoint"), "[::1]:80/x");
}

TEST(ObserveTablesTest, MutatedValidTraceNeverCrashes) {
  TraceBuilder b;
  b.Add(1, "camou.send.http", Http("7", "a.test/s", kJson, "TOKEN-A", "2"));
  b.Add(1, "camou.send.body", Body("7", "0", "0", kBody));
  b.Add(1, "camou.send.file", {{"loader", "7"}, {"element", "1"}, {"size", "9"}});
  b.Add(1, "camou.send.ws", WsArgs("TOKEN-A", "https://a.test", B64(kBody), "40"));
  b.Add(1, "Screen.width",
        {{"origin", "https://a.test"}, {"site", "https://a.test"}, {"script", "x.js"}},
        kRead);
  const std::vector<uint8_t> good = b.Bytes();
  ASSERT_GT(good.size(), 100u);
  std::mt19937 rng(7);
  for (int i = 0; i < 2000; ++i) {
    std::vector<uint8_t> m = good;
    if (i % 4 == 0) {
      m.resize(rng() % m.size());  // truncation
    } else {
      for (int k = 0; k <= i % 3; ++k) {
        m[rng() % m.size()] ^= static_cast<uint8_t>(1u << (rng() % 8));
      }
    }
    auto d = base::JSONReader::ReadDict(
        DecodeTables(m, {}, "{}", {"https://a.test", "TOKEN-A"}), base::JSON_PARSE_RFC);
    ASSERT_TRUE(d.has_value()) << "mutation " << i;
  }
}

}  // namespace
}  // namespace camoucfg::observe

// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_OBSERVE_TABLES_H_
#define COMPONENTS_CAMOUCFG_OBSERVE_TABLES_H_

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

#include "base/containers/span.h"

namespace camoucfg::observe {

// ---------------------------------------------------------------------------
// The EVENT contract (the send hooks emit it; DecodeTables reads it).
//
// Category "disabled-by-default-camou.observe.send". Every arg is a string or
// an unsigned integer (a uint is read back as its decimal text). The read
// hooks stay in "disabled-by-default-camou.observe" and carry the string args
// origin, site, script; the event name is the member, with ".get" for getters
// (Screen.width.get, Navigator.hardwareConcurrency.get).
//
//   camou.send.http   one per request that has a body
//     loader        uint > 0, joins the events of one request
//     endpoint      host[:port]/path, no query
//     method        request method
//     content_type  Content-Type header value
//     top_site      net::SchemefulSite::Serialize() of the top-frame origin
//                   ("" if none)
//     top_frame     UnguessableToken::ToString() of the top frame id ("" if
//                   none)
//     elements      uint, the number of body elements
//   camou.send.body   one per fragment of a bytes element
//     loader, element (uint index), offset (uint, bytes into the element),
//     b64 (base64 of at most 16 KiB), cut (uint 1 on a fragment of an element
//     that lost bytes past the 256 KiB element cap; "1" or "" also accepted)
//     A 307/308 re-read repeats fragments with the same offsets: kept once.
//   camou.send.file   one per file element
//     loader, element, size (uint, the file's length; its bytes are not read)
//   camou.send.ws     one per WebSocket message
//     endpoint, site (top-level site, "" in a worker), origin, script,
//     opcode (uint, 1 text or 2 binary), size (uint, the whole message),
//     b64 (base64 of at most 256 KiB; one arg carries the whole message),
//     cut (uint 1 when the message was cut at that cap, else ""/0)
//
// A body event whose loader has no camou.send.http event is dropped (counted
// nowhere); an http event with elements > 0 and neither bytes nor file
// elements is "missing". Fragments over 16 KiB are never emitted.
// A request whose fragments do not tile each element from offset 0, or whose
// bytes and file elements are not exactly 0..elements-1, is "partial": its row
// counts it (kinds.partial, partial) and the body is not decoded.
// A send row's kinds map holds json, form, multipart, opaque (decoded bodies),
// text, binary (ws), file (only file elements, their bytes never read),
// missing and partial. A ws message whose b64 does not decode adds to
// status.missing and has no row.
//
// The output is the tables JSON the page renders (documented in
// docs/observer/README.md). status: events, lost (trace buffer wrap: stats
// counters plus packets after a drop), self_reads (the page's own canary
// reads of origin chrome://observer; 0 after a refresh means the hooks are
// blind), cut (loaders or messages with a cut flag), body_cut (the walker hit
// its field/depth limit or an inflate hit its cap), missing, truth_ok.
// There are seven Observe* suites in components/camoucfg.
// ---------------------------------------------------------------------------

// Every document the recorded tab committed while recording: a reload gives a
// new top frame token, the first commit after the initial about:blank a new
// site. Empty lists match only unattributed events.
struct TabKey {
  std::vector<std::string> top_sites;      // e.g. "https://a.test"
  std::vector<std::string> top_frame_ids;  // UnguessableToken::ToString()
};

// trace: a serialized perfetto Trace (the TracePacket stream). trace_stats: a
// serialized TraceStats (may be empty). truth_json: the recorded tab's real
// values. Returns the tables JSON. Never crashes on any bytes.
std::string DecodeTables(base::span<const uint8_t> trace,
                         base::span<const uint8_t> trace_stats,
                         std::string_view truth_json,
                         const TabKey& tab);

}  // namespace camoucfg::observe

#endif  // COMPONENTS_CAMOUCFG_OBSERVE_TABLES_H_

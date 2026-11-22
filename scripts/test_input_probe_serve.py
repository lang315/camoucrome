"""The probe page sends deltas; the harness's server must rebuild the whole log from them, drop one that does not continue it."""
import json
import tempfile
import unittest
import urllib.request

import measure_input_probes as M


def post(srv, d):
    req = urllib.request.Request("http://127.0.0.1:%d/result?arm=x&run=0" % srv.server_address[1], data=json.dumps(d).encode(), method="POST")
    return urllib.request.urlopen(req).read().decode()


class Serve(unittest.TestCase):
    def test_deltas_rebuild_the_log(self):
        with tempfile.TemporaryDirectory() as d:
            srv, st = M.serve(d)
            try:
                post(srv, {"meta": {"a": 1}, "evFrom": 0, "ev": [{"n": 0}, {"n": 1}], "rafFrom": 0, "raf": [[1, 1]]})
                post(srv, {"meta": {"a": 2}, "evFrom": 2, "ev": [{"n": 2}], "rafFrom": 1, "raf": [[2, 2], [3, 3]]})
                self.assertEqual([e["n"] for e in st.snap["ev"]], [0, 1, 2])
                self.assertEqual(len(st.snap["raf"]), 3)
                self.assertEqual(st.snap["meta"], {"a": 2})
                post(srv, {"meta": {}, "evFrom": 9, "ev": [{"n": 9}], "rafFrom": 3, "raf": []})   # a hole: dropped
                self.assertEqual(len(st.snap["ev"]), 3)
            finally:
                srv.shutdown()


if __name__ == "__main__":
    unittest.main()

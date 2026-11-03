import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_text_pixels as m  # noqa: E402


def cell(left=5, right=50, ascent=20, descent=4, bbox=(195, 230, 250, 254), probe=0, width=55.0):
    return {"m": {"width": width, "actualBoundingBoxLeft": left, "actualBoundingBoxRight": right,
                  "actualBoundingBoxAscent": ascent, "actualBoundingBoxDescent": descent},
            "bbox": None if bbox is None else list(bbox), "probe": probe}


def test_bbox_empty_is_none():
    assert m.bbox_from_alpha([0] * 12, 4, 3) is None


def test_bbox_single_pixel():
    a = [0] * 20
    a[2 * 5 + 3] = 255
    assert m.bbox_from_alpha(a, 5, 4) == (3, 2, 4, 3)


def test_bbox_row_of_two():
    a = [0] * 20
    a[1 * 5 + 1] = 1
    a[1 * 5 + 3] = 9
    assert m.bbox_from_alpha(a, 5, 4) == (1, 1, 4, 2)


def test_metric_box():
    mm = {"actualBoundingBoxLeft": 5, "actualBoundingBoxRight": 50.5,
          "actualBoundingBoxAscent": 20, "actualBoundingBoxDescent": 4}
    assert m.metric_box(mm, 200, 250) == (195, 230, 250.5, 254)


def test_visible_identical_is_empty():
    assert m.visible_cells({"a": cell()}, {"a": cell()}) == []


def test_visible_ascent_one_px_off():
    # metric ascent +1 with the pixel top unchanged: the edge delta moves by 1
    assert m.visible_cells({"a": cell()}, {"a": cell(ascent=21)}) == ["a"]
    assert m.visible_fields({"a": cell()}, {"a": cell(ascent=21)}) == {"ascent": ["a"]}


def test_visible_antialias_tolerance():
    assert m.visible_cells({"a": cell()}, {"a": cell(ascent=20.3)}) == []


def test_visible_width_probe_change():
    assert m.visible_fields({"a": cell()}, {"a": cell(probe=7)}) == {"probe": ["a"]}


def test_raw_hist_rounds_to_quarter_px():
    # ascent delta: pixel top 230 - metric top (250-20) = 0; with ascent 19.8 -> 230 - 230.2 = -0.2 -> -0.25
    cells = {"a": cell(), "b": cell(ascent=19.8), "c": cell(ascent=19.8), "d": cell(bbox=None)}
    assert m.raw_hist(cells, "ascent") == {0.0: 1, -0.25: 2}
    assert m.probe_summary({"a": cell(probe=0), "b": cell(probe=4), "c": cell(probe=9)}) == (0, 4, 9)


def test_moved_identical_is_empty():
    assert m.moved_cells({"a": cell()}, {"a": cell()}) == []


def test_moved_tiny_change():
    assert m.moved_cells({"a": cell()}, {"a": cell(width=55.0625)}) == ["a"]

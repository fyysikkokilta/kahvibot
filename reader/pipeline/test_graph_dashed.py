"""Regression: the dashed-line walk that wedged the reader for 21 h.

On 2026-09-15 kahvi-reader spun at 56 percent of a core in userspace with
readings frozen and the IPC loop never draining. The faulthandler dump put it in
`_dashed`, reached from `tick` -> `warm_graph` -> `render`, and the geometry
below -- the temperature polyline from that day's own readings -- reproduces it
exactly: `carry` converges to within half an ULP of `dash`, so `pos + step`
rounds back to `pos` and the walk stops advancing.

The points are the real ones, trimmed to the shortest prefix that still spins.
"""
from __future__ import annotations

import math
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.graph_recent import _dashed  # noqa: E402

DASH, GAP = 14, 9

# The temperature line from readings-2026-09.jsonl for 2026-09-16, as mapped to
# plot coordinates by _draw_level.
SPIN_PTS = [
    (661.1480034722222, 219.68),
    (662.5325520833334, 219.68),
    (663.7912326388889, 219.68),
    (665.0499131944445, 219.68),
    (666.3715277777778, 219.68),
    (667.0008680555555, 219.424),
    (667.6302083333333, 219.424),
    (668.8888888888889, 219.424),
    (669.5182291666667, 219.424),
    (674.23828125, 219.68),
    (675.5598958333334, 219.68),
    (676.8185763888888, 219.68),
    (677.4479166666666, 219.68),
    (678.0772569444445, 219.68),
    (679.3988715277778, 219.68),
    (680.0282118055555, 219.68),
    (681.3498263888889, 219.68),
    (682.6085069444445, 219.68),
    (683.9301215277777, 219.68),
    (684.5594618055555, 219.68),
    (685.1888020833334, 219.68),
    (685.8181423611112, 219.68),
    (687.0768229166666, 219.68),
    (687.7061631944445, 219.68),
    (688.3355034722223, 219.68),
    (688.96484375, 219.68),
    (689.5941840277777, 219.68),
    (690.8528645833334, 219.68),
    (692.2374131944445, 219.68),
    (693.49609375, 219.68),
    (694.1254340277777, 219.68),
    (695.4470486111111, 219.68),
    (696.0763888888889, 219.68),
    (696.7057291666666, 219.68),
    (698.02734375, 219.68),
    (698.6566840277778, 219.68),
    (699.2860243055555, 219.68),
    (699.9153645833334, 219.68),
    (700.5447048611111, 219.68),
    (701.1740451388889, 219.68),
    (702.4956597222223, 219.68),
    (703.125, 219.68),
    (704.4466145833333, 219.68),
    (705.7682291666666, 219.68),
    (706.3975694444445, 219.68),
    (707.0269097222223, 219.68),
    (708.3485243055555, 219.68),
    (709.6072048611111, 219.68),
    (710.2365451388889, 219.68),
    (711.62109375, 219.68),
    (713.0056423611111, 219.68),
    (714.3272569444445, 219.68),
    (715.7118055555555, 219.68),
    (717.0334201388889, 141.856),
]


class CountingDraw:
    """Stands in for PIL's ImageDraw and refuses to be drawn on forever."""

    def __init__(self, budget=100000):
        self.calls = 0
        self.budget = budget
        self.total_len = 0.0

    def line(self, xy, fill=None, width=1):
        self.calls += 1
        if self.calls > self.budget:
            raise AssertionError("_dashed drew {} runs: it is spinning".format(self.calls))
        x1, y1, x2, y2 = xy
        self.total_len += math.hypot(x2 - x1, y2 - y1)


def run_with_timeout(fn, seconds=10.0):
    """A spin in a gap phase draws nothing, so the draw budget alone is not enough."""
    done = threading.Event()
    box = {}

    def target():
        try:
            box["result"] = fn()
        except BaseException as e:            # noqa: BLE001
            box["error"] = e
        finally:
            done.set()

    threading.Thread(target=target, daemon=True).start()
    if not done.wait(seconds):
        pytest.fail("_dashed did not return in {:.0f}s: it is spinning".format(seconds))
    if "error" in box:
        raise box["error"]
    return box.get("result")


def test_does_not_spin_on_the_2026_09_15_geometry():
    d = CountingDraw()
    run_with_timeout(lambda: _dashed(d, SPIN_PTS, (0, 0, 0), width=3, dash=DASH, gap=GAP))
    assert d.calls > 0, "nothing was drawn at all"


def test_still_dashes_a_plain_line():
    """The fix must not change ordinary output: about dash/(dash+gap) of the length."""
    d = CountingDraw()
    run_with_timeout(lambda: _dashed(d, [(0.0, 0.0), (1000.0, 0.0)], (0, 0, 0),
                                     dash=10, gap=6))
    assert d.calls == pytest.approx(1000 / 16, rel=0.1)
    assert d.total_len == pytest.approx(1000 * 10 / 16, rel=0.05)


def test_degenerate_pattern_terminates():
    """dash=gap=0 has no run to walk; it must stop rather than toggle forever."""
    d = CountingDraw()
    run_with_timeout(lambda: _dashed(d, [(0.0, 0.0), (100.0, 0.0)], (0, 0, 0),
                                     dash=0, gap=0))


def test_zero_length_and_nan_segments_are_skipped():
    d = CountingDraw()
    run_with_timeout(lambda: _dashed(d, [(5.0, 5.0), (5.0, 5.0)], (0, 0, 0)))
    assert d.calls == 0
    d2 = CountingDraw()
    run_with_timeout(lambda: _dashed(d2, [(0.0, 0.0), (float("nan"), 0.0)], (0, 0, 0)))

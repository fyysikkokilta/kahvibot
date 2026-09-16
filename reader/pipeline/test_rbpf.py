"""Behavioural tests for the (volume, temperature) filter. No model, no camera:
row distributions are synthesised, so these run anywhere and fast.

Run: cd reader && python -m pytest pipeline/test_rbpf.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.rbpf import Calibration, Physics, PotRBPF  # noqa: E402
from pipeline.reader import row_dist  # noqa: E402

ROWS = 256
Y_BASE, Y_TOP = 0.88, 0.12


def cal() -> Calibration:
    """A linear stand-in for the deployed spline: h in [0, 1] maps to 0-1250 ml."""
    return Calibration(h_knots=[0.0, 1.0], f_knots=[0.0, 1.0], full_ml=1250.0)


def peak_rowdist(ml_values, weights=None, sharpness=6.0, c=cal()):
    """A row distribution with a Gaussian bump per given volume."""
    weights = weights or [1.0] * len(ml_values)
    logits = np.zeros((3, ROWS))
    grid = np.arange(ROWS)
    for ml, wt in zip(ml_values, weights):
        h = float(c.h_of_ml(ml))
        row = (Y_BASE - h * (Y_BASE - Y_TOP)) * (ROWS - 1)
        logits[2] += wt * sharpness * np.exp(-0.5 * ((grid - row) / 4.0) ** 2)
    return row_dist(logits, Y_BASE, Y_TOP)


def settle(f, ml, steps=12, dt=10.0, power=100.0):
    for _ in range(steps):
        p = f.step(dt=dt, power_w=power, rowdist=peak_rowdist([ml]), surface_logit=3.0)
    return p


def test_converges_to_a_clear_surface():
    f = PotRBPF(cal(), n_particles=1500, seed=1)
    post = settle(f, 600.0)
    assert abs(post.ml_mean - 600.0) < 40.0
    assert post.ml_sd < 60.0
    assert post.n_modes == 1


def test_diffuse_frame_does_not_move_the_estimate_and_needs_no_gate():
    f = PotRBPF(cal(), n_particles=1500, seed=2)
    settle(f, 600.0)
    before = f.posterior().ml_mean
    flat = row_dist(np.zeros((3, ROWS)), Y_BASE, Y_TOP)   # no surface information
    for _ in range(10):
        f.step(dt=10.0, power_w=100.0, rowdist=flat, surface_logit=-3.0)
    after = f.posterior().ml_mean
    assert abs(after - before) < 25.0


def test_occlusion_propagates_without_collapsing():
    f = PotRBPF(cal(), n_particles=1500, seed=3)
    settle(f, 600.0)
    before = f.posterior()
    for _ in range(18):                       # three minutes with nobody visible
        f.step(dt=10.0, power_w=100.0, rowdist=None)
    after = f.posterior()
    assert abs(after.ml_mean - before.ml_mean) < 40.0
    assert after.ml_sd >= before.ml_sd        # uncertainty must grow, not shrink
    assert after.observed is False


def test_bimodal_frame_is_resolved_by_history_not_by_a_threshold():
    """The failure this filter exists for: the head is torn between two surfaces
    ~120 ml apart. Having been at 400 ml with no brew since, the filter must stay
    near 400 rather than flip to 520."""
    f = PotRBPF(cal(), n_particles=3000, seed=4)
    settle(f, 400.0, steps=15)
    for _ in range(6):
        f.step(dt=10.0, power_w=100.0,
               rowdist=peak_rowdist([400.0, 520.0], weights=[1.0, 1.15]),
               surface_logit=2.0)
    post = f.posterior()
    assert abs(post.ml_mean - 400.0) < 60.0
    assert abs(post.ml_mean - 520.0) > 60.0


def test_level_may_not_rise_without_the_element():
    """786 persisting up-steps in the field log had no brew behind them. With the
    plug reporting only a hotplate, a sustained high reading must not be believed."""
    f = PotRBPF(cal(), n_particles=2000, seed=5)
    settle(f, 300.0, steps=15)
    for _ in range(10):
        f.step(dt=10.0, power_w=120.0, rowdist=peak_rowdist([900.0]), surface_logit=2.0)
    assert f.posterior().ml_mean < 700.0


def test_brew_lets_the_level_rise():
    f = PotRBPF(cal(), n_particles=2000, seed=6)
    settle(f, 0.0, steps=10)
    start = f.posterior().ml_mean
    ml = 0.0
    for _ in range(21):                        # 210 s of element, as measured
        ml = min(1200.0, ml + 5.6 * 10.0)
        f.step(dt=10.0, power_w=1450.0, rowdist=peak_rowdist([ml]), surface_logit=3.0)
    post = f.posterior()
    assert post.ml_mean - start > 800.0
    assert post.brewing is True


def test_temperature_is_anchored_at_brew_end_then_cools():
    f = PotRBPF(cal(), n_particles=1200, seed=7)
    ml = 0.0
    for _ in range(21):
        ml = min(1200.0, ml + 5.6 * 10.0)
        f.step(dt=10.0, power_w=1450.0, rowdist=peak_rowdist([ml]), surface_logit=3.0)
    end = f.step(dt=10.0, power_w=0.0, rowdist=peak_rowdist([ml]), surface_logit=3.0)
    assert 70.0 < end.temp_mean < 90.0         # anchored near brew temperature
    for _ in range(360):                       # an hour, plate off
        f.step(dt=10.0, power_w=0.0, rowdist=peak_rowdist([ml]), surface_logit=3.0)
    cooled = f.posterior()
    assert cooled.temp_mean < end.temp_mean - 8.0
    assert cooled.temp_mean > Physics().ambient_c - 1.0


def test_small_pot_cools_faster_than_a_full_one():
    """The volume-temperature coupling that makes this a joint posterior rather
    than two separate filters: thermal mass scales with volume."""
    temps = {}
    for ml in (200.0, 1200.0):
        f = PotRBPF(cal(), n_particles=800, seed=8)
        f.v[:] = ml
        f.t_mean[:] = 80.0
        f.t_var[:] = 1.0
        for _ in range(180):                   # half an hour, plate off
            f.step(dt=10.0, power_w=0.0, rowdist=peak_rowdist([ml]), surface_logit=3.0)
        temps[ml] = f.posterior().temp_mean
    assert temps[200.0] < temps[1200.0] - 3.0


def test_posterior_reports_multimodality_when_it_is_real():
    f = PotRBPF(cal(), n_particles=3000, seed=9)
    f.v[:] = np.random.default_rng(0).uniform(0, 1250, f.n)   # no prior belief
    post = f.step(dt=10.0, power_w=100.0,
                  rowdist=peak_rowdist([300.0, 800.0], weights=[1.0, 1.0]),
                  surface_logit=2.0)
    assert post.n_modes >= 2
    assert max(post.modes_ml) - min(post.modes_ml) > 300.0


def test_calibration_inverse_round_trips():
    c = Calibration(Path(__file__).resolve().parents[1] / "models" / "calibration.json")
    for ml in (0.0, 120.0, 500.0, 900.0, 1250.0):
        assert abs(c.ml(c.h_of_ml(ml)) - ml) < 1.0

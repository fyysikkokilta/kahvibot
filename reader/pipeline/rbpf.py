"""Rao-Blackwellised particle filter over (volume, temperature) for one carafe.

Why a filter at all
-------------------
The reader is a sensor with its own randomness, not an oracle that is sometimes
right. Its head produces a distribution over the surface row; the deployed
pipeline threw that away, kept the soft-argmax, and used the distribution's
entropy as an accept/reject gate. Measured on archived frames, that discards
real structure: 7 % of pot-views are genuinely **bimodal**, the two modes a
median of 121 ml apart, with the second mode holding ~0.9 of the peak's mass.
That is the same ~100 ml bistability visible in the field log, where the reader
produced 786 persisting up-steps against 540 down-steps even though only a brew
can raise the level. An entropy scalar cannot tell "torn between two surfaces"
from "one blurry surface", so no threshold on it can fix this.

So: no gate. The network's row distribution enters as a likelihood, a diffuse
frame simply fails to move the posterior, and a bimodal frame keeps both
hypotheses alive until the dynamics or the plug decide between them.

Why Rao-Blackwellised
---------------------
The state is (V, T). Volume's observation - the row distribution - is
multimodal and non-Gaussian, and its dynamics contain discrete pour jumps, so
it must be sampled. Temperature, **conditional on a particle's volume and power
history**, obeys a linear Gaussian heat balance, so it is integrated
analytically with a scalar Kalman filter carried inside each particle. That is
the textbook RBPF split, and it matters here: T has no direct sensor, so
sampling it would waste particles on a dimension the data cannot constrain.
The output is a particle-weighted mixture of Gaussians: a joint posterior over
volume and temperature, not two independent point estimates.

What drives the modes
---------------------
The smart plug makes the regime observed rather than latent: the heating element
draws ~1450 W and the hotplate 57-182 W (measured at the guild room), so the
filter is *told* when coffee is being made instead of having to infer it. This
is what removes the filter's worst failure: a rise in level is only plausible
while the element is drawing, and at any other time an apparent rise is the
sensor flipping modes.

Temperature honesty
-------------------
There is no thermometer. T is propagated from physics and anchored at the end
of each brew, so its posterior is only as good as the constants in `Physics`,
which are nominal and unvalidated. `PhysicsFit` records how to calibrate them
from one afternoon with a probe thermometer. Volume is measured; temperature is
inferred. The API keeps them distinguishable.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FULL_ML_DEFAULT = 1250.0


# ---------------------------------------------------------------------------
# calibration, both directions
# ---------------------------------------------------------------------------

class Calibration:
    """h_norm <-> fill fraction, from the deployed calibration.json.

    The reader ships the forward map only. The filter carries particles in
    millilitres - the quantity with physics attached - so it needs the inverse
    to ask "what row would a carafe holding V ml put its surface on?".
    """

    def __init__(self, path: Path | str | None = None, h_knots=None, f_knots=None,
                 full_ml: float = FULL_ML_DEFAULT):
        if path is not None:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            h_knots, f_knots = d["h_knots"], d["f_knots"]
            full_ml = float(d.get("full_ml", FULL_ML_DEFAULT))
        self.h = np.asarray(h_knots, dtype=float)
        self.f = np.asarray(f_knots, dtype=float)
        self.full_ml = float(full_ml)

    def fraction(self, h):
        return np.clip(np.interp(h, self.h, self.f), 0.0, 1.0)

    def ml(self, h):
        return self.fraction(h) * self.full_ml

    def h_of_ml(self, ml):
        """Inverse map. Both knot vectors are monotone, so a plain interp back
        is exact at the knots and linear between them, matching the forward map."""
        frac = np.clip(np.asarray(ml, dtype=float) / self.full_ml, 0.0, 1.0)
        return np.interp(frac, self.f, self.h)


# ---------------------------------------------------------------------------
# physical and behavioural parameters
# ---------------------------------------------------------------------------

@dataclass
class Physics:
    """Nominal constants. Only `brew_rate` and the power thresholds are backed
    by measurement at the guild room; the thermal ones are textbook values for
    a 1.25 l glass carafe and should be fitted before any temperature claim is
    made to users (see PhysicsFit)."""

    # --- volume ---
    full_ml: float = FULL_ML_DEFAULT
    brew_rate_ml_s: float = 5.6          # 1250 ml over the ~215 s brews measured
    brew_rate_sd: float = 1.2            # spread over grind, basket, water level
    pour_per_hour: float = 3.0           # pours per hour while coffee is present
    brews_per_hour_prior: float = 0.4    # only used when no plug is reporting
    brew_duration_s: float = 215.0       # measured on the plugs: 198 s and 213 s
    pour_median_ml: float = 110.0        # measured median down-step in the field log
    pour_log_sd: float = 0.55
    evaporation_ml_per_hour: float = 6.0  # while hot and uncovered; small on purpose
    volume_walk_ml_s: float = 0.35       # process noise: unmodelled slosh, tilt, refills

    # --- power regimes, measured on the plugs ---
    brew_watts: float = 800.0            # element 1438-1546 W, plate <=182 W
    plate_watts_min: float = 20.0        # above this the plate is considered on
    plate_efficiency: float = 0.55       # fraction of plate power reaching the coffee

    # --- thermal ---
    c_coffee_j_per_ml_k: float = 4.18
    carafe_heat_capacity_j_k: float = 520.0   # ~620 g borosilicate
    loss_w_per_k: float = 0.55                # carafe on a plate, lid on
    ambient_c: float = 22.0
    brew_inlet_c: float = 92.0
    brew_end_c: float = 80.0             # bulk temperature just after a brew finishes
    brew_end_sd: float = 4.0
    temp_process_sd_per_s: float = 0.02  # K per sqrt(s); draughts, lid off, stirring

    # --- sensor ---
    outlier_floor: float = 0.02          # weight kept for "the row head is simply wrong"


@dataclass
class PhysicsFit:
    """How to replace the guessed thermal constants with measured ones.

    One afternoon, one probe thermometer:

    1. Brew a full pot, plate ON. Log probe temperature every 5 min for an hour
       alongside the plug's power. Fit `plate_efficiency` and `loss_w_per_k` to
       the plateau: at steady state plate_efficiency * P_plate = loss * (T-T_amb).
    2. Repeat with plate OFF. The exponential decay constant gives loss / C, and
       C is known from the volume, so this separates the two.
    3. Read the probe within a minute of brew end for `brew_end_c`.
    4. Half-full pot, plate OFF, to confirm the decay constant scales with C(V);
       that coupling is what lets cooling rate say anything about volume.

    Until then, report volume with confidence and temperature as an estimate.
    """
    note: str = "unfitted"


# ---------------------------------------------------------------------------
# the filter
# ---------------------------------------------------------------------------

@dataclass
class Posterior:
    """Summary of the joint posterior at one instant."""
    ml_mean: float
    ml_median: float
    ml_sd: float
    ml_lo: float                 # 10th percentile
    ml_hi: float                 # 90th percentile
    temp_mean: float
    temp_sd: float
    modes_ml: list               # significant modes, descending by mass
    n_modes: int
    ess: float                   # effective sample size after the last update
    brewing: bool
    p_brewing: float             # posterior probability the element is running
    seconds_since_brew: float | None
    observed: bool               # did a camera likelihood enter this step

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["modes_ml"] = [round(float(m), 1) for m in self.modes_ml]
        for k, v in list(d.items()):
            if isinstance(v, float):
                d[k] = round(v, 2)
        return d


class PotRBPF:
    """One carafe. Feed it time, plug power, and the reader's row distribution.

    Typical use, once per reader tick::

        f = PotRBPF(calibration)
        f.step(dt=10.0, power_w=plug_power, rowdist=pot["rowdist"],
               surface_logit=pot["v"])
        post = f.posterior()

    `rowdist=None` means the carafe was not detected (occluded, someone standing
    in the way). The filter then propagates without a measurement, which is the
    honest thing to do and needs no gate.
    """

    def __init__(self, calibration: Calibration, physics: Physics | None = None,
                 n_particles: int = 2000, seed: int = 0):
        self.cal = calibration
        self.p = physics or Physics()
        self.n = int(n_particles)
        self.rng = np.random.default_rng(seed)

        # particle state
        self.v = self.rng.uniform(0.0, self.p.full_ml, self.n)      # volume, ml
        self.q = np.clip(self.rng.normal(self.p.brew_rate_ml_s, self.p.brew_rate_sd, self.n),
                         1.0, None)                                  # brew rate, ml/s
        # Brewing is observed when a plug reports and latent otherwise, so each
        # particle carries its own mode. With a plug the switch is pinned and the
        # filter is strong; without one it still works, just vaguer.
        self.mode = np.zeros(self.n, dtype=bool)                     # True = brewing
        self.logw = np.full(self.n, -math.log(self.n))               # log weights
        # Rao-Blackwellised temperature: one Gaussian per particle
        self.t_mean = np.full(self.n, self.p.ambient_c)
        self.t_var = np.full(self.n, 25.0)

        self.brewing = False
        self._since_brew: float | None = None
        self._last_observed = False

    # -- weights -----------------------------------------------------------
    @property
    def w(self) -> np.ndarray:
        w = np.exp(self.logw - self.logw.max())
        return w / w.sum()

    def ess(self) -> float:
        w = self.w
        return float(1.0 / np.sum(w * w))

    # -- dynamics ----------------------------------------------------------
    def _step_mode(self, dt: float, power_w):
        """Advance the discrete regime; returns (started, ended) boolean arrays.

        With a plug the regime is dictated by measured wattage. Without one it is
        a two-state Markov chain sampled per particle, which keeps the filter
        usable when the plug drops off the Zigbee mesh.
        """
        was = self.mode.copy()
        if power_w is not None:
            self.mode = np.full(self.n, float(power_w) >= self.p.brew_watts)
        elif dt > 0:
            r = self.rng.random(self.n)
            start_p = 1.0 - math.exp(-self.p.brews_per_hour_prior / 3600.0 * dt)
            stop_p = 1.0 - math.exp(-dt / max(self.p.brew_duration_s, 1.0))
            self.mode = np.where(was, r >= stop_p, r < start_p)
        return (self.mode & ~was), (~self.mode & was)

    def _predict_volume(self, dt: float, brewing, brew_started) -> None:
        p, rng = self.p, self.rng
        if brew_started.any():
            # A brew almost always starts on an empty carafe: someone emptied or
            # swapped it. Allowing that jump here is what stops the filter from
            # fighting the level rise it is about to see. The minority branch
            # covers brewing on top of a part-full pot.
            fresh = (rng.random(self.n) < 0.85) & brew_started
            self.v = np.where(fresh, np.abs(rng.normal(0.0, 25.0, self.n)), self.v)
            self.q = np.where(brew_started,
                              np.clip(rng.normal(p.brew_rate_ml_s, p.brew_rate_sd, self.n), 1.0, None),
                              self.q)

        if brewing.any():
            self.v = self.v + brewing * self.q * dt
        if (~brewing).any():
            # Pours: a jump process. Only a pour may lower the level quickly, and
            # nothing at all may raise it, which is exactly the constraint the
            # unfiltered reader violated 786 times in the field log.
            lam = p.pour_per_hour / 3600.0
            hit = ((rng.random(self.n) < (1.0 - math.exp(-lam * dt)))
                   & (self.v > 20.0) & ~brewing)
            if hit.any():
                size = np.exp(rng.normal(math.log(p.pour_median_ml), p.pour_log_sd, hit.sum()))
                self.v[hit] = self.v[hit] - size
            hot = (self.t_mean > 45.0) & ~brewing
            self.v = self.v - hot * (p.evaporation_ml_per_hour / 3600.0) * dt

        self.v = self.v + rng.normal(0.0, p.volume_walk_ml_s * math.sqrt(max(dt, 1e-6)), self.n)
        np.clip(self.v, 0.0, p.full_ml * 1.05, out=self.v)

    def _predict_temperature(self, dt: float, power_w: float, brewing,
                             brew_ended) -> None:
        """Scalar Kalman prediction, conditional on each particle's volume.

        Heat balance:  C(V) dT/dt = eta*P_plate + q*c*(T_in - T) - U*(T - T_amb)
        which is linear in T, so mean and variance propagate in closed form.
        C(V) is the coupling that makes a big pot cool slower than a small one.
        """
        p = self.p
        C = p.c_coffee_j_per_ml_k * np.maximum(self.v, 1.0) + p.carafe_heat_capacity_j_k
        inflow_w_per_k = brewing * self.q * p.c_coffee_j_per_ml_k
        plate_on = (~brewing) & (power_w > p.plate_watts_min)
        plate_w = plate_on * (p.plate_efficiency * power_w)

        a = 1.0 - dt * (p.loss_w_per_k + inflow_w_per_k) / C
        b = dt * (plate_w + p.loss_w_per_k * p.ambient_c
                  + inflow_w_per_k * p.brew_inlet_c) / C
        a = np.clip(a, 0.0, 1.0)                      # keep the step stable at large dt

        self.t_mean = a * self.t_mean + b
        self.t_var = a * a * self.t_var + (p.temp_process_sd_per_s ** 2) * dt

        if brew_ended.any():
            # The one temperature observation available without a probe: a pot
            # that has just finished brewing is at brewing temperature. Treated
            # as a measurement, not an assignment, so its uncertainty is kept.
            r = p.brew_end_sd ** 2
            k = np.where(brew_ended, self.t_var / (self.t_var + r), 0.0)
            self.t_mean = self.t_mean + k * (p.brew_end_c - self.t_mean)
            self.t_var = (1.0 - k) * self.t_var

    # -- measurement -------------------------------------------------------
    def _update(self, rowdist: dict, surface_logit: float | None) -> None:
        """Weight particles by the network's own row distribution.

        The trained `surface_logit` head becomes the mixing weight of a robust
        likelihood: p(image | V) = pi * p_row(V) + (1 - pi) * flat. When the head
        says no surface is visible, pi is small, the likelihood is nearly flat,
        and the frame moves nothing. That is the gate's job, done continuously
        and without discarding the frame.
        """
        from .reader import surf_loglik

        h = self.cal.h_of_ml(self.v)
        ll = surf_loglik(rowdist, h)
        pi = 1.0 / (1.0 + math.exp(-float(surface_logit))) if surface_logit is not None else 0.9
        pi = min(max(pi, self.p.outlier_floor), 1.0 - self.p.outlier_floor)

        # flat alternative over the crop, in the same log-density units
        flat = -math.log(max(rowdist["n"], 2))
        m = np.maximum(ll, flat)
        mixed = m + np.log(pi * np.exp(ll - m) + (1.0 - pi) * np.exp(flat - m))

        self.logw = self.logw + mixed
        self.logw -= self.logw.max()
        self._last_observed = True

    def _resample(self) -> None:
        w = self.w
        pos = (self.rng.random() + np.arange(self.n)) / self.n
        idx = np.searchsorted(np.cumsum(w), pos)
        idx = np.clip(idx, 0, self.n - 1)
        self.v = self.v[idx]
        self.q = self.q[idx]
        self.mode = self.mode[idx]
        self.t_mean = self.t_mean[idx]
        self.t_var = self.t_var[idx]
        self.logw = np.full(self.n, -math.log(self.n))

    # -- public step -------------------------------------------------------
    def step(self, dt: float, power_w: float | None = None, rowdist: dict | None = None,
             surface_logit: float | None = None, resample_frac: float = 0.5) -> Posterior:
        dt = float(max(dt, 0.0))
        started, ended = self._step_mode(dt, power_w)

        self._last_observed = False
        if dt > 0:
            self._predict_volume(dt, self.mode, started)
            self._predict_temperature(dt, float(power_w or 0.0), self.mode, ended)

        if rowdist is not None:
            self._update(rowdist, surface_logit)
            if self.ess() < resample_frac * self.n:
                self._resample()

        p_brewing = float(np.sum(self.w * self.mode))
        if ended.any() and p_brewing < 0.5:
            self._since_brew = 0.0
        elif self._since_brew is not None and p_brewing < 0.5:
            self._since_brew += dt
        self.brewing = p_brewing >= 0.5
        self._p_brewing = p_brewing
        return self.posterior()

    # -- output ------------------------------------------------------------
    def posterior(self, mode_min_mass: float = 0.12, mode_min_gap_ml: float = 40.0) -> Posterior:
        w = self.w
        order = np.argsort(self.v)
        v_sorted, w_sorted = self.v[order], w[order]
        cdf = np.cumsum(w_sorted)
        mean = float(np.sum(w * self.v))
        sd = float(math.sqrt(max(np.sum(w * (self.v - mean) ** 2), 0.0)))

        def quant(p):
            return float(v_sorted[int(np.searchsorted(cdf, p).clip(0, self.n - 1))])

        # weighted histogram, to report genuine multimodality instead of hiding it
        edges = np.linspace(0.0, self.p.full_ml, 64)
        hist, _ = np.histogram(self.v, bins=edges, weights=w)
        centres = 0.5 * (edges[1:] + edges[:-1])
        modes = []
        for i in range(len(hist)):
            lo, hi = max(i - 1, 0), min(i + 2, len(hist))
            if hist[i] >= hist[lo:hi].max() and hist[i] >= mode_min_mass * hist.max():
                if modes and abs(centres[i] - modes[-1][0]) < mode_min_gap_ml:
                    if hist[i] > modes[-1][1]:
                        modes[-1] = (centres[i], hist[i])
                else:
                    modes.append((centres[i], hist[i]))
        modes.sort(key=lambda m: -m[1])

        t_mean = float(np.sum(w * self.t_mean))
        # law of total variance across the particle mixture
        t_var = float(np.sum(w * (self.t_var + (self.t_mean - t_mean) ** 2)))

        return Posterior(
            ml_mean=mean, ml_median=quant(0.5), ml_sd=sd,
            ml_lo=quant(0.10), ml_hi=quant(0.90),
            temp_mean=t_mean, temp_sd=math.sqrt(max(t_var, 0.0)),
            modes_ml=[m[0] for m in modes], n_modes=len(modes),
            ess=self.ess(), brewing=self.brewing, p_brewing=getattr(self, "_p_brewing", 0.0),
            seconds_since_brew=self._since_brew, observed=self._last_observed,
        )


@dataclass
class TwoPots:
    """Both carafes, each with its own filter and its own plug."""
    left: PotRBPF
    right: PotRBPF

    @classmethod
    def build(cls, calibration: Calibration, physics: Physics | None = None,
              n_particles: int = 2000, seed: int = 0) -> "TwoPots":
        return cls(PotRBPF(calibration, physics, n_particles, seed),
                   PotRBPF(calibration, physics, n_particles, seed + 1))

    def get(self, side: str) -> PotRBPF:
        return self.left if side == "left" else self.right

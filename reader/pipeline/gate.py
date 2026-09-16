"""The abstention gate, downstream of the model.

Two signals are available per pot:

* ``e`` — the reader's surface-row entropy (what the deployed 0.55 gate uses);
* ``a`` — temporal agreement: |h − h of the previous reading of the same pot|
  in millilitres, when that reading is younger than the agreement window
  (the streamlined sampler reads every ~10 s, so nearly always).

Field and blind-set evidence (the gym's GATE2/GATE3 reports): for v8, entropy
does not separate accurate readings from bad ones, on either camera epoch,
while neighbour agreement does — on blind non-empty clicks the 40 % most
consistent readings have a 14 ml median error against 25 ml for the 40 %
sharpest. So the default mode is ``agree`` with an entropy fallback for pots
that have no recent neighbour (first tick after dark, a lone bot frame).

Tiers:  ok  →  drawn as a normal reading
        uncertain  →  drawn with a doubled band, captioned "noin / about"
        abstain  →  rug strip only
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Gate:
    ok_max: float = 0.62            # entropy tier limits
    unc_max: float = 0.68
    mode: str = "entropy"           # "entropy" | "agree"
    agree_ok_ml: float = 40.0       # agreement tier limits, ml
    agree_unc_ml: float = 90.0

    # -- entropy only (kept for the archive sweeps and old records) ------------
    def tier(self, e: float) -> str:
        if e <= self.ok_max:
            return "ok"
        if e <= self.unc_max:
            return "uncertain"
        return "abstain"

    # -- the real decision: a pot dict with 'e' and optionally 'agree'/'a' ----------
    def tier_pot(self, pot: dict) -> str:
        a = pot.get("agree", pot.get("a"))
        if self.mode == "agree" and a is not None:
            if a <= self.agree_ok_ml:
                return "ok"
            if a <= self.agree_unc_ml:
                return "uncertain"
            return "abstain"
        return self.tier(pot["e"])

    def usable(self, pot: dict) -> bool:
        return self.tier_pot(pot) != "abstain"

    def ok(self, pot: dict) -> bool:
        return self.tier_pot(pot) == "ok"

    def apply(self, pots):
        """Annotate pots in place with 'tier' and 'ok' (bool), return them."""
        for p in pots:
            t = self.tier_pot(p)
            p["tier"] = t
            p["ok"] = t == "ok"
        return pots


LEGACY = Gate(0.55, 0.55, mode="entropy")
PROPOSED = Gate(0.62, 0.68, mode="agree", agree_ok_ml=40.0, agree_unc_ml=90.0)

# -*- coding: utf-8 -*-
"""Randomised annotation collection for kahvibot (UX_FEEDBACK.md, implemented).

Two-tap inline-keyboard surveys that collect the coffee-surface row from guild
members: the group reply carries one deep-link button, everything else happens
in the user's private chat with the bot. Design decisions, message texts,
record schema, rate limits and abuse handling follow UX_FEEDBACK.md; the
frame-coordinate arithmetic is pinned to read_frame.py (see GEOMETRY below).

Import contract: this module imports with NEITHER python-telegram-bot NOR
Pillow installed - every telegram/PIL touch is a lazy import inside the
methods that need it - so the sampling, blindness, ladder, rate-limit,
record and reduction logic is unit-testable anywhere. The bot constructs one
``FeedbackManager`` and wires five handlers; a fault anywhere in here must
degrade to "the photo still goes out", exactly like a reader fault.
"""
from __future__ import annotations

import gzip
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("kahvibot.feedback")

SCHEMA = "tg_click/1"
BANDS = 12            # screen-1 ladder resolution
TICKS = 12            # screen-2 resolution
BAND_ZOOM = 1.2       # screen 2 spans the chosen band +-0.1 band (1.2 bands)
SENTINEL_FRAC = 1 / 6.0   # ~1 in 6 prompted surveys re-serves a known frame
EVAL_DAY_PCT = 5          # ~5 % of days are evaluation days (blind pool)
POOL_TARGET_K = 5         # answers wanted per evaluation crop
OFFER_TTL_S = 6 * 3600    # a prompt answered later than this is not "prompted"
CACHE_TTL_S = 7 * 86400   # pre-rendered screens / cached frames live this long
STRATA = 8                # predicted-fill bands for stratification

# --------------------------------------------------------------------------
# GEOMETRY - pinned, line for line, to read_frame.py expand_box()/model_crop().
# Only the *transform arithmetic* is replicated (no pixel resampling), because
# what the record stores is frame-pixel rows plus the transform inputs; the
# fraction-of-crop-height is derived through this exact chain. If
# read_frame.expand_box or model_crop change, change this too - the test
# harness compares the two implementations on random boxes.
# --------------------------------------------------------------------------

def expand_box(box, width, height, margin=0.12, top_extra=0.06):
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    x1 -= bw * margin
    x2 += bw * margin
    y1 -= bh * (margin + top_extra)
    y2 += bh * margin
    return (max(0.0, x1), max(0.0, y1), min(float(width), x2), min(float(height), y2))


def crop_transform(box, frame_wh, crop_wh=(160, 320), margin=0.12):
    """(scale, off_x, off_y, pad_x, pad_y) of read_frame.model_crop, no pixels.

    frame_y = (cache_y - pad_y) / scale + off_y  and the inverse below.
    """
    width, height = frame_wh
    out_w, out_h = crop_wh
    x1, y1, x2, y2 = expand_box(box, width, height, margin=margin)
    sub_w = int(round(x2)) - int(round(x1))
    sub_h = int(round(y2)) - int(round(y1))
    if sub_w <= 0 or sub_h <= 0:
        return (1.0, x1, y1, 0, 0)
    scale = min(out_w / sub_w, out_h / sub_h)
    new_w = max(1, int(round(sub_w * scale)))
    new_h = max(1, int(round(sub_h * scale)))
    pad_x = (out_w - new_w) // 2
    pad_y = (out_h - new_h) // 2
    # model_crop returns the UNROUNDED expanded origin in its transform even
    # though the slice starts at the rounded one; match it exactly, bug or not.
    return (scale, x1, y1, pad_x, pad_y)


def frame_y_to_frac(y_px, tf, cache_h=320):
    """Frame-pixel row -> fraction of crop height (the ‡ y_surf convention)."""
    scale, _ox, off_y, _px, pad_y = tf
    return ((y_px - off_y) * scale + pad_y) / float(cache_h)


# --------------------------------------------------------------------------
# Blindness: a property of the DAY, decided once, by hash (UX_FEEDBACK §5).
# --------------------------------------------------------------------------

def stem_date(stem: str) -> str:
    """'coffee_2026-08-29_14-03-11' -> '2026-08-29' (empty if malformed)."""
    parts = stem.split("_")
    return parts[1] if len(parts) >= 2 else ""

def is_blind_day(stem: str, salt: str, pct: int = EVAL_DAY_PCT) -> bool:
    day = stem_date(stem)
    if not day:
        return False
    h = hashlib.sha256((salt + day).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100 < pct


# --------------------------------------------------------------------------
# Ladder: ticks span y_top..y_base from the PER-SIDE SPAN, never from the
# per-frame prediction (§5: the ladder must not anchor).
# --------------------------------------------------------------------------

class Ladder:
    def __init__(self, y_top_px: float, y_base_px: float):
        # image y grows downward: top of the span is the smaller value
        self.y_top = float(min(y_top_px, y_base_px))
        self.y_base = float(max(y_top_px, y_base_px))

    @property
    def span(self) -> float:
        return self.y_base - self.y_top

    def band_y(self, band: int) -> float:
        """Centre row of band 1..BANDS (1 = top of span = fullest)."""
        return self.y_top + (band - 0.5) * self.span / BANDS

    def band_window(self, band: int) -> Tuple[float, float]:
        """Screen-2 view: the chosen band widened to BAND_ZOOM bands."""
        c = self.band_y(band)
        half = 0.5 * BAND_ZOOM * self.span / BANDS
        return (max(self.y_top, c - half), min(self.y_base, c + half))

    def tick_y(self, band: int, tick: int) -> float:
        """Final row of tick 1..TICKS inside band's zoom window."""
        lo, hi = self.band_window(band)
        return lo + (tick - 0.5) * (hi - lo) / TICKS

    def quantisation_px(self, band: int) -> float:
        lo, hi = self.band_window(band)
        return (hi - lo) / TICKS


# --------------------------------------------------------------------------
# Message texts (UX_FEEDBACK §4.1, verbatim).
# --------------------------------------------------------------------------

TXT_PROMPT_CAPTION = (
    "Ehtisitkö 10 sekuntia? Merkitse kahvin pinta, niin kone oppii lukemaan pannun.\n"
    "Got 10 seconds? Mark the coffee surface and the machine learns to read the pot."
)
BTN_HELP = "✋ Autan / I'll help"
BTN_WRONG = "✏️ Väärin? / Wrong?"
BTN_CANT_SEE = "🙈 En näe pintaa / Can't see it"
BTN_SKIP = "⏭ Ohita / Skip"
BTN_BACK = "↩ Takaisin / Back"

TXT_SCREEN1_ASSISTED = (
    "{pot}, {hhmm}\n\n"
    "Missä kahvin pinta on? Valitse numero, joka on lähinnä pinnan ETUREUNAA - "
    "sitä kohtaa, jossa kahvi koskettaa lasia sinua kohti.\n"
    "Katkoviiva on koneen arvaus.\n\n"
    "Where is the coffee surface? Pick the number nearest the FRONT EDGE of the "
    "surface - where the coffee meets the glass nearest you.\n"
    "The dashed line is the machine's guess."
)
TXT_SCREEN1_BLIND = (
    "{pot}, {hhmm}\n\n"
    "Sokkokierros: sinä ensin. Kone paljastaa oman arvauksensa vasta lopuksi.\n"
    "Blind round: you go first. The machine reveals its own guess at the end.\n\n"
    "Missä kahvin pinta on? Valitse numero, joka on lähinnä pinnan ETUREUNAA.\n"
    "Where is the coffee surface? Pick the number nearest the FRONT EDGE."
)
TXT_SCREEN2 = (
    "Tarkenna: mikä viiva osuu pintaan?\n"
    "Sharpen it: which line sits on the surface?"
)
TXT_THANKS_ASSISTED = (
    "Kiitos! Merkitsit pinnan {fi_delta}.\nTästä se oppii.\n"
    "Thanks! You put the surface {en_delta}.\nThat is what it learns from."
)
TXT_THANKS_BLIND = (
    "Kiitos! Sinä: {you}. Kone: {machine}. Ero {ml} ml.\n"
    "Thanks! You: {you_en}. Machine: {machine_en}. {ml} ml apart."
)
TXT_CANT_SEE = (
    "Selvä - sekin on vastaus. Kone yrittää oppia, milloin pintaa ei voi nähdä.\n"
    "Fair enough - that is an answer too. The machine is learning when the "
    "surface can't be seen."
)
TXT_ALREADY_TODAY = (
    "Sait kyselyn jo tänään - kiitos! Huomenna taas.\n"
    "You already had a survey today - thanks! Try again tomorrow."
)
TXT_CONSENT = (
    "Tämä on kahvibotin merkintäkysely. Tallennan vain: mihin napautit, mistä\n"
    "kuvasta, ja tunnisteen käyttäjä-ID:stäsi (yksisuuntainen tiiviste - ei nimeä,\n"
    "ei viestejä). Kuvat ovat samoja, jotka botti on jo lähettänyt kiltiksen\n"
    "ryhmään. Lopeta milloin vain: /eikiitos\n\n"
    "This is the kahvibot annotation survey. Stored: where you tapped, which photo,\n"
    "and a one-way hash of your user ID - not your name, not your messages. The\n"
    "photos are the ones the bot has already posted to the guild chat.\n"
    "Stop any time: /eikiitos"
)
TXT_OPTED_OUT = (
    "Selvä, en kysy enää. Vapaaehtoiset merkinnät onnistuvat yhä: /merkkaa\n"
    "Understood, no more prompts. Volunteering still works: /merkkaa"
)
TXT_NO_FRAME = (
    "Ei tuoretta kuvaa merkittäväksi juuri nyt - pyydä ensin /status ryhmässä.\n"
    "No fresh photo to annotate right now - ask for /status in the group first."
)
TXT_EXPIRED = (
    "Tämä kysely ehti vanhentua. Uusi tulee kuvien mukana!\n"
    "This survey expired. A new one rides on the next photos!"
)
HELP_EXTRA = (
    "/merkkaa - Merkitse kahvin pinta yhteen kuvaan / Mark the coffee surface on one photo\n"
    "/eikiitos - Älä kysy minulta enää / Stop asking me"
)

POT_NAMES = {"left": "Vasen pannu / left pot", "right": "Oikea pannu / right pot"}


def _half_cups(ml: float) -> str:
    hc = round(ml / 62.5) / 2
    if hc <= 0:
        return "tyhjä / empty"
    return "~" + ("%g" % hc).replace(".5", "½")


# --------------------------------------------------------------------------
# Record construction (schema §7). Pure; raises on NaN by design.
# --------------------------------------------------------------------------

def make_record(offer: Dict[str, Any], answered: Dict[str, Any]) -> Dict[str, Any]:
    """Build one tg_click/1 line from an offer dict + the answer facts.

    eval_eligible is *computed*, never trusted from the caller:
    prompted && !hint_shown && !sentinel (weight is assigned by the reducer).
    """
    prompted = bool(answered["answering_user_hash"] == offer["offered_to"]
                    and answered["answered_at_s"] - offer["created_at_s"] <= OFFER_TTL_S
                    and offer.get("kind") == "prompt")
    hint_shown = bool(offer.get("hint_shown"))
    sentinel = bool(offer.get("sentinel"))
    rec = {
        "schema": SCHEMA,
        "key": offer["stem"] + "__" + offer["side"],
        "stem": offer["stem"],
        "side": offer["side"],
        "message_id": offer.get("message_id"),

        "y_surf": answered.get("y_surf"),
        "y_surf_frame_px": answered.get("y_surf_frame_px"),
        "surface_visible": answered["surface_visible"],
        "surf_method": "tg_ladder",
        "surf_n_points": 1,
        "x_surf": None,
        "y_base": None, "y_top": None,
        "era": "hd2026",
        "level": None,

        "box": offer.get("box"),
        "box_source": offer.get("box_source", "fastbox"),
        "frame_wh": offer.get("frame_wh", [1280, 720]),
        "crop_wh": [160, 320],
        "span_source": offer.get("span_source", "per_side_const_v1"),
        "span_frame_px": offer.get("span_frame_px"),

        "hint_shown": hint_shown,
        "hint": offer.get("hint"),
        "prompted": prompted,
        "eval_eligible": bool(prompted and not hint_shown and not sentinel),
        "sentinel": sentinel,
        "pool": offer.get("pool", "train"),
        "stratum": offer.get("stratum"),

        "user_hash": answered["answering_user_hash"],
        "issued_at": offer.get("issued_at"),
        "answered_at": answered["answered_at"],
        "latency_s": answered.get("latency_s"),
        "n_taps": answered.get("n_taps"),
        "band": answered.get("band"),
        "tick": answered.get("tick"),
        "bot_version": offer.get("bot_version", "kahvibot+feedback/1"),
        "reader_version": offer.get("reader_version"),
    }
    # allow_nan=False: a NaN would break every downstream consumer silently.
    json.dumps(rec, allow_nan=False)
    return rec


# --------------------------------------------------------------------------
# Reduction (§7): raw JSONL -> hand_lines-shaped dict. Pure, re-runnable.
# --------------------------------------------------------------------------

def reduce_clicks(lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Median over repeats per key; weights, never deletions; tick histogram.

    Only weight > 0 records contribute. The per-tick histogram (over ALL
    parseable records) is the §8 middle-button-mode check: report it, do not
    act on it silently.
    """
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    hist = [0] * (TICKS + 1)  # 1-indexed ticks
    for rec in lines:
        if rec.get("schema") != SCHEMA:
            continue
        t = rec.get("tick")
        if isinstance(t, int) and 1 <= t <= TICKS:
            hist[t] += 1
        w = rec.get("weight", 1.0)
        if rec.get("sentinel") or not rec.get("surface_visible"):
            continue
        if w is None or w <= 0 or rec.get("y_surf") is None:
            continue
        by_key.setdefault(rec["key"], []).append(rec)

    out: Dict[str, Any] = {}
    for key, recs in by_key.items():
        ys = sorted(r["y_surf"] for r in recs)
        k = len(ys)
        med = ys[k // 2] if k % 2 else 0.5 * (ys[k // 2 - 1] + ys[k // 2])
        spread = (ys[-1] - ys[0]) if k > 1 else 0.0
        out[key] = {
            "y_surf": round(med, 5),
            "surf_method": "tg_ladder",
            "surf_n_points": k,
            "surface_visible": True,
            "spread": round(spread, 5),
            "hint_shown": any(r.get("hint_shown") for r in recs),
            "eval_eligible": all(r.get("eval_eligible") for r in recs),
        }
    total = sum(hist)
    mode_tick = max(range(1, TICKS + 1), key=lambda i: hist[i]) if total else None
    return {"keys": out, "tick_histogram": hist[1:],
            "mode_tick": mode_tick,
            "mode_frac": (hist[mode_tick] / total) if total else None}


# --------------------------------------------------------------------------
# Persistent state: atomic JSON, one file. Counters, served table, offers.
# --------------------------------------------------------------------------

class SurveyState:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.d: Dict[str, Any] = {"users": {}, "served": {}, "offers": {},
                                  "day": "", "day_prompts": 0,
                                  "seen_users": {}}
        if self.path.exists():
            try:
                self.d.update(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                logger.warning("survey state unreadable, starting fresh", exc_info=True)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.d, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            logger.warning("survey state save failed", exc_info=True)

    # -- day rollover ------------------------------------------------------
    def roll_day(self, today: str) -> None:
        if self.d["day"] != today:
            self.d["day"] = today
            self.d["day_prompts"] = 0
            for u in self.d["users"].values():
                u["prompts_today"] = 0
                u["volunteered_today"] = 0

    def user(self, user_hash: str) -> Dict[str, Any]:
        return self.d["users"].setdefault(user_hash, {
            "consented": False, "opted_out": False,
            "prompts_today": 0, "volunteered_today": 0,
            "answers": 0, "sentinel_n": 0, "sentinel_abs_px": 0.0})

    def eligible_user_count(self, now_s: float, window_days: int = 14) -> int:
        cutoff = now_s - window_days * 86400
        seen = self.d["seen_users"]
        n = sum(1 for h, t in seen.items()
                if t >= cutoff and not self.d["users"].get(h, {}).get("opted_out"))
        return max(1, n)

    def note_seen(self, user_hash: str, now_s: float) -> None:
        self.d["seen_users"][user_hash] = now_s

    # -- served table: one answer per (crop, user) --------------------------
    def served(self, key: str) -> List[str]:
        return self.d["served"].setdefault(key, [])


# --------------------------------------------------------------------------
# Calibration (optional, motivational copy only - records store geometry).
# --------------------------------------------------------------------------

class _Cal:
    def __init__(self, path: Optional[Path]):
        self.h, self.f, self.full = None, None, 1250.0
        if path and path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                self.h, self.f = d["h_knots"], d["f_knots"]
                self.full = float(d.get("full_ml", 1250.0))
            except (OSError, ValueError, KeyError):
                pass

    def ml(self, h_norm: float) -> float:
        h_norm = min(1.0, max(0.0, h_norm))
        if not self.h:
            return h_norm * self.full  # linear fallback
        xs, ys = self.h, self.f
        if h_norm <= xs[0]:
            return ys[0] * self.full
        for i in range(1, len(xs)):
            if h_norm <= xs[i]:
                t = (h_norm - xs[i - 1]) / (xs[i] - xs[i - 1] or 1.0)
                return (ys[i - 1] + t * (ys[i] - ys[i - 1])) * self.full
        return ys[-1] * self.full


# --------------------------------------------------------------------------
# The manager. Telegram objects only at the edges; everything above is pure.
# --------------------------------------------------------------------------

class FeedbackManager:
    def __init__(self, *, enabled: bool, survey_dir: str, bot_username: str,
                 span: Dict[str, Dict[str, float]],
                 span_source: str = "per_side_const_v1",
                 rate_per_day: float = 8.0, blind_frac: float = 0.25,
                 daily_cap: int = 15, volunteer_cap: int = 5,
                 eval_day_salt: str = "coffee10-blind-v1",
                 frames_dir: str = "", sentinel_dir: str = "",
                 admin_chat: int = 0, reader_dir: str = "",
                 reader_version: str = ""):
        self.enabled = enabled
        self.dir = Path(survey_dir)
        self.cache = self.dir / "cache"
        self.bot_username = bot_username.lstrip("@")
        self.span = span
        self.span_source = span_source
        self.rate = float(rate_per_day)
        self.blind_frac = float(blind_frac)
        self.daily_cap = int(daily_cap)
        self.volunteer_cap = int(volunteer_cap)
        self.eval_day_salt = eval_day_salt
        self.frames_dir = Path(frames_dir) if frames_dir else None
        self.sentinel_dir = Path(sentinel_dir) if sentinel_dir else None
        self.admin_chat = admin_chat
        self.reader_version = reader_version
        self.clicks_path = self.dir / "tg_clicks.jsonl"
        if enabled:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.cache.mkdir(parents=True, exist_ok=True)
        self.state = SurveyState(self.dir / "state.json")
        self._secret = self._load_secret() if enabled else b"test-secret"
        self.cal = _Cal(Path(reader_dir) / "calibration.json" if reader_dir else None)

    @classmethod
    def from_config(cls, cfg, logger_=None) -> Optional["FeedbackManager"]:
        """Build from the bot's config module; None (disabled) on any fault."""
        try:
            g = lambda n, d: getattr(cfg, n, d)  # noqa: E731
            if not g("coffee_survey_enabled", False):
                return None
            return cls(
                enabled=True,
                survey_dir=g("coffee_survey_dir", "/home/konsta/coffee-reader/survey"),
                bot_username=g("coffee_survey_bot_username", "TsufeBot"),
                span=g("coffee_survey_span", {}),
                span_source=g("coffee_survey_span_source", "per_side_const_v1"),
                rate_per_day=g("coffee_survey_rate", 8),
                blind_frac=g("coffee_survey_blind_frac", 0.25),
                daily_cap=g("coffee_survey_daily_cap", 15),
                volunteer_cap=g("coffee_survey_volunteer_cap", 5),
                eval_day_salt=g("coffee_survey_eval_day_salt", "coffee10-blind-v1"),
                frames_dir=g("coffee_survey_frames_dir", ""),
                sentinel_dir=g("coffee_survey_sentinel_dir", ""),
                admin_chat=g("coffee_survey_admin_chat", 0),
                reader_dir=g("coffee_survey_reader_dir", "/home/konsta/coffee-reader"),
                reader_version=g("coffee_survey_reader_version", ""),
            )
        except Exception:
            (logger_ or logger).warning("survey disabled: bad config", exc_info=True)
            return None

    # -- identity ------------------------------------------------------------
    def _load_secret(self) -> bytes:
        p = self.dir / "secret"
        try:
            if not p.exists():
                p.write_bytes(secrets.token_bytes(32))
                try:
                    os.chmod(p, 0o600)
                except OSError:
                    pass
            return p.read_bytes()
        except OSError:
            logger.warning("survey secret unavailable; using ephemeral", exc_info=True)
            return secrets.token_bytes(32)

    def user_hash(self, user_id: int) -> str:
        return hmac.new(self._secret, str(user_id).encode(), hashlib.sha256).hexdigest()[:12]

    # -- ladder ---------------------------------------------------------------
    def ladder_for(self, side: str) -> Optional[Ladder]:
        s = self.span.get(side)
        if not s:
            return None
        return Ladder(float(s["top"]), float(s["base"]))

    def ladder_for_offer(self, offer: Dict[str, Any]) -> Optional[Ladder]:
        """The offer's own span (this frame's vessel geometry) when sane,
        else the per-side constants. Keeps old offers and sentinels working."""
        s = offer.get("span_frame_px") or {}
        try:
            top, base = float(s["top"]), float(s["base"])
            if 0.0 <= top < base:
                return Ladder(top, base)
        except (KeyError, TypeError, ValueError):
            pass
        return self.ladder_for(offer.get("side", ""))

    # ======================================================================
    # 1. group side: decorate the bot's photo reply
    # ======================================================================

    def maybe_offer(self, user_id: int, reading: Optional[dict],
                    now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Decide whether THIS reply carries a survey prompt for THIS user.

        Returns the offer dict (already persisted) or None. Never raises.
        """
        try:
            if not self.enabled:
                return None
            now = now or time.time()
            today = datetime.now().strftime("%Y-%m-%d")
            self.state.roll_day(today)
            uh = self.user_hash(user_id)
            self.state.note_seen(uh, now)
            u = self.state.user(uh)
            if u["opted_out"] or u["prompts_today"] >= 1:
                return None
            if self.state.d["day_prompts"] >= self.daily_cap:
                return None
            # target rate, not raw probability (§6)
            p = min(1.0, self.rate / self.state.eligible_user_count(now))
            if secrets.randbelow(10_000) >= int(p * 10_000):
                return None

            blind = secrets.randbelow(10_000) < int(self.blind_frac * 10_000)
            sentinel = secrets.randbelow(6) == 0
            offer = None
            if sentinel:
                offer = self._sentinel_offer(blind)
            if offer is None and blind:
                offer = self._pool_offer(uh)
            if offer is None:
                offer = self._fresh_offer(reading)  # assisted arm, current frame
                blind = False if offer else blind
            if offer is None:
                return None
            offer.update({
                "kind": "prompt", "offered_to": uh,
                "created_at_s": now, "token": "s" + secrets.token_urlsafe(8),
                "hint_shown": (not offer.get("blind", blind)) and offer.get("hint") is not None,
            })
            offer.setdefault("blind", blind)
            if offer["blind"]:
                offer["hint_shown"] = False
            self.state.d["offers"][offer["token"]] = offer
            u["prompts_today"] += 1
            self.state.d["day_prompts"] += 1
            self.state.save()
            return offer
        except Exception:
            logger.warning("maybe_offer failed", exc_info=True)
            return None

    def decorate(self, offer: Optional[Dict[str, Any]], reading_shown: bool):
        """(extra_caption, reply_markup) for the group photo reply."""
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            return None, None
        if offer:
            url = "https://t.me/%s?start=%s" % (self.bot_username, offer["token"])
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(BTN_HELP, url=url)]])
            return TXT_PROMPT_CAPTION, kb
        if reading_shown and self.enabled:
            tok = "v" + secrets.token_urlsafe(8)
            self.state.d["offers"][tok] = {"kind": "wrong", "token": tok,
                                           "created_at_s": time.time()}
            self.state.save()
            url = "https://t.me/%s?start=%s" % (self.bot_username, tok)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(BTN_WRONG, url=url)]])
            return None, kb
        return None, None

    def register_photo(self, sent_msg, frame_jpeg: bytes,
                       reading: Optional[dict],
                       offer: Optional[Dict[str, Any]]) -> None:
        """After reply_photo: bind stem to the SENT message time (§7 join key),
        cache the pre-watermark frame + boxes for 7 days, finalise the offer."""
        try:
            if not self.enabled:
                return
            stem = "coffee_" + sent_msg.date.astimezone().strftime("%Y-%m-%d_%H-%M-%S")
            meta = {"stem": stem, "message_id": sent_msg.message_id,
                    "ts": time.time(), "pots": (reading or {}).get("pots", []),
                    "frame_wh": [1280, 720]}
            (self.cache / (stem + ".jpg")).write_bytes(frame_jpeg)
            (self.cache / (stem + ".json")).write_text(
                json.dumps(meta, allow_nan=False), encoding="utf-8")
            self.state.d["latest_stem"] = stem
            # a fresh-frame offer was built before the send; give it its stem
            if offer and offer.get("frame") == "__pending__":
                offer["stem"] = stem
                offer["message_id"] = sent_msg.message_id
                offer["frame"] = str(self.cache / (stem + ".jpg"))
            self._prune(time.time())
            self.state.save()
        except Exception:
            logger.warning("register_photo failed", exc_info=True)

    # -- offer builders ------------------------------------------------------
    def _offer_from_pot(self, pot: dict, frame: str, stem: str,
                        pool: str, blind: bool) -> Optional[Dict[str, Any]]:
        side = pot.get("side")
        if side not in self.span:
            return None
        hint = None
        if pot.get("h_norm") is not None and pot.get("rows_frame_px"):
            hint = {"h_norm": pot["h_norm"],
                    "rows_frame_px": pot["rows_frame_px"]}
        fill = pot.get("fill_fraction")
        stratum = min(STRATA - 1, int(fill * STRATA)) if fill is not None else None
        # Ladder span: THIS frame's own vessel geometry (the reader's base and
        # max-fill rows), so the ticks land on the pot wherever the camera and
        # carafes sit today. This anchors the ladder to the vessel, never to
        # the surface estimate - the anti-anchoring property protects the
        # surface, not the glassware - and the archive constants proved stale
        # the first time the camera moved (2026-08). Constants stay as the
        # fallback for degenerate detections.
        span = {"base": self.span[side]["base"], "top": self.span[side]["top"]}
        span_source = self.span_source
        rows = pot.get("rows_frame_px") or {}
        try:
            b, t = float(rows["base"]), float(rows["top"])
            if 0.0 <= t and t + 120.0 <= b <= 720.0:
                span, span_source = {"base": b, "top": t}, "frame_rows_v1"
        except (KeyError, TypeError, ValueError):
            pass
        return {"stem": stem, "side": side, "frame": frame,
                "box": pot.get("box"), "frame_wh": [1280, 720],
                "box_source": "fastbox", "pool": pool, "blind": blind,
                "hint": hint, "stratum": stratum,
                "span_frame_px": span,
                "span_source": span_source,
                "reader_version": self.reader_version, "sentinel": False}

    def _fresh_offer(self, reading: Optional[dict]) -> Optional[Dict[str, Any]]:
        """Assisted arm: the photo being replied to right now (frame cached in
        register_photo, which fills in stem + path)."""
        pots = (reading or {}).get("pots") or []
        pots = [p for p in pots if p.get("side") in self.span]
        if not pots:
            return None
        pot = max(pots, key=lambda p: p.get("detector_score") or 0)
        o = self._offer_from_pot(pot, "__pending__", "__pending__",
                                 "train", blind=False)
        return o

    def _pool_offer(self, user_hash: str) -> Optional[Dict[str, Any]]:
        """Blind arm: sample the retained-frame eval pool (depth, k=5).

        Stratified over predicted-fill bands; NEVER over entropy/ok/score.
        """
        cands: Dict[int, List[Dict[str, Any]]] = {}
        for meta_path in self._retained_metas():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            stem = meta.get("stem") or meta_path.stem
            if not is_blind_day(stem, self.eval_day_salt):
                continue
            frame = meta_path.with_suffix(".jpg")
            if not frame.exists():
                continue
            for pot in meta.get("pots", []):
                key = stem + "__" + str(pot.get("side"))
                served = self.state.served(key)
                if user_hash in served or len(served) >= POOL_TARGET_K:
                    continue
                o = self._offer_from_pot(pot, str(frame), stem, "eval", blind=True)
                if o:
                    cands.setdefault(o["stratum"] if o["stratum"] is not None else -1,
                                     []).append(o)
        if not cands:
            return None
        # least-served stratum first: depth where the corpus is thin
        stratum = min(cands, key=lambda s: len(self.state.served(
            cands[s][0]["stem"] + "__" + cands[s][0]["side"])))
        group = cands[stratum]
        return group[secrets.randbelow(len(group))]

    def _sentinel_offer(self, blind: bool) -> Optional[Dict[str, Any]]:
        if not self.sentinel_dir or not self.sentinel_dir.exists():
            return None
        lines_path = self.sentinel_dir / "sentinel_lines.json"
        try:
            lines = json.loads(lines_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        keys = sorted(lines.keys())
        if not keys:
            return None
        key = keys[secrets.randbelow(len(keys))]
        ent = lines[key]
        stem, _, side = key.rpartition("__")
        frame = self.sentinel_dir / (stem + ".jpg")
        if not frame.exists() or side not in self.span:
            return None
        o = {"stem": stem, "side": side, "frame": str(frame),
             "box": ent.get("box"), "frame_wh": ent.get("frame_wh", [1280, 720]),
             "box_source": ent.get("box_source", "fastbox"),
             "pool": "sentinel", "blind": blind, "sentinel": True,
             "hint": ent.get("hint"), "stratum": ent.get("stratum"),
             "span_frame_px": ent.get("span_frame_px")
                 or ((ent.get("hint") or {}).get("rows_frame_px"))
                 or {"base": self.span[side]["base"],
                     "top": self.span[side]["top"]},
             "span_source": ent.get("span_source", self.span_source),
             "reader_version": self.reader_version,
             "truth_y_surf_frame_px": ent.get("y_surf_frame_px")}
        return o

    def _retained_metas(self) -> List[Path]:
        out: List[Path] = []
        if self.frames_dir and self.frames_dir.exists():
            out.extend(sorted(self.frames_dir.glob("*.json")))
        return out

    def _prune(self, now_s: float) -> None:
        for p in list(self.cache.glob("*")):
            try:
                if now_s - p.stat().st_mtime > CACHE_TTL_S:
                    p.unlink()
            except OSError:
                pass
        offers = self.state.d["offers"]
        for tok in [t for t, o in offers.items()
                    if now_s - o.get("created_at_s", 0) > OFFER_TTL_S and
                    not o.get("active_chat")]:
            offers.pop(tok, None)

    # ======================================================================
    # 2. private side: /start deep link -> screen 1 -> screen 2 -> record
    # ======================================================================

    def on_start(self, update, context) -> bool:
        """Deep-link entry. Returns False when the payload is not ours so the
        caller can fall back to the normal /start help text."""
        args = getattr(context, "args", None) or []
        if not args or args[0][:1] not in ("s", "v"):
            return False
        try:
            self._serve_screen1(update, context, args[0])
        except Exception:
            logger.warning("survey start failed", exc_info=True)
            self._safe_text(update.effective_chat, context.bot, TXT_EXPIRED)
        return True

    def _serve_screen1(self, update, context, token: str) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if chat.type != "private":
            return
        now = time.time()
        today = datetime.now().strftime("%Y-%m-%d")
        self.state.roll_day(today)
        uh = self.user_hash(user.id)
        u = self.state.user(uh)
        offer = self.state.d["offers"].get(token)

        if offer is None or now - offer.get("created_at_s", 0) > OFFER_TTL_S:
            self._safe_text(chat, context.bot, TXT_EXPIRED)
            return
        if offer.get("kind") == "wrong" or offer.get("offered_to") != uh:
            # volunteered path: someone else's prompt, or the Wrong? button
            if u["volunteered_today"] >= self.volunteer_cap:
                self._safe_text(chat, context.bot, TXT_ALREADY_TODAY)
                return
            if offer.get("kind") == "prompt" and offer.get("frame") not in (None, "__pending__"):
                # someone else's prompt: SAME frame, but a prompted:false,
                # train-only clone (UX_FEEDBACK §4) - never steal the original
                clone = dict(offer)
                clone.update({"kind": "volunteer", "offered_to": uh,
                              "created_at_s": now,
                              "token": "v" + secrets.token_urlsafe(8)})
                self.state.d["offers"][clone["token"]] = clone
                offer = clone
            else:
                offer = self._volunteer_offer_from(offer, uh, now)
            if offer is None:
                self._safe_text(chat, context.bot, TXT_NO_FRAME)
                return
            u["volunteered_today"] += 1
        if offer.get("frame") == "__pending__":
            self._safe_text(chat, context.bot, TXT_NO_FRAME)
            return

        consent = "" if u["consented"] else (TXT_CONSENT + "\n\n" + "─" * 20 + "\n\n")
        u["consented"] = True

        blind = bool(offer.get("blind")) or is_blind_day(offer["stem"], self.eval_day_salt)
        offer["blind"] = blind
        offer["hint_shown"] = (not blind) and offer.get("hint") is not None
        img = self._render_screen1(offer)
        if img is None:
            self._safe_text(chat, context.bot, TXT_NO_FRAME)
            return
        pot = POT_NAMES.get(offer["side"], offer["side"])
        hhmm = offer["stem"][-8:-3].replace("-", ":")
        tmpl = TXT_SCREEN1_BLIND if blind else TXT_SCREEN1_ASSISTED
        caption = consent + tmpl.format(pot=pot, hhmm=hhmm)
        try:
            from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup
            rows = [[B(str(n), callback_data="fb|%s|a|%d" % (offer["token"], n))
                     for n in range(r, r + 4)] for r in (1, 5, 9)]
            rows.append([B(BTN_CANT_SEE, callback_data="fb|%s|x" % offer["token"])])
            rows.append([B(BTN_SKIP, callback_data="fb|%s|k" % offer["token"])])
            m = context.bot.send_photo(chat_id=chat.id, photo=io.BytesIO(img),
                                       caption=caption[:1024],
                                       reply_markup=InlineKeyboardMarkup(rows))
            offer["active_chat"] = chat.id
            offer["dm_message_id"] = m.message_id
            offer["issued_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            offer["issued_at_s"] = now
            offer["answering_user"] = uh
            offer["n_taps"] = 0
            self.state.save()
        except Exception:
            logger.warning("screen 1 send failed", exc_info=True)

    def _volunteer_offer_from(self, src: Dict[str, Any], uh: str,
                              now: float) -> Optional[Dict[str, Any]]:
        """A volunteered survey on the latest cached frame: prompted stays
        False in the record because offered_to != answering user."""
        stem = self.state.d.get("latest_stem")
        if not stem:
            return None
        meta_p = self.cache / (stem + ".json")
        frame_p = self.cache / (stem + ".jpg")
        if not (meta_p.exists() and frame_p.exists()):
            return None
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        pots = [p for p in meta.get("pots", []) if p.get("side") in self.span]
        if not pots:
            return None
        pot = max(pots, key=lambda p: p.get("detector_score") or 0)
        o = self._offer_from_pot(pot, str(frame_p), stem, "train", blind=False)
        if o is None:
            return None
        o.update({"kind": "volunteer", "offered_to": uh,
                  "created_at_s": now, "message_id": meta.get("message_id"),
                  "token": "v" + secrets.token_urlsafe(8), "sentinel": False})
        self.state.d["offers"][o["token"]] = o
        return o

    # -- callbacks -----------------------------------------------------------
    def on_callback(self, update, context) -> None:
        q = update.callback_query
        try:
            parts = (q.data or "").split("|")
            if len(parts) < 3 or parts[0] != "fb":
                q.answer()
                return
            token, action = parts[1], parts[2]
            offer = self.state.d["offers"].get(token)
            uh = self.user_hash(update.effective_user.id)
            if offer is None or offer.get("answering_user") != uh:
                q.answer(TXT_EXPIRED.splitlines()[0], show_alert=True)
                return
            offer["n_taps"] = offer.get("n_taps", 0) + 1
            if action == "a":                       # band chosen -> screen 2
                self._serve_screen2(q, context, offer, int(parts[3]))
            elif action == "t":                     # tick chosen -> record
                self._finish(q, context, offer, offer.get("band", 6), int(parts[3]))
            elif action == "b":                     # back to screen 1
                self._back_to_screen1(q, context, offer)
            elif action == "x":                     # can't see it
                self._finish(q, context, offer, None, None, visible=False)
            elif action == "k":                     # skip
                self.state.d["offers"].pop(token, None)
                self.state.save()
                q.answer()
                try:
                    q.edit_message_caption(caption="⏭")
                except Exception:
                    pass
            else:
                q.answer()
        except Exception:
            logger.warning("survey callback failed", exc_info=True)
            try:
                q.answer()
            except Exception:
                pass

    def _serve_screen2(self, q, context, offer: Dict[str, Any], band: int) -> None:
        offer["band"] = band
        img = self._render_screen2(offer, band)
        if img is None:
            q.answer()
            return
        try:
            from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup, InputMediaPhoto
            rows = [[B(str(n), callback_data="fb|%s|t|%d" % (offer["token"], n))
                     for n in range(r, r + 4)] for r in (1, 5, 9)]
            rows.append([B(BTN_BACK, callback_data="fb|%s|b" % offer["token"])])
            q.edit_message_media(
                media=InputMediaPhoto(io.BytesIO(img), caption=TXT_SCREEN2),
                reply_markup=InlineKeyboardMarkup(rows))
            q.answer()
            self.state.save()
        except Exception:
            logger.warning("screen 2 edit failed", exc_info=True)

    def _back_to_screen1(self, q, context, offer: Dict[str, Any]) -> None:
        img = self._render_screen1(offer)
        if img is None:
            q.answer()
            return
        try:
            from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup, InputMediaPhoto
            pot = POT_NAMES.get(offer["side"], offer["side"])
            hhmm = offer["stem"][-8:-3].replace("-", ":")
            tmpl = TXT_SCREEN1_BLIND if offer.get("blind") else TXT_SCREEN1_ASSISTED
            rows = [[B(str(n), callback_data="fb|%s|a|%d" % (offer["token"], n))
                     for n in range(r, r + 4)] for r in (1, 5, 9)]
            rows.append([B(BTN_CANT_SEE, callback_data="fb|%s|x" % offer["token"])])
            rows.append([B(BTN_SKIP, callback_data="fb|%s|k" % offer["token"])])
            q.edit_message_media(
                media=InputMediaPhoto(io.BytesIO(img),
                                      caption=tmpl.format(pot=pot, hhmm=hhmm)[:1024]),
                reply_markup=InlineKeyboardMarkup(rows))
            q.answer()
        except Exception:
            logger.warning("back edit failed", exc_info=True)

    def _finish(self, q, context, offer: Dict[str, Any],
                band: Optional[int], tick: Optional[int],
                visible: bool = True) -> None:
        now = time.time()
        y_px = frac = None
        if visible and band and tick:
            ladder = self.ladder_for_offer(offer)
            y_px = ladder.tick_y(band, tick)
            tf = crop_transform(offer["box"], offer["frame_wh"])
            frac = frame_y_to_frac(y_px, tf)
        answered = {
            "answering_user_hash": offer.get("answering_user"),
            "answered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "answered_at_s": now,
            "latency_s": round(now - offer.get("issued_at_s", now), 1),
            "n_taps": offer.get("n_taps"),
            "band": band, "tick": tick,
            "surface_visible": visible,
            "y_surf": round(frac, 5) if frac is not None else None,
            "y_surf_frame_px": round(y_px, 1) if y_px is not None else None,
        }
        try:
            rec = make_record(offer, answered)
            with open(self.clicks_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, allow_nan=False) + "\n")
        except Exception:
            logger.warning("click record write failed", exc_info=True)
            q.answer()
            return

        u = self.state.user(offer.get("answering_user", ""))
        u["answers"] += 1
        if offer.get("sentinel") and y_px is not None and \
                offer.get("truth_y_surf_frame_px") is not None:
            u["sentinel_n"] += 1
            u["sentinel_abs_px"] += abs(y_px - offer["truth_y_surf_frame_px"])
        if offer.get("pool") == "eval" and visible:
            key = offer["stem"] + "__" + offer["side"]
            served = self.state.served(key)
            if offer.get("answering_user") not in served:
                served.append(offer.get("answering_user"))
        self.state.d["offers"].pop(offer.get("token", ""), None)
        self.state.save()

        text = self._confirmation(offer, y_px, visible)
        try:
            q.answer()
            q.edit_message_caption(caption=text[:1024])
        except Exception:
            self._safe_text_id(offer.get("active_chat"), context.bot, text)

    def _confirmation(self, offer: Dict[str, Any], y_px: Optional[float],
                      visible: bool) -> str:
        if not visible:
            return TXT_CANT_SEE
        hint = offer.get("hint") or {}
        rows = hint.get("rows_frame_px") or {}
        span = offer.get("span_frame_px") or {}
        if y_px is None or not span:
            return "Kiitos! / Thanks!"
        base, top = float(span["base"]), float(span["top"])
        h_you = (base - y_px) / (base - top) if base != top else 0.0
        ml_you = self.cal.ml(h_you)
        if rows.get("surf") is not None:
            h_m = (base - float(rows["surf"])) / (base - top) if base != top else 0.0
            ml_m = self.cal.ml(h_m)
            d = ml_you - ml_m
            if offer.get("blind"):
                return TXT_THANKS_BLIND.format(
                    you=_half_cups(ml_you) + " kuppia", machine=_half_cups(ml_m) + " kuppia",
                    you_en=_half_cups(ml_you) + " cups", machine_en=_half_cups(ml_m) + " cups",
                    ml=int(round(abs(d))))
            if abs(d) < 10:
                fi = "lähes samaan kohtaan kuin kone"
                en = "almost exactly where the machine did"
            elif d < 0:
                fi = "%d ml koneen arvausta alemmas" % int(round(-d))
                en = "%d ml below the machine's guess" % int(round(-d))
            else:
                fi = "%d ml koneen arvausta ylemmäs" % int(round(d))
                en = "%d ml above the machine's guess" % int(round(d))
            return TXT_THANKS_ASSISTED.format(fi_delta=fi, en_delta=en)
        return "Kiitos! (%s kuppia / cups)" % _half_cups(ml_you)

    # ======================================================================
    # 3. commands: /merkkaa /eikiitos /kahvistatsit
    # ======================================================================

    def on_merkkaa(self, update, context) -> None:
        try:
            chat = update.effective_chat
            if chat.type != "private":
                self._safe_text(chat, context.bot,
                                "Yksityisviestillä / In a private chat: "
                                "https://t.me/%s" % self.bot_username)
                return
            now = time.time()
            self.state.roll_day(datetime.now().strftime("%Y-%m-%d"))
            uh = self.user_hash(update.effective_user.id)
            u = self.state.user(uh)
            if u["volunteered_today"] >= self.volunteer_cap:
                self._safe_text(chat, context.bot, TXT_ALREADY_TODAY)
                return
            offer = self._volunteer_offer_from({"kind": "wrong"}, uh, now)
            if offer is None:
                self._safe_text(chat, context.bot, TXT_NO_FRAME)
                return
            u["volunteered_today"] += 1
            context.args = [offer["token"]]
            self._serve_screen1(update, context, offer["token"])
        except Exception:
            logger.warning("/merkkaa failed", exc_info=True)

    def on_eikiitos(self, update, context) -> None:
        try:
            uh = self.user_hash(update.effective_user.id)
            self.state.user(uh)["opted_out"] = True
            self.state.save()
            self._safe_text(update.effective_chat, context.bot, TXT_OPTED_OUT)
        except Exception:
            logger.warning("/eikiitos failed", exc_info=True)

    def on_stats(self, update, context) -> None:
        try:
            if update.effective_chat.type != "private":
                return
            u = self.state.user(self.user_hash(update.effective_user.id))
            n = u["answers"]
            if u["sentinel_n"]:
                px = u["sentinel_abs_px"] / u["sentinel_n"]
                agree = "; tarkkuus tunnetuilla kuvilla ~%.0f px / sentinel agreement ~%.0f px" % (px, px)
            else:
                agree = ""
            self._safe_text(update.effective_chat, context.bot,
                            "Merkintöjäsi / your annotations: %d%s. Kiitos!" % (n, agree))
        except Exception:
            logger.warning("/kahvistatsit failed", exc_info=True)

    # ======================================================================
    # 4. nightly export: gzipped JSONL as a document to the admin channel
    # ======================================================================

    def schedule_jobs(self, job_queue) -> None:
        if not (self.enabled and self.admin_chat):
            return
        try:
            from datetime import time as dtime
            job_queue.run_daily(self.nightly_upload, time=dtime(hour=3, minute=30))
        except Exception:
            logger.warning("survey job scheduling failed", exc_info=True)

    def nightly_upload(self, context) -> None:
        try:
            if not self.clicks_path.exists():
                return
            day = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            name = "tg_clicks_%s.jsonl.gz" % day   # idempotent by name (§7)
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
                gz.write(self.clicks_path.read_bytes())
            buf.seek(0)
            buf.name = name
            context.bot.send_document(chat_id=self.admin_chat, document=buf,
                                      filename=name)
        except Exception:
            logger.warning("nightly click upload failed", exc_info=True)

    # ======================================================================
    # rendering (lazy Pillow) - ~600x900 JPEG, 30-50 kB (§6)
    # ======================================================================

    def _render_screen1(self, offer: Dict[str, Any]) -> Optional[bytes]:
        return self._render(offer, band=None)

    def _render_screen2(self, offer: Dict[str, Any], band: int) -> Optional[bytes]:
        return self._render(offer, band=band)

    def _render(self, offer: Dict[str, Any], band: Optional[int]) -> Optional[bytes]:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return None
        try:
            frame_path = offer.get("frame")
            if not frame_path or not Path(frame_path).exists():
                return None
            im = Image.open(frame_path).convert("RGB")
            fw, fh = im.size
            x1, y1, x2, y2 = expand_box(offer["box"], fw, fh)
            ladder = self.ladder_for_offer(offer)
            if band is None:
                cy1, cy2 = y1, y2
            else:  # screen 2: the band window with vertical context
                lo, hi = ladder.band_window(band)
                pad = (hi - lo) * 0.8
                cy1, cy2 = max(0, lo - pad), min(fh, hi + pad)
            crop = im.crop((int(x1), int(cy1), int(x2), int(cy2)))
            out_w = 600
            scale = out_w / max(1, crop.width)
            out_h = min(1200, max(300, int(crop.height * scale)))
            crop = crop.resize((out_w, out_h), Image.LANCZOS)

            def to_out_y(y_frame: float) -> int:
                return int(round((y_frame - cy1) * (out_h / max(1e-6, (cy2 - cy1)))))

            dr = ImageDraw.Draw(crop)
            font = None
            for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                         "C:/Windows/Fonts/arialbd.ttf"):
                try:
                    font = ImageFont.truetype(cand, 22)
                    break
                except OSError:
                    continue
            if font is None:
                font = ImageFont.load_default()

            def hline(y, color, dashed=False, width=2):
                if dashed:
                    for x0 in range(0, out_w, 24):
                        dr.line([(x0, y), (min(x0 + 12, out_w), y)],
                                fill=color, width=width)
                else:
                    dr.line([(0, y), (out_w, y)], fill=color, width=width)

            if band is None:      # screen 1: 12 numbered band centres
                for b in range(1, BANDS + 1):
                    y = to_out_y(ladder.band_y(b))
                    if 0 <= y < out_h:
                        hline(y, (255, 210, 60), width=1)
                        dr.text((6, max(0, y - 13)), str(b),
                                fill=(255, 210, 60), font=font,
                                stroke_width=2, stroke_fill=(0, 0, 0))
            else:                 # screen 2: 12 fine ticks in the window
                for t in range(1, TICKS + 1):
                    y = to_out_y(ladder.tick_y(band, t))
                    if 0 <= y < out_h:
                        hline(y, (120, 220, 255), width=1)
                        dr.text((6, max(0, y - 13)), str(t),
                                fill=(120, 220, 255), font=font,
                                stroke_width=2, stroke_fill=(0, 0, 0))
            # the machine's dashed guess: assisted arm only, never blind (§4.1)
            if offer.get("hint_shown"):
                rows = (offer.get("hint") or {}).get("rows_frame_px") or {}
                if rows.get("surf") is not None:
                    y = to_out_y(float(rows["surf"]))
                    if 0 <= y < out_h:
                        hline(y, (255, 90, 90), dashed=True, width=3)
            bio = io.BytesIO()
            crop.save(bio, "JPEG", quality=87)
            return bio.getvalue()
        except Exception:
            logger.warning("survey render failed", exc_info=True)
            return None

    # -- small helpers --------------------------------------------------------
    @staticmethod
    def _safe_text(chat, bot, text: str) -> None:
        try:
            bot.send_message(chat_id=chat.id, text=text)
        except Exception:
            logger.warning("survey text send failed", exc_info=True)

    @staticmethod
    def _safe_text_id(chat_id, bot, text: str) -> None:
        if not chat_id:
            return
        try:
            bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            logger.warning("survey text send failed", exc_info=True)

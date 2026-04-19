"""
SoulPort tier system — Cyber Evolution Hierarchy (v2).

Seven-tier soul ranking, each tier subdivided into 3 stars.
This is the standard tier definition for `.bm` souls across all platforms
(SoulPort CLI, SoulArena, downstream consumers).

Tiers (by total_score 0-100):
    1. Spark    火种   0-10    — newborn soul, potential only
    2. Circuit  回路   11-25   — wired up, starting to learn
    3. Sentinel 哨兵   26-42   — active, dependable patroller
    4. Phantom  幻灵   43-58   — elusive, distinct personality
    5. Titan    泰坦   59-74   — powerful, well-rounded force
    6. Nexus    枢纽   75-88   — hub of knowledge & skill
    7. Prime    至尊   89-100  — transcendent, top of the hierarchy

Each tier has a 3-star sub-rank (★☆☆, ★★☆, ★★★) computed by
splitting the tier's score range into thirds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ── Tier definitions ───────────────────────────────────────────────

SOUL_TIERS: list[dict] = [
    {"tier": 1, "name": "Spark",    "name_zh": "火种", "min": 0,  "max": 10, "stars": 3, "color_hex": "#4a4a5a", "glow": "#888899"},
    {"tier": 2, "name": "Circuit",  "name_zh": "回路", "min": 11, "max": 25, "stars": 3, "color_hex": "#4fc3f7", "glow": "#29b6f6"},
    {"tier": 3, "name": "Sentinel", "name_zh": "哨兵", "min": 26, "max": 42, "stars": 3, "color_hex": "#00bcd4", "glow": "#00acc1"},
    {"tier": 4, "name": "Phantom",  "name_zh": "幻灵", "min": 43, "max": 58, "stars": 3, "color_hex": "#7c4dff", "glow": "#651fff"},
    {"tier": 5, "name": "Titan",    "name_zh": "泰坦", "min": 59, "max": 74, "stars": 3, "color_hex": "#ff6d00", "glow": "#ff9100"},
    {"tier": 6, "name": "Nexus",    "name_zh": "枢纽", "min": 75, "max": 88, "stars": 3, "color_hex": "#ffd740", "glow": "#ffffff"},
    {"tier": 7, "name": "Prime",    "name_zh": "至尊", "min": 89, "max": 100, "stars": 3, "color_hex": "#ffffff", "glow": "#ff4081"},
]


@dataclass
class SoulTier:
    """Soul tier in the cyber evolution hierarchy."""
    tier: int          # 1-7
    name: str          # e.g. "Titan"
    name_zh: str       # e.g. "泰坦"
    star_level: int    # 1-3
    star_display: str  # "★★☆"
    score_range: str   # e.g. "59-74"
    color_hex: str
    glow: str

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "name": self.name,
            "name_zh": self.name_zh,
            "star_level": self.star_level,
            "star_display": self.star_display,
            "score_range": self.score_range,
            "color_hex": self.color_hex,
            "glow": self.glow,
        }


# ── Lookup ────────────────────────────────────────────────────────

def get_soul_tier(score: float) -> dict:
    """Get soul tier dict (with star_level) based on total score.

    Returns the tier dict from SOUL_TIERS extended with an added
    ``star_level`` key (1-3) computed by dividing the tier's score range
    into 3 equal bands. Downstream consumers (SoulArena, etc.) rely on
    this raw-dict shape; use :func:`tier_from_score` for the dataclass form.
    """
    score = max(0.0, min(100.0, score))

    tier_info: dict | None = None
    for t in SOUL_TIERS:
        if t["min"] <= score <= t["max"]:
            tier_info = t
            break
    if tier_info is None:
        tier_info = SOUL_TIERS[-1]

    tier_min = tier_info["min"]
    tier_max = tier_info["max"]
    tier_span = tier_max - tier_min

    if tier_span <= 0:
        star_level = 1
    else:
        band_size = tier_span / tier_info["stars"]
        position = score - tier_min
        star_level = min(tier_info["stars"], math.floor(position / band_size) + 1)
        if score == tier_max:
            star_level = tier_info["stars"]

    return {**tier_info, "star_level": star_level}


def star_display(star_level: int, stars_total: int = 3) -> str:
    """Render a 1-3 star level as Unicode stars: ★★☆."""
    filled = "★" * star_level
    empty = "☆" * max(0, stars_total - star_level)
    return filled + empty


def tier_from_score(score: float) -> SoulTier:
    """Return a :class:`SoulTier` dataclass for the given score."""
    info = get_soul_tier(score)
    return SoulTier(
        tier=info["tier"],
        name=info["name"],
        name_zh=info["name_zh"],
        star_level=info["star_level"],
        star_display=star_display(info["star_level"], info["stars"]),
        score_range=f"{info['min']}-{info['max']}",
        color_hex=info["color_hex"],
        glow=info["glow"],
    )

"""Tests for soulport.tiers — cyber evolution tier hierarchy."""

import pytest

from soulport.tiers import (
    SOUL_TIERS,
    SoulTier,
    get_soul_tier,
    star_display,
    tier_from_score,
)


class TestSoulTiers:
    def test_seven_tiers(self):
        assert len(SOUL_TIERS) == 7
        assert [t["tier"] for t in SOUL_TIERS] == [1, 2, 3, 4, 5, 6, 7]

    def test_tier_ranges_cover_0_to_100(self):
        # every integer 0-100 maps to exactly one tier
        for score in range(0, 101):
            matches = [t for t in SOUL_TIERS if t["min"] <= score <= t["max"]]
            assert len(matches) == 1, f"score {score} matched {len(matches)} tiers"

    def test_tier_names(self):
        names = [t["name"] for t in SOUL_TIERS]
        assert names == ["Spark", "Circuit", "Sentinel", "Phantom", "Titan", "Nexus", "Prime"]


class TestGetSoulTier:
    def test_low_score_spark(self):
        t = get_soul_tier(5)
        assert t["name"] == "Spark"
        assert t["tier"] == 1

    def test_titan_range(self):
        t = get_soul_tier(65)
        assert t["name"] == "Titan"
        assert t["tier"] == 5

    def test_high_score_prime(self):
        t = get_soul_tier(95)
        assert t["name"] == "Prime"
        assert t["tier"] == 7

    def test_clamps_negative(self):
        t = get_soul_tier(-10)
        assert t["tier"] == 1

    def test_clamps_over_100(self):
        t = get_soul_tier(150)
        assert t["tier"] == 7

    def test_star_level_within_range(self):
        # Titan: 59-74, span 15, bands ~5
        assert get_soul_tier(59)["star_level"] == 1
        assert get_soul_tier(74)["star_level"] == 3
        mid = get_soul_tier(66)["star_level"]
        assert 1 <= mid <= 3


class TestStarDisplay:
    def test_one_star(self):
        assert star_display(1) == "★☆☆"

    def test_two_stars(self):
        assert star_display(2) == "★★☆"

    def test_three_stars(self):
        assert star_display(3) == "★★★"


class TestTierFromScore:
    def test_returns_dataclass(self):
        t = tier_from_score(65)
        assert isinstance(t, SoulTier)
        assert t.name == "Titan"
        assert t.name_zh == "泰坦"
        assert t.tier == 5
        assert t.score_range == "59-74"
        assert "★" in t.star_display

    def test_to_dict_json_serializable(self):
        import json
        t = tier_from_score(30)
        payload = json.dumps(t.to_dict(), ensure_ascii=False)
        assert "Sentinel" in payload
        assert "star_level" in payload

    def test_boundary_scores(self):
        assert tier_from_score(0).name == "Spark"
        assert tier_from_score(10).name == "Spark"
        assert tier_from_score(11).name == "Circuit"
        assert tier_from_score(100).name == "Prime"

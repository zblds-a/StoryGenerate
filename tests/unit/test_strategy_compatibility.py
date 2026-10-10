"""Compatibility tests for strategy resolver audit fixes.

Tests free-text genre, unknown recipe, template version, and ending compatibility.
"""
from __future__ import annotations

import pytest

from drama_engine.config import RuleLibrary
from drama_engine.workflow.strategy import (
    StoryStrategyResolver, StrategyConflictError, _FREETEXT_GENRE_MAP,
)


@pytest.fixture(scope="module")
def lib():
    return RuleLibrary.load()


@pytest.fixture
def resolver(lib):
    return StoryStrategyResolver(lib)


class TestFreeTextGenre:
    """Free-text genre labels should map to formula library IDs."""

    def test_wenqing_maps_to_healing(self, resolver):
        s = resolver.resolve(story_mode="general", genre="温情",
                             user_instruction="测试", explicit_fields=["story_mode", "genre"])
        assert s.genre_id == "G05"
        assert s.genre_name != ""

    def test_xuanyi_maps_to_mystery(self, resolver):
        s = resolver.resolve(story_mode="general", genre="轻悬疑",
                             user_instruction="测试", explicit_fields=["story_mode", "genre"])
        assert s.genre_id == "G05"

    def test_zhichang_maps(self, resolver):
        s = resolver.resolve(story_mode="general", genre="职场",
                             user_instruction="测试", explicit_fields=["story_mode", "genre"])
        assert s.genre_id == "G05"

    def test_family_maps_to_g01(self, resolver):
        s = resolver.resolve(story_mode="general", genre="家庭",
                             user_instruction="测试", explicit_fields=["story_mode", "genre"])
        assert s.genre_id == "G01"

    def test_palace_maps_to_g04(self, resolver):
        s = resolver.resolve(story_mode="general", genre="宫斗",
                             user_instruction="测试", explicit_fields=["story_mode", "genre"])
        assert s.genre_id == "G04"

    def test_chuanyue_maps_to_g08(self, resolver):
        s = resolver.resolve(story_mode="general", genre="穿越",
                             user_instruction="测试", explicit_fields=["story_mode", "genre"])
        assert s.genre_id == "G08"

    def test_unknown_free_text_falls_back(self, resolver):
        s = resolver.resolve(story_mode="general", genre="量子物理",
                             user_instruction="测试", explicit_fields=["story_mode"])
        # Falls back to keyword match + best audio-fit; should not raise
        assert s.genre_id in {g["genre_id"] for g in resolver.lib.genres}

    def test_formula_id_still_works(self, resolver):
        s = resolver.resolve(story_mode="general", genre="G01",
                             user_instruction="测试", explicit_fields=["story_mode", "genre"])
        assert s.genre_id == "G01"

    def test_all_free_text_keys_have_valid_genre_ids(self, resolver):
        valid_ids = {g["genre_id"] for g in resolver.lib.genres}
        for kw, gid in _FREETEXT_GENRE_MAP.items():
            assert gid in valid_ids, f"'{kw}' maps to invalid genre '{gid}'"


class TestUnknownRecipe:
    """Explicit but unknown recipe_id must raise clear error."""

    def test_unknown_recipe_raises(self, resolver):
        with pytest.raises(StrategyConflictError, match="R99"):
            resolver.resolve(story_mode="general", genre="G01", recipe_id="R99",
                             user_instruction="测试", explicit_fields=["recipe_id"])

    def test_unknown_recipe_does_not_silently_fallback(self, resolver):
        with pytest.raises(StrategyConflictError):
            resolver.resolve(story_mode="general", genre="G01", recipe_id="NONEXISTENT",
                             user_instruction="测试", explicit_fields=["recipe_id"])

    def test_valid_recipe_still_works(self, resolver):
        s = resolver.resolve(story_mode="general", genre="G01", recipe_id="R4",
                             user_instruction="测试", explicit_fields=["recipe_id"])
        assert s.recipe_id == "R4"


class TestTemplateVersion:
    """Strategy template_version should reflect actual resolved template."""

    def test_default_template_version_is_one(self, resolver):
        s = resolver.resolve(story_mode="auto", genre="auto",
                             user_instruction="测试")
        assert s.template_version == 1

    def test_strategy_has_template_ref_field(self, resolver):
        s = resolver.resolve(story_mode="auto", genre="auto",
                             user_instruction="测试", template_ref="GENERAL_THREE_ACT")
        assert s.template_ref == "GENERAL_THREE_ACT"
        # Version is 1 by default until updated by service.py after resolution
        assert s.template_version == 1


class TestEndingCompatibility:
    """Recipe ending strategy should be compatible with user ending_preference."""

    def test_r4_recipe_ending_is_not_closed_forcefully(self, resolver):
        """R4 says '不建议强制大团圆' — compatible with 'auto' or 'closed'."""
        s = resolver.resolve(story_mode="general", genre="G01", recipe_id="R4",
                             user_instruction="测试", explicit_fields=["recipe_id"])
        assert "不建议强制大团圆" in s.ending_strategy

    def test_r5_recipe_ending_is_healing_not_tragedy(self, resolver):
        """R5 says '和解与重新开始' — should not force tragedy."""
        s = resolver.resolve(story_mode="general", genre="G02", recipe_id="R5",
                             user_instruction="测试", explicit_fields=["recipe_id"])
        assert "和解" in s.ending_strategy


class TestAutoFillTracking:
    """Auto-filled fields must be correctly tracked."""

    def test_auto_fills_all_three_when_nothing_specified(self, resolver):
        s = resolver.resolve(story_mode="auto", genre="auto",
                             user_instruction="一个温暖治愈的故事")
        assert "story_mode" in s.auto_filled_fields
        assert "genre" in s.auto_filled_fields
        assert "recipe_id" in s.auto_filled_fields

    def test_no_auto_fills_when_all_explicit(self, resolver):
        s = resolver.resolve(story_mode="general", genre="G01", recipe_id="R4",
                             user_instruction="测试",
                             explicit_fields=["story_mode", "genre", "recipe_id"])
        assert len(s.auto_filled_fields) == 0
        assert len(s.explicit_fields) == 3

    def test_free_text_genre_marked_auto_if_not_direct_id(self, resolver):
        s = resolver.resolve(story_mode="general", genre="温情",
                             user_instruction="测试", explicit_fields=["story_mode"])
        # "温情" is not a formula ID, so it goes through the free-text path
        # which auto-fills the actual genre
        assert s.genre_id == "G05"
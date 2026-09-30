"""Audio Drama form handler — adapter for legacy routing."""
from __future__ import annotations


class AudioDramaHandler:
    key: str = "audio_drama"

    def writer_prompt(self, plan: dict, characters: list, mode_key: str) -> str:
        return _default_writer_prompt(plan, characters, "audio drama script")

    def validators(self) -> list:
        return []  # handled by existing graph validators

    def rule_packs(self) -> list[str]:
        return ["audio_story_constraints"]

    def package(self, raw_output: str, plan: dict) -> dict:
        return {"audio_drama": raw_output, "prose": ""}


class ProseStoryHandler:
    key: str = "prose_story"

    def writer_prompt(self, plan: dict, characters: list, mode_key: str) -> str:
        return _default_writer_prompt(plan, characters, "prose story")

    def validators(self) -> list:
        return []

    def rule_packs(self) -> list[str]:
        return ["story_progression"]

    def package(self, raw_output: str, plan: dict) -> dict:
        return {"prose": raw_output, "audio_drama": ""}


class NovelHandler:
    key: str = "novel"

    def writer_prompt(self, plan: dict, characters: list, mode_key: str) -> str:
        return _default_writer_prompt(plan, characters, "novel-style narrative with paragraphs, scenes, and embedded dialogue")

    def validators(self) -> list:
        return [NovelValidator()]

    def rule_packs(self) -> list[str]:
        return ["novel_adaptation", "story_progression"]

    def package(self, raw_output: str, plan: dict) -> dict:
        return {"novel": raw_output, "prose": raw_output}


class StorytellingHandler:
    key: str = "storytelling"

    def writer_prompt(self, plan: dict, characters: list, mode_key: str) -> str:
        return _default_writer_prompt(plan, characters, "oral storytelling style, narrator-led with dialogue inserts and pacing beats")

    def validators(self) -> list:
        return [StorytellingValidator()]

    def rule_packs(self) -> list[str]:
        return ["storytelling_oral"]

    def package(self, raw_output: str, plan: dict) -> dict:
        return {"storytelling": raw_output, "prose": raw_output}


class StandupHandler:
    key: str = "standup"

    def writer_prompt(self, plan: dict, characters: list, mode_key: str) -> str:
        return _default_writer_prompt(plan, characters, "standup comedy performance: single performer, setup-punchline-callback structure")

    def validators(self) -> list:
        return [StandupValidator()]

    def rule_packs(self) -> list[str]:
        return ["standup_performance"]

    def package(self, raw_output: str, plan: dict) -> dict:
        return {"standup": raw_output, "prose": raw_output}


class CrosstalkHandler:
    key: str = "crosstalk"

    def writer_prompt(self, plan: dict, characters: list, mode_key: str) -> str:
        return _default_writer_prompt(plan, characters, "crosstalk comedy dialogue: two performers (dougen/penggen), exchange-based structure")

    def validators(self) -> list:
        return [CrosstalkValidator()]

    def rule_packs(self) -> list[str]:
        return ["crosstalk_dialogue"]

    def package(self, raw_output: str, plan: dict) -> dict:
        return {"crosstalk": raw_output, "prose": raw_output}


# ═══════════════════════════════════════════════════════════════════
# Validators
# ═══════════════════════════════════════════════════════════════════
class NovelValidator:
    def validate(self, output: str) -> tuple[bool, str]:
        if not output or not output.strip():
            return False, "novel: empty output"
        if len(output.strip()) < 50:
            return False, "novel: output too short"
        return True, ""


class StorytellingValidator:
    def validate(self, output: str) -> tuple[bool, str]:
        if not output or not output.strip():
            return False, "storytelling: empty output"
        if len(output.strip()) < 30:
            return False, "storytelling: output too short"
        return True, ""


class StandupValidator:
    def validate(self, output: str) -> tuple[bool, str]:
        if not output or not output.strip():
            return False, "standup: empty output"
        if len(output.strip()) < 20:
            return False, "standup: output too short"
        return True, ""


class CrosstalkValidator:
    def validate(self, output: str) -> tuple[bool, str]:
        if not output or not output.strip():
            return False, "crosstalk: empty output"
        if len(output.strip()) < 20:
            return False, "crosstalk: output too short"
        return True, ""


# ═══════════════════════════════════════════════════════════════════
# Default prompt builder
# ═══════════════════════════════════════════════════════════════════
def _default_writer_prompt(plan: dict, characters: list, style: str) -> str:
    char_text = ", ".join(c.get("name", c.get("canon", {}).get("name", "?")) for c in characters[:3])
    premise = plan.get("premise", plan.get("central_question", ""))
    return f"Write a {style} about {char_text}. Premise: {premise}"
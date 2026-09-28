"""Phase 6: Content Form Resolver — 确定性，0 LLM。

Priority:
  1. explicit content_form → 精确匹配
  2. default = audio_drama
"""
from __future__ import annotations

from .models import ContentForm, ContentFormProfile
from .registry import get_content_form


def resolve_content_form(content_form: str | None = None) -> ContentFormProfile:
    """解析 Content Form。

    content_form=None → audio_drama（向后兼容）。
    content_form="unknown" → ContentFormNotSupportedError。
    """
    return get_content_form(content_form)


def content_form_enum(key: str | None) -> ContentForm:
    """将 string key 转为 ContentForm enum。"""
    key = key or ContentForm.AUDIO_DRAMA.value
    return ContentForm(key)
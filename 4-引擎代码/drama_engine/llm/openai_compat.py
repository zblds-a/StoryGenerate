"""OpenAI 兼容适配器。

为什么只写这一个就够：DeepSeek / 通义千问（DashScope 兼容模式）/ Kimi / 智谱 GLM /
OpenAI / 以及本地 vLLM、Ollama 的 /v1 端点，全部遵循同一套 Chat Completions 协议。
差别只在 base_url 与 model 名 —— 那是配置，不是代码。

不引入官方 SDK，用 httpx 直发请求的理由：少一层依赖、少一层版本漂移，
且能方便地把供应商私有字段（如 reasoning 开关）从 spec.extra 透传下去。
"""
from __future__ import annotations

import json
import time

import httpx

from .base import BaseLLMProvider, LLMResult, LLMSpec, estimate_tokens

# 常见供应商的默认端点，供部署时直接引用
KNOWN_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "openai": "https://api.openai.com/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
}


class OpenAICompatProvider(BaseLLMProvider):
    """任意 OpenAI 兼容端点。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = KNOWN_ENDPOINTS["deepseek"],
        timeout_sec: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.name = "openai_compat"
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries

    def complete(self, spec: LLMSpec, system: str, user: str) -> LLMResult:
        payload: dict = {
            "model": spec.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": spec.temperature,
            "max_tokens": spec.max_tokens,
        }
        # 供应商私有参数透传：编排层不解释它们的含义
        payload.update(spec.extra.get("provider_params", {}))
        if spec.extra.get("json_mode"):
            payload["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout_sec,
                )
                resp.raise_for_status()
                data = resp.json()
                latency = int((time.perf_counter() - t0) * 1000)
                usage = data.get("usage") or {}
                return LLMResult(
                    text=data["choices"][0]["message"]["content"] or "",
                    model=data.get("model", spec.model),
                    input_tokens=usage.get("prompt_tokens") or estimate_tokens(system + user),
                    output_tokens=usage.get("completion_tokens") or 0,
                    latency_ms=latency,
                )
            except Exception as exc:  # noqa: BLE001 - 需要覆盖网络/协议/限流多种异常
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))  # 指数退避
        raise RuntimeError(f"LLM 调用失败（已重试 {self.max_retries} 次）: {last_error}")

    def describe(self) -> dict:
        return {"provider": self.name, "base_url": self.base_url}


def build_provider_from_env() -> BaseLLMProvider:
    """按环境变量装配。未配置密钥时回落到 Mock，保证流水线始终可跑。"""
    import os

    from .mock import MockLLMProvider

    key = os.environ.get("DRAMA_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return MockLLMProvider()

    vendor = os.environ.get("DRAMA_LLM_VENDOR", "deepseek").lower()
    base_url = os.environ.get("DRAMA_LLM_BASE_URL") or KNOWN_ENDPOINTS.get(
        vendor, KNOWN_ENDPOINTS["deepseek"]
    )
    return OpenAICompatProvider(api_key=key, base_url=base_url)

"""标准错误体系 —— Task 2: Error Hierarchy。

原则：
  - 所有引擎错误继承自 StoryEngineError
  - 每个错误都有稳定的 error_code（不依赖字符串匹配）
  - 禁止 success 状态下返回空内容
"""
from __future__ import annotations

from enum import Enum


class EngineErrorCode(str, Enum):
    """稳定的错误码枚举。调用方应据此判断，不应依赖 message 字符串。"""

    INVALID_INPUT = "INVALID_INPUT"
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    MODEL_INVALID_OUTPUT = "MODEL_INVALID_OUTPUT"
    GENERATION_TIMEOUT = "GENERATION_TIMEOUT"
    PLAN_VALIDATION_FAILED = "PLAN_VALIDATION_FAILED"
    QUALITY_GATE_FAILED = "QUALITY_GATE_FAILED"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    GENERATION_CANCELLED = "GENERATION_CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class StoryEngineError(Exception):
    """引擎所有错误的基类。"""

    code: EngineErrorCode = EngineErrorCode.INTERNAL_ERROR

    def __init__(self, message: str = "", code: EngineErrorCode | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code.value, "message": self.message or str(self)}


class InvalidInputError(StoryEngineError):
    code = EngineErrorCode.INVALID_INPUT


class ModelNotConfiguredError(StoryEngineError):
    code = EngineErrorCode.MODEL_NOT_CONFIGURED


class ModelUnavailableError(StoryEngineError):
    code = EngineErrorCode.MODEL_UNAVAILABLE


class ModelTimeoutError(StoryEngineError):
    code = EngineErrorCode.MODEL_TIMEOUT


class ModelRateLimitedError(StoryEngineError):
    code = EngineErrorCode.MODEL_RATE_LIMITED


class ModelInvalidOutputError(StoryEngineError):
    code = EngineErrorCode.MODEL_INVALID_OUTPUT


class GenerationTimeoutError(StoryEngineError):
    code = EngineErrorCode.GENERATION_TIMEOUT


class PlanValidationError(StoryEngineError):
    code = EngineErrorCode.PLAN_VALIDATION_FAILED


class QualityGateError(StoryEngineError):
    code = EngineErrorCode.QUALITY_GATE_FAILED


class EmptyOutputError(StoryEngineError):
    code = EngineErrorCode.EMPTY_OUTPUT


class GenerationCancelledError(StoryEngineError):
    code = EngineErrorCode.GENERATION_CANCELLED


class InternalEngineError(StoryEngineError):
    code = EngineErrorCode.INTERNAL_ERROR


# HTTP status → Engine error 映射
HTTP_RETRYABLE_STATUSES: set[int] = {429, 500, 502, 503, 504}
HTTP_NON_RETRYABLE_STATUSES: set[int] = {400, 401, 403, 404}


def classify_http_error(status_code: int, message: str = "") -> StoryEngineError:
    """将 HTTP 状态码映射为引擎错误。"""
    if status_code == 429:
        return ModelRateLimitedError(message)
    if status_code in (500, 502, 503, 504):
        return ModelUnavailableError(message)
    if status_code in HTTP_NON_RETRYABLE_STATUSES:
        return ModelInvalidOutputError(message)
    return ModelUnavailableError(message)
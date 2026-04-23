"""Domain-specific exceptions. HTTP mapping happens at the API layer."""

from __future__ import annotations


class AppError(Exception):
    """Base for all domain errors. Always carries a machine code."""

    code: str = "app_error"
    http_status: int = 500

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404


class ValidationError(AppError):
    code = "validation_error"
    http_status = 400


class AuthError(AppError):
    code = "auth_error"
    http_status = 401


class ForbiddenError(AppError):
    code = "forbidden"
    http_status = 403


class ConflictError(AppError):
    code = "conflict"
    http_status = 409


class RuleBookMissingError(AppError):
    """Raised when a customer has no active rule book; never silently fall back."""

    code = "rule_book_missing"
    http_status = 422


class CostCapExceededError(AppError):
    code = "cost_cap_exceeded"
    http_status = 402


class LLMError(AppError):
    code = "llm_error"
    http_status = 502


class PreprocessingError(AppError):
    code = "preprocessing_error"
    http_status = 422

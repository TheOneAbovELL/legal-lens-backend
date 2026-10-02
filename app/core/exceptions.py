"""Structured application exceptions.

Every infrastructure or domain failure is raised as an :class:`AppError` subclass so the
API layer can turn it into a consistent, non-leaky error response.
"""

from __future__ import annotations


class AppError(Exception):
    code: str = "internal_error"
    http_status: int = 500
    retryable: bool = False
    #: Message safe to show to API clients. Internal detail stays in ``str(exc)``/logs.
    public_message: str = "An internal error occurred."

    def __init__(self, message: str | None = None, *, public_message: str | None = None) -> None:
        super().__init__(message or self.public_message)
        if public_message is not None:
            self.public_message = public_message


class ConfigurationError(AppError):
    code = "configuration_error"
    public_message = "The service is misconfigured."


class EmbeddingError(AppError):
    code = "embedding_error"
    http_status = 503
    public_message = "The embedding service is unavailable."


class VectorStoreError(AppError):
    code = "vector_store_error"
    http_status = 503
    retryable = True
    public_message = "The document index is unavailable."


class RetrievalError(AppError):
    code = "retrieval_error"
    http_status = 503
    public_message = "Document retrieval failed."


class RerankingError(AppError):
    code = "reranking_error"
    http_status = 503
    public_message = "Result reranking failed."


class LLMProviderError(AppError):
    code = "llm_provider_error"
    http_status = 502
    public_message = "The language model provider failed to respond."

    def __init__(
        self,
        message: str | None = None,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable


class DocumentProcessingError(AppError):
    code = "document_processing_error"
    http_status = 422
    public_message = "The document could not be processed."


class SafetyViolation(AppError):
    code = "safety_violation"
    http_status = 400
    public_message = "The request cannot be processed."


class InvalidQueryError(AppError):
    code = "invalid_query"
    http_status = 422
    public_message = "The query is invalid."


class AuthenticationError(AppError):
    code = "authentication_failed"
    http_status = 401
    public_message = "Invalid or missing credentials."


class AuthorizationError(AppError):
    code = "forbidden"
    http_status = 403
    public_message = "You are not allowed to perform this action."


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404
    public_message = "The requested resource was not found."


class ConflictError(AppError):
    code = "conflict"
    http_status = 409
    public_message = "The resource already exists."


class RateLimitExceeded(AppError):
    code = "rate_limited"
    http_status = 429
    public_message = "Too many requests. Please retry later."


class PipelineTimeoutError(AppError):
    code = "timeout"
    http_status = 504
    public_message = "The request took too long to process."


class ServiceNotReadyError(AppError):
    code = "not_ready"
    http_status = 503
    public_message = "The service is not ready."
